#!/usr/bin/env bash
set -euo pipefail
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
REPO_ROOT=$(git rev-parse --show-toplevel)
HELPER="$REPO_ROOT/claude/lib/pipeline/format_runlog.sh"

## Assertion 1: selftest 12/12 PASS
echo "--- Assertion 1: selftest 12/12 PASS ---"
output=$(bash "$HELPER" selftest 2>&1 || true)
echo "$output" | grep -q "selftest: 12/12 PASS" || { echo "FAIL: expected selftest: 12/12 PASS, got: $output"; exit 1; }
echo "PASS: selftest 12/12"

## Assertion 2: good block validates cleanly (exit 0)
echo "--- Assertion 2: good block validates ---"
cat > "$TMPDIR/good_block.txt" <<'EOF'
Production-Probe: BEGIN
1. Boot: PASS (mvn spring-boot:run, 8.4s to ready)
2. Golden path: PASS (GET /api/health -> 200, 142ms)
3. Failure path: PASS (invalid token -> 401, 23ms)
4. Console + Network: PASS (no console errors, all 2xx)
5. Screenshot / what users see: PASS (login form rendered)
6. Background tasks / leaks: PASS (no orphan threads)
7. State survives restart: PASS (session resumed after restart)
Summary: All probes green; feature ships clean.
Repo class: web-app
Probe depth: standard
Production-Probe: END
EOF
bash "$HELPER" validate-block "$TMPDIR/good_block.txt" || { echo "FAIL: good block should exit 0"; exit 1; }
echo "PASS: good block validates"

## Assertion 3: missing END marker exits 1 with RUNLOG_PROBE_BLOCK_INVALID
echo "--- Assertion 3: missing END marker ---"
cat > "$TMPDIR/missing_end.txt" <<'EOF'
Production-Probe: BEGIN
1. Boot: PASS (evidence)
2. Golden path: PASS (evidence)
3. Failure path: PASS (evidence)
4. Console + Network: PASS (evidence)
5. Screenshot / what users see: PASS (evidence)
6. Background tasks / leaks: PASS (evidence)
7. State survives restart: PASS (evidence)
Summary: test
Repo class: web-app
Probe depth: standard
EOF
err=$(bash "$HELPER" validate-block "$TMPDIR/missing_end.txt" 2>&1 || true)
bash "$HELPER" validate-block "$TMPDIR/missing_end.txt" 2>/dev/null && { echo "FAIL: missing END should exit 1"; exit 1; } || true
echo "$err" | grep -q "RUNLOG_PROBE_BLOCK_INVALID" || { echo "FAIL: expected RUNLOG_PROBE_BLOCK_INVALID on stderr, got: $err"; exit 1; }
echo "PASS: missing END exits 1 with correct message"

## Assertion 4: missing probe 3 exits 1
echo "--- Assertion 4: missing probe 3 ---"
cat > "$TMPDIR/missing_probe3.txt" <<'EOF'
Production-Probe: BEGIN
1. Boot: PASS (evidence)
2. Golden path: PASS (evidence)
4. Console + Network: PASS (evidence)
5. Screenshot / what users see: PASS (evidence)
6. Background tasks / leaks: PASS (evidence)
7. State survives restart: PASS (evidence)
Summary: test
Repo class: web-app
Probe depth: standard
Production-Probe: END
EOF
bash "$HELPER" validate-block "$TMPDIR/missing_probe3.txt" 2>/dev/null && { echo "FAIL: missing probe 3 should exit 1"; exit 1; } || true
echo "PASS: missing probe 3 exits 1"

## Assertion 5: F1-shape canonical line validates via cmd_validate (backward-compat)
echo "--- Assertion 5: F1-shape backward-compat via cmd_validate ---"
F1_LINE="- 2026-05-22 18:30: SUCCESS — PR #115 merged as 9c4991c. non-dev feature. analysis-v90 / plan-v90 / prompts-v88 / review-v100. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 2 files, +12/-3. Re-inject caveman contract on /compact + auto-compact."
bash "$HELPER" validate "$F1_LINE" || { echo "FAIL: F1-shape line should pass cmd_validate"; exit 1; }
echo "PASS: F1-shape backward-compat"

## Assertion 6: stdin input mode (validate-block -)
echo "--- Assertion 6: stdin input mode ---"
cat "$TMPDIR/good_block.txt" | bash "$HELPER" validate-block - || { echo "FAIL: stdin input mode should work"; exit 1; }
echo "PASS: stdin input mode"

echo "OK: test_format_runlog_validate_block.sh PASS"
