# GitHub Issues Integration

## Overview

`/pipeline --issues \<selector\>` ingests open GitHub Issues as an alternative
feature source, converting each issue into one H2 section in `docs/features.md`
and processing it through the standard autonomous pipeline.

**When to use `--issues` vs `docs/features.md`:**

- Use `--issues` when your team tracks work in GitHub Issues and you want the
  pipeline to pull from there directly without manually authoring a feature file.
- Use `docs/features.md` when you want full editorial control over the feature
  list, or when features do not map one-to-one with open issues.

**Default behavior unchanged:** when `--issues` is absent, the pipeline reads
`docs/features.md` as before. No behavioral change for existing workflows.

---

## CLI surface

All `--issues-*` flags are ignored when `--issues` is absent.

| Flag | Description |
|------|-------------|
| `--issues label:\<name\>` | Fetch open issues with label \<name\> |
| `--issues milestone:\<name\>` | Fetch open issues in milestone \<name\> |
| `--issues all` | Fetch all open issues (no filter) |
| `--issues \<name\>` | Bare value — defaults to `label:\<name\>` |
| `--issues-sort created` | Sort by creation date (default) |
| `--issues-sort updated` | Sort by last-updated date |
| `--issues-sort priority` | Sort by `priority:high/medium/low` labels (client-side) |
| `--issues-limit \<N\>` | Cap fetched issues at \<N\> (default 50, max 200) |
| `--issues-comment-author \<login\>` | Override maintainer heuristic for constraint extraction |

**Mutual exclusivity:** `--issues` cannot be combined with `--plan`, `--adopt`,
`--renew`, `--from`, or a positional feature-file path. Violating this stops the
pipeline with:

```
ERROR: --issues is mutually exclusive with --plan/--adopt/--renew/--from/positional path
```

---

## Issue → feature mapping

Each open issue becomes one `## \<type\>/issue-\<N\>-\<slug\>` section in
`docs/features.md`.

### Commit type

First match wins:

1. **Title prefix:** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`,
   `perf:`, `style:`, `build:`, `ci:`.
2. **Label:** `bug` → `fix`; `enhancement` → `feat`; `documentation` → `docs`;
   `refactor` → `refactor`; `performance` → `perf`; `chore` → `chore`.
3. **Bracket prefix:** `[BUG]` → `fix`; `[FEAT]` → `feat`; `[REFACTOR]` → `refactor`.
4. **Default:** `feat`.

### Slug derivation

Starting from the issue title:

1. Strip leading conventional prefixes (`feat:`, `[BUG]`, etc.).
2. Strip punctuation; downcase; collapse whitespace → `-`.
3. Cap at 50 characters at a word boundary.
4. If empty after normalization → fall back to `issue-<N>`.

### Body normalization (`**Description:**`)

1. Strip HTML comments (`<!-- ... -->`).
2. If body matches the bug-report template, extract user-authored prose
   paragraphs only.
3. Collapse multiple blank lines.
4. Cap at 2 KB; truncate at word boundary, append `… (see issue #<N> for full body)`.
5. If empty → `**Description:** See issue #<N>. No body provided.`

### Constraint extraction (`**Constraints:**`)

Merged from three sources (in priority order):

1. Issue body H2 sections named `Constraints`, `Requirements`,
   `Acceptance Criteria`, `Specification`, or `Spec`.
2. Maintainer comments that begin with `Constraints:`, `Requirements:`, or
   `Acceptance:`. Maintainer = repo owner or first commenter (or
   `--issues-comment-author \<login\>` override).
3. Labels with `requires:` prefix → individual constraint bullets.

If none → `**Constraints:** None stated.` Cap at 2 KB.

### Branch naming

```
\<type\>/issue-\<N\>-\<slug\>
```

Examples: `feat/issue-42-add-foo`, `fix/issue-103-login-redirect-loop`,
`refactor/issue-204-extract-validator`.

### PR body: `Closes #N`

The PR body assembled by `/pipeline` Path A (automatic) and `/ppr` (human-driver)
appends `Closes #<N>` to the `## Summary` section when the branch matches the
`^[a-z]+/issue-([0-9]+)-` pattern.

**Dedup mechanism:** `Closes #<N>` is emitted by a conditional printf that fires only when
`ISSUE_NUM` is non-empty (i.e., the branch matches `^[a-z]+/issue-([0-9]+)-`). For
non-issue branches, `ISSUE_NUM` is empty and no close keyword is appended. Exactly one
`Closes #N` line appears per issue-sourced PR body.

---

## Auto-close mechanism

GitHub automatically closes an issue when a PR containing a
[close keyword](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue)
(`Closes #<N>`, `Fixes #<N>`, `Resolves #<N>`) is **squash-merged** into the
default branch.

**Why `Closes` lives in the PR body, not the commit subject:**

- GitHub parses close keywords from PR bodies and commit messages, but only
  squash-merge commits (not individual feature-branch commits) trigger the
  auto-close on the default branch.
- Embedding `Closes #<N>` in the PR body is more robust: it survives rebase
  strategies and does not clutter commit history with tracking metadata.

**Post-merge verification (advisory):**

```bash
gh issue view <N> --json state -q '.state'
```

If the issue is still `OPEN` after merge, the GitHub keyword was not recognized
(e.g., wrong branch target, keyword typo). Resolve manually with `gh issue close <N>`.

---

## Examples

**Single feature from label:**

```bash
/pipeline --issues label:bug
```

Fetches all open issues labeled `bug`, maps each to `fix/issue-\<N\>-\<slug\>`.

**Milestone-scoped batch:**

```bash
/pipeline --issues milestone:v1.0
```

Fetches all open issues in milestone `v1.0`.

**Priority sort:**

```bash
/pipeline --issues all --issues-sort priority
```

Fetches all open issues, sorts `priority:high` before `priority:medium` before
`priority:low` before unlabeled.

**Limit override:**

```bash
/pipeline --issues all --issues-limit 10
```

Fetches all open issues but processes only the top 10 by creation date.

**Branch examples:**

```
feat/issue-42-add-foo
fix/issue-103-login-redirect-loop
refactor/issue-204-extract-validator
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ERROR: gh CLI not installed` | `gh` binary absent | Install: https://cli.github.com/ |
| `ERROR: gh not authenticated` | No valid GitHub token | Run `gh auth login` |
| `ERROR: --issues requires a GitHub remote` | Repo has no `origin` | `git remote add origin \<url\>` |
| `ERROR: No open issues match selector` | Label/milestone typo or no open issues | Check spelling: `gh label list` / `gh api repos/{owner}/{repo}/milestones` |
| `WARN: \<N\> issues match selector; processing top \<limit\>` | More issues than limit | Increase `--issues-limit` or use a narrower selector |
| Empty issue body → emits `See issue #<N>. No body provided.` | Issue was opened without a body | Add description to the issue on GitHub, then re-run |
| Multiple PRs reference same issue → advisory log | Team opened > 1 PR for the same issue | Close duplicate PRs manually; advisory does not block merge |
| Rate limit error | Too many `gh` API calls in a short window | Wait for reset: `gh api rate_limit` shows reset time |
