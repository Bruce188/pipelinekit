#!/usr/bin/env bash
# Verify sandbox providers use exec-style argv, not `sh -c "$str"`.
#
# `sh -c "$scrubbed"` re-tokenizes the command, losing argv boundaries and
# exposing a shell-injection surface if a caller passes AI-generated text
# with shell metachars. After F3 hardening, providers must invoke the
# command as a proper argv ("${prefix[@]}" + "$@"), never via `sh -c`.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PODMAN="$REPO_ROOT/claude/lib/sandbox/providers/podman.sh"
DOCKER="$REPO_ROOT/claude/lib/sandbox/providers/docker.sh"

fail=0

# AC1: podman.sh must not use `sh -c` for command dispatch.
# Strip comment lines first so prose explaining *why* `sh -c` is avoided
# doesn't trigger a false-positive. Use a word-boundary regex on the
# remaining code so chained forms (`&& sh -c`, `\\\n  sh -c`) are caught,
# not just `sh -c` at line start.
if grep -vE '^\s*#' "$PODMAN" | grep -qE '\bsh -c\b'; then
  echo "FAIL podman.sh still uses 'sh -c' for command dispatch"
  fail=1
else
  echo "PASS podman.sh has no 'sh -c' command dispatch"
fi

# AC2: docker.sh must not use `sh -c` for command dispatch
if grep -vE '^\s*#' "$DOCKER" | grep -qE '\bsh -c\b'; then
  echo "FAIL docker.sh still uses 'sh -c' for command dispatch"
  fail=1
else
  echo "PASS docker.sh has no 'sh -c' command dispatch"
fi

# AC3: podman.sh references --prefix-args (the new argv API)
if grep -q -- "--prefix-args" "$PODMAN"; then
  echo "PASS podman.sh uses env-scrub --prefix-args"
else
  echo "FAIL podman.sh does not invoke env-scrub --prefix-args"
  fail=1
fi

# AC4: docker.sh references --prefix-args
if grep -q -- "--prefix-args" "$DOCKER"; then
  echo "PASS docker.sh uses env-scrub --prefix-args"
else
  echo "FAIL docker.sh does not invoke env-scrub --prefix-args"
  fail=1
fi

# AC5: bash syntax check on both providers (sourceability)
if bash -n "$PODMAN"; then
  echo "PASS podman.sh bash -n syntax check"
else
  echo "FAIL podman.sh failed bash -n"
  fail=1
fi
if bash -n "$DOCKER"; then
  echo "PASS docker.sh bash -n syntax check"
else
  echo "FAIL docker.sh failed bash -n"
  fail=1
fi

# AC6: fail-closed when env-scrub.py is missing/broken
# Both providers must check the producer exit status and the first token of
# its output. mapfile-only consumption would silently dispatch with an empty
# prefix, running the container env-bare — a silent regression of the entire
# scrub contract.
for f in "$PODMAN" "$DOCKER"; do
  name=$(basename "$f")
  if grep -q "prefix_rc" "$f" && grep -q 'prefix\[0\].*!=.*"env"' "$f"; then
    echo "PASS $name fail-closes on env-scrub.py error"
  else
    echo "FAIL $name does not check env-scrub.py exit status / first token"
    fail=1
  fi
done

if [ $fail -ne 0 ]; then
  echo ""
  echo "TEST FAILED"
  exit 1
fi
echo ""
echo "all pass"
