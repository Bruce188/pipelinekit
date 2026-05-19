# Notice

Pipelinekit vendors source from several upstream projects. The authoritative attribution lives in per-directory `NOTICE.md` files inside the repo:

- [`claude/agents/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/agents/NOTICE.md) — `wshobson/agents` (10 specialist agents) + `alirezarezvani/ClaudeForge` (claude-md-guardian)
- [`claude/agents/personas/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/agents/personas/NOTICE.md) — `alirezarezvani/claude-skills` persona pack
- [`claude/skills/claude-md-enhancer/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/claude-md-enhancer/NOTICE.md) — `alirezarezvani/ClaudeForge` claude-md-enhancer skill
- [`claude/skills/tdd/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/tdd/NOTICE.md) — `mattpocock/skills` TDD doctrine pack
- [`claude/skills/openhuman/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/openhuman/NOTICE.md) — `tinyhumansai/openhuman` (concept-only — no source imported)
- [`claude/skills/write-a-skill/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/write-a-skill/NOTICE.md) — `mattpocock/skills` write-a-skill
- [`claude/skills/zoom-out/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/zoom-out/NOTICE.md) — `mattpocock/skills` zoom-out
- [`claude/lib/agentmemory/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/lib/agentmemory/NOTICE.md) — `rohitg00/agentmemory` (vendoring skeleton — SHA pinning in a follow-up iteration)

<div data-snippet="tutorial-cards"></div>

## For a consolidated view

The [Credits page](credits.html) presents every upstream + pinned SHA + license + scope + pipelinekit-deltas in a single table, plus the inspirational-but-not-vendored credits (Andrej Karpathy, Anthropic).

## Re-vendoring

Each `NOTICE.md` carries a canonical re-vendor recipe so updates stay mechanical: pick a new HEAD SHA, fetch the upstream blob, re-prepend the HTML-comment attribution header, re-apply the pipelinekit deltas (frontmatter rewrites + integration appendix), update the pinned SHA in `NOTICE.md`, commit with `chore: re-vendor <owner>/<repo> @ <short-sha>`. The Credits page summarizes the convention; the per-directory NOTICE is the authoritative recipe.

## License

Pipelinekit itself is [MIT licensed](https://github.com/Bruce188/pipelinekit/blob/main/LICENSE) (Copyright 2026 pipelinekit contributors). Vendored upstream files retain their original licenses linked above.
