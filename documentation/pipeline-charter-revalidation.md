# Pipeline Charter Revalidation

`/pipeline --renew` now revalidates `docs/charter.md` against the current repository state before regenerating feature files. This page describes the revalidation pass, the drift report artifact, the `--auto` flag, and the 7-day freshness skip.

---

## Overview

When you run `/pipeline --renew`, the pipeline regenerates `docs/features-renewed.md` from deferred and failed items. As of this extension, the pipeline first checks whether the active charter still reflects the current codebase. Lines or sections of the charter that no longer match repo reality are flagged as **drifted** or **obsolete**, and a drift report is written to `docs/charter-drift.md`.

This pass runs inside Step 6.5 of the `--renew` flow, between the Step 6 renewal log and the Step 7 proceed gate. It does not run when `--no-charter` is in effect.

---

## Invocation

```bash
# Interactive revalidation — pipeline pauses to ask about each drifted feature
/pipeline --renew

# Autonomous revalidation — accept all drift entries without prompting
/pipeline --renew --auto
```

`--auto` is a sub-option of `--renew`. Passing `--auto` without `--renew` has no effect.

---

## Freshness Skip

If the active charter was created within the last **7 days**, the revalidation pass is skipped entirely. The pipeline reads the `created:` field from the charter's YAML frontmatter and computes the age using the host's `date -d` command (GNU coreutils). When the charter is fresh, the pipeline emits:

```
CHARTER_REVALIDATE: fresh — charter created <ISO date> (<N> days ago); skipping re-validation pass
```

and advances directly to Step 7 without writing a drift report or prompting the user.

**Fall-through conditions.** The freshness check falls through (treats the charter as not fresh) when:
- The charter has no `---`-fenced frontmatter.
- The frontmatter has no `created:` key.
- The `created:` value fails to parse as a date.
- The host does not have GNU `date -d` (BSD `date` is not supported).
- The computed date is in the future.

Charters in any fall-through state proceed to the full revalidation pass.

**Adding a `created:` field to your charter:**

```markdown
---
created: 2026-05-19
---

# Charter: My Project
...
```

---

## Probe Surface

The revalidation pass inspects all 10 standard charter H2 sections. Sections with no repo-introspectable facts are probed as `current` automatically (narrative-only). Sections backed by filesystem artifacts are probed with read-only Glob and file-existence checks.

| Charter Section | Probe Strategy |
|----------------|----------------|
| `Goal` | Narrative — always `current` |
| `Users` | Narrative — always `current` |
| `Problem` | Narrative — always `current` |
| `Success` | Glob filename mentions; existence check under repo root |
| `Non-Goals` | Token-overlap against feature descriptions |
| `Constraints` | Glob filename mentions; package-manager file lookups for library mentions |
| `MVP Boundary` | `**Out (deferred):**` — token-overlap; `**In:**` — always `current` |
| `Prior Art` | External URLs — not probed; internal paths — existence check |
| `Open Questions` | Narrative — always `current` |
| `Decision Log` | Historical — always `current` |

Sections missing from the charter or with empty bodies are logged as a warning and treated as empty (zero drift produced):

```
CHARTER_REVALIDATE: warn — charter missing Non-Goals or MVP Boundary section; treating as empty
```

---

## Status Enum

Every drift entry carries one of three status values:

| Status | Meaning |
|--------|---------|
| `current` | The fact still holds — the file exists, the claim string is present, the library is still pinned. |
| `drifted` | The fact partially holds — the file exists but the claim is no longer accurate (for example, `orchestrate.sh` is present but is a stub). |
| `obsolete` | The entity the charter line references no longer exists at all — the file is gone or the library is uninstalled. |

Only `drifted` and `obsolete` entries appear in the drift report artifact. `current` entries are tallied but not enumerated.

---

## Drift Report Artifact

After the probe pass completes, the pipeline writes a drift report to `docs/charter-drift.md`. On subsequent runs the file is versioned per the project's Versioning Convention: `docs/charter-drift-v2.md`, `docs/charter-drift-v3.md`, etc.

The report is a markdown table with four columns:

| Column | Type | Description |
|--------|------|-------------|
| `section` | string | Charter H2 section where the drift originated (`Non-Goals`, `Success`, `Prior Art`, etc.) |
| `line` | string | The feature header that flagged drift (lower-cased, whitespace-collapsed) |
| `status` | enum | `drifted` or `obsolete` |
| `evidence` | string | Free-form explanation — e.g. `"feature blob token-overlaps Non-Goal phrase 'no auth ui'"` or `"file src/auth/handler.py absent under repo root"` |

**Example report:**

```markdown
# Charter Drift Report

Generated: 2026-05-19T14:30:00Z
Charter: docs/charter.md
Features scanned: 8
Drift entries: 2

| section | line | status | evidence |
|---------|------|--------|----------|
| Non-Goals | feat/add-oauth-login | drifted | feature blob token-overlaps Non-Goal phrase 'no third-party auth' |
| Prior Art | feat/migrate-storage | obsolete | internal path docs/prior-art/s3-spike.md absent under repo root |
```

The drift report is a workflow artifact. It lives in `docs/` and is never staged or committed (covered by the standard never-stage list).

---

## Drift-Resolution Loop

### Interactive mode (default)

When drift entries are found, the pipeline prompts you for each `(feature_header, drift_reason, status, evidence)` tuple via `AskUserQuestion`:

```
Feature `feat/add-oauth-login` may drift outside the charter.
Reason: feature blob token-overlaps Non-Goal phrase 'no third-party auth' [status: drifted].
How do you want to proceed?

A) Proceed    — keep this feature; run it through the pipeline unchanged.
B) Drop feature — remove this feature block from docs/features-renewed.md.
C) Edit charter — stop the pipeline so you can hand-edit the charter, then re-run.
```

Choosing **C (Edit charter)** stops the pipeline immediately and prints the charter path and the re-run command:

```
Charter file: docs/charter.md
Edit the Non-Goals or MVP Boundary section, then resume via:
  /pipeline --charter docs/charter.md --renew
```

### --auto mode

When `--auto` is set, every drift entry is auto-accepted without prompting. After the loop, an HTML-comment header block is prepended to `docs/features-renewed.md` recording the accepted entries:

```html
<!-- auto-accept: charter drift accepted without prompting; --renew --auto invoked at 2026-05-19T14:30:00Z
  drift entries:
    - feature: feat/add-oauth-login | section: Non-Goals | status: drifted | evidence: feature blob token-overlaps Non-Goal phrase 'no third-party auth'
    - feature: feat/migrate-storage | section: Prior Art | status: obsolete | evidence: internal path docs/prior-art/s3-spike.md absent under repo root
-->
```

The pipeline then logs:

```
CHARTER_REVALIDATE: auto-accepted 2 drift entries
```

and advances to Step 7.

Use `--auto` when running the pipeline unattended (CI, cron) and you want drift to be noted but not block the run.

---

## Clean Path

If no drift entries are found (all probed sections resolve as `current`), the pipeline logs:

```
CHARTER_REVALIDATE: clean — N features in scope
```

and advances directly to Step 7 without prompting or writing a drift report.

---

## Log Tokens

| Token | When emitted |
|-------|-------------|
| `CHARTER_REVALIDATE: fresh — charter created <date> (<N> days ago); skipping re-validation pass` | 7-day freshness skip fired |
| `CHARTER_REVALIDATE: skipped — no charter in effect` | Charter pointer is `(none)`, absent, or points to a missing file |
| `CHARTER_REVALIDATE: warn — charter missing Non-Goals or MVP Boundary section; treating as empty` | Expected charter section not found |
| `CHARTER_REVALIDATE: clean — N features in scope` | Probe pass found zero drift entries |
| `CHARTER_REVALIDATE: auto-accepted N drift entries` | `--auto` mode accepted drift without prompting |
| `CHARTER_REVALIDATE: user chose edit-charter for <feature_header>` | User chose option C in interactive mode |

---

## Python API

The revalidation logic is implemented in `claude/lib/pipeline/charter_revalidate.py`. The public surface is pure stdlib (`re`, `pathlib`, `datetime`) with no module-level I/O. The only filesystem write in the module is `write_drift_report`.

```python
from claude.lib.pipeline.charter_revalidate import (
    detect_drift,          # 4-tuple: (header, reason, status, evidence)
    detect_drift_legacy,   # 2-tuple shim for older consumers
    parse_charter_frontmatter,
    is_fresh,
    write_drift_report,
    probe_narrative,
    probe_success,
    probe_constraints,
    probe_prior_art,
    STATUS_CURRENT,
    STATUS_DRIFTED,
    STATUS_OBSOLETE,
)
```

**`detect_drift(charter_text, features_text)`** returns `list[tuple[str, str, str, str]]` — each entry is `(feature_header, drift_reason, status, evidence)`.

**`detect_drift_legacy(charter_text, features_text)`** returns `list[tuple[str, str]]` — strips status and evidence. Use this if you have existing code that unpacks 2-tuples and cannot migrate yet.

**`is_fresh(charter_text, today_iso, threshold_days=7)`** returns `True` when the charter frontmatter `created:` date is within `threshold_days` of `today_iso`. Returns `False` on any parse failure.

**`write_drift_report(drift_entries, docs_dir)`** writes the versioned drift report and returns the `pathlib.Path` of the written file.

---

## Shell Helper

`claude/lib/pipeline/charter_revalidate_skip.sh` implements the outer skip logic (missing charter + freshness check) as a standalone shell script. It is called by the pipeline orchestrator before dispatching the Python probe. Exit codes:

| Exit | Meaning |
|------|---------|
| `0` with `CHARTER_REVALIDATE: fresh` on stdout | 7-day skip fired — caller should skip the Python probe |
| `0` with `CHARTER_REVALIDATE: skipped` on stdout | No charter in effect — caller should skip the Python probe |
| `0` with `CHARTER_REVALIDATE: charter found at <path>` on stdout | Charter is present and stale — caller should run the Python probe |

The script uses GNU `date -d` for the freshness computation. On BSD hosts (macOS without GNU coreutils) the freshness check falls through silently and the Python probe runs.

---

## Related Files

| File | Purpose |
|------|---------|
| `claude/lib/pipeline/charter_revalidate.py` | Core Python implementation — drift detection, probes, report writer |
| `claude/lib/pipeline/charter_revalidate_skip.sh` | Shell skip helper — missing-charter and freshness checks |
| `claude/lib/pipeline/tests/test_charter_revalidate.py` | Python unit tests for the 4-tuple API, freshness, frontmatter parsing, and legacy shim |
| `claude/skills/pipeline/tests/test_renew_auto_flag.sh` | Shell smoke tests for `--renew --auto` contract (fresh fixture, stale fixture, auto-accept header) |
| `claude/skills/pipeline/reference.md` | Canonical sub-step 6.5 spec (freshness skip, probe table, status enum, drift-report schema, --auto bypass) |
| `claude/skills/pipeline/SKILL.md` | `--auto` flag enumeration and Step 1.6 pointer to drift artifact |
| `docs/charter-drift.md` | First drift report (workflow artifact — not committed) |
| `docs/charter-drift-vN.md` | Subsequent versioned drift reports |
