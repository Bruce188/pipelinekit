<!--
diataxis: explanation
-->
# /ppr --research flag

/ppr --research publishes keep-rows from research-results.tsv to a research/<tag>-<date> branch. Dry-run by default. Per-branch review before merge.

<div data-snippet="terminal-simulator"></div>

/ppr --research publishes keep-rows from research-results.tsv to a research/- branch. Dry-run by default. Per-branch review before merge.

/ppr --research publishes keep-rows from research-results.tsv to a research/- branch. Dry-run by default. Per-branch review before merge.

Added in commit `1d4489c` — May 2026

The `--research` flag extends the `/ppr` skill with a separate publish path for research output. When present, `/ppr` skips the normal push-and-PR flow entirely and instead reads the "keep" rows from `docs/research-results.tsv`, creates a dedicated branch, and pushes just those rows. **Dry-run is on by default** — no writes happen unless you pass `--no-dry-run` explicitly.

## Synopsis

    /ppr --research [--dry-run | --no-dry-run] [--research-tag <slug>]

## Flags

| Flag                    | Default                        | Description                                                                                                                                          |
|-------------------------|--------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--research`            | (required)                     | Activates research-publish mode. The standard push-and-PR steps do not run.                                                                          |
| `--dry-run`             | **on**                         | Preview only. Prints the planned branch name, keep-row count, and the exact git commands that would run. No branch is created, no files are written. |
| `--no-dry-run`          | off                            | Perform the real publish: create branch, write filtered TSV, commit, push. Requires `--research-tag`.                                                |
| `--research-tag <slug>` | (required with `--no-dry-run`) | Slug appended to the branch name: `research/<slug>-YYYY-MM-DD`. Must match `^[a-zA-Z0-9._-]+$`.                                                      |

## Behavior

### Source file

Reads `docs/research-results.tsv` (produced by the `/research-loop` skill). Only rows where `status == keep` are included; the header line is always preserved. If no keep rows exist, the command prints a warning and exits cleanly without creating a branch.

### Branch naming

Branch name: `research/<tag>-YYYY-MM-DD` (UTC date at run time). If that branch already exists locally or on `origin`, suffixes `-2` through `-9` are tried in order. If all nine slots are taken, the command exits non-zero and prints instructions to clean up the old branches or choose a different tag.

### Commit message

    chore: publish research keeps for <tag> (<N> rows)

### Push behavior

Uses `git push -u origin <branch>`. No `--force`. No PR is opened.

## Examples

### Preview before committing (safe default)

    # --dry-run is the default, so both forms are equivalent:
    /ppr --research --research-tag my-experiment
    /ppr --research --dry-run --research-tag my-experiment

Output includes the planned branch name, keep-row count, and the exact git commands that *would* run. Nothing is written.

### Publish for real

    /ppr --research --no-dry-run --research-tag my-experiment

Creates `research/my-experiment-2026-05-19`, writes the filtered TSV, commits, and pushes. Exits 0 on success.

## Exit codes

| Code | Meaning                                                                                   |
|------|-------------------------------------------------------------------------------------------|
| `0`  | Success (including dry-run and zero-keep-rows cases).                                     |
| `1`  | Missing required argument, branch name exhausted, push failure, or source file not found. |

## Relationship to normal /ppr

**Important:** `--research` is a *mode selector*. When it is present, the standard Steps 1–4 of `/ppr` (safety checks, push, open PR) are completely skipped. The two modes are mutually exclusive in a single invocation.

- Normal `/ppr`: push committed changes + open PR against the base branch.
- `/ppr --research`: publish filtered research TSV to a `research/*` branch. No PR.

## Prerequisites

- `docs/research-results.tsv` must exist and contain at least a header row.
- The working directory must be a git repository with a configured `origin` remote.
- You must be authenticated to push to `origin`.

See `claude/skills/ppr/SKILL.md` for the full skill specification and `claude/skills/ppr/ppr_research_flag.sh` for the implementation.

## Pipelinekit command cheatsheet

Filter by `ppr`, `research`, or `pipeline` to surface the commands you reach for when running a research-loop iteration.

<div data-snippet="command-cheatsheet"></div>

