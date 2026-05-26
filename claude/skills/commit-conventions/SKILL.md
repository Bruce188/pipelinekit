---
name: commit-conventions
description: Conventional commit format, message rules, and attribution policy. Loaded when writing commit messages, creating PRs, or merging branches.
allowed-tools:
  - Read
user-invocable: false
paths:
  - claude/skills/commit-conventions/**
---

# Commit Conventions

Rules for all commit messages, PR titles, and merge commits.

## Format

```
<type>(<scope>): <description>
```

Scope is optional. When used, it names the module or area affected (e.g., `feat(auth): add token refresh`).

## Valid Types

| Type | Use When |
|------|----------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring with no behavior change |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `chore` | Build, CI, tooling, dependencies |
| `perf` | Performance improvement |

## Message Rules

1. Use imperative mood: "add feature" not "added feature" or "adds feature"
2. Lowercase the first word after the colon: `feat: add` not `feat: Add`
3. No trailing period
4. Subject line max 72 characters
5. Body (optional) separated by a blank line, wrapped at 80 characters
6. One logical change per commit

## Prohibited Content

- No `Co-authored-by` trailers (all casing variants)
- No AI attribution (`Generated with`, `claude-code-assisted`, etc.)
- No workflow metadata: task IDs, `review-vN`, `plan-vN`, finding counts
- No internal process references: `wip:`, `stream A/B/C/D/E`, `parallel streams`, `apply review`, `N findings`, `merge: stream`, `across N streams`
- No emojis in commit messages

## Quality Check

Before finalizing a commit message, ask: "Would a human developer write this?" If not, rewrite it.
