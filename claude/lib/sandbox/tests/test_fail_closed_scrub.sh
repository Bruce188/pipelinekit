#!/usr/bin/env bash
# Behavioral test: providers must refuse to launch the container when
# env-scrub.py fails or returns unexpected output. The previous code path
# silently used mapfile < <(...), which drops the producer exit status —
# a broken env-scrub.py would have caused the container to launch with all
# secrets intact.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PODMAN="$REPO_ROOT/claude/lib/sandbox/providers/podman.sh"
DOCKER="$REPO_ROOT/claude/lib/sandbox/providers/docker.sh"

fail=0
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

# Build a fake CLAUDE_HOME with a broken env-scrub.py
mkdir -p "$tmpdir/claude_home/hooks"
cat >"$tmpdir/claude_home/hooks/env-scrub.py" <<'EOF'
#!/usr/bin/env python3
import sys
sys.stderr.write("intentional failure for fail-closed test\n")
sys.exit(7)
EOF
chmod +x "$tmpdir/claude_home/hooks/env-scrub.py"

# Build a stub `podman`/`docker` on PATH that just exits 0 (success) so the
# test detects fail-closed BEFORE the container engine would even be called.
# If sandbox_enter dispatches the engine, we'll see rc=0; if it fail-closes,
# we should see rc != 0.
mkdir -p "$tmpdir/stub_bin"
for engine in podman docker; do
  cat >"$tmpdir/stub_bin/$engine" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$tmpdir/stub_bin/$engine"
done

mkdir -p "$tmpdir/wt"

run_provider_test() {
  local provider_path="$1" engine="$2" expected_rc_min="$3"
  local rc
  set +e
  ( CLAUDE_HOME="$tmpdir/claude_home" \
    PATH="$tmpdir/stub_bin:$PATH" \
    bash -c "source '$provider_path' && sandbox_enter '$tmpdir/wt' true" \
    >/dev/null 2>&1 )
  rc=$?
  set -e
  if [ "$rc" -ge "$expected_rc_min" ]; then
    echo "PASS $(basename "$provider_path") fail-closed (rc=$rc) when env-scrub.py exits non-zero"
  else
    echo "FAIL $(basename "$provider_path") did NOT fail-closed: rc=$rc (expected >= $expected_rc_min)"
    fail=1
  fi
}

run_provider_test "$PODMAN" podman 1
run_provider_test "$DOCKER" docker 1

# Second scenario: env-scrub.py exits 0 but emits unexpected first token.
cat >"$tmpdir/claude_home/hooks/env-scrub.py" <<'EOF'
#!/usr/bin/env python3
print("not-env")
EOF
chmod +x "$tmpdir/claude_home/hooks/env-scrub.py"

run_provider_test "$PODMAN" podman 1
run_provider_test "$DOCKER" docker 1

if [ $fail -ne 0 ]; then
  echo ""
  echo "TEST FAILED"
  exit 1
fi
echo ""
echo "all pass"
