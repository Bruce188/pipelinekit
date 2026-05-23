---
name: new-branch
description: Create a conventional feature branch from main/master. Use when starting new work, before first commit, or when on main/master.
argument-hint: <type/name> (e.g., feat/auth, fix/login-bug, refactor/cleanup) OR --research-tag <slug> for research/<slug>-YYYY-MM-DD
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
paths:
  - claude/skills/new-branch/**
  - .git/HEAD
---

# Create Feature Branch

Create a feature branch following conventional naming conventions.

## Usage

```
/new-branch feat/user-auth
/new-branch fix/login-redirect
/new-branch refactor/api-cleanup
/new-branch feat/issue-42-add-foo
/new-branch fix/issue-103-login-redirect-loop
/new-branch refactor/issue-204-extract-validator
```

## Steps

1. Validate the branch name argument:
   - Must start with a valid type prefix: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `perf/`
   - Must use kebab-case after the prefix
   - Cannot be `main` or `master`
   - If no argument given, ask the user what to name the branch

1a. **`--research-tag <slug>` override (optional).** If `--research-tag <slug>` is
    passed instead of (or in addition to) a positional `<type/name>` argument:
    - Compute branch name as `research/<slug>-$(date -u +%Y-%m-%d)` (UTC).
    - Skip the type-prefix validator in Step 1 — the `research/` prefix is
      deliberately not in the conventional allowlist, but is allowed here.
      The `research/` prefix bypasses the validator; all other branch rules still apply.
    - The slug must be kebab-case after the `--research-tag` flag.
    - Continue to Step 2 (base-branch verification) with the computed name.

2. Verify a base branch exists:
   - Run the Base Branch Detection snippet from `~/.claude/rules/workflow.md` § Base Branch Detection
   - If no `main` or `master` branch is found and there's no remote: offer to create one (`git branch main $(git rev-list --max-parents=0 HEAD | tail -1)` for existing repos, or `git init && git checkout -b main && git commit --allow-empty -m "init: empty base"` for new repos)
   - Do not proceed until a base branch exists

3. Check current state:
   - If on a feature branch with uncommitted changes, warn and ask to stash or commit first
   - If not on main/master, ask if user wants to switch to main first

4. If switching to main:
   - `git checkout main` (or master)
   - `git pull origin main` (if remote exists)

5. Create and switch: `git checkout -b $ARGUMENTS`

6. Confirm: show `git branch` output with the new branch highlighted

## Branch Naming Conventions

| Prefix | Use |
|--------|-----|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `refactor/` | Code restructure |
| `docs/` | Documentation |
| `test/` | Test additions |
| `chore/` | Maintenance |
| `perf/` | Performance |
| `research/` | Karpathy autoresearch loop (date-stamped, set via `--research-tag <slug>`) |

Issue-sourced branches add `issue-<N>-` between the type prefix and the slug (e.g., `feat/issue-42-add-foo`). The `/pipeline --issues` flow emits this form automatically.

### What's Next

```
---

Branch created: [branch name]

Next: Run /clear to reset context, then /implement-plan to start executing tasks.

For `research/` branches: the follow-on is the `/research` skill (run
`bash claude/skills/research/research-loop.sh --research-tag <slug> ...`),
not `/implement-plan`. Results are appended to `docs/research-results.tsv`.

Note: `research/` branches skip the conventional type-prefix validator by design.

---
```
