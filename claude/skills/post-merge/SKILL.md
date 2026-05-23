---
name: post-merge
description: Clean up after PR merge. Switches to main, pulls latest, deletes merged feature branch locally and remotely. Use after a PR has been merged on GitHub.
argument-hint: [branch-to-delete] (optional, defaults to current branch)
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
paths:
  - claude/skills/post-merge/**
  - docs/progress.md
  - docs/pipeline-state.md
---

# Post-Merge Cleanup

Clean up local and remote state after a PR has been merged.

## Usage

```
/post-merge              # cleans up current branch
/post-merge feat/auth    # cleans up specified branch
```

## Steps

1. Identify the branch to clean up:
   - If `$ARGUMENTS` is provided, use that branch name
   - Otherwise, use the current branch name
   - If current branch is main/master, ask which branch to clean up

2. Safety checks:
   - NEVER delete main or master
   - Check for uncommitted changes — if any, warn and ask to stash
   - Detect the base branch using the standard snippet from `~/.claude/rules/workflow.md` § Base Branch Detection.

3. Switch to base branch and pull (pull before merge check to avoid stale state):
   ```bash
   git checkout "$BASE"
   git pull origin "$BASE"
   ```

4. Verify the branch has been merged: `git log "$BASE"..<branch> --oneline` should be empty after merge, or check `gh pr view --json state`

5. Delete local branch:
   ```bash
   git branch -d <branch>
   ```
   If `-d` fails (unmerged), show the warning and ask user to confirm `-D` force delete.

6. Delete remote branch (if exists):
   ```bash
   git push origin --delete <branch>
   ```

7. Clean up tracking:
   ```bash
   git remote prune origin
   ```

8. Confirm: show `git branch -a` to verify cleanup is complete.

9. CD/CI health check (advisory):
   If `gh` CLI is available (`command -v gh >/dev/null 2>&1`):
   ```bash
   gh run list --branch "$BASE" --limit 3 --json name,status,conclusion,headBranch
   ```
   Parse with python3 and report any workflows where `headBranch` matches `$BASE` and `conclusion` is `failure`:
   ```
   WARNING: Failing workflows on [BASE]: [workflow names]
   Triage with /incident for a structured analysis.
   ```
   If no failures or `gh` is unavailable: skip silently (no output).
   This is advisory only — do not halt or block. The user decides what to do.

9b. Azure project-signal advisory:
   Check whether the repo has Azure deployment signals. The probe looks for any of:
   - `azure-pipelines.yml` (Azure Pipelines CI/CD config)
   - `.azure/config` (Azure CLI workspace defaults)
   - `az-deploy.sh` (project-local Azure deploy script)
   ```bash
   if ls azure-pipelines.yml .azure/config az-deploy.sh 2>/dev/null | head -1 >/dev/null; then
     echo "Azure project signal detected. Consider @azure-deployment-engineer for deploy review."
   fi
   ```
   This step is advisory and non-blocking. It NEVER invokes `az` from inside `/post-merge` —
   the deployment-engineer agent is the executor; `/post-merge` only signals presence of
   Azure-flavored artifacts. The user decides whether to invoke `@azure-deployment-engineer`
   for the next iteration.
   If `ls` returns no matches: skip silently (no output).

10. Advisory: Run Hook Tests

   Invoke `/test-hooks` to run the hook unit-test suite and surface any regressions.
   This step is non-blocking — failures are informational only and do not affect the
   outcome of `/post-merge`. Branch cleanup and overall success state are unaffected.

   ```
   /test-hooks
   ```

   The summary (pass/fail counts and any failing test names) prints to stdout.
   If all tests pass, a single green summary line is shown. If any test failures
   are reported, print one additional advisory line:

   ```
   Hook test failures detected. Consider /incident for triage.
   ```

   Either way, proceed to the next step.

11. Deferred-Items Audit (advisory):

   Read `docs/progress.md`. If either the `## Deferred` table or the `## Status` table is empty,
   skip silently. Otherwise, for each row in `## Deferred`, fuzzy-match against done tasks in `## Status`
   and prompt the user per match. **Never auto-remove — per-match prompt only.**

   Tokenization (use python3):
   - Lowercase, split on non-alphanumeric characters, drop tokens shorter than 3 chars, drop stopwords:
     `the`, `a`, `an`, `and`, `or`, `to`, `for`, `of`, `in`, `on`, `with`.

   Match rule (conservative by design — false positives prompt; false negatives keep item deferred):
   - A Deferred row fuzzy-matches a done task if: **(≥2 shared tokens) OR (Jaccard overlap ≥ 0.60)**
     where Jaccard = |intersection| / |union| of the two token sets.

   For each match, prompt the user exactly once:
   ```
   Deferred item '<item>' overlaps completed task '<task>' — remove from Deferred? [y/N]
   ```
   - Remove the Deferred row **only on explicit `y` response**.
   - On `N`, empty input, or anything else: keep the row (safe default).

   Write the updated `docs/progress.md` only if at least one row was removed.

   Example prompt/response flow:
   ```
   Deferred item 'Pipeline phase-as-subagent architecture (Part A)' overlaps completed task
   'Add Step 5.0 Mode Detection + conditional dispatch in SKILL.md' — remove from Deferred? [y/N]
   > N
   (row preserved)

   Deferred item 'Pipeline external orchestrator (Part B)' overlaps completed task
   'Wire up the main feature loop' — remove from Deferred? [y/N]
   > y
   (row removed from Deferred table)
   ```

   Implementation notes:
   - Use python3 for tokenization/scoring (jq not installed — `feedback_hooks_jq.md`).
   - Audit runs only when both tables are non-empty.
   - This step is advisory and non-blocking — any error reading or writing `progress.md` logs a warning
     and continues to the next step without halting.

12. Output What's Next:

```
---

Branch cleaned up. Main is up to date.

Next: Run /clear to reset context and start fresh for the next task.

---
```

## Safety Rules

- NEVER delete main or master
- Only delete branches confirmed merged (use -d not -D by default)
- If uncommitted changes exist, stash first and warn
- Always pull main before starting next work
