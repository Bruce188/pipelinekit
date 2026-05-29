#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
SKILL="$ROOT/claude/skills/implement-plan/SKILL.md"
PIPELINE="$ROOT/claude/skills/pipeline/SKILL.md"
PIPELINED="$ROOT/claude/skills/pipeline"
REF="$ROOT/claude/skills/pipeline/reference.md"
RULES="$ROOT/claude/rules/agents-worktrees.md"

fail=0
check() { local label="$1" cmd="$2"; if eval "$cmd" >/dev/null; then echo "PASS  $label"; else echo "FAIL  $label"; fail=1; fi; }

check "AC1 single-message wording"        "grep -q 'single message'             '$SKILL'"
check "AC2 parallel-dispatch contract"    "grep -q 'PARALLEL DISPATCH CONTRACT'  '$SKILL'"
check "AC3 beacon in implement-plan"      "grep -q 'PARALLEL_DISPATCH:'          '$SKILL'"
check "AC4 beacon awareness in template"  "grep -q 'PARALLEL_DISPATCH'           '$REF'"
check "AC5 --no-parallel preserved"       "grep -q '\-\-no-parallel'             '$SKILL'"
check "AC6 5.5.3a parallel grouping"      "grep -q 'Step 5.5.3a' "$PIPELINED"/*.md"
check "AC7 one-message fan-out wording"   "grep -q 'one Agent-batch message' "$PIPELINED"/*.md"
check "AC8 template mentions dispatch"    "grep -qE 'dispatch in one message|one Agent-batch message|single-message fan-out' '$REF'"
check "AC11 forced-sequential branch"     "grep -qF 'If \`--no-parallel\` was passed' '$SKILL'"
check "AC12 8-batch cap preserved"        "grep -q 'Cap parallel fan-out at 8'   '$SKILL'"

exit $fail
