#!/usr/bin/env bash
# claude/skills/caveman-mode/tests/test_v2_qa.sh
#
# Behavioral Q&A smoke pack for v2 bounded-paraphrase mode. MANUAL EVAL.
#
# Five sample input files are listed below. Each has three questions that the
# POST-COMPRESSION output MUST still answer equivalently to the PRE input.
# A human reviewer scores each file: pass = >= 2/3 questions answered
# correctly against the compressed file. Aggregate pass = 4/5 files pass.
#
# This script DOES NOT run a model. It logs MANUAL_EVAL_REQUIRED and exits 0.
# The validator pack (test_v2_validator.sh) covers the deterministic side;
# this pack covers the behavioral side that requires a human in the loop.

set -uo pipefail

cat <<'README'
==============================================================================
v2 bounded-paraphrase — behavioral Q&A pack (manual eval)
==============================================================================

Manual scoring rubric:
  - For each sample file, ask the 3 questions of the post-compression file
    (use whichever Claude session is convenient — Haiku is fine).
  - Score each question: PASS if the answer is substantively equivalent to
    the pre-compression answer, FAIL otherwise.
  - File passes if >= 2/3 questions PASS.
  - Pack passes if >= 4/5 files PASS.

------------------------------------------------------------------------------
Sample 1: claude/CLAUDE.md.template
  Q1: What is the never-stage list and where does it live?
  Q2: Which commit-type prefixes are enforced by validate-commit-msg.sh?
  Q3: How does the base-branch detection snippet pick a default?

Sample 2: claude/rules/workflow.md
  Q1: What does the --scope argument do on /review?
  Q2: Which files are produced by /create-plan?
  Q3: Where do review findings get saved?

Sample 3: claude/rules/agents-worktrees.md
  Q1: What is the wip: commit requirement for worktree agents?
  Q2: What is the task-notification XML schema?
  Q3: When should a worker emit "blocked" vs "failed"?

Sample 4: <synthetic> small Tier-1 fixture with MUST/NEVER lines
  Q1: How many MUST literals does the file contain?
  Q2: Which path patterns are gated?
  Q3: What is the exit code on a reject?

Sample 5: <synthetic> small rules-style fixture with numbered steps
  Q1: How many procedural steps are listed?
  Q2: What is the first step?
  Q3: What is the terminal step's expected output?
------------------------------------------------------------------------------

MANUAL_EVAL_REQUIRED — no automated assertions in this pack.
README

echo ""
echo "MANUAL_EVAL_REQUIRED"
exit 0
