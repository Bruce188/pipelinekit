---
name: feedback-subagent-first
description: "Multi-step / batched / autonomous / \"5 at a time\" work dispatches via Agent tool by default, not inline. Bundle parallel dispatches into a single message."
metadata:
  node_type: memory
  type: feedback
  last_seen: 2026-05-24
  confidence: 1
  originSessionId: c2fe837f-fixture-illustrative-only-no-pii
---

# Subagent-First

When work is multi-step, parallel-decomposable, or batched, dispatch via the [[Agent tool]] by default. Bundle multiple independent streams in a SINGLE assistant turn so they run concurrently. Inline is the EXCEPTION, reserved for one-shots under ~3 tool calls.

See also: [[agents-worktrees]] § Subagent Defaults.
