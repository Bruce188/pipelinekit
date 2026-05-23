# claude/agents

Authoring rules for pipelinekit subagent personas. Each `.md` file in this directory defines one named agent the orchestrator can dispatch via the `Agent` tool. Single file per agent — no subdirectories.

## Frontmatter Shape

Every agent file opens with a YAML frontmatter block.

```yaml
---
name: my-agent
description: One sentence the orchestrator reads when matching this agent to a task. Lead with the role noun (reviewer, implementer, auditor) and the trigger verb.
# Optional below this line:
tools: Read, Write, Edit, Grep, Glob, Bash, Agent
model: opus
maxTurns: 30
---
```

Field rules:

- `name` must match the file name exactly (`claude/agents/foo.md` → `name: foo`). Slash-command dispatch and the `Agent` tool both key on this.
- `description` is the routing surface — the orchestrator's `Agent` tool routing reads this string when picking an agent for a task. Lead with role + trigger; keep under 200 chars so it fits the dispatch slate.
- `tools` is a COMMA-LIST (flow-list form is canonical for agents — different from skills, which use the block-list form for `allowed-tools`). One line, comma-separated.
- `model` accepts `opus | sonnet | haiku | inherit`. `inherit` keeps the orchestrator's current model for the subagent dispatch.
- `maxTurns` caps the agent's tool-call budget for a single dispatch. Defaults to the orchestrator's per-dispatch cap when omitted.

## Authoring Conventions

The body of an agent file IS its system prompt. The orchestrator concatenates the body verbatim into the subagent's context window at dispatch time.

- **First line establishes identity.** Open with `You are <role>...` (e.g. "You are an expert code reviewer", "You are a test writer"). The orchestrator's dispatch layer uses the opening clause as a sanity check that the agent body matches the frontmatter role.
- **No H1.** Skip top-level headers — the system prompt is treated as one continuous block. Use H2s and H3s for the agent's own structure.
- **Explicit boundaries.** State what the agent does NOT do as clearly as what it does. The `tdd-test-writer` agent explicitly says it does not implement; the `code-reviewer` agent explicitly says it does not write code. Boundary clarity prevents role drift.
- **Reference doctrine via path.** If the agent depends on shipped doctrine (e.g. the vendored TDD pack at `claude/skills/tdd/`), list the canonical paths to read rather than inlining the doctrine.

## Tool Allowlist Precision

Declare `tools:` to scope what the dispatched subagent can use. A read-only auditor agent gets `tools: Read, Grep, Glob` — not `*`.

- Wildcard (`*`) is reserved for intentionally broad agents — `general-purpose`, `claude`. Listing `*` on a narrow-role agent grants the subagent unconstrained tool access and bypasses the per-agent budget.
- Adding `Agent` to the list lets the agent dispatch further subagents. Reserve for orchestration-shaped agents (architects, reviewers that consult specialists). Most agents do NOT need `Agent` in their toolbelt.
- `Bash` access on an agent that has no clear shell need is a smell — review whether the agent's job actually requires shell execution before adding it.

## Model Selection

`model: opus | sonnet | haiku | inherit` is a HINT to the orchestrator; the dispatch layer may override based on the task surface or current budget posture.

- `opus` — reasoning-heavy roles (architects, reviewers, planners).
- `sonnet` — balanced cost/quality for implementer-class agents.
- `haiku` — high-throughput narrow roles (token scanners, lint pre-flights).
- `inherit` — match the orchestrator's current model; useful for agents that act as extensions of the caller rather than as independent specialists.

When the agent declares no `model:` key, the orchestrator picks based on the task surface.

## Task-Notification XML

Every worktree agent (any agent dispatched via `isolation: "worktree"` or behind `EnterWorktree`) MUST emit a `<task-notification>` XML block as the LAST content in its final response. Reproduced verbatim from `~/.claude/rules/agents-worktrees.md`:

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

Rules for the block:

- MUST be the last content in the response (tail-regex match by the lead).
- File list capped at 50 entries; excess summarized as `<files count="N"><file>...</file><more>N-50</more></files>`.
- Paths only — never embed file contents inside `<file>` tags.
- Agents that fail to emit the block are still accepted, but the lead logs the fallback: `worker X did not emit task-notification — falling back to free-form parsing`.

Non-worktree agents (the bulk of this directory — reviewers, planners, implementers that run in the main session) do not need the XML block.

## Worktree Agent Commit Discipline

Worktree agents MUST commit their work before reporting done. Uncommitted worktree changes are lost on cleanup. The commit message convention for worktree agents is:

```
wip: [stream description]
```

The validator hook (`../hooks/validate-commit-msg.sh`) allows `wip:` only when the toplevel path contains `/.claude/worktrees/<name>(/|$)`. Outside a worktree, `wip:` is rejected. See the hook body for the exact regex.

## See Also

- Root rules: `../../CLAUDE.md`.
- Sibling subdir rules: `../skills/CLAUDE.md`, `../hooks/CLAUDE.md`.
- Worktree merge protocol: `~/.claude/rules/agents-worktrees.md` § Lead Merge Protocol.
