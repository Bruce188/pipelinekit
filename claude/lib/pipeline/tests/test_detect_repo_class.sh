#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=$(git rev-parse --show-toplevel)
HELPER="$REPO_ROOT/claude/lib/pipeline/detect_repo_class.sh"

run_scenario() {
  local desc="$1"
  local result="$2"
  local expected="$3"
  if [[ "$result" == "$expected" ]]; then
    echo "PASS: $desc"
  else
    echo "FAIL: $desc — expected '$expected', got '$result'"
    exit 1
  fi
}

# ============================================================================
# Scenario 1: workflow-toolkit detection (scripts/install.sh + claude/hooks/tests/)
# ============================================================================
echo "--- Scenario 1: workflow-toolkit ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  mkdir -p "$sandbox/scripts" "$sandbox/claude/hooks/tests"
  touch "$sandbox/scripts/install.sh" "$sandbox/claude/hooks/tests/test_x.sh"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "workflow-toolkit detection" "$result" "workflow-toolkit"
)

# ============================================================================
# Scenario 2: service detection via *.sln
# ============================================================================
echo "--- Scenario 2: service (*.sln) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/MyApp.sln"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "service via *.sln" "$result" "service"
)

# ============================================================================
# Scenario 3: service detection via package.json with "start" script
# ============================================================================
echo "--- Scenario 3: service (package.json start) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  printf '{"scripts":{"start":"node index.js"}}\n' > "$sandbox/package.json"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "service via package.json start" "$result" "service"
)

# ============================================================================
# Scenario 4: web-app detection via pom.xml
# ============================================================================
echo "--- Scenario 4: web-app (pom.xml) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/pom.xml"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "web-app via pom.xml" "$result" "web-app"
)

# ============================================================================
# Scenario 5: web-app detection via package.json with "dev" script
# ============================================================================
echo "--- Scenario 5: web-app (package.json dev) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  printf '{"scripts":{"dev":"vite --port 3000"}}\n' > "$sandbox/package.json"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "web-app via package.json dev" "$result" "web-app"
)

# ============================================================================
# Scenario 6: web-app detection via pyproject.toml with fastapi
# ============================================================================
echo "--- Scenario 6: web-app (pyproject.toml fastapi) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  printf '[project]\nname = "myapp"\n\n[tool.poetry.dependencies]\nfastapi = "^0.100.0"\n' > "$sandbox/pyproject.toml"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "web-app via pyproject.toml fastapi" "$result" "web-app"
)

# ============================================================================
# Scenario 7: library fallback (source dir only, no markers)
# ============================================================================
echo "--- Scenario 7: library fallback ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  mkdir -p "$sandbox/src"
  touch "$sandbox/src/lib.py"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "library fallback" "$result" "library"
)

# ============================================================================
# Scenario 8: workflow-toolkit precedence over web-app conflict (R1 binding)
# ============================================================================
echo "--- Scenario 8: workflow-toolkit precedence over web-app ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  mkdir -p "$sandbox/scripts" "$sandbox/claude/hooks/tests"
  touch "$sandbox/scripts/install.sh" "$sandbox/claude/hooks/tests/test_x.sh"
  printf '{"scripts":{"dev":"vite --port 3000"}}\n' > "$sandbox/package.json"
  result=$(cd "$sandbox" && bash "$HELPER" --repo-class)
  run_scenario "workflow-toolkit precedence over web-app (R1)" "$result" "workflow-toolkit"
)

# ============================================================================
# Scenario 9: --probe-depth with no docs/charter.md -> standard + stderr CHARTER_PROBE_DEPTH_DEFAULTED
# ============================================================================
echo "--- Scenario 9: probe-depth no charter ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  depth_out=$(cd "$sandbox" && bash "$HELPER" --probe-depth 2>/dev/null)
  depth_err=$(cd "$sandbox" && bash "$HELPER" --probe-depth 2>&1 1>/dev/null || true)
  run_scenario "probe-depth no charter -> standard stdout" "$depth_out" "standard"
  if echo "$depth_err" | grep -q "CHARTER_PROBE_DEPTH_DEFAULTED: standard (no charter"; then
    echo "PASS: probe-depth no charter -> CHARTER_PROBE_DEPTH_DEFAULTED on stderr"
  else
    echo "FAIL: probe-depth no charter -> expected CHARTER_PROBE_DEPTH_DEFAULTED on stderr, got: $depth_err"
    exit 1
  fi
)

# ============================================================================
# Scenario 10: --probe-depth with charter.md lacking the H2 section -> standard + legacy stderr
# ============================================================================
echo "--- Scenario 10: probe-depth legacy charter (no H2) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  mkdir -p "$sandbox/docs"
  printf '# Charter\n\n## Overview\nSome content here.\n\n## AI Layer\nSome AI notes.\n' > "$sandbox/docs/charter.md"
  depth_out=$(cd "$sandbox" && bash "$HELPER" --probe-depth 2>/dev/null)
  depth_err=$(cd "$sandbox" && bash "$HELPER" --probe-depth 2>&1 1>/dev/null || true)
  run_scenario "probe-depth legacy charter -> standard stdout" "$depth_out" "standard"
  if echo "$depth_err" | grep -q "CHARTER_PROBE_DEPTH_DEFAULTED: standard (legacy charter)"; then
    echo "PASS: probe-depth legacy charter -> CHARTER_PROBE_DEPTH_DEFAULTED: standard (legacy charter) on stderr"
  else
    echo "FAIL: probe-depth legacy charter -> expected 'CHARTER_PROBE_DEPTH_DEFAULTED: standard (legacy charter)' on stderr, got: $depth_err"
    exit 1
  fi
)

# ============================================================================
# Scenario 11: --probe-depth with charter.md § "## Production-readiness probe depth\n\nparanoid" -> paranoid
# ============================================================================
echo "--- Scenario 11: probe-depth charter paranoid ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  mkdir -p "$sandbox/docs"
  printf '# Charter\n\n## Review style\nteams\n\n## Production-readiness probe depth\nparanoid\n\n## AI Layer\nnotes\n' > "$sandbox/docs/charter.md"
  depth_out=$(cd "$sandbox" && bash "$HELPER" --probe-depth 2>/dev/null)
  depth_err=$(cd "$sandbox" && bash "$HELPER" --probe-depth 2>&1 1>/dev/null || true)
  run_scenario "probe-depth charter paranoid" "$depth_out" "paranoid"
  if [[ -z "$depth_err" ]] || ! echo "$depth_err" | grep -q "CHARTER_PROBE_DEPTH_DEFAULTED"; then
    echo "PASS: probe-depth charter paranoid -> no CHARTER_PROBE_DEPTH_DEFAULTED on stderr"
  else
    echo "FAIL: probe-depth charter paranoid -> unexpected CHARTER_PROBE_DEPTH_DEFAULTED on stderr: $depth_err"
    exit 1
  fi
)

# ============================================================================
# Scenario 12: --selftest exits 0 (from actual repo root which is workflow-toolkit)
# ============================================================================
echo "--- Scenario 12: --selftest from repo root ---"
(
  cd "$REPO_ROOT"
  bash "$HELPER" --selftest
  echo "PASS: --selftest exits 0"
)

echo "OK: test_detect_repo_class.sh — 12/12 scenarios PASS"
