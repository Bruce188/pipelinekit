---
name: new-branch
description: Create a conventional feature branch from main/master. Use when starting new work, before first commit, or when on main/master.
argument-hint: <type/name> (e.g., feat/auth, fix/login-bug, refactor/cleanup)
disable-model-invocation: true
allowed-tools: Bash, Read, AskUserQuestion
---

# Create Feature Branch

Create a feature branch following conventional naming conventions.

## Usage

```
/new-branch feat/user-auth
/new-branch fix/login-redirect
/new-branch refactor/api-cleanup
```

## Steps

1. Validate the branch name argument:
   - Must start with a valid type prefix: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `perf/`
   - Must use kebab-case after the prefix
   - Cannot be `main` or `master`
   - If no argument given, ask the user what to name the branch

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

### What's Next

```
---

Branch created: [branch name]

Next: Run /clear to reset context, then /implement-plan to start executing tasks.

---
```
