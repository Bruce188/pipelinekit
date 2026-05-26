<!--
diataxis: explanation
-->
# Memory Migration Notes

How pipelinekit migrates from flat-file memory to agentmemory MCP.

## Background

Prior to F8, Claude saved memories as plain markdown files under `~/.claude/projects/<slug>/memory/*.md`. The agentmemory MCP replaces this flat-file store as the canonical write and read surface, adding Ebbinghaus-curve decay, relation-graph consolidation, and cross-session semantic retrieval.

## Overview

pipelinekit's memory system has moved to the agentmemory MCP as the canonical write and read surface. The legacy flat-file store under `~/.claude/projects/<slug>/memory/*.md` remains readable for a 30-day rollback window, after which cleanup is handled by a separate future feature.

The migration affects how Claude saves and retrieves memories during sessions. Previously, saves landed as plain markdown files. Now they route through `memory_save` and retrieval uses `memory_recall` or `memory_smart_search`. Recency-weighted relevance is computed automatically by agentmemory using an Ebbinghaus forgetting curve over `last_accessed`, removing the need to track `last_seen` / `confidence` fields manually.

The live contract governing Claude's session-time behavior lives in `claude/CLAUDE.md.template § Memory System`. When a user re-runs `bash scripts/install.sh`, the installer regenerates `~/.claude/CLAUDE.md` from the updated template, bringing the live system prompt in sync.

For the codebase structure of this toolkit, see [documentation/codebase-map.html](codebase-map.html).

## Migration Semantics

`scripts/migrate_flatfile_memory_to_agentmemory.py` is the migration script. It walks `--memory-root` (default: `~/.claude/projects`) looking for `*.md` files under `<root>/**/memory/*.md` or directly inside `<root>/*.md` (fixture-style flat layouts). It skips `MEMORY.md` (the deprecated index file).

**Default mode is `--dry-run`.** Running the script without any flag previews the migration without writing anything. Each file is summarized as:

```
dry-run: would save <path> tags=[...] category=<category>
```

**Apply mode requires explicit opt-in.** Pass `--apply` to perform the migration. The two flags are mutually exclusive — passing both is a usage error (exit 2).

**Idempotency by content hash.** The script deduplicates by SHA-256 hash of the body text (frontmatter is excluded from hashing). On a re-run, files whose body hash was already logged receive the status `skipped-duplicate`. Frontmatter changes (e.g. updating `last_seen`) do not affect the hash.

**Log path.** Applied migrations are recorded at `<memory-root>/<slug>/memory/.migration.log` (or `<memory-root>/.migration.log` for fixture-style flat layouts). Each line is a 4-tab-separated record:

```
<ISO8601 UTC>   <sha256(body)>   <source-path>   <status>
```

Status values: `applied`, `skipped-duplicate`. The `apply-no-mcp-router` status is reserved for future use when a MCP-presence probe is wired in.

**Routing marker.** Each applied file emits one JSON line on stdout:

```json
{"_payload_kind": "memory_save", "tags": [...], "category": "...", "content": "...", "ts": "..."}
```

The `_payload_kind: memory_save` key is the routing marker. A harness that learns to route MCP RPCs from stdout can grep this key and dispatch to agentmemory. Current harnesses without that routing treat the line as harmless output.

**Log-before-emit ordering.** The log entry is written before the stdout payload is emitted. On a crash between the two, the log entry survives and the second run skips the duplicate.

**apply-no-mcp-router fallback.** In F8, the script logs `applied` unconditionally — it cannot detect whether the harness has an MCP router. The `apply-no-mcp-router` status is reserved for a future release that adds a MCP-presence probe.

## 30-Day Rollback Window

The flat-file store at `~/.claude/projects/<slug>/memory/*.md` remains readable for 30 days following the migration date. During this window, the flat files serve as a side-by-side comparison surface while validating agentmemory's behavior.

**First-cleanup-eligible date formula:** `migration-date + 30 days`. The operator manually records the migration date when running `--apply` and computes the cutoff:

```
Migration date: <date you ran --apply>
First cleanup-eligible: <migration-date + 30 days>
```

**Hard-deletion of the flat-file store is deferred to a separate future feature.** F8 does NOT delete any markdown file. Do not manually remove the flat-file store until after the rollback window closes and agentmemory has been validated for your session patterns.

Operator checklist (fill in after running `--apply`):

- [ ] Migration date: ____
- [ ] First cleanup-eligible: ____
- [ ] agentmemory recall validated in a fresh session
- [ ] `PIPELINE_KEEP_FLAT_FILE_MEMORY=1` dual-write confirmed (optional)

## Dual-Write Opt-In via PIPELINE_KEEP_FLAT_FILE_MEMORY

<div data-snippet="comparison-tabs"></div>

`PIPELINE_KEEP_FLAT_FILE_MEMORY=1` is a system-prompt-level toggle. When this environment variable is set, Claude emits a flat-file sidecar alongside each `memory_save` invocation. The hook does NOT change — only Claude's session-time behavior changes.

**Sidecar filename convention:** `<category>_<tags-joined-with-underscores>.md`. For example, a `memory_save` call with `category=feedback` and `tags=[feedback, subagent-first]` produces `feedback_feedback_subagent-first.md`.

**When to use dual-write.** Set `PIPELINE_KEEP_FLAT_FILE_MEMORY=1` during the 30-day rollback window to run both the agentmemory MCP and the legacy flat-file store in parallel. This lets you diff entries, check for missing saves, and validate that agentmemory's recall rankings match expectations.

**When to turn it off.** Immediately after the rollback window closes. Dual-write is not the steady-state — it exists for the A/B verification period only. Running with the toggle indefinitely produces stale flat files that diverge from agentmemory as entries age and are consolidated.

## Verification Steps

<div data-snippet="terminal-simulator"></div>

The following steps require a live `~/.claude.json` with `mcpServers.agentmemory` (Layer-2 operator probes — deferred from the in-band test suite because they require a live MCP router).

**Step 1: Verify agentmemory is wired.**

```python
python3 -c "
import json
d = json.load(open('$HOME/.claude.json'))
print('agentmemory present:', 'agentmemory' in d.get('mcpServers', {}))
"
```

If the output is `agentmemory present: False`, re-run `bash scripts/install.sh` to provision the MCP entry.

**Step 2: Dry-run against the live memory root.**

```bash
python3 scripts/migrate_flatfile_memory_to_agentmemory.py --dry-run
```

This uses the default `--memory-root ~/.claude/projects`. Review the printed summary and tag distribution.

**Step 3: Inspect output.**

Check that file counts, tags, and categories match expectations. Common taxonomy mappings:

- `feedback_*.md` → `tags=[feedback, <name-suffix>]`, `category=feedback`
- `user_profile.md` → `tags=[profile]`, `category=user`
- `project_*.md` → `tags=[project, <slug>]`, `category=project`
- `reference_*.md` → `tags=[reference]`, `category=reference`

**Step 4: Apply.**

```bash
python3 scripts/migrate_flatfile_memory_to_agentmemory.py --apply
```

One JSON payload line is emitted per file. The `.migration.log` is written alongside each memory directory.

**Step 5: Validate recall in a fresh Claude Code session.**

Open a new Claude Code session and invoke `memory_recall` against an expected tag:

```
memory_recall(tags=["feedback"])
```

Verify the recalled entry matches a file from Step 4.

**Step 6 (optional): Validate dual-write.**

Set `PIPELINE_KEEP_FLAT_FILE_MEMORY=1` for one session and verify both surfaces are populated: an agentmemory entry AND a sidecar markdown file under `~/.claude/projects/<slug>/memory/`.
