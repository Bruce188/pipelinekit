---
name: learn
description: Read interface for pipelinekit's per-project learnings journal. Reads ~/.pipelinekit/projects/<slug>/learnings.jsonl. The write path is the inline shell helper at claude/lib/learn-append.sh — invoked best-effort from pipeline Path A at post-review and post-merge.
argument-hint: [show|recent N|search <term>]
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
---

# Learn — Per-Project Learnings Journal (Read Interface)

Stores one lesson per line in JSONL at `~/.pipelinekit/projects/<slug>/learnings.jsonl`, where `<slug>` is the basename of `git rev-parse --show-toplevel`. The file is outside any project's git tree (lives under `$HOME`), so no `.gitignore` entry is needed in any project.

## Storage location

Path: `~/.pipelinekit/projects/<slug>/learnings.jsonl`

Slug derivation:
```bash
PROJECT_SLUG="$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo unknown)"
```

Auto-created on first write (`mkdir -p` in the helper).

## JSONL schema (one line per lesson)

```json
{
  "ts": "2026-05-17T14:23:11Z",
  "project_slug": "pipelinekit",
  "feature": "feat/integrate-gstack-natives",
  "severity": "info|warn|error",
  "category": "review|post-merge|ci|architecture|test|security",
  "lesson": "free-text 1-2 sentence lesson",
  "source": "review|post-merge"
}
```

## Write path

This skill is read-only. Writes go through `claude/lib/learn-append.sh`:

```bash
bash claude/lib/learn-append.sh --severity info --category review --source review \
  --feature "<feature-name>" --lesson "<one-line lesson>"
```

The pipeline dispatches the helper best-effort from two trigger points (Path A success only):
1. Post-review, pre-PR — captures the review outcome.
2. Post-merge gate success — captures merge SHA + post-merge regressions caught.

Failure of either dispatch does NOT downgrade the feature's terminal status (mirrors the docs-phase best-effort semantics).

## Read operations

`Skill: learn show` — print the entire journal for the current project (path resolved via slug).

`Skill: learn recent N` — print the last N entries (default 10).

`Skill: learn search <term>` — grep entries whose `lesson` field contains `<term>` (case-insensitive).

All three operations are pure reads. They never modify the journal.

## Safety

The helper aborts if `~/.pipelinekit/` ever resolves inside a project's git tree (defensive — this would mean `$HOME` is inside a repo, which is broken). The helper also creates `~/.pipelinekit/projects/<slug>/` with `mkdir -p` if missing.
