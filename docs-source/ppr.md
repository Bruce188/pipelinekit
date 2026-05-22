# /ppr — Push + PR

The closing step of every pipeline feature: push the committed branch to origin and open a pull request. Runs after `/review` passes. The human approves the PR separately — `/ppr` never auto-merges. This page documents the everyday push-PR flow; for the separate research-publish flow, see [/ppr --research flag](ppr-research-flag.html).

<div data-snippet="terminal-simulator"></div>

## Synopsis

```
/ppr                                 # everyday mode: push branch, open PR
/ppr --research [--dry-run|--no-dry-run] --research-tag <slug>  # research-publish mode (separate page)
```

No arguments needed in everyday mode. The current branch is detected automatically. The PR body is auto-derived from `docs/progress.md`, the active charter (if any), the active plan, and the most recent `/review` file.

## Prerequisites

`/ppr` is the last step of a pipeline feature. It assumes:

1. **Branch:** You're on a feature branch, not on `main` / `master`. (Direct push to base is blocked.)
2. **Changes:** Everything is committed. Uncommitted changes cause a hard STOP — `/ppr` never auto-commits.
3. **Review:** `/review` has run and passed (zero findings at any severity, OR all nit-level findings auto-fixed).
4. **Review freshness:** HEAD has not advanced past the SHA recorded in the review file (`**HEAD:** <sha>` line). Re-run `/review` if you've committed since.

If any prerequisite fails, `/ppr` STOPs with a descriptive error and does not push anything.

## Process

### Step 1: Safety checks

```bash
git branch --show-current     # must NOT equal $BASE
git status --short            # must be clean (no uncommitted changes)
git diff "$BASE"...HEAD --stat  # must be non-empty (real diff to push)
gh pr view --json state       # must not already exist for this branch
```

If a PR already exists for the branch, `/ppr` STOPs. If the branch has been pushed but no PR exists, `/ppr` skips ahead to Step 3 (Create PR).

### Step 1.5: Review check

Reads `docs/progress.md` → follows the `**Review:**` pointer → opens the review file. Verifies:

- **Zero blocking, zero non-blocking, zero nit findings** — anything unresolved STOPs the push.
- **Review-HEAD freshness** — the review file's `**HEAD:** <sha>` is compared against `git rev-parse HEAD` via prefix match (short hashes vary in length). If they don't match, the review is stale and `/ppr` STOPs with a re-run hint.

When `docs/progress.md` doesn't exist, `/ppr` warns and proceeds (workflow-overlay-optional mode). The warning is logged but is not a blocker.

### Step 1.6: Landing report (advisory)

If the repo has a `VERSION` file or a `package.json:version` field, `/ppr` invokes the [`landing-report` skill](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/landing-report/SKILL.md) to detect version-slot collisions (e.g., a tag `v1.2.3` already exists upstream). The result is **advisory only** — collisions print a warning to stdout but do NOT stop the push. The author of the PR decides whether to bump the version before merging.

When neither marker file is present, the step silently skips.

### Step 1.7: Auto-format (language-specific)

Detect-by-marker, then run the project formatter so CI doesn't bounce the PR on whitespace:

| Marker | Formatter | Detection |
|---|---|---|
| `*.sln` | `dotnet format` | .NET solution file at repo root |
| `package.json` with `format` script | `npm run format` (or `pnpm format` / `yarn format`) | npm script present |
| `pyproject.toml` with Ruff/Black configured | `ruff format .` / `black .` | depending on config |
| `go.mod` | `gofmt -w .` / `go fmt ./...` | Go module |

If the formatter touches anything, the changes are committed as `style: apply <tool>` so the PR's commit history reflects the auto-format step. If the formatter is a no-op (code already clean), nothing happens. **Skipped entirely** when no marker is detected.

### Step 2: Push

```bash
git push -u origin "$(git branch --show-current)"   # first push: sets upstream
```

`-u` is always passed — it's safe on subsequent pushes too. If push fails (auth error, branch protection rule, etc.), `/ppr` STOPs with the git error message. **Never proceeds to PR creation on an unpushed branch** — a half-success would leave a PR pointing at a branch the reviewer can't access.

### Step 3: Create the PR

The PR body is composed from multiple sources:

1. **`## Summary`** — starts with a `CHARTER_GOAL_LINE` excerpt if `docs/charter.md` has a `## Goal` section (truncated at 200 chars with `…` if longer). Followed by 2–3 bullets describing what changed and why, derived from the commit messages and progress.md.
2. **`Closes #N`** — auto-emitted when the branch name matches `^[a-z]+/issue-([0-9]+)-` (issue-mode pipeline runs). Exactly one close keyword for issue branches, zero for non-issue branches.
3. **`## Changes`** — key files modified with one-line descriptions per file.
4. **`## Verification`** — checkbox list: sanity gate, secret scan, review agents (code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer).
5. **`## Review evidence`** — spec-tracer outcome verbatim (when the review file has one), alongside the other agent outcomes.

**Title format:** conventional commit — `<type>[(scope)]: <description>`, capped at 72 characters.

**Hard rules on the PR body:**

- No AI attribution. No "Generated by", no "Co-authored by Claude", no "AI-assisted".
- No `Co-authored-by` trailers in commits or in the PR body.
- No workflow metadata — no task IDs ("1.1", "2.3"), no phase numbers, no review-file references ("review-v23"), no `reopened:` annotations, no pipeline-internal terminology. The PR should read as if a human authored it.

If `gh pr create` fails (network, auth, repo permissions), `/ppr` STOPs with the gh error. The "What's Next" block in Step 4 only fires on success.

### Step 4: What's Next

On success, `/ppr` prints:

```
PR opened: <URL>

Human action required:
  - Review and approve the PR
  - Merge when ready

After merge: Run /post-merge to clean up, then /clear to reset context.
```

The human owns the merge decision. `/ppr` never auto-merges. There is no `--auto-merge` flag. The reviewer is expected to read the PR body, eyeball the diff, and click "Merge" themselves.

## Branch protection compatibility

`/ppr` respects whatever branch protection rules the repo has set up:

- **Required reviewers** — the PR opens but cannot be merged until the required reviewer approves. `/ppr`'s job ends at PR-open; the merge happens later.
- **Required status checks** — CI runs after push; the PR shows the status badges. `/ppr` does NOT poll for CI completion (that's a `/post-merge` concern, optionally).
- **Force-push protection** — `/ppr` only does `git push -u origin <branch>`, never `--force`. If the branch already exists upstream with diverged history, the push fails cleanly.
- **Linear history** — `/ppr` does not rebase. If the repo requires linear history, the human is expected to rebase manually (or `/post-merge --rebase` if available).

## Failure modes

| Condition | Behavior | Recovery |
|---|---|---|
| On `main` / `master` | STOP | Run `/new-branch <feature-name>` first |
| Uncommitted changes | STOP | Run `/implement-plan` to finish, or `git commit` manually |
| Diff against base is empty | STOP | Either nothing to ship, or commits were reverted — investigate |
| PR already exists | STOP | Skip `/ppr` or close the existing PR first |
| `/review` not run or has findings | STOP | Run `/review`; address findings via `/implement-plan` |
| Review HEAD stale | STOP | Re-run `/review` to refresh the recorded HEAD |
| Push fails (auth/branch protection) | STOP with git error | Fix the underlying issue (auth, force-push policy, etc.) |
| `gh pr create` fails | STOP with gh error | Usually auth (`gh auth status`) or rate-limit |

In every failure case `/ppr` exits non-zero and does NOT print the "What's Next" block, so the orchestrator (when `/ppr` is run via `/pipeline`) does not advance the pipeline state.

## See also

- **[/ppr --research](ppr-research-flag.html)** — separate mode for publishing research-loop keep-rows to a `research/<tag>-<date>` branch (no PR opened, parked for human review).
- **[Review cost profile](review-cost.html)** — the `/review` phase that gates `/ppr`.
- **[Pipeline](pipeline.html)** — the orchestrator that runs `/ppr` as Path A (clean-merge after review passes) of every feature.
