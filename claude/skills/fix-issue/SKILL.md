---
name: fix-issue
description: Fix a GitHub issue by number. Reads the issue, implements a fix with TDD, and commits.
allowed-tools:
  - Read
  - Edit
  - Bash
  - Glob
  - Grep
disable-model-invocation: true
paths:
  - claude/skills/fix-issue/**
---

# Fix Issue

Fix a GitHub issue by number. Pass the issue number as the argument (e.g., `/fix-issue 42`).

## Workflow

### 1. Pre-check

Run `gh auth status`. If not authenticated, STOP with: "Run `gh auth login` first."

### 2. Read Issue

```bash
gh issue view $ARGUMENTS --json title,body,labels,assignees
```

Extract the problem description and any acceptance criteria from the issue body.

### 3. Search Codebase

Find files relevant to the reported issue. Use Grep/Glob to locate the affected code. Identify the root cause.

If surface-level grep/glob does not surface the root cause within 2-3 search rounds, dispatch the `debugger` agent with a prompt summarizing the symptom, the files already inspected, and the hypothesis space. Wait for its `<task-notification>` before continuing.

### 4. Write Failing Test (Red)

Write a test that reproduces the reported bug. Run the test suite -- confirm the new test FAILS.

If there is no test framework set up in this project, skip TDD and note "TDD skipped: no test framework". Proceed directly to Step 5.

### 5. Implement Fix (Green)

Make the minimal code change to fix the issue and pass the test.

### 6. Refactor

Clean up the fix if needed without changing behavior. Re-run tests -- all must pass.

### 7. Verify

Run the full test suite. All tests must pass.

### 8. Commit

Stage changed files (following the "Never stage" canonical list from `~/.claude/rules/workflow.md`) and commit:

```bash
git commit -m "fix: resolve #$ARGUMENTS"
```

## Rules

- Do NOT create branches or PRs -- the user manages those separately
- Follow project conventions (the harness auto-loads relevant convention skills)
- If the issue is too complex for a single fix (requires multiple coordinated changes across many files), suggest the user run `/analyze` instead
