#!/usr/bin/env bash
set -euo pipefail
# test_claude_md_template_memory_section.sh — assert the Memory System rewrite
# from F8 (feat/agentmemory-replace-flat-file-memory) is intact.
#
# Runtime: < 1s. Safe to re-run; reads only.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TEMPLATE="$REPO_ROOT/claude/CLAUDE.md.template"

PASS=0; FAIL=0; FAILED_NAMES=()
record() {
  if [ "$2" = "PASS" ]; then PASS=$((PASS+1)); echo "PASS: $1"
  else FAIL=$((FAIL+1)); FAILED_NAMES+=("$1"); echo "FAIL: $1 -- ${3:-}"
  fi
}

if [ ! -f "$TEMPLATE" ]; then
  echo "FAIL: template_not_found -- $TEMPLATE"
  echo "Results: 0 PASS / 1 FAIL"
  exit 1
fi

# Test 01: memory_save present
grep -qF 'memory_save' "$TEMPLATE" && record "memory_save_present" PASS || record "memory_save_present" FAIL

# Test 02: memory_recall present
grep -qF 'memory_recall' "$TEMPLATE" && record "memory_recall_present" PASS || record "memory_recall_present" FAIL

# Test 03: legacy markdown-save phrasing ABSENT (case-insensitive, extended-regex)
if grep -qiE 'save memories? as markdown|write a markdown file|save memory to a markdown file' "$TEMPLATE"; then
  record "legacy_markdown_save_absent" FAIL "found legacy phrasing"
else
  record "legacy_markdown_save_absent" PASS
fi

# Test 04: Ebbinghaus present
grep -qF 'Ebbinghaus' "$TEMPLATE" && record "ebbinghaus_present" PASS || record "ebbinghaus_present" FAIL

# Test 05: When NOT to save block present
grep -qF 'When NOT to save' "$TEMPLATE" && record "when_not_to_save_present" PASS || record "when_not_to_save_present" FAIL

# Test 06: PIPELINE_KEEP_FLAT_FILE_MEMORY toggle documented
grep -qF 'PIPELINE_KEEP_FLAT_FILE_MEMORY' "$TEMPLATE" && record "dual_write_toggle_present" PASS || record "dual_write_toggle_present" FAIL

# Test 07: agentmemory token count >= 4
N=$(grep -cF 'agentmemory' "$TEMPLATE")
if [ "$N" -ge 4 ]; then
  record "agentmemory_tokens_ge_4" PASS
else
  record "agentmemory_tokens_ge_4" FAIL "found $N, expected >= 4"
fi

# Test 08: MEMORY.md cross-reference dropped
if grep -qF 'MEMORY.md' "$TEMPLATE"; then
  record "memory_md_xref_dropped" FAIL "MEMORY.md still cross-referenced"
else
  record "memory_md_xref_dropped" PASS
fi

# Test 09: taxonomy mapping table present (sanity — one well-known row)
if grep -qE '\| `feedback`\s+\|.*\[feedback\]' "$TEMPLATE"; then
  record "taxonomy_table_feedback_row" PASS
else
  record "taxonomy_table_feedback_row" FAIL "feedback row missing or malformed"
fi

echo "Results: $PASS PASS / $FAIL FAIL"
[ "$FAIL" -ne 0 ] && { echo "Failed: ${FAILED_NAMES[*]}"; exit 1; }
exit 0
