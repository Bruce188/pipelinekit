<!--
diataxis: reference
-->
# Changelog — pipelinekit v0.0.1

The complete development history of pipelinekit, organized by theme. This is the first version (v0.0.1, not yet released as a tag). PRs are linked to GitHub; the bullet summary is the one-line headline.

<div data-snippet="timeline-scrubber"></div>

## /pipeline orchestrator

The autonomous Charter → Analyze → Plan → Implement → Review → Merge loop. The user provides a feature description; pipelinekit ships a merged PR.

- [#2](https://github.com/Bruce188/pipelinekit/pull/2) — Charter Discovery mode (Step 0 of /pipeline)
- [#26](https://github.com/Bruce188/pipelinekit/pull/26) — Charter re-validation pass on `/pipeline --renew`
- [#28](https://github.com/Bruce188/pipelinekit/pull/28) — Charter auto-extract Step 0 skip condition
- [#31](https://github.com/Bruce188/pipelinekit/pull/31) — Agent-teams toggle lifted from /review to /pipeline orchestrator
- [#35](https://github.com/Bruce188/pipelinekit/pull/35) — Path M inline-fix expansion in post-review routing
- [#36](https://github.com/Bruce188/pipelinekit/pull/36) — Parallelize implement phase via single-message multi-Agent dispatch
- [#37](https://github.com/Bruce188/pipelinekit/pull/37) — Unified Run Log entry format across all pipeline writes
- [#38](https://github.com/Bruce188/pipelinekit/pull/38) — Eliminate overlay pattern from pipelinekit
- [#39](https://github.com/Bruce188/pipelinekit/pull/39) — GitHub Issues integration (`--issues` mode + `Closes #N` PR body)
- [#44](https://github.com/Bruce188/pipelinekit/pull/44) — `/pipeline --renew` charter revalidation with 3-valued status + `--auto` flag
- [#46](https://github.com/Bruce188/pipelinekit/pull/46) — Charter Topic 10 deployment-target classifier
- [#47](https://github.com/Bruce188/pipelinekit/pull/47) — Decomposition compliance gate for `/create-plan` and `/analyze`
- [#57](https://github.com/Bruce188/pipelinekit/pull/57) — Step 0 Topic 10 auto-detect probes monorepo sub-dirs
- Remove the dead `claude -p` subprocess orchestrator stub from /pipeline scope

## Multi-agent /review system

Configurable multi-agent review with auto-scaling agent selection, charter-aware classification, and findings routing.

- [#10](https://github.com/Bruce188/pipelinekit/pull/10) — Karpathy-reviewer anti-hallucination agent (Agent 6 in /review)
- [#27](https://github.com/Bruce188/pipelinekit/pull/27) — Charter-aware finding classification in /review
- [#45](https://github.com/Bruce188/pipelinekit/pull/45) — Two-axis review finding classification (scope × intent)
- [#65](https://github.com/Bruce188/pipelinekit/pull/65) — Hooks `args: string[]` exec form migration + `terminalSequence` regression test
- [#67](https://github.com/Bruce188/pipelinekit/pull/67) — Native surface docs + bundled NB cleanup from v3/v4 reviews

## Skills + agents catalog

Vendored ecosystems + native pipelinekit skills.

- [#9](https://github.com/Bruce188/pipelinekit/pull/9) — Vendor mattpocock/skills TDD doctrine pack + wire `tdd-test-writer` + `tdd-implementer` agents
- [#11](https://github.com/Bruce188/pipelinekit/pull/11) — Absorb gstack patterns — model-overlays, host-adapters, /learn, /landing-report
- [#12](https://github.com/Bruce188/pipelinekit/pull/12) — Vendor wshobson agent pack + add /incident skill
- [#13](https://github.com/Bruce188/pipelinekit/pull/13) — Vendor ClaudeForge claude-md-enhancer skill + guardian agent
- [#14](https://github.com/Bruce188/pipelinekit/pull/14) — Vendor alirezarezvani/claude-skills authoring standard + /code-health reference
- [#18](https://github.com/Bruce188/pipelinekit/pull/18) — Vendor alirezarezvani/claude-skills persona pack + wire /interview-prp + /analyze
- [#41](https://github.com/Bruce188/pipelinekit/pull/41) — pipeline-mobile-notifications — native PushNotification + Channels integration

## Cloud deployment providers

Five first-class providers, all driven from Charter Topic 10. Each ships a `<provider>-ops` skill, a `<provider>-deployment-engineer` agent, and an HTML user guide.

- [#5](https://github.com/Bruce188/pipelinekit/pull/5) — Azure CLI overlay (skill + agent + install gate + post-merge advisory)
- [#25](https://github.com/Bruce188/pipelinekit/pull/25) — Azure Mode overlay in CLAUDE.md.template
- [#30](https://github.com/Bruce188/pipelinekit/pull/30) — Vercel deployment-provider selector scaffolding
- [#53](https://github.com/Bruce188/pipelinekit/pull/53) — Azure Mode overlay in CLAUDE.md.template (v2 refresh)
- [#59](https://github.com/Bruce188/pipelinekit/pull/59) — Railway as first-class deployment provider
- [#60](https://github.com/Bruce188/pipelinekit/pull/60) — Render as first-class deployment provider
- [#61](https://github.com/Bruce188/pipelinekit/pull/61) — DigitalOcean App Platform as first-class deployment provider
- [#62](https://github.com/Bruce188/pipelinekit/pull/62) — Extract shared deployment principles into `deployment-engineer.md` base

## Sandbox infrastructure

Pluggable execution sandboxes for /pipeline subprocess invocations.

- [#7](https://github.com/Bruce188/pipelinekit/pull/7) — Pluggable SandboxProvider library with 8-agent fan-out cap
- [#21](https://github.com/Bruce188/pipelinekit/pull/21) — Switch sandbox providers to exec-style argv (eliminates shell-injection surface)
- [#22](https://github.com/Bruce188/pipelinekit/pull/22) — Optional `orchestrate.sh` subprocess driver stub
- [#23](https://github.com/Bruce188/pipelinekit/pull/23) — Fail-closed when `env-scrub.py` returns unexpected output
- [#24](https://github.com/Bruce188/pipelinekit/pull/24) — Versioned sandbox base image + build script
- [#48](https://github.com/Bruce188/pipelinekit/pull/48) — Sandbox unset-default contradiction — `worktree-only` is the correct default
- [#49](https://github.com/Bruce188/pipelinekit/pull/49) — Sandbox orchestrate wrapper — `sandbox_wrap` helper + `run_host_adapter` + `run_mcp`
- [#50](https://github.com/Bruce188/pipelinekit/pull/50) — Sandbox providers runtime-injection assertion test coverage
- [#58](https://github.com/Bruce188/pipelinekit/pull/58) — Add `ripgrep` and `fd-find` to sandbox base image
- [#70](https://github.com/Bruce188/pipelinekit/pull/70) — Extract `sandbox_wrap` into shared library

## Research loop + /research

Karpathy-style autoresearch loop (hypothesize → mutate → benchmark → keep-or-reset).

- [#8](https://github.com/Bruce188/pipelinekit/pull/8) — /research skill — Karpathy autoresearch loop driver
- [#54](https://github.com/Bruce188/pipelinekit/pull/54) — Add `parse-json` subcommand to `cost_log.py` + wire into research-loop
- [#55](https://github.com/Bruce188/pipelinekit/pull/55) — `--restart-from-iter <N>` flag for research-loop.sh
- [#56](https://github.com/Bruce188/pipelinekit/pull/56) — Wrap `claude -p` invocations in research-loop.sh with sandbox provider
- [#69](https://github.com/Bruce188/pipelinekit/pull/69) — `--research` flag on /ppr to publish research keep-rows to a branch
- [#71](https://github.com/Bruce188/pipelinekit/pull/71) — Research-results TSV viewer (sortable / filterable HTML)

## Mobile + Azure + specialized overlays

Workload-specific overlays.

- [#4](https://github.com/Bruce188/pipelinekit/pull/4) — Mobile-app workload overlay (Expo / iOS / mobile-dev agent)
- [#5](https://github.com/Bruce188/pipelinekit/pull/5) — Azure CLI overlay (also in deployment providers above)

## Hooks + enforcement

PreToolUse / PostToolUse / SessionStart / etc. hooks that enforce contracts at the Claude Code surface.

- [#19](https://github.com/Bruce188/pipelinekit/pull/19) — Worker-delegation phase 2 — CodexWorker spec + routing
- [#20](https://github.com/Bruce188/pipelinekit/pull/20) — Worker-delegation phases 4–5 + `validate-task-spec` hook
- [#33](https://github.com/Bruce188/pipelinekit/pull/33) — Subagent docs-write block via heredoc convention
- [#40](https://github.com/Bruce188/pipelinekit/pull/40) — Blacksmith runners as default CI/CD target + R5 plan-lint guard
- [#52](https://github.com/Bruce188/pipelinekit/pull/52) — R5 lint coverage for `${{ matrix.os }}` runner label
- [#63](https://github.com/Bruce188/pipelinekit/pull/63) — Normalize skill frontmatter `allowed-tools` to YAML list
- [#64](https://github.com/Bruce188/pipelinekit/pull/64) — `permissionMode: default` on azure + vercel deployment-engineers
- [#112](https://github.com/Bruce188/pipelinekit/pull/112) — Break stop-self-reflect recursion via `PIPELINE_NO_SELF_REFLECT=1` env-var guard (precursor fix; hook later removed in #117)
- [#113](https://github.com/Bruce188/pipelinekit/pull/113) — `context-budget-advisor.py` UserPromptSubmit hook — 200K-token soft cap advisory
- [#114](https://github.com/Bruce188/pipelinekit/pull/114) — Subagent-First core principle + dispatch defaults documented in `~/.claude/rules/agents-worktrees.md`
- [#115](https://github.com/Bruce188/pipelinekit/pull/115) — `agent-caveman-gate.sh` PreToolUse Agent gate enforces caveman-subagent contract inheritance on every `Agent` dispatch
- [#116](https://github.com/Bruce188/pipelinekit/pull/116) — Re-inject caveman contract on `/compact` + auto-compact via `post-compact-context.sh`; clarify SessionStart banner so main-agent narrative observes the same three-zone split
- [#119](https://github.com/Bruce188/pipelinekit/pull/119) — `subagent-first-nudge.sh` UserPromptSubmit hook makes Subagent-First the **default** mode (no trigger keyword required); per-prompt opt-out via literal phrases (`no subagents`, `do it inline`, `do it yourself`, etc.); kill switch `PIPELINE_NO_SUBAGENT_NUDGE=1`
- [#120](https://github.com/Bruce188/pipelinekit/pull/120) — Reimplement removed agentmemory feature as `memory-journal.sh` (Stop hook, append-only JSONL, no LLM call) + user-invoked `/digest-memories` skill (in-session synthesis, no `claude -p` spawn). Replaces #117's stop-self-reflect; cost is bounded and user-controlled
- [#133](https://github.com/Bruce188/pipelinekit/pull/133) — `/caveman-compress <file>` sub-command — Tier 1 in-place compression (`CLAUDE.md*`, `rules/*.md`) via deterministic shell allowlist gate + three-zone byte-preserving rewrite. Applied to 4 Tier 1 source files: total -3084 bytes (64205 → 61121).
- [#189](https://github.com/Bruce188/pipelinekit/pull/189) — WSL2 `.wslconfig` advisory in `install.sh` (`_wslconfig_advisor`: warns when `autoMemoryReclaim` is absent, prints a tuned block; opt-out `PIPELINE_NO_WSLCONFIG_ADVICE=1`) + session-aware `mcp-rss-cap.sh` (counts serena + language servers, scales the cap by live session count so concurrent sessions don't false-alarm)

## MCP integrations

Model Context Protocol servers shipped or wired.

- [#16](https://github.com/Bruce188/pipelinekit/pull/16) — claude-context community MCP as opt-in codebase semantic RAG
- [#66](https://github.com/Bruce188/pipelinekit/pull/66) — Harden `.mcp.json.template` (pin git refs)

## Bootstrap + install

Getting pipelinekit running on different hosts.

- [#3](https://github.com/Bruce188/pipelinekit/pull/3) — Oracle Cloud + Hetzner cloud bootstrap scripts
- [#15](https://github.com/Bruce188/pipelinekit/pull/15) — EnterWorktree / ExitWorktree guidance + Claude Code v2.1.72 version-floor gate

## Worker abstraction

Pluggable worker layer so /pipeline can dispatch to alternate Claude SDKs or external tools.

- (Phase 1 commit) — Worker-provider abstraction layer (phase 1 docs)
- [#19](https://github.com/Bruce188/pipelinekit/pull/19) — CodexWorker spec + routing (phase 2)
- [#20](https://github.com/Bruce188/pipelinekit/pull/20) — Phases 4–5 + `validate-task-spec` hook

## Bug fixes

- [#51](https://github.com/Bruce188/pipelinekit/pull/51) — codex.sh exec bugs — exit-code propagation, output dir, stderr, positional prompt
- [#110](https://github.com/Bruce188/pipelinekit/pull/110) — un-wire `cost_log.py` from `PostToolUse` (it's a CLI, not a hook — was emitting argparse usage errors on every tool call) + scrub three hardcoded `/home/bruce/pipelinekit/` paths from `task-spec.md`
- [#111](https://github.com/Bruce188/pipelinekit/pull/111) — README hook inventory: drop `cost_log` (not a hook); 24 → 23
- [#112](https://github.com/Bruce188/pipelinekit/pull/112) — break `stop-self-reflect` recursion via `PIPELINE_NO_SELF_REFLECT=1` env-var guard on the `claude -p` spawn (memory-thrash root cause)
- [#113](https://github.com/Bruce188/pipelinekit/pull/113) — add `context-budget-advisor.py` UserPromptSubmit hook: emits a `/compact` advisory once session context passes 200K tokens (configurable via `PIPELINE_COMPACT_THRESHOLD_TOKENS`); re-warns every +20K, resets after a 50K drop. Independent of model window size — even 1M-context models benefit from a reset around 200K because attention quality and per-call cost both degrade as context grows.

## Skill removals (breaking)

- [#29](https://github.com/Bruce188/pipelinekit/pull/29) — Deprecate `/interview-prp` in favor of `/pipeline` Step 0 Charter Discovery (banner + migration notice; skill still installed)
- [#68](https://github.com/Bruce188/pipelinekit/pull/68) — Remove deprecated `/interview-prp` skill entirely (second half of 2-release deprecation)
- [#81](https://github.com/Bruce188/pipelinekit/pull/81) — Remove `openhuman` skill and vendored `agentmemory` retrieval layer (8 orphan agents audited and dropped; installer references scrubbed)
- [#117](https://github.com/Bruce188/pipelinekit/pull/117) — Remove `stop-self-reflect` Stop hook entirely. Empirical evidence: 28 artifacts written across two projects in ~24h, 100% `{"proposals":[]}` (zero useful CLAUDE.md amendments produced) while burning ~28 min of `claude -p` Opus time + MCP load per session. Hook plus its cost-event integration (originally added in #103), recursion guard (#112), tests, charter Topic 14 ("Self-reflection"), and standalone documentation page all dropped. Charter discovery loses Topic 14; Topic 15 (Codebase Map confirmation) renumbers to Topic 14.
- [#118](https://github.com/Bruce188/pipelinekit/pull/118) — Remove `annotate-plan` skill (slash command `/annotate-plan`). Inserted in the manual workflow between `/create-plan` and `/implement-plan`; dead-by-disuse for the `/pipeline`-driven flow that drives all production use. Empirical: zero invocations across all session transcripts. Removes the skill dir, the catalog entry, and the slash-command cheatsheet row. The manual workflow stays valid — users can still hand-edit plan files between phases — just without an `/annotate-plan` orchestration helper.

## Documentation system

The system that produces this very page.

- [#6](https://github.com/Bruce188/pipelinekit/pull/6) — docs-writer post-merge phase + /document-release skill
- [#43](https://github.com/Bruce188/pipelinekit/pull/43) — docs-vs-documentation format split (markdown for LLMs, HTML for humans)
- [#67](https://github.com/Bruce188/pipelinekit/pull/67) — Native surface docs + bundled NB cleanup
- [#72](https://github.com/Bruce188/pipelinekit/pull/72) — Docs refresh post-PR44-to-PR71 (cloud providers, /ppr --research, skill/agent counts)
- [#73](https://github.com/Bruce188/pipelinekit/pull/73) — docs-writer/2 rich-template + interactive HTML throughout `documentation/`

## Counts at end of v0.0.1

- **78** commits on `main`
- **72** numbered pull requests
- **43** native skills
- **31** specialized agents
- **24** hooks (was 23 after #111; the new `context-budget-advisor` restores parity but at the UserPromptSubmit surface, not as a CLI re-wire)
- **5** cloud deployment providers (Azure, Vercel, Railway, Render, DigitalOcean) on a shared `deployment-engineer.md` base
- **18** documentation pages (all self-contained HTML, no CDN, file://-openable)
- **128** unit + shell tests, all green

## Release-flow command cheatsheet

Filter the slash-command table by `release`, `ppr`, or `pipeline` to surface the commands you reach for when cutting a new tag or rolling forward changelog entries.

<div data-snippet="command-cheatsheet"></div>
