---
diataxis: reference
---

<!-- richness-exempt: license and attribution reference; a short table needs no interactivity -->

# Credits

These are pipelinekit's license and the projects it builds on.

## License

pipelinekit is MIT licensed. See [`LICENSE`](https://github.com/Bruce188/pipelinekit/blob/main/LICENSE).

## Upstreams

pipelinekit v0.1.0 vendors one third-party skill: `frontend-design` from [anthropics/skills](https://github.com/anthropics/skills), unchanged, under the Apache License 2.0. Its `LICENSE.txt` is next to it in `claude/skills/frontend-design/`, and `SOURCE.md` there records the commit and the checksums. The vendored agents and skills in 0.0.1 came from [wshobson/agents](https://github.com/wshobson/agents), [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills), [alirezarezvani/ClaudeForge](https://github.com/alirezarezvani/ClaudeForge) and [mattpocock/skills](https://github.com/mattpocock/skills). All of them were removed with the pipeline. Their notices are still in the git history of earlier releases.

| Project | Role |
|---------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | The runtime that the hooks, skills and agent plug into |
| [anthropics/skills](https://github.com/anthropics/skills) | Source of the `frontend-design` skill: `skills/frontend-design` at commit `41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`, Apache-2.0, vendored unchanged |
| [serena](https://github.com/oraios/serena) | MCP server for symbol navigation, installed at a pinned commit |
| [context7](https://github.com/upstash/context7) | Optional MCP server for library docs |
| [gitleaks](https://github.com/gitleaks/gitleaks) | Secret scanner used by the repo's pre-commit hook |
| [Python-Markdown](https://python-markdown.github.io/) and [Pygments](https://pygments.org/) | Used by the `docs-writer` renderer |
