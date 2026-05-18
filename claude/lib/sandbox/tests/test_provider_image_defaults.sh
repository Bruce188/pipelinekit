#!/usr/bin/env bash
# Verifies the podman and docker sandbox providers default to the namespaced
# pipelinekit/sandbox-base image tag and route their fallback through
# PIPELINEKIT_SANDBOX_TAG.
#
# Plan-v23 Tasks 1.4 / 1.5 / 1.6:
#   1. grep -c 'pipelinekit/sandbox-base:' on each provider == 1
#   2. grep -c 'pipelinekit-sandbox:latest' on each provider == 0
#   3. Both providers reference PIPELINEKIT_SANDBOX_TAG.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PODMAN="$REPO_ROOT/claude/lib/sandbox/providers/podman.sh"
DOCKER="$REPO_ROOT/claude/lib/sandbox/providers/docker.sh"

fail=0

# AC1: exactly one reference to pipelinekit/sandbox-base: in each provider.
for f in "$PODMAN" "$DOCKER"; do
  name=$(basename "$f")
  count=$(grep -c 'pipelinekit/sandbox-base:' "$f" || true)
  if [ "$count" = "1" ]; then
    echo "PASS $name has exactly 1 reference to pipelinekit/sandbox-base:"
  else
    echo "FAIL $name has $count references to pipelinekit/sandbox-base: (want 1)"
    fail=1
  fi
done

# AC2: zero references to the legacy pipelinekit-sandbox:latest string.
for f in "$PODMAN" "$DOCKER"; do
  name=$(basename "$f")
  count=$(grep -c 'pipelinekit-sandbox:latest' "$f" || true)
  if [ "$count" = "0" ]; then
    echo "PASS $name has no legacy pipelinekit-sandbox:latest reference"
  else
    echo "FAIL $name still references legacy pipelinekit-sandbox:latest ($count occurrence(s))"
    fail=1
  fi
done

# AC3: both files reference PIPELINEKIT_SANDBOX_TAG.
for f in "$PODMAN" "$DOCKER"; do
  name=$(basename "$f")
  if grep -q 'PIPELINEKIT_SANDBOX_TAG' "$f"; then
    echo "PASS $name references PIPELINEKIT_SANDBOX_TAG"
  else
    echo "FAIL $name does not reference PIPELINEKIT_SANDBOX_TAG"
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "TEST FAILED"
  exit 1
fi
echo ""
echo "all pass"
