<!--
diataxis: reference
-->
# Credits

Pipelinekit ships under the MIT license and stands on the shoulders of several upstream projects, plus inspiration from individual researchers and the Claude platform itself. This page consolidates every vendored upstream + its pinned SHA + license, plus the inspirational-but-not-vendored credits.

## Vendored upstreams (legal attribution)

These projects contributed source code that lives inside the pipelinekit tree. Each has a per-directory `NOTICE.md` with the full upstream license text inline. Re-vendoring procedures are documented in each NOTICE so updates stay mechanical.

| Upstream | Pinned SHA | License | Vendored into | Scope |
|---|---|---|---|---|
| [wshobson/agents](https://github.com/wshobson/agents) | `08ded5e7` | MIT (© 2024 Seth Hobson) | `claude/agents/` | 2 specialist agents (deployment-engineer, incident-responder) |
| [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | `0d477a06` | MIT (© 2025 Alireza Rezvani) | `claude/agents/personas/`, `claude/skills/{write-a-skill,zoom-out}/` (via mattpocock), referenced by `documentation/SKILL-AUTHORING-STANDARD.html` + `documentation/SKILL_PIPELINE.html` | Skill-authoring DNA template (10 patterns), SKILL pipeline lifecycle reference, persona pack |
| [alirezarezvani/ClaudeForge](https://github.com/alirezarezvani/ClaudeForge) | `6eb741b4` | MIT (© 2025 Alireza Rezvani) | `claude/agents/claude-md-guardian.md`, `claude/skills/claude-md-enhancer/` | CLAUDE.md drift detection + best-practices audit; the parent claude-md-enhancer skill |
| [mattpocock/skills](https://github.com/mattpocock/skills) | `e74f0061` | MIT (© Matt Pocock) | `claude/skills/tdd/`, `claude/skills/write-a-skill/`, `claude/skills/zoom-out/` | TDD doctrine pack (deep-modules, interface-design, mocking, refactoring, tests), skill-authoring helper, zoom-out reflection skill |

### What "pipelinekit deltas" means

For every vendored file, pipelinekit applies a small, documented set of transformations so re-vendoring stays mechanical:

1. **HTML-comment attribution header** prepended to the top of each file, naming the upstream + short SHA + license.
2. **Frontmatter rewrites** where upstream conventions diverge (e.g., ClaudeForge's `permissions:` block is dropped; `model: haiku` → `model: sonnet`).
3. **Integration appendix** appended to the END of the file (e.g., agents get a `## Pipelinekit Integration — /review` block).
4. **Re-vendor procedure** documented in the per-directory `NOTICE.md` so a future maintainer can pull a new SHA and re-apply deltas without re-reading this page.

The deltas are intentionally surface-level — pipelinekit does NOT rewrite upstream prose, examples, or doctrine. Re-vendoring is mostly mechanical: bump the SHA, re-fetch the file, re-prepend the header, re-append the integration block. See any `NOTICE.md` for the canonical 7-step recipe.

## Inspirational-but-not-vendored

These projects and people influenced pipelinekit's design without contributing source code. There's no legal attribution obligation, but credit is due.

| Influence | What pipelinekit borrowed | Where it appears |
|---|---|---|
| **[Andrej Karpathy](https://karpathy.ai/)** | The autoresearch-loop pattern (hypothesize → mutate one file → benchmark → keep-or-reset → append TSV row → repeat). | `claude/skills/research/` (the `/research` skill). The `symbol-verifier` agent (anti-hallucination focus) is inspired by the same first-principles verification ethos. |
| **[Anthropic](https://www.anthropic.com/)** | The entire runtime: Claude Code, the Agent SDK, the multi-agent dispatch primitive, Skills, Hooks, MCP, the `PushNotification` tool, and the underlying Claude models that every pipelinekit phase calls. | Pervasive. Pipelinekit IS a workflow overlay on Claude Code — without Anthropic's platform there's no pipelinekit. |

## Pipelinekit's own license

Pipelinekit itself is **MIT licensed** — see [`LICENSE`](https://github.com/Bruce188/pipelinekit/blob/main/LICENSE) at the repo root. Copyright 2026 pipelinekit contributors.

The MIT terms apply to all original pipelinekit code: the orchestrator (`claude/skills/pipeline/orchestrate.sh`), the workflow skills, the hooks, the docs-writer template + snippet library, the install scripts, and the documentation. Vendored upstream files retain their original licenses (linked above) — the per-directory `NOTICE.md` is authoritative for each one.

## How to add a new upstream

If you're vendoring a new upstream into pipelinekit, the convention is:

1. **Pin a SHA.** Never reference `main` or `HEAD` — always a specific commit. Document the pinning command (`gh api repos/<owner>/<repo>/commits/HEAD --jq .sha`) in the NOTICE.
2. **Write a `NOTICE.md`** in the same directory as the vendored files. Include: upstream URL, pinned SHA, upstream file paths, license, pipelinekit deltas, re-vendor procedure.
3. **Prepend HTML-comment attribution headers** to each vendored file (so a reader of the file alone can trace it back).
4. **Add a row to the table on this page** so the cross-project audit stays current.
5. **Add a row to the [skills audit](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/docs-writer/skills-audit.py)** if the vendored upstream adds new user-facing skills.

The goal is that any future maintainer can re-vendor every upstream by following the per-NOTICE recipe — no detective work, no implicit knowledge.
