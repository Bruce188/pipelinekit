# Manual Smoke — Charter Discovery (interactive `/pipeline` Step 0)

> Manual post-merge smoke for `/pipeline` Step 0 (Charter Discovery). Companion to the assertion-style `test_*.sh` scripts in this directory. Re-runs APPEND a new dated sub-heading to `## Observed Evidence`; this file is SINGLE-VERSION and does NOT follow the Versioning Convention.

## Purpose

Document the smoke procedure for `/pipeline` Step 0 in enough detail that any operator can execute it post-merge. The smoke is intentionally manual: Step 0 relies on `AskUserQuestion`, which is interactive-session-only, so it cannot be automated as an assertion-style script alongside the other `test_*.sh` files in this directory.

## When to Run

Post-merge of any change touching `claude/skills/pipeline/SKILL.md` Step 0 or `claude/skills/pipeline/charter.md`. Run against a fresh `docs/` directory in a staging area (NOT the active project's `docs/charter.md` — see Smoke Procedure step 1 below).

## Subprocess-Mode Caveat

From `claude/skills/pipeline/SKILL.md § "Step 0: Charter Discovery"`:

> Step 0 relies on `AskUserQuestion`, which is interactive-session-only. If invoked via a subprocess driver (e.g., `orchestrate.sh` or `claude -p`), Step 0 cannot run.

The smoke MUST run in an interactive Claude Code session (`claude`), NOT via `orchestrate.sh` and NOT via `claude -p`.

## Smoke Procedure

1. **Set up a fresh staging area** so the active project's `docs/charter.md` is left alone:
   ```bash
   mkdir -p /tmp/pipelinekit-smoke-charter
   cd /tmp/pipelinekit-smoke-charter
   git init -q
   git commit --allow-empty -qm "init"
   ```

2. **Open a fresh interactive Claude Code session** from that staging directory:
   ```bash
   claude
   ```
   (NOT `claude -p`, NOT `orchestrate.sh`.)

3. **Invoke `/pipeline` interactively** with NO positional feature file, NO `--no-charter`, and NO `--charter <path>`:
   ```
   /pipeline
   ```

4. **Step through Charter Discovery (Step 0)**: answer each `AskUserQuestion` topic. After ~5 rounds, when the convergence-check choice list is shown, pick **"ship the charter now"** (the escape-hatch option per `claude/skills/pipeline/charter.md § "Escape-Hatch Convention"`).

5. **Allow Step 0 to write the charter** (`docs/charter.md`) and set the `**Charter:**` pointer in `docs/progress.md`. Cancel/exit the pipeline before any further phases run — the smoke covers Step 0 only (Ctrl+C, or `/clear`).

## Acceptance Criteria

Pass/fail checks the operator runs in the staging directory after the smoke:

a. `docs/charter.md` exists.

b. `docs/charter.md` contains the H2 sections enumerated in the required-topics list of `claude/skills/pipeline/charter.md § "Charter File Schema"` (verify via `grep -n '^## ' docs/charter.md` and cross-check against the schema list). The optional `## Stakeholders` section is present iff the smoke answers triggered the multi-party probe per the `### Stakeholders (conditional probe)` sub-section of the question bank. Do NOT hardcode a section count — the schema is the source of truth.

c. `docs/progress.md` contains the literal `**Charter:** docs/charter.md` (or the versioned path the smoke produced) on the pointer line.

d. Step 0 exited cleanly via the "ship the charter now" branch — no error, no `/clear` triggered from inside the topic loop.

## Observed Evidence

<!-- Operator: after running the smoke, paste evidence here under a dated
     sub-heading: (1) output of `grep -n '^## ' docs/charter.md`, (2) the
     `**Charter:**` pointer line from `docs/progress.md`, (3) one-line
     PASS / FAIL verdict. Re-runs APPEND a new dated sub-heading; do NOT
     version this file. -->

### TODO — pending operator run

## Bugs Caught

If the smoke uncovers a regression in Step 0 or downstream, record the symptom here AND open a SEPARATE `fix:` feature. The procedure-spec deliverable MUST NOT bundle bug-fixes.

## Run Metadata

- Timestamp:
- pipelinekit commit SHA the smoke ran against:
- Claude Code CLI version:
- Host OS:
- OS distro:
