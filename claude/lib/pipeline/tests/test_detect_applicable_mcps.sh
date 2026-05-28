#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=$(git rev-parse --show-toplevel)
HELPER="$REPO_ROOT/claude/lib/pipeline/detect_applicable_mcps.sh"

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
# Scenario 1: --applicable in python sandbox → includes serena + 3 always-on
# ============================================================================
echo "--- Scenario 1: --applicable in python sandbox ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/app.py"
  out=$(cd "$sandbox" && bash "$HELPER" --applicable)
  if echo "$out" | grep -q "serena" \
      && echo "$out" | grep -q "context7" \
      && echo "$out" | grep -q "agentmemory" \
      && echo "$out" | grep -q "sequential-thinking"; then
    echo "PASS: --applicable in python sandbox includes serena + 3 always-on"
  else
    echo "FAIL: --applicable in python sandbox — got: $out"
    exit 1
  fi
)

# ============================================================================
# Scenario 2: --applicable in docs-only sandbox → serena ABSENT, 3 always-on present
# ============================================================================
echo "--- Scenario 2: --applicable in docs-only sandbox (no source) ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/README.md" "$sandbox/notes.txt"
  out=$(cd "$sandbox" && bash "$HELPER" --applicable)
  if ! echo "$out" | grep -q "serena" \
      && echo "$out" | grep -q "context7" \
      && echo "$out" | grep -q "agentmemory" \
      && echo "$out" | grep -q "sequential-thinking"; then
    echo "PASS: --applicable in docs-only sandbox: serena absent, 3 always-on present"
  else
    echo "FAIL: --applicable in docs-only sandbox — got: $out"
    exit 1
  fi
)

# ============================================================================
# Scenario 3a: --applicable in typescript sandbox → serena present
# ============================================================================
echo "--- Scenario 3a: --applicable in typescript sandbox ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/index.ts"
  out=$(cd "$sandbox" && bash "$HELPER" --applicable)
  if echo "$out" | grep -q "serena"; then
    echo "PASS: --applicable in .ts sandbox includes serena"
  else
    echo "FAIL: --applicable in .ts sandbox — got: $out"
    exit 1
  fi
)

# ============================================================================
# Scenario 3b: --applicable in go sandbox → serena present
# ============================================================================
echo "--- Scenario 3b: --applicable in go sandbox ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/main.go"
  out=$(cd "$sandbox" && bash "$HELPER" --applicable)
  if echo "$out" | grep -q "serena"; then
    echo "PASS: --applicable in .go sandbox includes serena"
  else
    echo "FAIL: --applicable in .go sandbox — got: $out"
    exit 1
  fi
)

# ============================================================================
# Scenario 3c: --applicable in rust sandbox → serena present
# ============================================================================
echo "--- Scenario 3c: --applicable in rust sandbox ---"
(
  sandbox=$(mktemp -d)
  trap "rm -rf '$sandbox'" EXIT
  touch "$sandbox/lib.rs"
  out=$(cd "$sandbox" && bash "$HELPER" --applicable)
  if echo "$out" | grep -q "serena"; then
    echo "PASS: --applicable in .rs sandbox includes serena"
  else
    echo "FAIL: --applicable in .rs sandbox — got: $out"
    exit 1
  fi
)

# ============================================================================
# Scenario 4: --wire-cmd context7 → exact command string
# ============================================================================
echo "--- Scenario 4: --wire-cmd context7 ---"
(
  result=$(bash "$HELPER" --wire-cmd context7)
  run_scenario "--wire-cmd context7 exact string" \
    "$result" \
    "claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp@latest"
)

# ============================================================================
# Scenario 5: --wire-cmd serena → exact command string
# ============================================================================
echo "--- Scenario 5: --wire-cmd serena ---"
(
  result=$(bash "$HELPER" --wire-cmd serena)
  run_scenario "--wire-cmd serena exact string" \
    "$result" \
    "claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd"
)

# ============================================================================
# Scenario 6: --wire-cmd sequential-thinking → exact command string
# ============================================================================
echo "--- Scenario 6: --wire-cmd sequential-thinking ---"
(
  result=$(bash "$HELPER" --wire-cmd sequential-thinking)
  run_scenario "--wire-cmd sequential-thinking exact string" \
    "$result" \
    "claude mcp add --scope user sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking"
)

# ============================================================================
# Scenario 7: --wire-cmd agentmemory → VERIFY_ONLY sentinel (NOT a mcp add string)
# ============================================================================
echo "--- Scenario 7: --wire-cmd agentmemory → VERIFY_ONLY ---"
(
  result=$(bash "$HELPER" --wire-cmd agentmemory)
  run_scenario "--wire-cmd agentmemory is VERIFY_ONLY" "$result" "VERIFY_ONLY"
  # confirm it is NOT a claude mcp add command
  if echo "$result" | grep -q "mcp add"; then
    echo "FAIL: --wire-cmd agentmemory must NOT emit a claude mcp add string"
    exit 1
  fi
  echo "PASS: --wire-cmd agentmemory does not contain 'mcp add'"
)

# ============================================================================
# Scenario 8: --auto-wire-set → exactly the 4 names; codegraph/graphify/local-rag ABSENT
# ============================================================================
echo "--- Scenario 8: --auto-wire-set ---"
(
  out=$(bash "$HELPER" --auto-wire-set)
  if echo "$out" | grep -q "context7" \
      && echo "$out" | grep -q "agentmemory" \
      && echo "$out" | grep -q "serena" \
      && echo "$out" | grep -q "sequential-thinking"; then
    echo "PASS: --auto-wire-set contains all 4 expected names"
  else
    echo "FAIL: --auto-wire-set missing expected name — got: $out"
    exit 1
  fi
  # suggestion names must be ABSENT
  if echo "$out" | grep -qE 'codegraph|graphify|local-rag'; then
    echo "FAIL: --auto-wire-set contains suggestion name — got: $out"
    exit 1
  fi
  echo "PASS: --auto-wire-set excludes codegraph, graphify, local-rag"
)

# ============================================================================
# Scenario 9: --suggestions → exactly codegraph, graphify, local-rag
# ============================================================================
echo "--- Scenario 9: --suggestions ---"
(
  out=$(bash "$HELPER" --suggestions)
  if echo "$out" | grep -q "codegraph" \
      && echo "$out" | grep -q "graphify" \
      && echo "$out" | grep -q "local-rag"; then
    echo "PASS: --suggestions contains codegraph, graphify, local-rag"
  else
    echo "FAIL: --suggestions missing expected name — got: $out"
    exit 1
  fi
)

# ============================================================================
# Scenario 10: --selftest from repo root exits 0
# ============================================================================
echo "--- Scenario 10: --selftest from repo root ---"
(
  cd "$REPO_ROOT"
  bash "$HELPER" --selftest
  echo "PASS: --selftest exits 0 from repo root"
)

echo "OK: test_detect_applicable_mcps.sh — 10/10 scenarios PASS"
