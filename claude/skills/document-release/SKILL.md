---
name: document-release
description: Update application documentation in `documentation/` after a release. Reads the most recent merge commit (or `--since <sha>`) and `docs/progress.md`, then writes/updates `documentation/` and lands a separate `docs:` commit on the current branch. Runnable ad-hoc outside the `/pipeline` workflow.
argument-hint: [--since <sha>]
---

# Document Release

Standalone skill for updating application documentation after a release. Reads the
most recent merge commit (or a user-supplied `--since <sha>` range) and
`docs/progress.md`, then dispatches the `docs-writer` agent (or runs inline) to
update files in `documentation/` and commits the result as a `docs: ...` commit on
the current branch.

For the pipeline-integrated version, see `claude/skills/pipeline/SKILL.md`
§ Documentation Update Phase. The standalone `/document-release` skill is for
ad-hoc invocation outside `/pipeline`.

## Keywords

documentation, docs, release notes, post-release, merge commit, API docs, user guides,
architecture docs, documentation/, docs:, /document-release, docs-writer, post-merge docs

## How to Use

Natural-language invocations:
- "Update documentation/ for the last release"
- "Document the merge from `<sha>` to HEAD"
- "/document-release"
- "/document-release --since v1.2.0"

Argument:
- `--since <sha>` — explicit starting point (tag, commit SHA, or branch name); the
  skill inspects `git diff <sha>...HEAD` and `git log <sha>..HEAD --stat`. If omitted,
  the skill uses the most recent merge commit.

## Capabilities

### Default mode (no args)

Locate the most recent merge commit:
```bash
git log --merges -1 --format=%H
```
If no merge commit is found in the last 10 commits, fall back to the `HEAD~5..HEAD`
range. Use this range as the source of truth for what changed.

### Explicit range (`--since <sha>`)

Inspect the diff between the supplied SHA and HEAD:
```bash
git diff <sha>...HEAD
git log <sha>..HEAD --stat
```

### Dispatch mode

Invoke the `docs-writer` agent via the `Skill` tool or Agent tool. The agent reads
the diff and `docs/progress.md`, then writes/updates application documentation in
`documentation/`.

If the `docs-writer` skill is unavailable, run inline:
1. Read the diff output.
2. Identify changed surfaces (API endpoints, user-facing behavior, architecture).
3. Write or update files in `documentation/` directly.

### Commit mode

After the documentation update, commit the result on the current branch:
```bash
git add documentation/
git commit -m "docs: <auto-derived description>"
```
Description is derived from `docs/progress.md` feature context or the merge commit
subject. NEVER use `git commit --amend` on any prior commit — the doc update always
lands as a discrete, separate `docs:` commit.

## When to Use

- After a manual merge (outside `/pipeline`) where you want a doc update without
  re-running the full pipeline.
- After cherry-picking changes from another branch that need doc reflection.
- When the `/pipeline` Documentation Update Phase was skipped (`PIPELINE_SKIP_DOCS=1`)
  and you want to backfill the documentation.
- As a CI step in a project that prefers explicit docs invocation over auto-firing.

## When NOT to Use

- **Inside a `/pipeline` run** — the pipeline's Documentation Update Phase already
  dispatches `docs-writer` for you (cross-reference: `claude/skills/pipeline/SKILL.md`
  § Documentation Update Phase). Running both is redundant.
- **On a feature branch before merge** — the skill assumes a merged change is what
  needs documenting; for in-progress feature docs, write them inline as part of the
  feature.
- **For workflow files** (`docs/progress.md`, `docs/plan-*.md`, etc.) — the
  `docs-writer` agent contract forbids `docs/` writes
  (`claude/agents/docs-writer.md` lines 11-16). This skill writes to `documentation/`
  ONLY. NEVER write to `docs/` — that directory is reserved for AI workflow files.

## Limitations

- **Single-commit scope:** no support for selecting a non-contiguous range of commits.
- **Best-effort:** if the `docs-writer` subagent fails, the skill emits a warning and
  exits non-zero — no partial-write rollback.
- **Commit signing:** if the repo enforces signed commits and the agent's commit is
  not signed, the `git commit` will fail — re-run with appropriate signing config.

## Best Practices

- Run from the base branch (after merge has landed) — NOT from the feature branch.
- Verify `documentation/` is committed to the repo (it is, per project conventions —
  only `docs/` is excluded via `.git/info/exclude`).
- Confirm `git log` shows the expected `docs: ...` commit before pushing.
