<!-- Adopted from rohitg00/agentmemory @ TBD — MIT (Copyright <YYYY> rohitg00). See claude/lib/agentmemory/NOTICE.md. -->

# AgentMemory (Opt-In Memory Retrieval Layer)

> community project (NOT Anthropic-official) — review upstream before sandbox
> use and PIN the version before production use.

## What it provides

AgentMemory is an opt-in structured-retrieval layer over the existing
`~/.claude/memory/<slug>/` flat-file markdown memory system. It adds:

- **Semantic similarity** — vector-based retrieval of memories by meaning,
  not just substring match.
- **Decay** — recency-weighted scoring that down-weights stale memories
  (complements, does NOT replace, the flat-file decay rule documented at
  `claude/memory/MEMORY.md` lines 7-13).
- **Contextual recall** — retrieves memories relevant to the current
  phase / task context, scoped by tag / file / project slug.

## When to opt in

Install with `CLAUDE_INSTALL_OPTIONALS=agentmemory` (comma-list flag,
passed to `scripts/install.sh`). When not in the optional list, pipelinekit
installs and runs exactly as today — no new dependencies, no Phase Tool
Routing changes, no behavior drift.

## Complementarity with the flat-file memory system

AgentMemory is **additive**, not a replacement.

1. **Flat-file remains canonical.** Memory writes always land as plain
   markdown files (`user_profile.md`, `feedback_*.md`, `project_*.md`,
   `reference_*.md`) in `~/.claude/memory/<slug>/`. The flat-file system
   is the source of truth — agentmemory rebuilds its index from these
   files.
2. **Plain-markdown inspectability preserved.** `cat`, Read, and grep
   continue to work on every memory file. AgentMemory's vector store
   (if a separate store mode is chosen) is a secondary index, NEVER the
   only access path.
3. **One mode at a time.** The user explicitly chooses either:
   - **Same store** — vector index rebuilt from the markdown files on
     each refresh. Recommended default — preserves single-source-of-truth
     invariant.
   - **Separate store** — independent vector DB used for retrieval
     queries. The follow-up iteration documents the trade-offs.
   Never both writing concurrently — divergence between stores would
   compromise inspectability.
4. **Default behavior unchanged.** Without `agentmemory` in
   `CLAUDE_INSTALL_OPTIONALS`, every memory read / write goes through
   the flat-file path with no agentmemory involvement.

## Community status

AgentMemory is a community project (NOT Anthropic-official) maintained at
`https://github.com/rohitg00/agentmemory`. See `NOTICE.md` for vendor
attribution and the re-vendor procedure. PIN the version to a specific
commit or release before sandbox or production use.

## Deferred to follow-up iterations

- Full wiring of agentmemory queries into the `/analyze` /
  `/create-plan` / `/implement-plan` / `/review` Phase Tool Routing
  Memory Reads column (`claude/rules/workflow.md` § Phase Tool Routing).
- "Same store vs separate store" decision matrix with concrete trade-offs.
- Upstream file copy + real SHA pin (MVP keeps `**Pinned SHA:** TBD`).
- Vector-store backup / migration tooling.
- Smoke tests for the opt-in path beyond `scripts/verify.sh`.
