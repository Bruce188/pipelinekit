#!/usr/bin/env bash
# Verify claude/skills/pipeline/orchestrate.sh stub presence + contract.
#
# orchestrate.sh is the OPTIONAL out-of-process driver for unattended runs.
# It must source the sandbox library and wrap each `claude -p` invocation
# with sandbox_enter / sandbox_exit so subprocess execution participates in
# the same isolation boundary as the in-process Skill.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
ORCH="$REPO_ROOT/claude/skills/pipeline/orchestrate.sh"

fail=0

# AC1: file exists and passes bash syntax check
if [ ! -f "$ORCH" ]; then
  echo "FAIL orchestrate.sh missing at $ORCH"
  exit 1
fi
if bash -n "$ORCH"; then
  echo "PASS orchestrate.sh bash -n"
else
  echo "FAIL orchestrate.sh bash -n"
  fail=1
fi

# AC2: references sandbox_enter AND sandbox_exit
if grep -q "sandbox_enter" "$ORCH" && grep -q "sandbox_exit" "$ORCH"; then
  echo "PASS orchestrate.sh wires sandbox_enter / sandbox_exit"
else
  echo "FAIL orchestrate.sh missing sandbox_enter/exit"
  fail=1
fi

# AC3: references `claude -p`
if grep -q "claude -p" "$ORCH"; then
  echo "PASS orchestrate.sh dispatches via 'claude -p'"
else
  echo "FAIL orchestrate.sh does not dispatch via claude -p"
  fail=1
fi

# AC4: sources SandboxProvider.sh
if grep -q "SandboxProvider.sh" "$ORCH"; then
  echo "PASS orchestrate.sh sources SandboxProvider.sh"
else
  echo "FAIL orchestrate.sh does not source SandboxProvider.sh"
  fail=1
fi

# AC5: declares run_phase function
if grep -qE '^(run_phase|function run_phase)' "$ORCH"; then
  echo "PASS orchestrate.sh declares run_phase()"
else
  echo "FAIL orchestrate.sh missing run_phase()"
  fail=1
fi

if [ $fail -ne 0 ]; then
  echo ""
  echo "TEST FAILED"
  exit 1
fi
echo ""
echo "all pass"
