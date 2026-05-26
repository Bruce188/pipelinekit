<!-- snippet: typed-subagent-default v1 — 2026-05-27 -->

# Typed-subagent dispatch contract

If you dispatch further subagents, set `subagent_type` to the most specific matching specialist (e.g. `code-reviewer`, `debugger`, `docs-writer`, `security-auditor`, `test-engineer`, `performance-tuner`, `spec-tracer`, `refactor-expert`, `symbol-verifier`, `tdd-test-writer`, `tdd-implementer`, `production-probe`, `incident-responder`, `claude-md-guardian`, `mobile-dev`, `deployment-engineer`).

`general-purpose` is a fallback only when no specialist matches OR when a specialist explicitly fails (e.g. namespace collision). The fallback reason MUST be named in the dispatch prompt or surrounding narrative.

Full routing table: `~/.claude/rules/agents-worktrees.md § Typed-subagent selection rule`.
