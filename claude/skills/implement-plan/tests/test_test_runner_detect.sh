#!/usr/bin/env bash
# Smoke test for claude.lib.pipeline.test_runner_detect.detect_test_runner.
#
# Covers the four documented positive cases (pytest via pyproject.toml,
# pytest via setup.py, npm test, go test, make test), the two
# fall-through negatives (package.json with empty scripts.test,
# Makefile with only a pretest: target and no test: target), the empty
# directory negative, AND the first-match-wins ordering assertion
# (pyproject.toml + go.mod + Makefile all present should resolve to
# pytest because it is the highest-priority probe).
#
# Each case runs in an isolated mktemp -d directory with trap-based
# cleanup. The helper is invoked via a python3 -c one-liner so the test
# does not depend on pytest being installed locally.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
FAIL=0

run_case() {
  local label="$1" expected="$2" tmp="$3"
  local actual
  actual=$(python3 -c "
import sys
sys.path.insert(0, '$REPO')
from claude.lib.pipeline.test_runner_detect import detect_test_runner
result = detect_test_runner('$tmp')
print(result if result is not None else 'None')
")
  if [ "$actual" = "$expected" ]; then
    echo "PASS  $label  ->  $actual"
  else
    echo "FAIL  $label  expected '$expected'  got '$actual'" >&2
    FAIL=1
  fi
}

# ---------------------------------------------------------------------------
# Case 1 — pyproject.toml -> pytest
# ---------------------------------------------------------------------------
TMP1=$(mktemp -d)
trap 'rm -rf "$TMP1"' EXIT
touch "$TMP1/pyproject.toml"
run_case "pyproject.toml -> pytest" "pytest" "$TMP1"

# ---------------------------------------------------------------------------
# Case 2 — setup.py -> pytest
# ---------------------------------------------------------------------------
TMP2=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2"' EXIT
touch "$TMP2/setup.py"
run_case "setup.py -> pytest" "pytest" "$TMP2"

# ---------------------------------------------------------------------------
# Case 3 — package.json with scripts.test=jest -> npm test
# ---------------------------------------------------------------------------
TMP3=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3"' EXIT
cat > "$TMP3/package.json" <<'EOF'
{"name":"x","scripts":{"test":"jest"}}
EOF
run_case "package.json scripts.test=jest -> npm test" "npm test" "$TMP3"

# ---------------------------------------------------------------------------
# Case 4 — package.json with empty scripts -> None (negative)
# ---------------------------------------------------------------------------
TMP4=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4"' EXIT
cat > "$TMP4/package.json" <<'EOF'
{"name":"x","scripts":{}}
EOF
run_case "package.json empty scripts -> None" "None" "$TMP4"

# ---------------------------------------------------------------------------
# Case 5 — go.mod -> go test ./...
# ---------------------------------------------------------------------------
TMP5=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4" "$TMP5"' EXIT
touch "$TMP5/go.mod"
run_case "go.mod -> go test ./..." "go test ./..." "$TMP5"

# ---------------------------------------------------------------------------
# Case 6 — Makefile with test: target -> make test
# ---------------------------------------------------------------------------
TMP6=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4" "$TMP5" "$TMP6"' EXIT
cat > "$TMP6/Makefile" <<'EOF'
.PHONY: test
test:
	echo running tests
EOF
run_case "Makefile with test: target -> make test" "make test" "$TMP6"

# ---------------------------------------------------------------------------
# Case 7 — Makefile with only pretest: target -> None (no test: target)
# ---------------------------------------------------------------------------
TMP7=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4" "$TMP5" "$TMP6" "$TMP7"' EXIT
cat > "$TMP7/Makefile" <<'EOF'
.PHONY: pretest
pretest:
	echo pre
# test: this is a comment, not a target
EOF
run_case "Makefile pretest:-only -> None" "None" "$TMP7"

# ---------------------------------------------------------------------------
# Case 8 — empty directory -> None
# ---------------------------------------------------------------------------
TMP8=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4" "$TMP5" "$TMP6" "$TMP7" "$TMP8"' EXIT
run_case "empty dir -> None" "None" "$TMP8"

# ---------------------------------------------------------------------------
# Case 9 — first-match-wins: pyproject.toml + go.mod + Makefile -> pytest
# ---------------------------------------------------------------------------
TMP9=$(mktemp -d)
trap 'rm -rf "$TMP1" "$TMP2" "$TMP3" "$TMP4" "$TMP5" "$TMP6" "$TMP7" "$TMP8" "$TMP9"' EXIT
touch "$TMP9/pyproject.toml"
touch "$TMP9/go.mod"
cat > "$TMP9/Makefile" <<'EOF'
test:
	echo running tests
EOF
run_case "first-match-wins: pyproject+go+make -> pytest" "pytest" "$TMP9"

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "FAIL: at least one case did not match expected output." >&2
  exit 1
fi

echo ""
echo "All 9 cases passed."
