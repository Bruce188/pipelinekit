---
description: Detailed rules for agent management, worktree isolation, and merge protocol. Loads only when working inside Claude config tree or a project with one.
paths:
  - "**/.claude/**"
---

# Agent & Worktree Rules (Detailed)

## Subagent Defaults

Subagent dispatch via the `Agent` tool is the DEFAULT execution mode for ANY non-trivial work — no trigger keyword required. This is reinforced on every prompt by `claude/hooks/subagent-first-nudge.sh` (UserPromptSubmit), which injects a default-mode reminder unless the prompt contains an explicit opt-out phrase.

Common dispatch shapes (all default to subagents — listed for clarity, not as gating criteria):

- **Multi-feature batches**: "process features 7–11", "batch A", "parallel streams", "5 at a time" → one subagent per feature, ALL dispatched in a single message so they run concurrently.
- **Autonomous runs**: "overnight", "while I sleep", "don't pause", "don't ask for confirmation", "target 10 AM", `--auto` flag → main session orchestrates and never blocks on a single feature's implementation.
- **Independent investigations**: "audit X", "find all Y", "where is Z used" → dispatch `Explore` or `general-purpose` with the scoped question; do not grep inline if the answer needs > 3 queries.
- **Long-running phases**: any implement-plan / review phase with > 5 tasks or > 2k LOC diff → dispatch via `/pipeline` Phase Mode `subagent` (default for new features per `~/.claude/rules/workflow.md § Phase Mode Precedence`).

Inline execution is the EXCEPTION, reserved for:
- **Trivial one-shots** under ~3 tool calls where dispatch overhead exceeds the work itself (e.g. read one file, edit one line, run one test).
- **Interactive Q&A** with the user actively present and watching (turn-by-turn pairing).
- **Per-prompt opt-out** via these literal phrases: `no subagents`, `no agents`, `do it inline`, `inline mode`, `do it yourself`, `skip subagents`, `skip agents`, `no dispatch`, `don't dispatch`. The nudge hook detects these and emits an opt-out notice instead of the default-mode banner.

**Kill switch.** Export `PIPELINE_NO_SUBAGENT_NUDGE=1` to silence the nudge entirely for a session — the default-mode rule still applies, but the hook stops injecting reminders.

**Self-correction rule.** If the user has to say "use subagents" or "make sure to continue with subagents" mid-flight, the prior dispatch decision was wrong. Switch to dispatch mode for the remaining work immediately, and do NOT finish the current inline step first as a courtesy — abandon it (or stash it for the subagent to pick up) and dispatch.

**Parallelism reminder.** Multiple independent subagents in a SINGLE message run concurrently. Calling `Agent` five times across five sequential turns serializes them and forfeits the parallelism. Bundle into one message.

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

Interactive worktree creation uses the native Claude Code `EnterWorktree` / `ExitWorktree` tools (Claude CLI `>= v2.1.72`). `EnterWorktree` creates a worktree under `$HOME/.claude/worktrees/<branch>` and switches the harness into it; `ExitWorktree` returns the session to the source repo without removing the worktree (so the lead can squash-merge per § Lead Merge Protocol). On Claude CLI `< v2.1.72`, fall back to manual `git worktree add` — the same `$HOME/.claude/worktrees/<branch>` path convention applies so `verify-worktree-commit.sh` continues to fire correctly. The subprocess-mode driver (not shipped in this overlay) also uses manual `git worktree add` because it has no Claude harness to dispatch tool calls into.

Lifecycle rules (apply to both native-tool and manual paths):
- Zero changes = auto-removed by Claude Code
- Uncommitted changes = persist (lead controls lifecycle)
- Agent finishes without committing = worktree directory exists until removed (recovery window)
- The commit instruction prevents needing recovery

## Env handoff via `.worktreeinclude`

Worker prompts no longer need inline env-copy boilerplate. Worktree creation
reads `.worktreeinclude` (resolved from the repo-root template
`.worktreeinclude.template`) and bind-mounts each matching path from the
source repo into the new worktree at the same relative path. Where bind-mount
is unavailable (Windows host without WSL2 mount-share, or filesystems that
reject bind), the mechanism falls back to `cp -p` of each matching path.

**Opt-in flow:**
1. Copy `.worktreeinclude.template` (committed at repo root) to `.worktreeinclude`.
2. Edit `.worktreeinclude` to declare the env/secret paths your worktree agents need.
3. The next worktree-creation step picks it up automatically.

**Hook composition.** The resolved `.worktreeinclude` lists secret paths
(typically `.env`, `credentials*`). The existing `block-stage-sensitive.sh`
hook (driven by `claude/config/never-stage.txt`) already refuses to stage
those paths inside the worktree, so accidental commits of secret contents
are blocked at the same gate as in the main repo.

**Why not in worker prompts.** Putting env-copy commands in worker prompts
meant every prompt had to enumerate the secret paths — fragile and easy to
forget. The `.worktreeinclude` mechanism centralizes the list in one file
per repo.

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
