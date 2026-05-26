# Workflow Hygiene

<!-- richness budget: visual-token status pills + comparison-tabs (≥ 1 — default threshold) -->

Three documented drift modes accumulated in `docs/` over the pipelinekit lifetime:
rotation drift, orphan snapshots, and `features.md` bloat. As of 2026-05-23 the
`docs/` tree had grown to ~7 MB across 424 files with `docs/progress.md` alone at
265 KB / ~66 K tokens per `Read`. This page documents the hygiene contract that
keeps the tree small from now on.

## WHAT

The three drift modes (each fixed independently — see the corresponding skill):

<div data-snippet-mount="comparison-tabs">
<div data-tab="rotation">

**Rotation drift** (`/create-plan` Step 5). The rotator used to scope by `## Status`
H2 only — but `docs/progress.md` accumulated 62 `## Iteration:` H2 blocks because
the alt anchor was invisible to the gate. Fix: both anchors are now valid
iteration-boundary markers.

</div>
<div data-tab="orphans">

**Orphan snapshots** (no janitor). Halt-incident snapshots (e.g.
`docs/pipeline-state.md.feature-7-done`, `docs/RESUME.md`, `docs/features-master.md`)
accumulated forever — 39 files as of 2026-05-23. Fix: `/post-merge` Step 12
runs a janitor reading `claude/config/orphan-patterns.txt` (fnmatch globs).

</div>
<div data-tab="features-bloat">

**features.md bloat.** Done feature blocks lingered in `docs/features.md` instead
of being archived. 11 merged blocks (PRs #97-#107) sat alongside the in-progress
12th. Fix: `claude/lib/pipeline/features_pruner.py` (invoked from `/post-merge`
Step 12) moves done blocks to `docs-source/feature-history.md` and re-renders
the HTML audit trail.

</div>
<div data-tab="dashboard-decisions">

**Dashboard + decisions log (F13).** Two new generated pages close the
introspection gap. `claude/lib/pipeline/dashboard_renderer.py` emits a 12-section
live-state dashboard at `documentation/dashboard.html` with an ISO8601
`Generated:` timestamp. `claude/lib/pipeline/decisions_renderer.py` emits a
newest-first per-feature rationale log at `documentation/decisions.html`. Both
share a single extractor at `claude/lib/pipeline/workflow_extractor.py` (hybrid
RICH/EMBEDDED mode). Both honour `PIPELINE_HYGIENE_OFF=1` and run AFTER the
features-pruner inside the same `/post-merge` Step 12 `else` branch.

</div>
</div>

## WHEN

The hygiene block runs on **every** `/post-merge` invocation (Step 12). One env var
controls the entire block:

| Env var | Default | Effect |
|---------|---------|--------|
| `PIPELINE_HYGIENE_OFF` | unset (block runs) | When `=1`, BOTH the janitor and the pruner are skipped (single switch — SubQ-C). |
| `PIPELINE_JANITOR_DRY_RUN` | `1` (dry-run on) | When `=0`, the orphan janitor actually deletes matched files. Default ON for safety. |

The rotator (`/create-plan` Step 5) is plan-iteration-driven — it fires whenever a
new plan version is being written, not at `/post-merge` time.

## HOW

<span class="status-pill status-success">JANITOR</span> &nbsp; reads `claude/config/orphan-patterns.txt`
(fnmatch globs, default-allow on missing) and intersects each candidate against
`claude/config/never-stage.txt` (default-deny). Double-matched paths are NEVER
deleted. Single-matched paths are removed under `PIPELINE_JANITOR_DRY_RUN=0`,
logged under `=1`. The never-stage list covers root `.env`, env-file variants
(`.env.local`, `.env.production`, `.env.development`, `.env.*`), crypto material
(`*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.cer`, `*.crt`, SSH keypairs `id_rsa*` /
`id_ed25519*` / `id_dsa*` / `id_ecdsa*`), and credential directories (`.aws/`,
`.ssh/`, `.gnupg/`, `.kube/config`) — coverage asserted by
`claude/hooks/tests/test_never_stage_expanded.sh`.

<span class="status-pill status-success">PRUNER</span> &nbsp; reads `docs/features.md`,
detects `ppr-done — PR #N squashed` markers in each `## ` H2 block's Run Log,
moves matching blocks to `docs-source/feature-history.md`, and re-renders
`documentation/feature-history.html` via `claude/skills/docs-writer/render.py`.

<span class="status-pill status-success">ROTATOR</span> &nbsp; recognises BOTH `## Status`
AND `## Iteration:` as iteration-boundary H2 anchors. Older blocks rotate into
`docs/archive/progress-v<N>.md` per the Versioning Convention; the most recent
block stays in `docs/progress.md`.

## WHY

Token cost on 2026-05-23: ~7 MB across 424 files in `docs/`; `docs/progress.md`
alone was 265 KB / ~66 K tokens per `Read`. Every pipeline phase reads
`docs/progress.md` to follow the `**Plan:**` / `**Analysis:**` pointers. Without
this hygiene block, each phase was eating ~13× the post-rotation token budget on
a single file load. Multiply by feature count and you get a context-budget
blowout per `/pipeline` run.

## SEE ALSO

- `/create-plan` Step 5 — rotation logic (dual-anchor recognition).
- `/post-merge` Step 12 — hygiene block (janitor + pruner).
- `claude/config/orphan-patterns.txt` — fnmatch glob source-of-truth.
- `claude/config/never-stage.txt` — never-stage intersection guard.
- `claude/lib/pipeline/features_pruner.py` — pruner module.
- `claude/lib/pipeline/workflow_extractor.py` — shared hybrid (RICH/EMBEDDED) extractor for dashboard + decisions.
- `claude/lib/pipeline/dashboard_renderer.py` — 12-section dashboard emitter.
- `claude/lib/pipeline/decisions_renderer.py` — newest-first decisions log emitter.
- `documentation/dashboard.html` — rendered live-state dashboard.
- `documentation/decisions.html` — rendered decisions log.
- `documentation/feature-history.html` — rendered audit trail.

<details>
<summary>Hygiene block opt-out env vars at a glance</summary>

| Env var | Default | Effect |
|---------|---------|--------|
| `PIPELINE_HYGIENE_OFF` | unset | When `=1`, the whole Step 12 block (janitor + pruner + dashboard + decisions) short-circuits. |
| `PIPELINE_JANITOR_DRY_RUN` | `1` | When `=0`, the orphan janitor deletes matched files. Default ON for safety. |

Wall-time budget: dashboard + decisions each carry a 5-second SIGALRM cap. On
overrun they log `*_BUDGET_EXCEEDED` and exit `0` — never block `/post-merge`.

</details>
- `~/.claude/rules/workflow.md` § Versioning Convention — archive numbering rule.
