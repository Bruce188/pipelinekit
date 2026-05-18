# Memory Index

This is the scaffold for your auto-memory store. Claude populates this as you work.

## Recency-weighted confidence

Each entry below carries `last_seen` (date the underlying file was last touched or revalidated) and `confidence` (a 0.0–1.0 weight). Compute current confidence on read with the decay rule:

```
confidence_now = confidence * (1 - 0.05) ^ weeks_since_last_seen
```

Memories below `confidence_now ≈ 0.6` should be cross-checked before being treated as ground truth. When you re-validate an entry (re-read it and confirm it still applies), update its `last_seen` to today and reset `confidence` to 1.0. When a memory is contradicted in a session, drop confidence to 0.3 and add a `superseded_by:` pointer.

## User
<!-- e.g., - [User Profile](user_profile.md) — short hook. `last_seen: 2026-05-15, confidence: 1.0` -->

## Feedback
<!-- e.g., - [Worktree Commit](feedback_worktree_commit.md) — agents must commit before reporting done. `last_seen: 2026-05-15, confidence: 1.0` -->

## Project
<!-- e.g., - [Q3 Migration](project_q3_migration.md) — scope and constraints. `last_seen: 2026-05-15, confidence: 1.0` -->

## Reference
<!-- e.g., - [Linear pipeline](reference_linear.md) — pipeline bugs tracked in INGEST project. `last_seen: 2026-05-15, confidence: 1.0` -->

<!-- Agentmemory (opt-in, community): when installed via CLAUDE_INSTALL_OPTIONALS=agentmemory, the vendored claude/lib/agentmemory/ skeleton adds a structured-retrieval layer (semantic similarity, decay, contextual recall) over the markdown memory files indexed above. Flat-file remains the canonical write path; agentmemory is a secondary index. See claude/lib/agentmemory/README.md. -->
