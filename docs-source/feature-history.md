# Feature History

<!-- richness budget: spatial timeline + visual-token status pills + interactive collapsible-details (≥ 2 target) -->

Rendered audit trail for pipelinekit features. Each merged feature appears
below as its own H2 with a `<details>` collapsible body. The pipeline appends
new entries automatically via `claude/lib/pipeline/features_pruner.py` during
`/post-merge` Step 12.

## Timeline

Spatial overview of recent feature merges (left to right). Built as inline SVG
so it renders standalone without any client dependencies.

<svg viewBox="0 0 800 200" data-snippet-mount="timeline-scrubber" aria-label="feature merge timeline" style="width:100%;max-width:800px;height:auto;">
  <line x1="20" y1="100" x2="780" y2="100" stroke="currentColor" stroke-width="2" />
  <g fill="currentColor" font-size="10" text-anchor="middle">
    <circle cx="80"  cy="100" r="4"/><text x="80"  y="120">F1</text>
    <circle cx="150" cy="100" r="4"/><text x="150" y="120">F2</text>
    <circle cx="220" cy="100" r="4"/><text x="220" y="120">F3</text>
    <circle cx="290" cy="100" r="4"/><text x="290" y="120">F4</text>
    <circle cx="360" cy="100" r="4"/><text x="360" y="120">F5</text>
    <circle cx="430" cy="100" r="4"/><text x="430" y="120">F6</text>
    <circle cx="500" cy="100" r="4"/><text x="500" y="120">F7</text>
    <circle cx="570" cy="100" r="4"/><text x="570" y="120">F8</text>
    <circle cx="640" cy="100" r="4"/><text x="640" y="120">F9</text>
    <circle cx="710" cy="100" r="4"/><text x="710" y="120">F10</text>
    <circle cx="770" cy="100" r="4"/><text x="770" y="120">F11</text>
  </g>
</svg>

## Status legend

<span class="status-pill status-merged">merged</span>
&nbsp; <span class="status-pill status-in-progress">in-progress</span>
&nbsp; <span class="status-pill status-blocked">blocked</span>

## Features

Per-feature sections (backfilled and ongoing) follow. Each H2 wraps its body
in `<details><summary>` so the page stays scannable as the audit trail grows.

<details>
<summary><span class="status-pill status-merged">scaffold</span> &nbsp; about this page</summary>

This page is auto-maintained by `claude/lib/pipeline/features_pruner.py`. New
merged-feature blocks land here as the pipeline runs `/post-merge` Step 12.
The skeleton ships with zero per-feature entries; Task 2.1 of the
fix/docs-workflow-hygiene plan backfills the F1-F11 history below.

</details>

<!-- Per-feature H2 sections injected by Task 2.1 backfill below this comment. -->

## F1 — feat/charter-ai-layer-topics

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#97](https://github.com/Bruce188/pipelinekit/pull/97)
**SHA:** `81efc28`
**Merged:** 2026-05-23T07:26:53Z

Extends Charter Discovery (Step 0 of `/pipeline`) with four new AI Layer topics (12-15) so charters capture model preferences, prompt-caching expectations, agent-team review style, and budget caps upfront.

<details>
<summary>Details</summary>

- Feature class: dev
- Adds Topics 12-15 to the Charter Discovery question set
- Charter schema updated; downstream phases honour new fields
- Stop-self-reflect hook never-stage rules extended to cover `claude-md-proposal-v*.md` artifacts

</details>

## F2 — chore/harness-paths-audit

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#98](https://github.com/Bruce188/pipelinekit/pull/98)
**SHA:** `59f0c76`
**Merged:** 2026-05-23T08:07:19Z

Adds an investigation report documenting harness paths frontmatter coverage across skills — establishes the baseline before paths-enforcement (F4) lands.

<details>
<summary>Details</summary>

- Feature class: non-dev (docs)
- Inventory of skills missing `paths:` frontmatter declarations
- Recommendation hand-off to F4 (write-a-skill paths enforcer)

</details>

## F3 — fix/install-settings-completeness

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#99](https://github.com/Bruce188/pipelinekit/pull/99)
**SHA:** `8be1f22`
**Merged:** 2026-05-23T08:28:33Z

Closes hook-registration gap from the dormancy audit: `scripts/install.sh` now enumerates all 23 distinct Claude-harness hook scripts (previously wired only 14). Smoke test asserts every shipped hook is wired.

<details>
<summary>Details</summary>

- Feature class: dev
- Adds `test_05_full_inventory_parity` to `claude/hooks/tests/test_install_settings_shape.sh`
- New "## Registering in install.sh" section in `claude/hooks/CLAUDE.md`
- Excludes git-only `validate-task-spec.py` from harness wiring

</details>

## F4 — feat/write-a-skill-paths-enforcer

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#100](https://github.com/Bruce188/pipelinekit/pull/100)
**SHA:** `6fffc3a`
**Merged:** 2026-05-23T08:46:42Z

Adds Step 1 to the `write-a-skill` meta-skill requiring all new skills to declare `paths:` in frontmatter, with a small allowlist of global-by-design skills exempted.

<details>
<summary>Details</summary>

- Feature class: dev
- Enforces paths-scoping convention for new skills
- New tests asserting requirement enforcement and allowlist exception
- Builds on F2 audit baseline

</details>

## F5 — feat/analyze-cites-codebase-map

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#101](https://github.com/Bruce188/pipelinekit/pull/101)
**SHA:** `0a6b945`
**Merged:** 2026-05-23T08:57:58Z

Wires the `documentation/codebase-map.html` artifact into the `/analyze` skill exploration flow and the pipeline analyze-phase prompt template. Graceful degradation when the map is absent.

<details>
<summary>Details</summary>

- Feature class: dev
- analyze skill cites the codebase map when present
- pipeline analyze-phase prompt template references the map
- Falls through cleanly when no map exists (no error)

</details>

## F6 — feat/pipeline-verify-gates-hook-smoke

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#102](https://github.com/Bruce188/pipelinekit/pull/102)
**SHA:** `f9c35bc`
**Merged:** 2026-05-23T09:15:23Z

Adds Step 5.5.7 smoke-test sub-step: pipeline verify now discovers `claude/hooks/tests/test_*.sh` via `find` and runs each. Authors get smoke-gate visibility from `claude/hooks/CLAUDE.md`.

<details>
<summary>Details</summary>

- Feature class: dev
- Pipeline verify phase gates on hook smoke tests
- Auto-discovers hook test files
- CLAUDE.md documents the smoke-gate contract for hook authors

</details>

## F7 — feat/stop-reflect-cost-logging

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#103](https://github.com/Bruce188/pipelinekit/pull/103)
**SHA:** `17012ec`
**Merged:** 2026-05-23T09:37:16Z

`stop-self-reflect` hook now appends a `cost-events.jsonl` line after each `claude -p` invocation so Step 1.46 budget preflight reflects all session cost. Best-effort; hook still exits 0 on write failure.

<details>
<summary>Details</summary>

- Feature class: dev
- Hook writes one JSONL line per reflect invocation
- Budget preflight (Step 1.46) consumes the log
- Smoke tests cover happy + failure paths
- Exit-0 guarantee preserved on write failure

</details>

## F8 — feat/review-checks-skill-compliance

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#104](https://github.com/Bruce188/pipelinekit/pull/104)
**SHA:** `c05c445`
**Merged:** 2026-05-23T10:03:21Z

`/review` skill grows skill-compliance gates for `paths:`, denial-tracker integration, and richness checks — review now catches missing-frontmatter and rendered-HTML quality regressions before merge.

<details>
<summary>Details</summary>

- Feature class: dev
- New review gates: paths-declared, denial-tracker integration, richness threshold
- Composes with F4 (paths enforcement) and F10 (richness threshold bump)

</details>

## F9 — chore/pipeline-terminal-state

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#105](https://github.com/Bruce188/pipelinekit/pull/105)
**SHA:** `5d9796e`
**Merged:** 2026-05-23T10:24:14Z

On clean exit, Step 5.10 Terminal Cleanup writes `**Step:** done`, `**Completed:** <ISO8601 UTC>`, and `**Features merged:** <count>` to `docs/pipeline-state.md`. Step 3 grows a terminal-state guard that refuses silent re-execution of a finished pipeline.

<details>
<summary>Details</summary>

- Feature class: non-dev (chore)
- Adds terminal state marker fields to pipeline state schema
- `--restart-from` guard fires before override on a `done` state
- Removes dead Step 6 cleanup-line that previously deleted state files

</details>

## F10 — chore/html-effectiveness-wiring

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#106](https://github.com/Bruce188/pipelinekit/pull/106)
**SHA:** `7995b08`
**Merged:** 2026-05-23T11:01:02Z

Authors two new reference pages — `html-effectiveness-principles.md` and `design-tokens.md` — and links them from the documentation index. Adds a Page-type → snippet taxonomy table to the docs-writer skill. Bumps richness threshold to require two distinct rich-pattern matches per page.

<details>
<summary>Details</summary>

- Feature class: non-dev (chore/docs)
- Two new reference pages: html-effectiveness-principles, design-tokens
- Page-type → snippet taxonomy table in docs-writer SKILL.md
- Richness check threshold raised: 2 distinct patterns required

</details>

## F11 — chore/caveman-mode-split-ultra-wenyan

**Status:** <span class="status-pill status-merged">merged</span>
**PR:** [#107](https://github.com/Bruce188/pipelinekit/pull/107)
**SHA:** `2b70c5f`
**Merged:** 2026-05-23T11:19:34Z

Caveman-mode skill grows a three-zone content split — Zone 1 (code) stays normal English, Zone 2 (wenyan compressed prose), Zone 3 (fragmentary directives). Cleaner verbosity gradient for mixed-content responses.

<details>
<summary>Details</summary>

- Feature class: non-dev (chore)
- Three-zone content split (code / wenyan / fragments)
- Refines intensity levels: wenyan-ultra, ultra, full, lite
- Skill snippet contracts updated accordingly

</details>
