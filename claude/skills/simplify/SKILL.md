---
name: simplify
description: "Post-green reductive refactor: remove unused helpers, dead branches, over-generalized abstractions, and redundant null checks; revert on test failure."
allowed-tools: Read, Edit, Bash, Grep, Glob
context: fork
---

# Simplify

Post-green reductive refactor. Runs after the TDD green phase to tighten code that was written to pass tests — not to redesign it.

## Contract

1. Read files changed in HEAD (git diff --name-only HEAD~1..HEAD).
2. Look for **reductive** opportunities only:
   - Unused helpers (functions, variables, imports never referenced)
   - Dead branches (conditions that can never be true given surrounding logic)
   - Over-generalized abstractions (parameters or generics used with only one concrete value)
   - Redundant null checks (guards that duplicate an outer guard already in scope)
3. If reductions found: apply edits, run the project test suite, commit "refactor: simplify <task>".
4. If no reductions found OR tests fail post-edit: `git reset --hard HEAD` and log the skip reason.

## Scope

Strictly **intra-file reductive**. Each edit must make the file shorter or simpler without changing observable behavior.

Do NOT:
- Rename variables or functions (cosmetic, not reductive)
- Inline functions across call sites (cross-file impact)
- Refactor across multiple files in one edit
- Add new abstractions or helpers
- Change public API signatures

## Process

Step 1: identify changed files via git diff --name-only HEAD~1..HEAD.
Step 2: review each file for reductive opportunities (use Read + Grep to inspect; no edits yet).
Step 3: if opportunities found, apply edits with the Edit tool.
Step 4: run the project test suite (use the project standard test command).
Step 5a: if tests pass, stage and commit: git commit -m "refactor: simplify <task>"
Step 5b: if tests fail or no opportunities found, revert all edits and log the skip reason.
