#!/usr/bin/env bash
# tests/test_blacksmith_lint_r5.sh
# Smoke test for R5 (Blacksmith runner enforcement) lint rule.
# Pattern: bash-based, no external framework, prints PASS/FAIL per test.
# Uses python3 for parsing (not jq) per feedback_hooks_jq.md.
set -euo pipefail

PASS=0
FAIL=0

# Resolve fixtures directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures/blacksmith"

# Python3 script that implements R5 parsing logic.
# Takes one argument: path to the fixture plan file.
# Exits 0 if no R5 violations, exits 1 if violations found.
# Emits R5_VIOLATION: <file>:<line> on stdout for each violation.
LINT_R5_PY='
import sys
import re

fixture_path = sys.argv[1]
with open(fixture_path, "r") as f:
    lines = f.readlines()

WORKFLOW_PATTERN = re.compile(r"\.github/workflows/[^\s]+\.(yml|yaml)")
RUNS_ON_PATTERN = re.compile(r"^\s*runs-on:\s*(.+)$")
TASK_HEADER_PATTERN = re.compile(r"^#{1,3} Task \d+\.\d+")
FILES_PATTERN = re.compile(r"^\*\*Files")
CONTEXT_PATTERN = re.compile(r"^\*\*Context")
GAP_PATTERN = re.compile(r"BLACKSMITH_DOES_NOT_SUPPORT_")

violations = []
i = 0
total_lines = len(lines)

while i < total_lines:
    line = lines[i]

    if TASK_HEADER_PATTERN.match(line):
        task_start = i
        task_lines = [line]
        i += 1
        while i < total_lines and not TASK_HEADER_PATTERN.match(lines[i]):
            task_lines.append(lines[i])
            i += 1

        workflow_files = []
        context_content = []
        runs_on_lines = []
        in_files_section = False
        in_context_section = False

        for j, tl in enumerate(task_lines):
            abs_lineno = task_start + j + 1

            if FILES_PATTERN.match(tl.strip()):
                in_files_section = True
                in_context_section = False
                continue

            if CONTEXT_PATTERN.match(tl.strip()):
                in_context_section = True
                in_files_section = False
                continue

            if tl.strip().startswith("**") and ":**" in tl.strip():
                if not FILES_PATTERN.match(tl.strip()) and not CONTEXT_PATTERN.match(tl.strip()):
                    in_files_section = False
                    in_context_section = False

            if in_files_section:
                m = re.match(r"^\s*[-*]\s+`?([^\s`]+)`?", tl)
                if m:
                    path = m.group(1)
                    if WORKFLOW_PATTERN.search(path):
                        workflow_files.append(path)
                elif tl.strip() and not tl.strip().startswith("-") and not tl.strip().startswith("*"):
                    if not tl.strip().startswith("("):
                        in_files_section = False

            if in_context_section:
                context_content.append(tl)

            m = RUNS_ON_PATTERN.match(tl)
            if m:
                runs_on_lines.append((abs_lineno, m.group(1).strip()))

        if not workflow_files:
            continue

        has_gap_context = any(GAP_PATTERN.search(cl) for cl in context_content)

        for lineno, runner_val in runs_on_lines:
            contains_blacksmith = "blacksmith-" in runner_val
            if contains_blacksmith:
                continue
            if has_gap_context:
                continue
            print(f"R5_VIOLATION: {fixture_path}:{lineno}")
            violations.append(lineno)
    else:
        i += 1

if violations:
    sys.exit(1)
sys.exit(0)
'

# Run lint_r5_check on a fixture file
lint_r5_check() {
  local fixture="$1"
  python3 -c "$LINT_R5_PY" "$fixture"
}

assert_violation() {
  local fixture="$1"
  local test_name="$2"
  local output
  local rc=0
  output=$(lint_r5_check "$fixture" 2>&1) || rc=$?
  if [ $rc -ne 0 ] && echo "$output" | grep -q "R5_VIOLATION:"; then
    echo "PASS: $test_name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $test_name (expected R5_VIOLATION, got rc=$rc output='$output')"
    FAIL=$((FAIL + 1))
  fi
}

assert_clean() {
  local fixture="$1"
  local test_name="$2"
  local output
  local rc=0
  output=$(lint_r5_check "$fixture" 2>&1) || rc=$?
  if [ $rc -eq 0 ] && ! echo "$output" | grep -q "R5_VIOLATION:"; then
    echo "PASS: $test_name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $test_name (expected no violation, got rc=$rc output='$output')"
    FAIL=$((FAIL + 1))
  fi
}

test_01_violation_ubuntu_latest() {
  assert_violation \
    "$FIXTURES_DIR/plan-violation-ubuntu-latest.md" \
    "test_01_violation_ubuntu_latest"
}

test_02_compliant_blacksmith_runner() {
  assert_clean \
    "$FIXTURES_DIR/plan-compliant-blacksmith.md" \
    "test_02_compliant_blacksmith_runner"
}

test_03_documented_gap_passes() {
  assert_clean \
    "$FIXTURES_DIR/plan-documented-gap-windows.md" \
    "test_03_documented_gap_passes"
}

test_04_non_workflow_file_ignored() {
  assert_clean \
    "$FIXTURES_DIR/plan-no-workflow-file.md" \
    "test_04_non_workflow_file_ignored"
}

test_05_yaml_extension_also_caught() {
  assert_violation \
    "$FIXTURES_DIR/plan-violation-yaml-ext.md" \
    "test_05_yaml_extension_also_caught"
}

test_06_other_hosted_runner_blocked() {
  assert_violation \
    "$FIXTURES_DIR/plan-violation-macos.md" \
    "test_06_other_hosted_runner_blocked"
}

test_07_matrix_os_label_blocked() {
  assert_violation \
    "$FIXTURES_DIR/plan-violation-matrix-os.md" \
    "test_07_matrix_os_label_blocked"
}

# Run all tests
test_01_violation_ubuntu_latest
test_02_compliant_blacksmith_runner
test_03_documented_gap_passes
test_04_non_workflow_file_ignored
test_05_yaml_extension_also_caught
test_06_other_hosted_runner_blocked
test_07_matrix_os_label_blocked

echo ""
echo "Total: $PASS PASS, $FAIL FAIL"
exit $((FAIL > 0))
