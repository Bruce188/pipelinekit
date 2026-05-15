---
description: Detailed rules for agent management, worktree isolation, and merge protocol. Loads only when working inside Claude config tree or a project with one.
paths:
  - "**/.claude/**"
---

# Agent & Worktree Rules (Detailed)

## Skill Isolation
Skills that write code should use `context: fork` in SKILL.md frontmatter. For parallel skill execution touching different files, combine `context: fork` with `isolation: "worktree"`.

## Worktree Agent Prompt Requirement
Every worktree agent prompt MUST include this instruction verbatim:
> Before reporting done: stage all your changes and commit with message `wip: [stream description]`. If a pre-commit hook fails, fix the issue and retry the commit. Do NOT report done without a successful commit — uncommitted worktree changes are lost on cleanup.

## Cross-Worker Scratchpad
Every worktree agent prompt under a parallel phase ALSO gets the scratchpad contract:
> Shared scratchpad: `<absolute path to .claude/scratchpad/<phase-id>/>`. If you discover something a sibling stream needs to know (shared utility, conflicting assumption, upstream dependency), drop a note there named `<your-stream>-to-<sibling-stream>.md` — small plain-text (<5KB). Before you report done, read any `*-to-<your-stream>.md` files left by siblings. Do not put file contents in the scratchpad — notes only.

The scratchpad lives at `.claude/scratchpad/<phase-id>/` and is excluded from git via `.git/info/exclude`. The lead surfaces any `*-to-*.md` files in the merge-commit context after all streams complete, then removes the scratchpad on successful merge. On merge failure, the scratchpad is left in place for post-mortem.

## Worktree Lifecycle
- Zero changes = auto-removed by Claude Code
- Uncommitted changes = persist (lead controls lifecycle)
- Agent finishes without committing = worktree directory exists until removed (recovery window)
- The commit instruction prevents needing recovery

## Worktree Agent Task-Notification XML
Per NETMIND Part 1 §6.2, Claude Code uses a `<task-notification>` XML block to report worker results back to the coordinator. Every worktree agent's final response MUST end with a block in this format:

```xml
<task-notification>
  <task-id>[stream or task name]</task-id>
  <status>completed|failed|blocked</status>
  <summary>1-3 sentence summary of what was done (or why it failed).</summary>
  <files>
    <file>path/one.ext</file>
    <file>path/two.ext</file>
  </files>
  <usage>
    <total_tokens>[if available, else omit]</total_tokens>
    <tool_uses>[if available, else omit]</tool_uses>
  </usage>
</task-notification>
```

Rules:
- The XML must be the **last** content in the response so the lead can parse unambiguously (regex finds `<task-notification>...</task-notification>` at the tail).
- File list capped at 50 entries; excess summarized as `<files count="N"><file>...</file><more>N-50</more></files>`.
- Do not embed file contents — paths only.
- Agents that fail to emit the XML are still accepted, but the lead logs: "worker X did not emit task-notification — falling back to free-form parsing."

## Lead Merge Protocol
After all worktree agents complete:
1. Parse the `<task-notification>` block from each worker's final response. Log stream names, statuses, and file lists. If a worker did not emit the block, log "worker X did not emit task-notification — falling back to free-form parsing" and continue.
2. Check each worktree branch has commits: `git log worktree-branch --oneline -5`
3. No commits? Check if worktree dir still exists: `ls .claude/worktrees/`. Copy/cherry-pick changes before cleanup.
4. **Squash-merge** into working branch: `git merge --squash worktree-branch` then commit with a clean conventional message. Never use `--no-ff` — it preserves `wip:` commits on the target branch.
5. Run `build && test` after all merges
6. Resolve conflicts (zero file overlap should prevent this)
7. Clean up only after successful merge + test: `git branch -d worktree-agent-*` + `rm -rf .claude/worktrees/agent-*`

## Commit Message Hygiene (No AI Traces)
Commit messages on feature branches and main must never reveal the AI workflow. Specifically:
- **Never use:** `wip:`, `stream A/B/C/D/E`, `parallel streams`, `review-vN`, `apply review`, `N findings`, `merge: stream`, `across N streams`
- **Squash worktree commits** into one clean conventional commit per stream (e.g. `fix: harden execution engine close pipeline`)
- **Feature branch → main merges** use a single descriptive message. No bullet-point lists of findings or stream names.
- **Review iteration commits** use generic language: `fix: address code review feedback` — no version numbers, no finding counts, no stream references.
- Think: "Would a human developer write this commit message?" If not, rewrite it.

## Agent Team Failure Recovery
- Teammate fails or stuck: redirect via Shift+Down
- Two teammates claim same task: lead resolves via mid-flight steering
- One blocks on another: lead provides needed info directly

## Post-Parallel Evaluation
After parallel subagent runs complete, ask:
- Did any agent fail and need rerunning?
- Were there merge conflicts?
- Did streams need info from each other?
- Was one stream blocked on another's output?
If yes to any, suggest agent teams for the next similar parallel task.

## Plans with Parallel Work
Plans with parallel agent work (streams/teammates) MUST produce BOTH files:
- The plan file (docs/plan.md or docs/plan-vN.md)
- A prompts file (docs/prompts.md) with discrete teammate prompt blocks
Never embed teammate instructions as prose in the plan.
