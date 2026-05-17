---
name: ppr
description: Push + PR. Push committed changes to origin and open a pull request. Run after /review passes. Human approves the PR separately.
argument-hint: (no arguments needed)
allowed-tools: Bash, Read
---

# PPR — Push + PR

Closes the implementation loop: push → open PR. Changes should already be committed by `/implement-plan`.

**Prerequisite:** `/review` must have passed (sanity gate + all agents clean, or all nit findings auto-fixed).

---

## Process

### Step 1: Safety Checks

```bash
git branch --show-current
```

Detect the base branch using the standard snippet from `~/.claude/rules/workflow.md` § Base Branch Detection.

If current branch equals `$BASE`: **STOP.**
> "Cannot push directly to $BASE. Run `/new-branch` first."

```bash
git status --short
CURRENT_BRANCH="$(git branch --show-current)"
git log "origin/${CURRENT_BRANCH}..HEAD" --oneline 2>/dev/null || echo "(no upstream yet — all local commits are unpushed)"
```

If there are uncommitted changes: **STOP.**
> "Uncommitted changes detected. Run `/implement-plan` to complete and commit, or commit manually before running `/ppr`."

If no unpushed commits (upstream exists and is up-to-date) AND no uncommitted changes:
  Check if a PR already exists: `gh pr view --json state 2>/dev/null`
  If PR exists: **STOP.** "PR already exists for this branch."
  If no PR exists: log "Branch already pushed — skipping to PR creation." and jump to Step 3.

Check the diff against base:
```bash
git diff "$BASE"...HEAD --stat
```
If empty: **STOP.**
> "Diff against $BASE is empty — all changes may have been reverted. Nothing to PR."

---

### Step 1.5: Review Check

Verify that `/review` has been run and passed:

1. Read `docs/progress.md` — check for a `**Review:**` pointer
2. If no `**Review:**` pointer exists: warn "No review file found. Run `/review` before `/ppr`." and **STOP.**
3. If pointer exists: read the review file
4. Check for findings at ANY severity:
   - If zero blocking AND zero non-blocking AND zero nit findings: proceed
   - If ANY findings remain at any severity: warn "Unresolved findings: [N blocking, M non-blocking, P nits]. Run `/implement-plan` to address remaining findings." and **STOP.**
5. Check review staleness: If the review file contains a `**HEAD:**` field, compare using prefix matching (short hashes vary in length):
   ```bash
   REVIEW_HEAD="<from review file>"
   CURRENT_HEAD=$(git rev-parse HEAD)
   ```
   If `$CURRENT_HEAD` does not start with `$REVIEW_HEAD` (or vice versa): warn "HEAD has advanced past the reviewed commit ($REVIEW_HEAD vs $CURRENT_HEAD). Run `/review` again." and **STOP.**
   Note: This depends on `/review` recording `**HEAD:** [hash]` in its review file (see review/SKILL.md Step 8).

If `docs/progress.md` does not exist: warn "No progress.md found — skipping review check. Consider running /review before pushing." and proceed.

---

### Step 1.6: Landing Report (advisory)

Detect version-slot collisions before push. Fires only when a `VERSION` file or `package.json:version` is present in the repo root; otherwise silently skips.

```bash
if [ -f VERSION ] || python3 -c 'import json,sys;sys.exit(0 if json.load(open("package.json",encoding="utf-8")).get("version") else 1)' 2>/dev/null; then
  Skill: landing-report
fi
```

Behavior:
- **Collision detected** — print warning to stdout (e.g., `landing-report: collision=yes — tag v1.2.3 already exists`), but DO NOT stop. The push proceeds.
- **No collision** — print one-line summary (`landing-report: ... collision=no`) and continue.
- **Neither marker present** — silent skip (`SKIP: no VERSION or package.json:version found` on stderr), continue.

Advisory only — never blocks the push.

---

### Step 1.7: Auto-format (language-specific)

Before push, apply the project's formatter so CI doesn't bounce the PR on mechanical style issues. Detect by marker file and run unconditionally — the formatter is a no-op when code is already clean.

**.NET solutions** (`*.sln` present):
```bash
if ls *.sln 2>/dev/null | head -1 >/dev/null; then
  dotnet format
  if ! git diff --quiet; then
    git add -u
    git commit -m "style: apply dotnet format"
  fi
fi
```
The final `dotnet format --verify-no-changes` runs in CI (e.g., the Deploy to Azure workflow); running `dotnet format` here pre-emptively keeps the PR green. If you're resuming a branch that was previously green, this step is a fast no-op.

**Other toolchains** — same pattern: detect by marker, run formatter, commit if dirty.
- `package.json` with a `format` script → `npm run format` (or `pnpm format` / `yarn format`)
- `pyproject.toml` with Ruff/Black → `ruff format .` or `black .`
- `go.mod` → `gofmt -w .` or `go fmt ./...`

Skip this step entirely when no marker is detected.

---

### Step 2: Push

```bash
# First push to this branch (sets upstream)
git push -u origin "$(git branch --show-current)"

# Subsequent pushes
# git push origin "$(git branch --show-current)"
```

Try `-u` first — it handles both cases safely.

**Check the exit code.** If push fails (auth error, remote config, branch protection): **STOP** with descriptive error. Do NOT proceed to PR creation on an unpushed branch.

---

### Step 3: Create Pull Request

Read:
- `git log "$BASE"..HEAD --oneline` — commits being merged
- `git diff "$BASE"...HEAD --stat` — files changed
- `docs/progress.md` — completed tasks for context
- The plan file referenced by the `**Plan:**` field in `docs/progress.md` (fall back to `docs/plan.md` if no pointer exists) — for understanding the broader objective
- The review file referenced by the `**Review:**` pointer in `docs/progress.md` — for surfacing spec-tracer and other agent evidence in the PR body

Before composing the PR body, read the `**Review:**` pointer from `docs/progress.md` and open the referenced review file. Include the spec-tracer outcome (pass / findings) verbatim in the PR body under a "Review evidence" subsection, alongside the other agent outcomes (code-reviewer, security-auditor, test-engineer, performance-tuner). If no review file exists, omit the subsection.

**Charter Goal prefix for `## Summary`:**

Before composing the PR body, check for an active charter:

```bash
test -f docs/charter.md && echo "CHARTER_FOUND" || echo "NO_CHARTER"
```

If `docs/charter.md` exists: read the `## Goal` section. Extract the first sentence or the full section text (whichever is shorter). If the text is ≤ 200 characters, use it verbatim as the opening line of `## Summary`. If > 200 characters, truncate at the nearest word boundary and append `…`.

Set `CHARTER_GOAL_LINE` to this one-line excerpt (or empty string if no charter). The `## Summary` section starts with `CHARTER_GOAL_LINE` followed by the standard 2–3 bullets describing what changed and why.

If `docs/charter.md` is absent: `CHARTER_GOAL_LINE=""`. Behavior unchanged — current auto-summary logic.

A future `--summary "..."` flag override is deferred to a later iteration. If passed, it replaces both `CHARTER_GOAL_LINE` and the auto-derived bullets.

Generate PR title and body:
- Title: conventional format `<type>[(scope)]: <description>` (≤ 72 chars)
- **No AI attribution** — no "Generated by", "Co-authored by Claude", "AI-assisted", etc.
- **No Co-authored-by trailers**
- **No workflow metadata** — no task IDs (e.g., "1.1", "2.3"), phase numbers, review file references (e.g., "review-v23"), `reopened:` annotations, or pipeline-internal terminology. The PR should read as if authored by a human developer.

```bash
gh pr create \
  --title "[type(scope): description]" \
  --body "$(cat <<'EOF'
## Summary
[CHARTER_GOAL_LINE — verbatim charter Goal excerpt, or omit line if no charter]
[2–3 bullets: what changed and why]

## Changes
[key files modified and what each does]

## Verification
- [ ] Sanity gate passed
- [ ] Secret scan clean
- [ ] Review agents passed (code, security, testing, performance, spec-tracer)
EOF
)"
```

**Check the exit code.** If `gh pr create` fails: **STOP** with descriptive error. Do NOT output the "What's Next" block with a nonexistent PR URL.

Capture and display the PR URL only on success.

---

### Step 4: What's Next

```
---

PR opened: [PR URL]

Human action required:
  - Review and approve the PR
  - Merge when ready

After merge: Run /post-merge to clean up, then /clear to reset context.

---
```
