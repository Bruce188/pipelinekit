<!--
diataxis: reference
-->
# Glossary

Definitions of the terms that recur across pipelinekit skills, agents, hooks, and prompts. Each entry links to a primary source where the term is defined and used.

## Terms

- **caveman** — Verbosity-floor mode for pipelinekit sessions that drops articles, filler, and hedging from narrative prose while preserving exact strings (code, paths, commit messages, security warnings). Toggle with `/caveman lite|full|ultra|wenyan|off`. Default verbosity floor is `wenyan-ultra`. The orchestrator propagates the floor to subagents via the inherited contract block. [Source: caveman-mode SKILL](../claude/skills/caveman-mode/SKILL.md)

- **wenyan-ultra** — Three-zone caveman variant. Zone 1 (code, paths, commits, errors) renders as exact English. Zone 2 (narrative prose) renders as real classical Chinese 文言 with at least one Han character per paragraph. Zone 3 (status fragments, beacons) renders as ultra-terse English fragments. The default verbosity floor; the inherited contract block at `claude/snippets/caveman-subagent.md` propagates this contract to onward Agent dispatches. [Source: caveman-subagent contract](../claude/snippets/caveman-subagent.md)

- **Path A** — Pipeline review-outcome route where `/review` finds zero blocking and zero non-blocking findings. The feature proceeds straight to `/ppr` (push + open PR). When `--no-review` is set, the orchestrator synthesises a Path A pass with a one-line skip-notice. [Source: workflow rules](../claude/rules/workflow.md)

- **Path B** — Pipeline review-outcome route where `/review` returns one or more findings. The orchestrator dispatches a fresh `Skill: implement-plan` subagent in `**Phase Mode:** subagent` to apply fixes, then re-runs `/review`. Hard cap of five cycles before escalation. Path B always uses Agent-tool dispatch — never inline. [Source: pipeline SKILL § Step 5.7](../claude/skills/pipeline/SKILL.md)

- **Path C** — Pipeline replan route triggered when Path B exhausts its five-cycle budget without convergence. Dispatches a fresh `Skill: create-plan` subagent to rewrite the plan against the same charter, then restarts implement + review from scratch. Tracked via `**Replan count:**` in `docs/pipeline-state.md`. [Source: pipeline SKILL § Step 5.8](../claude/skills/pipeline/SKILL.md)

- **Path D** — Fresh-context salvage route. When the pipeline is stuck after Path B and Path C and `**Path D attempted:**` is still false, the orchestrator dispatches one final subagent in a clean context to attempt salvage with only the charter and current diff as input. Persisted before dispatch so a mid-dispatch crash cannot double-fire on resume. [Source: pipeline reference § Path D](../claude/skills/pipeline/reference.md)

- **Path M** — Inline mini-fix route taken after `/review` when all findings are mechanical non-blockers (≤ 5 lines per finding, ≤ 1 file each, ≤ 3 findings total, ≤ 8 aggregate lines, `Suggestion:` shape only). The orchestrator applies edits inline with the Edit tool — no subagent dispatch. Max two cycles tracked via `**Inline cycles:**`. [Source: pipeline SKILL § Step 5.7 Row 1.7](../claude/skills/pipeline/SKILL.md)

- **Path N** — Nit-only inline route. Similar gate to Path M but specifically for `Nit:` findings discovered during the optional Row-2 nit preamble. Edit-tool only, max two cycles, falls through to Path B subagent dispatch if any cycle finds a non-nit. Tracked separately from Path M via `**Nit cycles:**`. [Source: workflow rules § Phase Mode Precedence](../claude/rules/workflow.md)

- **charter** — One-page project contract written by `/pipeline` Step 0 (Charter Discovery) covering nine topics: project type, primary language, deployment target, observability, CI host, secret store, testing posture, branching model, and review style. Persisted at `docs/charter.md`. Downstream phases read the charter to scope analysis depth, plan structure, and review-team composition. Skip with `--no-charter`. [Source: pipeline SKILL § Step 0](../claude/skills/pipeline/SKILL.md)

- **Phase Mode (subagent vs inline)** — Per-feature dispatch mode recorded as `**Phase Mode:**` in `docs/pipeline-state.md`. `subagent` (default for every new feature) dispatches each pipeline phase via the Agent tool in a fresh context. `inline` is preserved only for legacy state files and the Path M / Path N sub-paths; new features never start in `inline`. Resume must preserve saved mode — silent downgrade is a contract violation. [Source: workflow rules § Phase Mode Precedence](../claude/rules/workflow.md)

- **Zone 1/2/3** — The three verbosity zones that compose the caveman wenyan-ultra contract. Zone 1 (code, paths, commits, errors) is exact English with no transformation; Zone 2 (narrative prose) renders as classical Chinese 文言; Zone 3 (status fragments, beacons) renders as ultra-terse English. The boundaries are explicit so that pipeline beacons, hook output, and security warnings stay parseable. [Source: caveman-subagent contract](../claude/snippets/caveman-subagent.md)

- **Inline cycles** — Counter incremented once per Path M cycle, capped at two. Stored as `**Inline cycles:**` in `docs/pipeline-state.md`. Resets at feature init. Overflow forces the next review through Path B (re-review only, no second inline pass). Independent from `**Nit cycles:**` used by Path N. [Source: pipeline SKILL § Step 5.7](../claude/skills/pipeline/SKILL.md)

- **Review style** — Per-feature toggle controlling whether `/review` dispatches the multi-agent review team or a single reviewer. Three values: `always teams`, `never teams`, `orchestrator decides`. Set by priority: `--no-teams` override > Charter Topic 11 > default `orchestrator decides`. Heuristic for the default: `DIFF_LINES > 500 OR DIFF_FILES > 8 OR feature_class = dev → teams-on`. Sticky per feature. [Source: pipeline state schema](../claude/rules/workflow.md)

- **Worktree agent** — A subagent dispatched into an isolated git worktree at `$HOME/.claude/worktrees/<branch>` so it can edit files without colliding with sibling streams or the main checkout. Required to commit before reporting done with a `wip:` message; the `verify-worktree-commit.sh` hook enforces this. Lead squash-merges the worktree branch into the working branch and cleans up afterwards. [Source: agents-worktrees rules § Worktree Lifecycle](../claude/rules/agents-worktrees.md)

- **Subagent-First** — Default-on policy that routes non-trivial work through Agent-tool dispatch rather than inline execution. The `subagent-first-nudge.sh` hook injects a reminder on session start and after compaction. Inline execution is the exception, reserved for trivial one-shots (≤ ~3 tool calls), interactive Q&A, or explicit opt-out phrases like `no subagents`, `do it inline`. Bundle independent streams in a single message so they run concurrently. [Source: agents-worktrees rules § Subagent Defaults](../claude/rules/agents-worktrees.md)

- **TDD (red/green)** — Test-Driven Development discipline enforced by pipelinekit for `dev`-class features. The `tdd-test-writer` agent writes failing tests first (red phase); a separate run of the `tdd-implementer` agent writes the minimum production code that makes them pass (green phase). The `tdd-red-phase-gate.sh` hook blocks any commit that contains both new tests and new production code in the same change. [Source: tdd SKILL](../claude/skills/tdd/SKILL.md)

- **Acceptance Criteria** — Numbered list of verifiable conditions on a feature block in `docs/features.md` defining "done." Each criterion must be testable by automated tests or observable behaviour. When present, analysis includes ACs as context, plans map ACs to tasks, review agents verify each AC is met, and PR bodies include AC status. The `ac_lint.py` library checks criterion shape and uniqueness during Step 1 ingestion. [Source: pipeline features template](../claude/skills/pipeline/features-template.md)

## Cross-reference

For pipeline-state field schemas, see [workflow rules](../claude/rules/workflow.md) § Pipeline State Schema. For the full subagent-dispatch protocol, see [agents-worktrees rules](../claude/rules/agents-worktrees.md). For the caveman contract that propagates to onward Agent calls, see [the subagent snippet](../claude/snippets/caveman-subagent.md).
