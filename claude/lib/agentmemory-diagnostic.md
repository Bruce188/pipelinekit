# agentmemory MCP — Diagnostic Run Log

> One-shot diagnostic evidence captured during `fix/agentmemory-restore-or-demote` (F17). This is not steady-state documentation — it is the record of why `provision_agentmemory_mcp()` in `scripts/install.sh` had to write to two paths.

## Diagnostic Run Log

### Symptom

After running `bash scripts/install.sh` on a fresh checkout, the agentmemory MCP did not appear in `claude mcp list`. Skills that gated on `mcp__agentmemory__memory_recall` silently degraded to "agentmemory not configured" on every dispatch. Memory writes routed to flat-file at `~/.claude/projects/<slug>/memory/*.md` continued to work, but agentmemory was the intended canonical surface and never came online.

### Root cause

`provision_agentmemory_mcp()` (formerly only the legacy write block at `scripts/install.sh` ~line 770) wrote the MCP server entry ONLY to:

```
${CLAUDE_HOME}/.mcp.json
```

where `CLAUDE_HOME` is the pipelinekit-local Claude directory (typically `~/.claude/`). However, **Claude CLI does not read `~/.claude/.mcp.json`** when computing the `mcp list`. The canonical configuration surface for user-scope MCP servers is:

```
~/.claude.json   (top-level, NOT inside ~/.claude/)
```

with the `mcpServers` block at the root of that JSON object.

The legacy `${CLAUDE_HOME}/.mcp.json` path is a phantom — it was preserved from an earlier Claude Code build that read MCP entries from that location, but current CLI ignores it. Selftest fixtures (`_selftest_agentmemory_mcp_provisioned`) grepped the legacy file, so the test passed even when no server was actually wired into the user's CLI.

A secondary failure mode contributed: the env block hardcoded literal `${VOYAGE_API_KEY}` / `${OPENAI_API_KEY}` placeholders. When the user's shell had neither variable set, Claude CLI warned about missing env vars and refused to connect the server even if the entry was in the right file.

### Fix

`provision_agentmemory_mcp()` now writes to BOTH paths:

1. **Step 3a (legacy)** — preserves the `${CLAUDE_HOME}/.mcp.json` write for backward compat and to keep the existing `_selftest_agentmemory_mcp_provisioned` sandbox passing without rewriting fixtures.
2. **Step 3b (user-scope)** — adds a parallel write to `~/.claude.json` that:
   - Loads existing JSON if present (preserves all top-level keys: `numStartups`, `userID`, `autoUpdates`, `fsdSetup`, ...).
   - Defends against corrupt JSON / non-object root / non-object `mcpServers` block with `sys.exit(0)` warn-and-skip — never overwrites a settings file we can't safely merge.
   - Backs up the existing file to `~/.claude.json.bak-<unix-ts>` before write.
   - Atomic write via temp file + `os.replace`.
   - Idempotent on re-run: merges rather than replaces.

Additionally, the env block now conditionally includes `VOYAGE_API_KEY` / `OPENAI_API_KEY` only when those vars are set in the installer's shell, eliminating the "missing env var" warning when neither key is configured (the `local-onnx-quant` fallback handles that case at runtime).

### Verification (manual smoke — DEFERRED from F17 dispatch)

The F17 subagent was forbidden from running `bash scripts/install.sh` against the live `~/.claude.json` (destructive without user consent). Manual verification steps for the user:

```bash
# 1. Run the installer (it will back up ~/.claude.json before merging)
bash scripts/install.sh

# 2. Confirm the merge: agentmemory should appear in user-scope MCP list
claude mcp list | grep agentmemory
# Expected: agentmemory: ✓ Connected (or: agentmemory: starting)

# 3. Confirm backups exist
ls -la ~/.claude.json.bak-* 2>/dev/null
# Expected: at least one backup file with current-day timestamp

# 4. Confirm unrelated top-level keys survived the merge
python3 -c "import json; d=json.load(open('~/.claude.json'.replace('~','/home/$USER'))); print(sorted(d.keys()))"
# Expected: includes pre-existing keys (e.g. numStartups, userID, fsdSetup, autoUpdates)

# 5. From inside Claude Code, call memory_recall in a probe session
#    Should return canonical entries (or empty list if fresh install — both indicate the server is connected).
```

### Skill-side verification (in-dispatch, completed)

```bash
grep -l "memory_recall" \
  claude/skills/analyze/SKILL.md \
  claude/skills/create-plan/SKILL.md \
  claude/skills/implement-plan/SKILL.md \
  claude/skills/review/SKILL.md
# Returns all 4 files — confirmed in the F17 commit.
```

### Files touched by the fix

- `scripts/install.sh` — `provision_agentmemory_mcp()` function (lines ~755–913). +114 net lines.
- `claude/skills/analyze/SKILL.md` — Step 3.5 sub-step 0 (memory_recall probe) + Step 5 `## Memory Context` template block + `mcp__agentmemory` in `allowed-tools`.
- `claude/skills/create-plan/SKILL.md` — Step 1.5 sub-step 0 (memory_recall probe) + `mcp__agentmemory` in `allowed-tools`.
- `claude/skills/implement-plan/SKILL.md` — Step 1.2a (memory_recall probe, before local-rag) + `mcp__agentmemory` in `allowed-tools`.
- `claude/skills/review/SKILL.md` — Step 3c (canonical memory recall, alongside prior review findings) + `mcp__agentmemory` in `allowed-tools`.
- `claude/CLAUDE.md.template` — `## Memory System` rewritten with explicit `### Primary surface — agentmemory MCP` and `### Secondary surface — flat-file rollback window` to resolve the canonical-vs-legacy ambiguity.

### Why this is a one-shot diagnostic

Once the fix is merged and verified manually by the user, this file becomes historical evidence — the kind of artefact you keep around for six months in case the symptom recurs, then archive. It is NOT documentation of how agentmemory currently works (that lives in `claude/CLAUDE.md.template` § Memory System) and NOT a runbook for diagnosing future MCP-registration bugs (those should be filed against the relevant MCP server's docs). Treat it as a tombstone for the specific phantom-path bug fixed in F17.
