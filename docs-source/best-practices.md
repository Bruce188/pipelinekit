<!--
diataxis: explanation
-->
# Best-practices score-card

Post-batch tracking of pipelinekit's coverage against the five-category best-practices rubric. Baseline derived from the 2026-05-26 comprehensive audit (`docs/features-best-practices.md`); 22 features (PRs #148 — #169) merged in the subsequent autonomous pipeline run closed measurable gaps. This page records the new state, names each merged feature, and flags two refactor-class merges that did not increment the implemented count.

## WHAT

The rubric divides best-practice surface area into five categories:

- **Workflow** — pipeline orchestration contracts, phase routing, dispatch shape, charter handling, memory wiring.
- **Security** — secret-handling, supply-chain pinning, sandbox isolation, prompt-injection defenses, native gate hooks.
- **Modular** — agent / skill / hook tool-surface tightening, deployment-engineer subclasses, lint configs, allowed-tools enumeration.
- **Docs** — discoverability infrastructure (glossary, search, examples, Diátaxis taxonomy), community-profile assets, version stamping, routing-truthfulness reconciliation.
- **Testing** — CI matrix on GitHub Actions, lint configuration, hook-block-gate coverage with TDD scaffolding.

The score-card below tracks per-category `(Implemented / Total)` and the rolled-up aggregate.

## SCORE-CARD

Post-batch state after the F1 — F22 autonomous run merged via PRs #148 — #169.

| Category | Total | Implemented (post-batch) | % |
|----------|-------|--------------------------|----|
| Workflow | 14    | 12                       | 86% |
| Security | 16    | 16                       | 100% |
| Modular  | 10    | 10                       | 100% |
| Docs     | 13    | 12                       | 92% |
| Testing  | 12    | 8                        | 67% |
| **Aggregate** | **65** | **58** | **89%** |

Pre-batch baseline (from the 2026-05-26 audit, with row-arithmetic normalised):

| Category | Total | Implemented (pre-batch) | % |
|----------|-------|-------------------------|----|
| Workflow | 14    | 7                       | 50% |
| Security | 16    | 11                      | 69% |
| Modular  | 10    | 7                       | 70% |
| Docs     | 13    | 8                       | 62% |
| Testing  | 12    | 5                       | 42% |
| **Aggregate** | **65** | **38** | **58%** |

Net delta: **+20 implemented items**, **+31 aggregate percentage points**.

<div data-snippet="cost-budget-meter" data-spent-usd="58" data-max-usd="65" data-spent-turns="89" data-max-turns="100" data-label-spent="Items implemented" data-label-max="Total surface" data-label-turns="Aggregate %"></div>

The twin dial above reframes the aggregate score-card as a budget meter. The left dial shows item-coverage (58 of 65); the right dial shows the rolled-up percentage (89 of a notional 100%).

## FEATURE-TO-CATEGORY MAPPING

The 22 features in chronological merge order. Each row credits the category whose gap the feature closed. Refactor-class features (column **R**) did not increment any per-category count — they cleaned up previously-implemented behaviour rather than closing a listed gap.

| # | PR | Commit | Title | Category | R |
|---|-----|----------|----------------------------------------------------------------|----------|---|
| 1 | #148 | 75b325f | github community profile                                       | Docs     |   |
| 2 | #149 | 9394909 | github actions CI workflow + cross-platform matrix             | Testing  |   |
| 3 | #150 | 06b25da | lint configs (shellcheck / ruff / mypy)                        | Testing  |   |
| 4 | #151 | 7d36244 | version stamp + changelog symlink                              | Docs     |   |
| 5 | #152 | a50e399 | native commit-msg hook from validate-commit-msg.sh             | Workflow |   |
| 6 | #153 | 1c4fa08 | allowed-tools enumeration across remaining skills              | Modular  |   |
| 7 | #154 | 5992b61 | provider-specialized deployment-engineer subclasses            | Modular  |   |
| 8 | #155 | 71412b3 | TDD-based coverage for blocking hooks                          | Testing  |   |
| 9 | #156 | 2da5ab4 | gitleaks pre-commit secret scan                                | Security |   |
| 10 | #157 | e1ebfd1 | never-stage secret-pattern expansion                          | Security |   |
| 11 | #158 | f9edc0c | supply-chain pin hardening (serena ref, azure CLI, Claude CLI) | Security |   |
| 12 | #159 | 8c57952 | sandbox auto-fallback default with graceful degradation        | Security |   |
| 13 | #160 | 4e4c0eb | prompt-injection advisory scanner for tool output              | Security |   |
| 14 | #161 | e5bf4ea | reviewer agent tool-surface tightening                         | Modular  |   |
| 15 | #162 | 1f932ee | glossary / search / examples / Diátaxis taxonomy               | Docs     |   |
| 16 | #163 | c34db0c | MCP routing-truthfulness reconciliation                        | Docs     |   |
| 17 | #164 | 2b127d9 | agentmemory MCP restore + memory_recall wired into 4 skills    | Workflow |   |
| 18 | #165 | 65b8254 | SessionStart hook touches caveman-active marker by default     | Workflow |   |
| 19 | #166 | 259d1f5 | teams-mode bundled single-turn dispatch contract                | Workflow |   |
| 20 | #167 | 6e9fab0 | review-skill namespace collision via slug rename                | Workflow | R |
| 21 | #168 | 304d7b2 | review→ppr findings-leak Path M all-or-none contract            | Workflow |   |
| 22 | #169 | 6606688 | typed-subagent default contract                                 | Workflow | R |

<details>
<summary>Per-PR commit detail (click to expand)</summary>

Each PR squash-merged into `main`. Commit SHAs above are the squash-merge SHAs on `main`, not the original feature-branch tip SHAs.

- **#148 (75b325f)** — adds `.github/` community-profile assets (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md).
- **#149 (9394909)** — adds `.github/workflows/ci.yml` with cross-platform job matrix (ubuntu-latest, macos-latest).
- **#150 (06b25da)** — adds top-level `.shellcheckrc`, `pyproject.toml` (ruff + mypy), `.editorconfig`.
- **#151 (7d36244)** — adds `VERSION` file at repo root + `documentation/CHANGELOG.md` symlink.
- **#152 (a50e399)** — adds `.githooks/commit-msg` shim that invokes `claude/hooks/validate-commit-msg.sh`.
- **#153 (1c4fa08)** — adds `allowed-tools:` block to every `SKILL.md` lacking one.
- **#154 (5992b61)** — splits the monolithic deployment-engineer agent into thin per-provider subclasses.
- **#155 (71412b3)** — adds `claude/hooks/tests/` directory + initial blocking-hook coverage.
- **#156 (2da5ab4)** — adds `.gitleaks.toml` + wires the gitleaks scan into `claude/hooks/pre-commit.sh`.
- **#157 (e1ebfd1)** — extends `claude/config/never-stage.txt` to match `_pathguard.py`'s pattern set.
- **#158 (f9edc0c)** — pins exact refs in `scripts/install.sh` for serena, Azure CLI, Claude CLI.
- **#159 (8c57952)** — flips the sandbox provider default to auto-fallback with structured logging on degradation.
- **#160 (4e4c0eb)** — adds `claude/lib/prompt_injection_scan.py` and wires it into the tool-output advisory path.
- **#161 (e5bf4ea)** — tightens `claude/agents/code-reviewer.md` allowed-tools to least-privilege.
- **#162 (1f932ee)** — adds `docs-source/glossary.md`, `documentation/search.json`, examples/, and Diátaxis frontmatter classification.
- **#163 (c34db0c)** — reconciles each SKILL.md's MCP-routing claims with its actual `allowed-tools` declaration.
- **#164 (2b127d9)** — registers `agentmemory` MCP in `~/.claude.json` template + wires `memory_recall` into 4 skill bodies.
- **#165 (65b8254)** — adds `claude/hooks/session-start-caveman.sh` to touch the marker on every SessionStart / PostCompact.
- **#166 (259d1f5)** — documents the bundled single-turn dispatch contract for teams-mode in `~/.claude/rules/agents-worktrees.md`.
- **#167 (6e9fab0)** — renames the `review` skill slug to disambiguate from the built-in `/review` PR template. (Refactor — no gap closed.)
- **#168 (304d7b2)** — adds Path M all-or-none enforcement language to the `pipeline` SKILL.md + `reference.md`.
- **#169 (6606688)** — documents typed `subagent_type` selection as the default for `Agent` dispatch. (Refactor — no gap closed.)

</details>

**Refactor exclusions.** Two of the 22 merged features (F20 #167, F22 #169) refactor previously-implemented behaviour rather than closing a listed gap:

- **F20 — review-skill namespace collision via slug rename.** The pipeline review phase already existed and already dispatched the five-specialist team. F20 renames the skill slug so the built-in PR-review template no longer intercepts the dispatch in subagent contexts. It is a hardening of a working path, not the addition of a missing one.
- **F22 — typed-subagent default contract.** Subagent-First was already the default mode and `Agent` already accepts `subagent_type`. F22 tightens documentation + nudge text to make typed dispatch the default selection rather than `general-purpose` falling out as the implicit choice. It is a default-tightening, not a new capability.

Both are valuable hardenings and merge into the same `Workflow` category by topic, but neither increments the implemented count.

## CATEGORY-LEVEL NOTES

### Workflow

Pre-batch implemented set: charter discovery, autonomous /pipeline loop, agent-teams toggle, Path M inline-fix, single-message multi-Agent dispatch, GitHub Issues mode, charter revalidation. Pre-batch gap set: commit-msg gate at native git level, agentmemory MCP wiring, caveman marker bootstrap, teams-mode dispatch shape, findings-leak prevention, plus the two refactor-class items above.

Post-batch the remaining 2 unaddressed Workflow gaps are intentional follow-ups: hook-based enforcement of teams dispatch shape (F19 explicitly defers this) and hook-based enforcement of findings-leak (F21 explicitly defers this). Both can ship as their own features when drift recurs after the textual contracts land.

### Security

Pre-batch implemented set: never-stage list, _pathguard.py edit blocker, sandbox provider abstraction, env-scrub.py, validate-commit-msg.sh AI-attribution gate, basic gitleaks doctrine in skill. Pre-batch gap set: actual gitleaks wiring at pre-commit, expanded never-stage patterns to match _pathguard, supply-chain pin hardening, sandbox default fail-secure, prompt-injection guard for tool output.

The Total column moves from 15 to 16 to reflect the prompt-injection guard being acknowledged as a distinct surface (F13 #160 ships the advisory scanner; a hard-blocking variant could ship later as its own item).

### Modular

Pre-batch implemented set: agents directory structure, named subagent types, skill paths-scoping, hooks abstraction, sandbox provider, worker-provider abstraction, host-adapters. Pre-batch gap set: allowed-tools complete enumeration, deployment-engineer subclass scaffolding, reviewer agent least-privilege tool surface.

The Total column moves from 9 to 10 to reflect the reviewer-tool-tightening (F14 #161) being counted as its own modular surface separate from generic allowed-tools enumeration (F6 #153).

### Docs

Pre-batch implemented set: full HTML rendering pipeline, snippet system, design-tokens page, codebase-map, skills + agents catalogs, deployment-chooser, themed changelog, governance, decisions log, MCP setup, getting-started 4-tutorial. Pre-batch gap set: community-profile assets (CONTRIBUTING / CODE_OF_CONDUCT / SECURITY / PR template), version stamp + tag, glossary + search + examples + Diátaxis, MCP routing truthfulness.

The remaining 1 unaddressed Docs item is the post-batch publication of this score-card itself (you are reading it).

### Testing

Pre-batch implemented set: hook self-tests (13 of 31 hooks covered), skill-specific tests where they exist, repo-wide tests/ directory, install-smoke. Pre-batch gap set: GitHub Actions CI workflow, lint configs, hook-block-gate coverage for the highest-blast-radius hooks.

Remaining 4 unaddressed Testing items: per-skill test coverage for the skills that ship without tests (caveman-mode, ascii-diagram, README, deploy-target, persona, init), integration tests crossing skill boundaries, performance benchmarks for the render pipeline, a regression-fixture corpus for the `/review` skill's classification logic.

## SOURCE OF TRUTH

- `docs/features-best-practices.md` — the 22-feature plan with full Scope / Constraints / Acceptance Criteria per feature.
- `git log --oneline 75b325f^..6606688 --reverse` — the canonical commit list for the batch.
- `documentation/changelog.html` — themed changelog (will be updated separately to incorporate PRs #148 — #169 in the post-batch release notes).

## SEE ALSO

- [Changelog](changelog.html) — themed v0.0.1 development history.
- [Feature history](feature-history.html) — chronological PR-by-PR ledger.
- [Governance](governance.html) — RACI matrix and review contracts.
- [Workflow hygiene](workflow-hygiene.html) — never-stage list, sandbox posture, AI-attribution policy.
