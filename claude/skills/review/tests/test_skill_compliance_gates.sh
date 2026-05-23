#!/usr/bin/env bash
# Smoke tests for claude/skills/review/check-skill-compliance.sh.
# 8 test functions exercise gates (a), (b), (c) plus their opt-outs and the
# no-false-positives contract. Each test synthesizes its own tmpdir.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_SCRIPT="$(cd "${SCRIPT_DIR}/.." && pwd)/check-skill-compliance.sh"

PASS=0
FAIL=0
TMP_DIRS=()

cleanup() {
  for d in "${TMP_DIRS[@]}"; do
    [ -d "$d" ] && rm -rf "$d"
  done
}
trap cleanup EXIT

mk_tmp() {
  local d
  d=$(mktemp -d)
  TMP_DIRS+=("$d")
  echo "$d"
}

assert_contains() {
  local label="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -qE "$expected"; then
    PASS=$((PASS + 1))
    echo "PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $label — expected match for /$expected/"
    echo "----- actual -----"
    echo "$actual"
    echo "------------------"
  fi
}

assert_no_finding() {
  local label="$1" actual="$2"
  # No-finding output is just the summary line.
  if echo "$actual" | grep -qE '^\*\*Severity:\*\*'; then
    FAIL=$((FAIL + 1))
    echo "FAIL: $label — expected no findings but found one"
    echo "----- actual -----"
    echo "$actual"
    echo "------------------"
  else
    PASS=$((PASS + 1))
    echo "PASS: $label"
  fi
}

# --- test_01: gate (a) blocks skill without paths ---
test_01_gate_a_blocks_skill_without_paths() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/claude/skills/foo"
  cat > "$d/claude/skills/foo/SKILL.md" <<'EOF'
---
name: foo
description: A test skill without paths.
allowed-tools:
  - Read
---
# foo

Body.
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/claude/skills/foo/SKILL.md" 2>&1 || true)
  assert_contains "test_01_gate_a_blocks_skill_without_paths (severity)" '\*\*Severity:\*\* blocking' "$out"
  assert_contains "test_01_gate_a_blocks_skill_without_paths (file)" "claude/skills/foo/SKILL\.md" "$out"
}

# --- test_02: gate (a) honors allowlist (one of the allowlisted names) ---
test_02_gate_a_honors_allowlist() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/claude/skills/pipeline"
  cat > "$d/claude/skills/pipeline/SKILL.md" <<'EOF'
---
name: pipeline
description: Autonomous pipeline orchestrator.
allowed-tools:
  - Read
---
# pipeline

Body.
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/claude/skills/pipeline/SKILL.md" 2>&1 || true)
  assert_no_finding "test_02_gate_a_honors_allowlist" "$out"
}

# --- test_03: gate (b) warns hook without denial_tracker ---
test_03_gate_b_warns_hook_without_denial_tracker() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/claude/hooks"
  cat > "$d/claude/hooks/new-hook.sh" <<'EOF'
#!/bin/bash
# A new hook without telemetry coverage.
echo "hook ran"
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/claude/hooks/new-hook.sh" 2>&1 || true)
  assert_contains "test_03_gate_b_warns_hook_without_denial_tracker" '\*\*Severity:\*\* non-blocking' "$out"
}

# --- test_04: gate (b) honors `# denial_tracker:no <reason>` opt-out ---
test_04_gate_b_honors_opt_out() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/claude/hooks"
  cat > "$d/claude/hooks/new-hook.sh" <<'EOF'
#!/bin/bash
# denial_tracker:no Stop-hook non-blocking contract.
echo "hook ran"
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/claude/hooks/new-hook.sh" 2>&1 || true)
  assert_no_finding "test_04_gate_b_honors_opt_out" "$out"
}

# --- test_05: gate (c) blocks low richness ---
test_05_gate_c_blocks_low_richness() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/docs-source" "$d/documentation"
  cat > "$d/docs-source/test.md" <<'EOF'
# Test page

Plain markdown without any richness anchors.
EOF
  cat > "$d/documentation/test.html" <<'EOF'
<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><h1>Test</h1><p>Plain paragraph. No snippet mounts.</p></body></html>
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/docs-source/test.md" 2>&1 || true)
  assert_contains "test_05_gate_c_blocks_low_richness (severity)" '\*\*Severity:\*\* blocking' "$out"
  assert_contains "test_05_gate_c_blocks_low_richness (issue)" "richness" "$out"
}

# --- test_06: gate (c) honors <!-- richness-exempt --> marker ---
test_06_gate_c_honors_exempt() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/docs-source" "$d/documentation"
  cat > "$d/docs-source/test.md" <<'EOF'
<!-- richness-exempt: stub doc -->
# Test page

Plain markdown without any richness anchors.
EOF
  cat > "$d/documentation/test.html" <<'EOF'
<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><h1>Test</h1><p>Plain paragraph.</p></body></html>
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/docs-source/test.md" 2>&1 || true)
  assert_no_finding "test_06_gate_c_honors_exempt" "$out"
}

# --- test_07: gate (c) blocks missing render (no HTML) ---
test_07_gate_c_blocks_missing_render() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/docs-source"
  cat > "$d/docs-source/test.md" <<'EOF'
# Test page

No HTML rendered yet.
EOF
  local out
  out=$(bash "$GATE_SCRIPT" --files "$d/docs-source/test.md" 2>&1 || true)
  assert_contains "test_07_gate_c_blocks_missing_render (severity)" '\*\*Severity:\*\* blocking' "$out"
  assert_contains "test_07_gate_c_blocks_missing_render (issue)" "render" "$out"
}

# --- test_08: no false positives on unrelated files ---
test_08_no_false_positives() {
  local d; d=$(mk_tmp)
  mkdir -p "$d/tests"
  echo '# tests change' > "$d/tests/foo.sh"
  local out exit_code
  out=$(bash "$GATE_SCRIPT" --files "$d/tests/foo.sh" 2>&1)
  exit_code=$?
  assert_no_finding "test_08_no_false_positives (no findings)" "$out"
  if [ "$exit_code" -eq 0 ]; then
    PASS=$((PASS + 1))
    echo "PASS: test_08_no_false_positives (exit 0)"
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: test_08_no_false_positives (exit $exit_code, expected 0)"
  fi
}

# Run all tests.
test_01_gate_a_blocks_skill_without_paths
test_02_gate_a_honors_allowlist
test_03_gate_b_warns_hook_without_denial_tracker
test_04_gate_b_honors_opt_out
test_05_gate_c_blocks_low_richness
test_06_gate_c_honors_exempt
test_07_gate_c_blocks_missing_render
test_08_no_false_positives

# test_08 has 2 sub-asserts; others have 1-2. Total of unique "test slot" passes
# equals 8 if no FAIL — collapse per-test PASS counts via the "Results" line
# convention: PASS reflects sub-assertion count, but the gate is FAIL==0.
echo "Results: $PASS PASS / $FAIL FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
