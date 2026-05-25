#!/usr/bin/env bash
set -euo pipefail
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
REPO_ROOT=$(git rev-parse --show-toplevel)
FORMAT_RUNLOG="$REPO_ROOT/claude/lib/pipeline/format_runlog.sh"

# Gate-logic shim: implements the probe-block precondition from SKILL.md § Post-Merge Verification Gate
# Args: <feature_file> [gate_merge_date]
# If modern (Run Log date >= gate_merge_date) and no probe block -> append "PostMerge: FAILED (probe missing)"
# If legacy (Run Log date < gate_merge_date) -> no-op
run_gate() {
  local feature_file="$1"
  local gate_merge_date="${2:-2026-05-25}"

  # Find the most recent Run Log canonical line date
  local runlog_date
  runlog_date=$(grep -oE '^\- [0-9]{4}-[0-9]{2}-[0-9]{2}' "$feature_file" 2>/dev/null | tail -1 | awk '{print $2}' || true)

  if [[ -z "$runlog_date" ]]; then
    return 0
  fi

  # Legacy carve-out: pre-gate date -> no-op (R5 backward-compat)
  if [[ "$runlog_date" < "$gate_merge_date" ]]; then
    return 0
  fi

  # Idempotency: if probe block already present, no-op
  if grep -q "^Production-Probe: BEGIN$" "$feature_file" 2>/dev/null; then
    return 0
  fi

  # No probe block: gate fails
  printf 'PostMerge: FAILED (probe missing)\n' >> "$feature_file"
}

# run_gate_with_block: full gate including POSTMERGE_OK path (when probe block present and valid)
run_gate_with_block() {
  local feature_file="$1"
  local gate_merge_date="${2:-2026-05-25}"

  local runlog_date
  runlog_date=$(grep -oE '^\- [0-9]{4}-[0-9]{2}-[0-9]{2}' "$feature_file" 2>/dev/null | tail -1 | awk '{print $2}' || true)

  if [[ -z "$runlog_date" ]]; then
    return 0
  fi

  if [[ "$runlog_date" < "$gate_merge_date" ]]; then
    return 0
  fi

  # Idempotency: if POSTMERGE_OK already present, no-op
  if grep -q "^POSTMERGE_OK:" "$feature_file" 2>/dev/null; then
    return 0
  fi

  # Probe block must be present
  if ! grep -q "^Production-Probe: BEGIN$" "$feature_file" 2>/dev/null; then
    printf 'PostMerge: FAILED (probe missing)\n' >> "$feature_file"
    return 0
  fi

  # Validate the block
  local block
  block=$(awk '/^Production-Probe: BEGIN$/,/^Production-Probe: END$/' "$feature_file")
  if ! printf '%s\n' "$block" | bash "$FORMAT_RUNLOG" validate-block - 2>/dev/null; then
    printf 'PostMerge: FAILED (probe-block invalid)\n' >> "$feature_file"
    return 0
  fi

  printf 'POSTMERGE_OK: mock-cmd\n' >> "$feature_file"
}

## Scenario 1: Run Log line WITHOUT probe block -> gate appends PostMerge: FAILED (probe missing)
echo "--- Scenario 1: no probe block -> FAILED (probe missing) ---"
(
  cat > "$TMPDIR/feature_no_block.md" <<'EOF'
### Run Log

- 2099-01-01 12:00: SUCCESS — PR #200 merged as abc1234. dev feature. analysis-v96 / plan-v96 / prompts-v93 / review-v107. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 5 files, +100/-20. Test feature for gate scenario 1.
EOF

  run_gate "$TMPDIR/feature_no_block.md" "2026-05-25"

  grep -q "PostMerge: FAILED (probe missing)" "$TMPDIR/feature_no_block.md" || { echo "FAIL: expected PostMerge: FAILED (probe missing)"; exit 1; }
  if grep -q "POSTMERGE_OK" "$TMPDIR/feature_no_block.md" 2>/dev/null; then
    echo "FAIL: POSTMERGE_OK must NOT be present"; exit 1
  fi
  echo "PASS: Scenario 1"
)

## Scenario 2: Run Log line WITH valid probe block -> gate appends POSTMERGE_OK
echo "--- Scenario 2: valid probe block -> POSTMERGE_OK ---"
(
  cat > "$TMPDIR/feature_with_block.md" <<'EOF'
### Run Log

- 2099-01-01 12:00: SUCCESS — PR #200 merged as abc1234. dev feature. analysis-v96 / plan-v96 / prompts-v93 / review-v107. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 5 files, +100/-20. Test feature for gate scenario 2.
Production-Probe: BEGIN
1. Boot: PASS (app started in 5s)
2. Golden path: PASS (GET /health -> 200)
3. Failure path: PASS (invalid auth -> 401)
4. Console + Network: PASS (no errors)
5. Screenshot / what users see: PASS (UI rendered)
6. Background tasks / leaks: PASS (no leaks)
7. State survives restart: PASS (state persisted)
Summary: All probes green.
Repo class: web-app
Probe depth: standard
Production-Probe: END
EOF

  run_gate_with_block "$TMPDIR/feature_with_block.md" "2026-05-25"

  grep -q "POSTMERGE_OK" "$TMPDIR/feature_with_block.md" || { echo "FAIL: expected POSTMERGE_OK"; exit 1; }
  if grep -q "FAILED (probe missing)" "$TMPDIR/feature_with_block.md" 2>/dev/null; then
    echo "FAIL: FAILED (probe missing) must NOT be present"; exit 1
  fi
  echo "PASS: Scenario 2"
)

## Scenario 3: Idempotency — second gate run on Scenario-2 fixture is a no-op
echo "--- Scenario 3: idempotency (second run = no-op) ---"
(
  cat > "$TMPDIR/feature_idempotent.md" <<'EOF'
### Run Log

- 2099-01-01 12:00: SUCCESS — PR #200 merged as abc1234. dev feature. analysis-v96 / plan-v96 / prompts-v93 / review-v107. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 5 files, +100/-20. Test feature for idempotency.
Production-Probe: BEGIN
1. Boot: PASS (app started in 5s)
2. Golden path: PASS (GET /health -> 200)
3. Failure path: PASS (invalid auth -> 401)
4. Console + Network: PASS (no errors)
5. Screenshot / what users see: PASS (UI rendered)
6. Background tasks / leaks: PASS (no leaks)
7. State survives restart: PASS (state persisted)
Summary: All probes green.
Repo class: web-app
Probe depth: standard
Production-Probe: END
EOF

  run_gate_with_block "$TMPDIR/feature_idempotent.md" "2026-05-25"
  cp "$TMPDIR/feature_idempotent.md" "$TMPDIR/feature_idempotent_run1.md"
  run_gate_with_block "$TMPDIR/feature_idempotent.md" "2026-05-25"
  cp "$TMPDIR/feature_idempotent.md" "$TMPDIR/feature_idempotent_run2.md"

  diff "$TMPDIR/feature_idempotent_run1.md" "$TMPDIR/feature_idempotent_run2.md" || { echo "FAIL: second run changed file (idempotency violated)"; exit 1; }
  echo "PASS: Scenario 3"
)

## Scenario 4: Workflow-toolkit carve-out — all probes NOT EXECUTED + Boot extra line -> validate-block PASS + POSTMERGE_OK
echo "--- Scenario 4: workflow-toolkit carve-out ---"
(
  cat > "$TMPDIR/feature_workflow_toolkit.md" <<'EOF'
### Run Log

- 2099-01-01 12:00: SUCCESS — PR #200 merged as abc1234. dev feature. analysis-v96 / plan-v96 / prompts-v93 / review-v107. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 5 files, +100/-20. Workflow-toolkit feature.
Production-Probe: BEGIN
1. Boot: NOT EXECUTED (workflow-toolkit)
2. Golden path: NOT EXECUTED (workflow-toolkit)
3. Failure path: NOT EXECUTED (workflow-toolkit)
4. Console + Network: NOT EXECUTED (workflow-toolkit)
5. Screenshot / what users see: NOT EXECUTED (workflow-toolkit)
6. Background tasks / leaks: NOT EXECUTED (workflow-toolkit)
7. State survives restart: NOT EXECUTED (workflow-toolkit)
Boot: NOT EXECUTED (workflow-toolkit) — selftest 4 PASS / 0 FAIL, hook-smoke 5 PASS / 0 FAIL, skill-smoke 12 PASS / 0 FAIL
Summary: Workflow-toolkit feature — no live app; selftest + hook-smoke + skill-smoke evidence captured.
Repo class: workflow-toolkit
Probe depth: standard
Production-Probe: END
EOF

  # validate-block must PASS for workflow-toolkit probe block
  block=$(awk '/^Production-Probe: BEGIN$/,/^Production-Probe: END$/' "$TMPDIR/feature_workflow_toolkit.md")
  printf '%s\n' "$block" | bash "$FORMAT_RUNLOG" validate-block - || { echo "FAIL: workflow-toolkit probe block should validate"; exit 1; }

  run_gate_with_block "$TMPDIR/feature_workflow_toolkit.md" "2026-05-25"
  grep -q "POSTMERGE_OK" "$TMPDIR/feature_workflow_toolkit.md" || { echo "FAIL: workflow-toolkit probe block should yield POSTMERGE_OK"; exit 1; }
  echo "PASS: Scenario 4"
)

## Scenario 5: Backward-compat — F1-shape legacy Run Log (pre-gate date) -> gate no-op (R5)
echo "--- Scenario 5: F1-shape legacy entry (pre-gate) -> no-op ---"
(
  cat > "$TMPDIR/feature_legacy.md" <<'EOF'
### Run Log

- 2026-05-22 18:30: SUCCESS — PR #115 merged as 9c4991c. non-dev feature. analysis-v90 / plan-v90 / prompts-v88 / review-v100. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 2 files, +12/-3. Re-inject caveman contract on /compact + auto-compact.
EOF

  run_gate "$TMPDIR/feature_legacy.md" "2026-05-25"

  if grep -q "POSTMERGE_OK" "$TMPDIR/feature_legacy.md" 2>/dev/null; then
    echo "FAIL: POSTMERGE_OK must NOT be present for legacy entry"; exit 1
  fi
  if grep -q "PostMerge: FAILED" "$TMPDIR/feature_legacy.md" 2>/dev/null; then
    echo "FAIL: PostMerge: FAILED must NOT be present for legacy entry"; exit 1
  fi
  echo "PASS: Scenario 5"
)

echo "OK: test_production_probe_gate.sh — 5/5 scenarios PASS"
