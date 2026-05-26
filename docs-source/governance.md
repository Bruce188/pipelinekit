<!--
diataxis: explanation
-->
# Governance playbook — AI Champions and standardization

How to land pipelinekit conventions across multiple projects without skill drift, hook divergence, or a CLAUDE.md that nobody owns. Names a single role per team — the AI Champion — and codifies the playbook that role runs.

## Why governance — the standardization gap

AI-tooling adoption tends to grow bottom-up: one engineer installs a hook, another writes a skill, a third edits `CLAUDE.md` for one project but not the rest. Without explicit ownership, the surface area between projects diverges fast. Two teams running the same orchestrator end up with subtly different never-stage lists, different conventional-commit prefixes, and different memory-feed expectations. The cost shows up as pipeline failures that reproduce on one machine and not another, onboarding sessions that take days because the new engineer's checkout doesn't match the senior engineer's, and `/review` findings that disagree with `/analyze` recommendations because they read different rules.

pipelinekit is the convention-bearer. The skill set, agent personas, hooks, and `~/.claude/CLAUDE.md` template are the standardization surface. Governance is what keeps that surface coherent across projects. Without a named owner, conventions calcify into folklore — readable in the repo but invisible to the next contributor. With a named owner — the AI Champion — conventions become a deliberate artifact, reviewed and rolled forward on a cadence.

## AI Champions — role definition

An **AI Champion** is one engineer per team who owns the AI-tooling surface for that team's projects. The role is concrete, not honorific.

<div data-snippet="governance-roles-table"></div>

Responsibilities:

- **Skill review** — every new skill, agent, or hook lands on the Champion's desk for review before merge. The Champion validates the contract (frontmatter shape, `paths:` scoping, `allowed-tools` precision) against `claude/skills/CLAUDE.md` and its siblings.
- **Hook approval** — hooks are policy. The Champion confirms exit-code semantics, JSON stdin/stdout contracts, and that the hook doesn't bypass `block-stage-sensitive.sh` or its siblings.
- **Onboarding** — new engineers run `scripts/install.sh`, hit any friction, and surface the friction to the Champion. The Champion either fixes the install path or documents the workaround.
- **Escalation** — when `@incident-responder` triages a pipeline failure that traces back to a convention question (not a code bug), the Champion owns the resolution.

Time commitment: roughly **2 hours per week** in steady-state, weighted toward Mondays (review queue) and Fridays (retrospective + memory write-back). Spikes during onboarding weeks and after a `~/.claude/` overlay update.

Succession: rotate the role every **quarter**. The outgoing Champion writes a 1-page handoff covering open review threads, pending convention questions, and any project-specific deltas they introduced. The handoff lands as a `feedback_*.md` memory under `~/.claude/projects/<slug>/memory/` so the incoming Champion can read it on day one. Quarterly rotation prevents the role from becoming a knowledge silo.

## Standardization playbook

Use this playbook to roll pipelinekit conventions out across multiple projects. Each step has a single owner — the Champion — and a single exit criterion.

1. **Audit existing surface.** Run the `claude-md-enhancer` skill against each project's `CLAUDE.md`. Capture the drift between the project's current rules, the user-global rules in `~/.claude/CLAUDE.md`, and the canonical conventions in `claude/skills/CLAUDE.md`, `claude/agents/CLAUDE.md`, and `claude/hooks/CLAUDE.md`. Exit criterion: a drift list with one row per deviation and a "keep / align / delete" disposition.
2. **Land the baseline overlay on one pilot project.** Run `scripts/install.sh` on the project the Champion knows best. Confirm `~/.claude/CLAUDE.md`, `~/.claude/rules/workflow.md`, and `~/.claude/rules/agents-worktrees.md` are in place. Run `/pipeline` end-to-end on a real feature. Exit criterion: green pipeline run with no manual interventions.
3. **Codify per-project deltas.** Anything the pilot needs that the baseline does not provide — a project-specific charter, a custom skill, a mode-specific overlay (Azure, Vercel, Railway, Render, DigitalOcean) — goes into the project's `CLAUDE.md` as an additive section, never an override. The Champion documents each delta with a one-line "why" so the next engineer can read intent, not just rules. Exit criterion: every delta in the project's `CLAUDE.md` has a justification line.
4. **Roll out to additional projects.** Repeat steps 2 and 3 for each new project. The Champion is the convention-bearer: when two projects diverge on a convention, the Champion picks one and updates the other to match (or escalates the disagreement back to the user-global rules if the conflict is genuine).

## Approval workflow — adding skills / agents / hooks

A new skill, agent, or hook crosses the team's convention surface. It needs explicit review. Use this three-stage flow.

1. **Draft.** Author opens a PR that adds the new artifact. The artifact MUST satisfy the per-file conventions in `claude/skills/CLAUDE.md` (skills), `claude/agents/CLAUDE.md` (agents), or `claude/hooks/CLAUDE.md` (hooks). PR description includes a one-paragraph "why this isn't already covered by an existing skill / agent / hook" — the Champion checks this against the "When to Extend vs Add New" rule in `claude/skills/CLAUDE.md`.
2. **Review.** The AI Champion + one peer review the PR. Champion focuses on contract compliance (frontmatter, allowlist, paths scoping); peer focuses on the behavior the artifact ships. Both must approve before merge. Disagreements escalate to a 15-minute synchronous discussion with the user-global rules in `~/.claude/CLAUDE.md` as the tiebreaker.
3. **Merge.** Merge after the smoke tests pass — `bash claude/skills/docs-writer/tests/test_render.sh` for docs-writer changes, the skill's own `tests/` directory for skill-specific tests, the hook test harness under `claude/hooks/` for new hooks. The merge commit follows conventional-commit format and never references the AI workflow (no `Co-Authored-By`, no review-cycle metadata).

## Advisory hooks — prompt-injection scanner

The orchestrator validates substituted user input before dispatching a prompt (`claude/skills/pipeline/reference.md § Placeholder Substitution Safety`). That covers feature names, descriptions, and path placeholders. It does NOT cover tool output — `WebFetch` responses, `Read` calls against `/tmp/` or `/var/`, PR-comment data ingested via `--issues`. That untrusted text otherwise flows into subsequent prompts unchecked, which is the classic prompt-injection vector for an LLM-with-shell agent (CWE-94 / CWE-74).

`claude/hooks/scan-tool-output.sh` is the v1 advisory layer for that gap. It registers as a `PostToolUse` hook:

- Fires on `WebFetch` always.
- Fires on `Read` only when the resolved file path is outside the repo root (`/tmp/`, `/var/`, `/home/<other>/`, or any URL form).
- Calls `claude.hooks._promptguard.scan(text)` and emits a stderr warning of the form `WARN: prompt-injection pattern detected: <pattern> in <source>` for each match.
- Always exits 0 — **advisory only**. v1 will not strand the operator mid-workflow on a false positive. A hard-block layer can follow once the false-positive rate is empirically known.

Pattern catalogue: the canonical list lives in `claude/hooks/_promptguard.py` and covers XML-shape system tags, the canonical instruction-override prefaces, role-reassignment markers, column-0 role-impersonation prefixes, and ChatML role markers. Matching is case-insensitive. The scanner logs only the `(source, pattern, position)` triple to stderr — never the scanned text — to keep credential-bearing fetches out of the session log.

The Champion owns the catalog. Adding a pattern requires a PR that (a) extends `_LITERAL_PATTERNS` / `_FLEX_PATTERNS` / `_ROLE_PREFIXES` in `claude/hooks/_promptguard.py`, (b) adds positive + negative test cases in `claude/hooks/tests/test_promptguard.py`, and (c) re-scans `docs-source/` to confirm the corpus stays under the documented allowlist threshold (< 5 hits at v1, enumerated as a top-of-file comment in `_promptguard.py`).

## Adoption metrics

Governance is invisible when it works. Measure adoption to confirm it is working — and to surface drift before it becomes a fire.

- **Skill activation rate.** Which skills actually fire on PRs? Derive from `~/.claude/logs/` (per-session JSONL) by counting the unique skill-dispatch lines per week. A skill that has not fired in 4 weeks is a candidate for deprecation or for a routing-surface fix in its `description:` field. Target: every skill in the active catalog fires at least once per quarter.
- **Hook failure rate.** Count of `exit 1` / `exit 2` outcomes from hooks per week, read from `~/.claude/logs/hook-events.jsonl` if present, otherwise from grep against the session logs. A spiking failure rate on a single hook signals either a recently introduced bug or a convention the team is rejecting. Target: aggregate hook failure rate stays under 5% of total hook invocations per week.
- **Time-to-onboard.** Median minutes from `scripts/install.sh` (clean checkout) to the first successful `/pipeline` run on a real feature. Collect manually for now — the Champion notes the metric for each onboarding session and rolls it into the quarterly retrospective. Target: 30 minutes for engineers who have used Claude Code before, 90 minutes for engineers new to the toolchain.

## Governance command cheatsheet

Filter the slash-command table by `review`, `pipeline`, or `ppr` to surface the commands a Champion uses most frequently when shepherding adoption.

<div data-snippet="command-cheatsheet"></div>

## Deprecation policy

Skills, agents, hooks, slash-commands, and flags are removed on a published schedule — never silently. The Champion owns enforcement; this section is the contract every contributor reads before deleting a surface.

### Notice window

Any user-visible surface (skill name, agent name, slash-command, CLI flag, configuration key, hook trigger event) MUST land its deprecation notice **at least one minor release before removal**. Patch releases never remove surfaces. The notice has three required parts:

1. A bold `> ⚠️ **Deprecated in v<X.Y>; removed in v<X.Y+1>.**` callout at the top of the surface's documentation page (or its frontmatter section for slash-commands and flags).
2. A console-emitted warning printed by the surface itself on every invocation — exactly one line, prefixed `DEPRECATED:`, naming the replacement (or `no replacement — see <doc-link>` when none exists).
3. A changelog entry under the deprecating release's section, naming the old surface, the planned removal release, and the migration path.

### Alias window

Renames carry an alias for one full minor release. The new name is canonical from day one; the old name remains invocable, emits the `DEPRECATED:` warning on every call, and is removed in the next minor release. Aliases are recorded in `claude/skills/<new>/SKILL.md` (or the equivalent agent / hook / command file) under an `## Alias` H2 section listing the old name and the alias-removal release. Example: `--auto` was a deprecation alias for `--no-prompts` for one release before removal.

### Removal criteria

Surfaces are eligible for removal when ALL of the following hold:

- The notice window has expired (the named removal release has shipped).
- The Champion has verified the surface has zero in-bound references across `claude/`, `documentation/`, `docs-source/`, `examples/`, `scripts/`, and the pinned upstream-vendored content in `claude/tresor-resources/`. A repo-wide grep for the old name MUST return only the changelog entry that documented the deprecation.
- A migration recipe (one paragraph plus a one-line `before` / `after` example) exists in the next-release changelog under a `### Migration` subsection.
- The removal PR is reviewed and merged by the Champion (or a delegated reviewer named in the project's `CODEOWNERS`), not the author of the deprecation.

### Communication channels

Each deprecation appears in three places: the surface's own doc page (callout), the changelog (entry), and the next-release announcement (a single bulleted list under `### Deprecations` near the top of the release notes). The Champion confirms all three landed before merging the deprecation PR — a deprecation that ships in only one channel is treated as un-shipped.

### Exceptions

Security fixes may remove surfaces without the notice window when a vulnerability is being actively exploited and a one-release pause would extend the exposure window. Such removals MUST land with: an explicit `### Security removal` changelog subsection citing the CVE or advisory, a Champion-signed approval recorded in the PR description, and a follow-up migration guide published within seven days of the release.
