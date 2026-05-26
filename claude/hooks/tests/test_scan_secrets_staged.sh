#!/usr/bin/env bash
# test_scan_secrets_staged.sh — smoke test for scan-secrets-staged.sh.
#
# ACs:
#   1. Clean file passes (exit 0).
#   2. AKIA-key fixture blocks (exit 2).
#   3. PIPELINEKIT_ALLOW_SECRET=1 opt-out passes (exit 0 + stderr notice).
#   4. No staged files passes (exit 0).
#
# Hermetic: each test creates its own mktemp -d git sandbox.
# SKIP path: gitleaks not on PATH -> exit 0 with notice.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../scan-secrets-staged.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "SKIP: gitleaks not on PATH (test cannot execute against live binary)" >&2
  echo "Results: 0 PASS / 0 FAIL (SKIPPED)"
  exit 0
fi

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

# Each test runs in its own sandbox git repo.
mk_sandbox() {
  local dir
  dir=$(mktemp -d "${TMPDIR:-/tmp}/pkit-scan-secrets-XXXXXX")
  (cd "$dir" && git init -q && git config user.email t@e && git config user.name t)
  echo "$dir"
}

# --- AC1: clean file passes ---
SB1=$(mk_sandbox)
(
  cd "$SB1"
  echo "Hello world" > README.md
  git add README.md
  EXIT=0
  bash "$HOOK" >/dev/null 2>&1 || EXIT=$?
  if [ "$EXIT" -eq 0 ]; then
    echo "PASS: AC1_clean_file_passes"
  else
    echo "FAIL: AC1_clean_file_passes -- expected exit 0, got $EXIT"
    exit 1
  fi
)
SUB_EXIT=$?
rm -rf "$SB1"
if [ "$SUB_EXIT" -eq 0 ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); FAILED+=("AC1_clean_file_passes"); fi

# --- AC2: AKIA-key fixture blocks ---
SB2=$(mk_sandbox)
(
  cd "$SB2"
  cat > leaky.txt <<'LEAKY'
# Example config -- DO NOT COMMIT
aws_access_key = "AKIAIOSFODNN7EXAMPLE"
LEAKY
  git add leaky.txt
  EXIT=0
  bash "$HOOK" >/dev/null 2>&1 || EXIT=$?
  if [ "$EXIT" -eq 2 ]; then
    echo "PASS: AC2_aws_key_blocked"
  else
    echo "FAIL: AC2_aws_key_blocked -- expected exit 2, got $EXIT"
    exit 1
  fi
)
SUB_EXIT=$?
rm -rf "$SB2"
if [ "$SUB_EXIT" -eq 0 ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); FAILED+=("AC2_aws_key_blocked"); fi

# --- AC3: opt-out env skips ---
SB3=$(mk_sandbox)
(
  cd "$SB3"
  cat > leaky.txt <<'LEAKY'
aws_access_key = "AKIAIOSFODNN7EXAMPLE"
LEAKY
  git add leaky.txt
  EXIT=0
  OUT=$(PIPELINEKIT_ALLOW_SECRET=1 bash "$HOOK" 2>&1) || EXIT=$?
  if [ "$EXIT" -eq 0 ] && echo "$OUT" | grep -qi "opt-out"; then
    echo "PASS: AC3_opt_out_env_skips"
  else
    echo "FAIL: AC3_opt_out_env_skips -- expected exit 0 + opt-out msg, got exit $EXIT; out=$OUT"
    exit 1
  fi
)
SUB_EXIT=$?
rm -rf "$SB3"
if [ "$SUB_EXIT" -eq 0 ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); FAILED+=("AC3_opt_out_env_skips"); fi

# --- AC4: no staged files passes ---
SB4=$(mk_sandbox)
(
  cd "$SB4"
  EXIT=0
  bash "$HOOK" >/dev/null 2>&1 || EXIT=$?
  if [ "$EXIT" -eq 0 ]; then
    echo "PASS: AC4_no_staged_files_passes"
  else
    echo "FAIL: AC4_no_staged_files_passes -- expected exit 0, got $EXIT"
    exit 1
  fi
)
SUB_EXIT=$?
rm -rf "$SB4"
if [ "$SUB_EXIT" -eq 0 ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); FAILED+=("AC4_no_staged_files_passes"); fi

echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
