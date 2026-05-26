#!/usr/bin/env bash
# claude/lib/sandbox/tests/test_provider_auto_resolution.sh
#
# Verifies SandboxProvider.sh `provider_detect` auto-resolution behaviour.
# Default flipped from worktree-only to auto. The auto path probes
# podman → docker → worktree-only fallback, with a one-line stderr log on
# fallback. Explicit overrides and PIPELINE_NO_SANDBOX=1 must still win.
#
# F12 acceptance criteria (plan-v126.md):
#   AC1: unset SANDBOX_PROVIDER, podman on PATH                → "podman", no stderr
#   AC2: unset SANDBOX_PROVIDER, docker on PATH (no podman)    → "docker", no stderr
#   AC3: unset SANDBOX_PROVIDER, neither on PATH               → "worktree-only", stderr fallback line
#   AC4: SANDBOX_PROVIDER=worktree-only, podman on PATH        → "worktree-only" (override wins)
#   AC5: PIPELINE_NO_SANDBOX=1                                 → "worktree-only", short-circuit
#
# Technique: PATH shadowing — prepend a stub directory to a curated minimal
# PATH (system /usr/bin:/bin) and gate engine visibility by which stubs exist.
# We also explicitly probe `command -v` against ONLY the stub dirs we control
# by replacing PATH with the stub dir alone for the `command -v` resolution,
# while keeping `bash` discoverable via its absolute path.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PROVIDER_LIB="$REPO_ROOT/claude/lib/sandbox/SandboxProvider.sh"
BASH_BIN="$(command -v bash)"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

fail=0

pass_msg() { echo "PASS $1"; }
fail_msg() { echo "FAIL $1: $2" >&2; fail=1; }

# Build stub directories. Each stub is an executable shell script that
# returns immediately — `command -v` only needs the file to be executable.
podman_dir="$tmpdir/podman-only"
docker_dir="$tmpdir/docker-only"
none_dir="$tmpdir/none"

mkdir -p "$podman_dir" "$docker_dir" "$none_dir"

cat >"$podman_dir/podman" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$podman_dir/podman"

cat >"$docker_dir/docker" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$docker_dir/docker"

# Run provider_detect inside a sub-bash with a curated PATH.
# - PATH = "<stub_dir>" (no system dirs) — guarantees `command -v podman`
#   resolves against the stub when present, and resolves NOWHERE when absent.
# - bash itself invoked via absolute path so system bash is reachable
#   without leaking system PATH to `command -v`.
# - Inside the sub-bash, sourcing SandboxProvider.sh uses only shell builtins
#   (no external commands besides `command`), so a minimal PATH suffices.

run_case() {
  local stub_path="$1"
  local sandbox_provider_env="$2"   # value to export, or "<unset>" to unset
  local pipeline_no_sandbox_env="$3" # value to export, or "<unset>" to unset
  local stderr_file="$4"

  local exports=""
  if [ "$sandbox_provider_env" = "<unset>" ]; then
    exports="unset SANDBOX_PROVIDER;"
  else
    exports="export SANDBOX_PROVIDER='$sandbox_provider_env';"
  fi
  if [ "$pipeline_no_sandbox_env" = "<unset>" ]; then
    exports="$exports unset PIPELINE_NO_SANDBOX;"
  else
    exports="$exports export PIPELINE_NO_SANDBOX='$pipeline_no_sandbox_env';"
  fi

  PATH="$stub_path" "$BASH_BIN" -c "
    $exports
    source '$PROVIDER_LIB'
    provider_detect
  " 2>"$stderr_file"
}

# ---------------------------------------------------------------------------
# AC1: unset SANDBOX_PROVIDER, podman on PATH → podman, no stderr
# ---------------------------------------------------------------------------
stderr_file="$tmpdir/ac1.err"
out=$(run_case "$podman_dir" "<unset>" "<unset>" "$stderr_file")
err=$(cat "$stderr_file")
if [ "$out" = "podman" ] && [ -z "$err" ]; then
  pass_msg "AC1 auto + podman-on-PATH → podman, no stderr"
else
  fail_msg "AC1" "stdout='$out' stderr='$err' (want stdout=podman, stderr empty)"
fi

# ---------------------------------------------------------------------------
# AC2: unset SANDBOX_PROVIDER, docker on PATH (no podman) → docker, no stderr
# ---------------------------------------------------------------------------
stderr_file="$tmpdir/ac2.err"
out=$(run_case "$docker_dir" "<unset>" "<unset>" "$stderr_file")
err=$(cat "$stderr_file")
if [ "$out" = "docker" ] && [ -z "$err" ]; then
  pass_msg "AC2 auto + docker-only-on-PATH → docker, no stderr"
else
  fail_msg "AC2" "stdout='$out' stderr='$err' (want stdout=docker, stderr empty)"
fi

# ---------------------------------------------------------------------------
# AC3: unset SANDBOX_PROVIDER, neither on PATH → worktree-only + stderr log
# ---------------------------------------------------------------------------
stderr_file="$tmpdir/ac3.err"
out=$(run_case "$none_dir" "<unset>" "<unset>" "$stderr_file")
err=$(cat "$stderr_file")
expected_msg="sandbox: container runtime not found — using worktree-only fallback"
if [ "$out" = "worktree-only" ] && [ "$err" = "$expected_msg" ]; then
  pass_msg "AC3 auto + neither-on-PATH → worktree-only + stderr fallback line"
else
  fail_msg "AC3" "stdout='$out' stderr='$err' (want stdout=worktree-only, stderr='$expected_msg')"
fi

# ---------------------------------------------------------------------------
# AC4: SANDBOX_PROVIDER=worktree-only override wins over podman-on-PATH
# ---------------------------------------------------------------------------
stderr_file="$tmpdir/ac4.err"
out=$(run_case "$podman_dir" "worktree-only" "<unset>" "$stderr_file")
err=$(cat "$stderr_file")
if [ "$out" = "worktree-only" ] && [ -z "$err" ]; then
  pass_msg "AC4 explicit worktree-only override wins"
else
  fail_msg "AC4" "stdout='$out' stderr='$err' (want stdout=worktree-only, stderr empty)"
fi

# ---------------------------------------------------------------------------
# AC5: PIPELINE_NO_SANDBOX=1 short-circuit unaffected even with engine on PATH
# ---------------------------------------------------------------------------
stderr_file="$tmpdir/ac5.err"
out=$(run_case "$podman_dir" "podman" "1" "$stderr_file")
err=$(cat "$stderr_file")
if [ "$out" = "worktree-only" ] && [ -z "$err" ]; then
  pass_msg "AC5 PIPELINE_NO_SANDBOX=1 short-circuit unchanged"
else
  fail_msg "AC5" "stdout='$out' stderr='$err' (want stdout=worktree-only, stderr empty)"
fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "TEST FAILED"
  exit 1
fi
echo ""
echo "all pass"
