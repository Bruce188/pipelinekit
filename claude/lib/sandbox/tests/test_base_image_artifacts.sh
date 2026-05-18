#!/usr/bin/env bash
# Canonical artifact-presence test for the sandbox base image build recipe
# (Containerfile) and its build-script wrapper (build.sh).
#
# Asserts the union of plan-v23 Task 1.1 and Task 1.2 acceptance criteria
# in a single file. Returns non-zero with one FAIL line per missing/invalid
# artifact; exits 0 only when every assertion passes.
#
# No external dependencies — pure bash + coreutils.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
CF="$REPO_ROOT/scripts/sandbox/Containerfile"
BUILD="$REPO_ROOT/scripts/sandbox/build.sh"

fail=0

# -----------------------------------------------------------------------------
# Containerfile assertions (plan-v23 Task 1.1)
# -----------------------------------------------------------------------------

# 1.1 AC1: file exists
if [ -f "$CF" ]; then
  echo "PASS Containerfile present at $CF"
else
  echo "FAIL Containerfile not found at $CF"
  fail=1
fi

if [ -f "$CF" ]; then
  # 1.1 AC2: first non-blank, non-comment line is FROM <allowed slim base>
  first_line=$(grep -vE '^\s*(#|$)' "$CF" | head -n1)
  if echo "$first_line" | grep -qE '^FROM[[:space:]]+(debian:13-slim|ubuntu:24\.04)\b'; then
    echo "PASS Containerfile first non-comment line is FROM <slim base>: $first_line"
  else
    echo "FAIL Containerfile first non-comment line is not a permitted FROM directive: $first_line"
    fail=1
  fi

  # 1.1 AC3: pinned claude-code semver marker
  if grep -q '@anthropic-ai/claude-code@' "$CF"; then
    echo "PASS Containerfile pins @anthropic-ai/claude-code@<version>"
  else
    echo "FAIL Containerfile does not pin @anthropic-ai/claude-code@<version>"
    fail=1
  fi

  # 1.1 AC4: apt cache cleanup
  if grep -q 'rm -rf /var/lib/apt/lists/\*' "$CF"; then
    echo "PASS Containerfile cleans /var/lib/apt/lists/*"
  else
    echo "FAIL Containerfile does not clean /var/lib/apt/lists/*"
    fail=1
  fi
fi

# -----------------------------------------------------------------------------
# build.sh assertions (plan-v23 Task 1.2)
# -----------------------------------------------------------------------------

# 1.2 AC1: presence + executable
if [ -f "$BUILD" ] && [ -x "$BUILD" ]; then
  echo "PASS build.sh present and executable at $BUILD"
else
  echo "FAIL build.sh not found or not executable at $BUILD"
  fail=1
fi

if [ -f "$BUILD" ]; then
  # 1.2 AC2: bash -n syntax check
  if bash -n "$BUILD"; then
    echo "PASS build.sh bash -n syntax check"
  else
    echo "FAIL build.sh failed bash -n"
    fail=1
  fi

  # 1.2 AC3: no standalone `push` keyword in command position.
  # Comment lines are excluded so prose explaining "no push step" doesn't false-positive.
  if grep -nE '^[[:space:]]*[^#]*\bpush\b' "$BUILD" >/dev/null; then
    echo "FAIL build.sh contains a 'push' keyword in command position"
    grep -nE '^[[:space:]]*[^#]*\bpush\b' "$BUILD"
    fail=1
  else
    echo "PASS build.sh has no 'push' keyword in command position"
  fi

  # 1.2 AC4: references PIPELINEKIT_SANDBOX_TAG
  if grep -q 'PIPELINEKIT_SANDBOX_TAG' "$BUILD"; then
    echo "PASS build.sh references PIPELINEKIT_SANDBOX_TAG"
  else
    echo "FAIL build.sh does not reference PIPELINEKIT_SANDBOX_TAG"
    fail=1
  fi

  # 1.2 AC5: references both engines
  if grep -q 'podman' "$BUILD" && grep -q 'docker' "$BUILD"; then
    echo "PASS build.sh references both podman and docker"
  else
    echo "FAIL build.sh does not reference both podman and docker"
    fail=1
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "TEST FAILED"
  exit 1
fi
echo ""
echo "all pass"
