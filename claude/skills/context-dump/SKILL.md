---
name: context-dump
description: Save current session context to docs/context-dump.md for handoff or resumption
disable-model-invocation: true
---

Dump the current session context to `docs/context-dump.md`. This file is overwritten each run, not versioned.

## Steps

1. Read `docs/progress.md` -- extract the `**Plan:**` pointer, active/recent tasks (any `doing` or recent `done`), and `Last updated:` date
2. Run `git log --oneline -10` -- capture recent commits
3. Run `git diff --stat` -- capture uncommitted changes
4. Run `git diff --cached --stat` -- capture staged changes
5. Note the current branch: `git branch --show-current`
6. Write `docs/context-dump.md` with the following structure:

```markdown
# Context Dump
**Date:** [current date/time]
**Branch:** [current branch]

## Current Work
[Active task from progress.md, plan objective, what was being worked on]

## Key Decisions
[Reflect on architectural choices, tradeoffs, or pivots made during this session that are not captured in commit messages or task specs]

## Files Modified
[Committed: from git log. Uncommitted: from git diff --stat (unstaged) and git diff --cached (staged). List files with brief why]

## Remaining Work
[Unfinished tasks from progress.md, next steps]

## Gotchas & Blockers
[Issues discovered, workarounds applied, things the next session needs to know]
```

## Rules

- Overwrite `docs/context-dump.md` each time -- do not append or version
- Do not stage or commit `docs/context-dump.md` (it is in the "Never stage" list)
- Keep each section concise -- this is a quick-reference handoff, not a narrative
- If `docs/progress.md` does not exist, note "No progress file found" in the Current Work section and populate remaining sections from git state alone
