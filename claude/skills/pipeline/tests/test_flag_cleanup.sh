#!/usr/bin/env bash
# Smoke test for feat/flag-cleanup (Stream E audit).
#
# Asserts:
# 1. claude/skills/pipeline/SKILL.md Step 1 parser block has 0 hits for
#    the removed pipeline flags (`--teams` as pipeline arg, NOT the
#    deprecation STOP mention; `--health`, `--design-pass`).
# 2. claude/skills/pipeline/SKILL.md has >=1 hit for each new flag
#    (`--no-prompts`, `--no-review`, `--no-ppr`, `--no-docs`, `--no-tdd`,
#    `--no-notifications`, `--no-teams`).
# 3. claude/skills/review/SKILL.md description + argument-hint lines
#    omit `--health`, `--design-pass`, `--teams` (positive form). The
#    body keeps deprecation STOPs.
# 4. claude/rules/workflow.md flag table maps 1-to-1 onto the SKILL.md
#    parser block (no UNDOCUMENTED leftover).
#
# Run from repo root:
#   bash claude/skills/pipeline/tests/test_flag_cleanup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PIPELINE_SKILL="$REPO_ROOT/claude/skills/pipeline/SKILL.md"
REVIEW_SKILL="$REPO_ROOT/claude/skills/review/SKILL.md"
WORKFLOW="$REPO_ROOT/claude/rules/workflow.md"

PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

[ -f "$PIPELINE_SKILL" ] || { echo "missing: $PIPELINE_SKILL"; exit 1; }
[ -f "$REVIEW_SKILL"   ] || { echo "missing: $REVIEW_SKILL"; exit 1; }
[ -f "$WORKFLOW"       ] || { echo "missing: $WORKFLOW"; exit 1; }

echo "Test 1: pipeline SKILL.md parser block does not declare removed flags as positive args"
# Extract Step 1 parse block: lines starting with `- \`--` between
# "### Step 1: Parse Arguments" and "### Step 1.4:".
PARSE_BLOCK=$(awk '/^### Step 1: Parse Arguments/,/^### Step 1\.4:/' "$PIPELINE_SKILL")

# Positive flag declarations follow the pattern `- \`--flag\` = ...`.
# The deprecation STOP entries use a different shape (`- \`--teams\` (pipeline-level): REMOVED.`),
# so we match strictly on ` = ` to exclude the STOP entries.
if echo "$PARSE_BLOCK" | grep -E '^- `--teams` =' >/dev/null; then
  fail "Step 1 parser block still declares \`--teams\` as a positive flag"
else
  ok "Step 1 parser block does not declare \`--teams\` as a positive flag"
fi

if echo "$PARSE_BLOCK" | grep -E '^- `--health` =' >/dev/null; then
  fail "Step 1 parser block still declares \`--health\` as a positive flag"
else
  ok "Step 1 parser block does not declare \`--health\` as a positive flag"
fi

if echo "$PARSE_BLOCK" | grep -E '^- `--design-pass` =' >/dev/null; then
  fail "Step 1 parser block still declares \`--design-pass\` as a positive flag"
else
  ok "Step 1 parser block does not declare \`--design-pass\` as a positive flag"
fi

echo "Test 2: pipeline SKILL.md declares every new flag at least once"
for flag in --no-prompts --no-review --no-ppr --no-docs --no-tdd --no-notifications --no-teams; do
  if grep -F "\`${flag}\`" "$PIPELINE_SKILL" >/dev/null; then
    ok "pipeline SKILL.md mentions ${flag}"
  else
    fail "pipeline SKILL.md does not mention ${flag}"
  fi
done

echo "Test 3: pipeline SKILL.md keeps the deprecation STOP message for --teams (audit trail)"
if grep -F 'DEPRECATED: --teams (pipeline) removed' "$PIPELINE_SKILL" >/dev/null; then
  ok "pipeline SKILL.md contains --teams deprecation STOP"
else
  fail "pipeline SKILL.md is missing the --teams deprecation STOP message"
fi

echo "Test 4: pipeline SKILL.md keeps the --auto deprecation alias note"
if grep -F 'DEPRECATED: --auto is now --no-prompts' "$PIPELINE_SKILL" >/dev/null; then
  ok "pipeline SKILL.md contains --auto deprecation alias note"
else
  fail "pipeline SKILL.md is missing the --auto deprecation alias note"
fi

echo "Test 5: review SKILL.md description + argument-hint dropped --health, --design-pass, positive --teams"
HEAD=$(head -20 "$REVIEW_SKILL")
for forbidden in '\[--health\]' '\[--design-pass\]' '\[--teams\]'; do
  if echo "$HEAD" | grep -E "$forbidden" >/dev/null; then
    fail "review SKILL.md frontmatter still lists ${forbidden}"
  else
    ok "review SKILL.md frontmatter does not list ${forbidden}"
  fi
done

echo "Test 6: review SKILL.md frontmatter accepts --no-teams"
if echo "$HEAD" | grep -F -- '--no-teams' >/dev/null; then
  ok "review SKILL.md frontmatter lists --no-teams"
else
  fail "review SKILL.md frontmatter does not list --no-teams"
fi

echo "Test 7: review SKILL.md keeps deprecation STOPs for --health and --design-pass"
if grep -F 'DEPRECATED: --health removed' "$REVIEW_SKILL" >/dev/null; then
  ok "review SKILL.md has --health deprecation STOP"
else
  fail "review SKILL.md missing --health deprecation STOP"
fi

if grep -F 'DEPRECATED: --design-pass removed' "$REVIEW_SKILL" >/dev/null; then
  ok "review SKILL.md has --design-pass deprecation STOP"
else
  fail "review SKILL.md missing --design-pass deprecation STOP"
fi

echo "Test 8: workflow.md flag table has rows for every new flag and lacks rows for removed flags"
TABLE=$(awk '/^\| Argument \| Available on \| Behavior \|/,/^$/' "$WORKFLOW")

for flag in --no-prompts --no-review --no-ppr --no-docs --no-tdd --no-notifications --no-teams --issues --issues-limit --issues-sort --issues-comment-author --plan; do
  if echo "$TABLE" | grep -F "\`${flag}\`" >/dev/null; then
    ok "workflow.md flag table contains row for ${flag}"
  else
    fail "workflow.md flag table missing row for ${flag}"
  fi
done

# Removed rows: leading-column match only (`| \`--flag\` |` shape).
# This excludes body-text mentions like `--auto` deprecation alias inside the `--no-prompts` row.
for removed in '--health' '--auto' '--teams'; do
  if echo "$TABLE" | grep -E "^\| \`${removed}\` \|" >/dev/null; then
    fail "workflow.md flag table still has leading-column row for removed flag ${removed}"
  else
    ok "workflow.md flag table has no leading-column row for removed flag ${removed}"
  fi
done

echo
echo "Result: $PASS pass, $FAIL fail"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
