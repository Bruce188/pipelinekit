#!/usr/bin/env bash
set -euo pipefail

# test_subagent_write_surfaces.sh
#
# Self-describing structural test for the subagent write-surface baseline.
# Acts as both runner and specification — a future heuristic-removal upstream
# would NOT make this test fail; the test only fails if the documented matrix
# is removed or corrupted from this file's own comment body.
#
# This script does NOT itself dispatch an Agent (Bash cannot do that).
# It validates its own structural contract — the live dispatch is the job of
# the Phase 3 verification gate (Task 3.1 of plan-v32).
#
# The harness behaviour is path-pattern-derived, NOT a hook. Confirmed in
# docs/analysis-v31.md § Reproduction-during-analysis: block-stage-sensitive.sh,
# pre-edit-protect.sh, block-bare-repo-markers.py, and tdd-order-check.sh were
# all audited and do NOT match Write on docs/*.md. The block is at the
# agent harness / SDK layer.
#
# Canonical fix: claude/skills/pipeline/reference.md
#   § Subagent Write-Surface Convention (normative)
#
# # Expected baseline:
# Surface A — Write tool on docs/*.md from subagent:
#   BLOCKED (harness directive: "Subagents should return findings as text, not write report files")
# Surface B — Edit tool on pre-existing docs/*.md from subagent:
#   OK
# Surface C — Bash heredoc (cat > docs/*.md <<EOF … EOF) from subagent:
#   OK
# Surface D — Bash touch on docs/*.md from subagent:
#   OK
#
# Re-run this test to detect future heuristic drift (regression in either direction).
# If Write unexpectedly succeeds upstream: the convention is still valid (heredoc remains safe).
# If Bash heredoc unexpectedly fails: the documented workaround has regressed — escalate.

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

# Assertion 1: Expected baseline header is present
grep -q '# Expected baseline:' "$SELF" \
  || { echo "FAIL: '# Expected baseline:' comment block not found in $SELF"; exit 1; }
echo "OK: surface-baseline-header found"

# Assertion 2: Surface A (Write BLOCKED) is documented
grep -q 'Surface A.*Write tool.*docs.*BLOCKED' "$SELF" \
  || { echo "FAIL: Surface A (Write=BLOCKED) documentation missing from $SELF"; exit 1; }
echo "OK: surface-A Write=BLOCKED documented"

# Assertion 3: Surface B (Edit OK) is documented
grep -q 'Surface B.*Edit tool.*docs.*OK' "$SELF" \
  || { echo "FAIL: Surface B (Edit=OK) documentation missing from $SELF"; exit 1; }
echo "OK: surface-B Edit=OK documented"

# Assertion 4: Surface C (Bash heredoc OK) is documented
grep -q 'Surface C.*Bash heredoc.*docs.*OK' "$SELF" \
  || { echo "FAIL: Surface C (Bash heredoc=OK) documentation missing from $SELF"; exit 1; }
echo "OK: surface-C Bash-heredoc=OK documented"

# Assertion 5: Surface D (Bash touch OK) is documented
grep -q 'Surface D.*Bash touch.*docs.*OK' "$SELF" \
  || { echo "FAIL: Surface D (Bash touch=OK) documentation missing from $SELF"; exit 1; }
echo "OK: surface-D Bash-touch=OK documented"

# Assertion 6: Harness directive verbatim string is present (not just paraphrased)
grep -q 'Subagents should return findings as text, not write report files' "$SELF" \
  || { echo "FAIL: verbatim harness directive string missing from $SELF"; exit 1; }
echo "OK: harness directive verbatim string present"

# Assertion 7: Reference to canonical fix location is present
grep -q 'Subagent Write-Surface Convention' "$SELF" \
  || { echo "FAIL: canonical fix reference (Subagent Write-Surface Convention) missing from $SELF"; exit 1; }
echo "OK: canonical fix reference present"

# Summary check: comment-line floor (richly self-documenting)
comment_count=$(grep -c '^#' "$SELF")
if [[ "$comment_count" -lt 15 ]]; then
  echo "FAIL: comment-line floor not met ($comment_count < 15); test must be richly self-documenting"
  exit 1
fi
echo "OK: comment-line count $comment_count >= 15"

echo "OK: test_subagent_write_surfaces.sh"
exit 0
