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

# ---------------------------------------------------------------------------
# Runtime injection assertions (AC3, AC4, AC5, AC9, AC10, AC11)
#
# Each branch sources a provider, invokes sandbox_enter with a shell-metachar
# payload as a single argv element, and asserts the side-effect file was NOT
# created. Because all providers use exec-style argv dispatch (exec "$@" for
# worktree-only, "${prefix[@]}" "$@" for podman/docker), the payload is passed
# as a literal string to /bin/echo — the shell never sees it as code.
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROVIDERS_DIR="$SCRIPT_DIR/../providers"

wt_status="SKIP"
podman_status="SKIP"
docker_status="SKIP"

runtime_fail=0

# assert_no_injection_<provider>()
#   Sources the named provider, invokes sandbox_enter with a shell-injection
#   payload, and asserts the side-effect file was NOT created. Returns 0 on
#   PASS/SKIP, non-zero on FAIL. Status is collected by the caller via
#   command substitution of stdout (see § Run the three runtime branches).
assert_no_injection_worktree() {
  local tmpdir
  tmpdir=$(mktemp -d)
  # Cleanup on return — works in both success and failure paths.
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" RETURN

  # Construct payload: when passed as a single argv element to /bin/echo,
  # this string must reach /bin/echo verbatim. If the provider were using
  # sh -c or eval it would re-tokenize and execute the touch command.
  local payload="hello'; touch ${tmpdir}/pwned; echo '"

  # Source the provider in a subshell to avoid leaking sandbox_enter.
  (
    # shellcheck source=/dev/null
    source "${PROVIDERS_DIR}/worktree-only.sh"
    sandbox_enter "$tmpdir" /bin/echo "$payload" >/dev/null
  )
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    echo "FAIL: worktree-only sandbox_enter exited non-zero (rc=$rc)"
    return 1
  fi

  if [ -e "$tmpdir/pwned" ]; then
    echo "FAIL: worktree-only runtime injection — $tmpdir/pwned was created (exec-argv boundary violated)"
    return 1
  fi

  echo "PASS: worktree-only runtime injection asserted (no $tmpdir/pwned)"
  return 0
}

assert_no_injection_podman() {
  # Skip checks
  command -v podman >/dev/null 2>&1 || { echo "SKIP podman not on PATH"; return 0; }

  local image="${SANDBOX_PODMAN_IMAGE:-${PIPELINEKIT_SANDBOX_TAG:-localhost/pipelinekit/sandbox-base:latest}}"
  podman image inspect "$image" >/dev/null 2>&1 || { echo "SKIP no sandbox image ($image)"; return 0; }

  local tmpdir
  tmpdir=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" RETURN

  # Sentinel bind-mount probe: write a 1-byte file from inside the container.
  # If the bind-mount is broken (SELinux relabel, rootless uid mapping, etc.)
  # the touch inside the container would silently fail — which would also
  # cause the payload's touch to silently fail, producing a false PASS.
  # We must probe first and SKIP rather than false-PASS.
  if ! podman run --rm \
       --userns=keep-id \
       --volume "$tmpdir:$tmpdir:rw,Z" \
       --workdir "$tmpdir" \
       "$image" \
       /bin/sh -c "touch ${tmpdir}/sentinel" >/dev/null 2>&1; then
    echo "SKIP podman cannot write to bind mount in this environment"
    return 0
  fi
  if [ ! -e "$tmpdir/sentinel" ]; then
    echo "SKIP podman cannot write to bind mount in this environment"
    return 0
  fi

  local payload="hello'; touch ${tmpdir}/pwned; echo '"

  # Source provider in subshell to avoid leaking sandbox_enter definitions.
  (
    export SANDBOX_PODMAN_IMAGE="$image"
    # shellcheck source=/dev/null
    source "${PROVIDERS_DIR}/podman.sh"
    sandbox_enter "$tmpdir" /bin/echo "$payload" >/dev/null
  )
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    echo "FAIL: podman sandbox_enter exited non-zero (rc=$rc)"
    return 1
  fi

  if [ -e "$tmpdir/pwned" ]; then
    echo "FAIL: podman runtime injection — $tmpdir/pwned was created (exec-argv boundary violated)"
    return 1
  fi

  echo "PASS: podman runtime injection asserted (no $tmpdir/pwned)"
  return 0
}

assert_no_injection_docker() {
  # Skip checks
  command -v docker >/dev/null 2>&1 || { echo "SKIP docker not on PATH"; return 0; }

  local image="${SANDBOX_DOCKER_IMAGE:-${PIPELINEKIT_SANDBOX_TAG:-localhost/pipelinekit/sandbox-base:latest}}"
  docker image inspect "$image" >/dev/null 2>&1 || { echo "SKIP no sandbox image ($image)"; return 0; }

  local tmpdir
  tmpdir=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" RETURN

  # Sentinel bind-mount probe — same logic as podman branch.
  if ! docker run --rm \
       --volume "$tmpdir:$tmpdir:rw" \
       --workdir "$tmpdir" \
       "$image" \
       /bin/sh -c "touch ${tmpdir}/sentinel" >/dev/null 2>&1; then
    echo "SKIP docker cannot write to bind mount in this environment"
    return 0
  fi
  if [ ! -e "$tmpdir/sentinel" ]; then
    echo "SKIP docker cannot write to bind mount in this environment"
    return 0
  fi

  local payload="hello'; touch ${tmpdir}/pwned; echo '"

  (
    export SANDBOX_DOCKER_IMAGE="$image"
    # shellcheck source=/dev/null
    source "${PROVIDERS_DIR}/docker.sh"
    sandbox_enter "$tmpdir" /bin/echo "$payload" >/dev/null
  )
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    echo "FAIL: docker sandbox_enter exited non-zero (rc=$rc)"
    return 1
  fi

  if [ -e "$tmpdir/pwned" ]; then
    echo "FAIL: docker runtime injection — $tmpdir/pwned was created (exec-argv boundary violated)"
    return 1
  fi

  echo "PASS: docker runtime injection asserted (no $tmpdir/pwned)"
  return 0
}

# ---------------------------------------------------------------------------
# Run the three runtime branches and collect statuses.
# ---------------------------------------------------------------------------

_wt_out=$(assert_no_injection_worktree 2>&1)
echo "$_wt_out"
if echo "$_wt_out" | grep -q "^PASS:"; then
  wt_status="PASS"
elif echo "$_wt_out" | grep -q "^SKIP"; then
  wt_status="SKIP"
else
  wt_status="FAIL"
  runtime_fail=1
fi

_podman_out=$(assert_no_injection_podman 2>&1)
echo "$_podman_out"
if echo "$_podman_out" | grep -q "^PASS:"; then
  podman_status="PASS"
elif echo "$_podman_out" | grep -q "^SKIP"; then
  podman_status="SKIP"
else
  podman_status="FAIL"
  runtime_fail=1
fi

_docker_out=$(assert_no_injection_docker 2>&1)
echo "$_docker_out"
if echo "$_docker_out" | grep -q "^PASS:"; then
  docker_status="PASS"
elif echo "$_docker_out" | grep -q "^SKIP"; then
  docker_status="SKIP"
else
  docker_status="FAIL"
  runtime_fail=1
fi

echo ""
echo "runtime: worktree=$wt_status, podman=$podman_status, docker=$docker_status"

if [ "$wt_status" = "SKIP" ] && [ "$podman_status" = "SKIP" ] && [ "$docker_status" = "SKIP" ]; then
  echo "WARNING: all three runtime branches SKIPped — runtime injection assertion was not actually exercised" >&2
fi

if [ "$runtime_fail" -ne 0 ]; then
  echo ""
  echo "RUNTIME INJECTION TEST FAILED"
  exit 1
fi
