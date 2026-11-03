---
diataxis: reference
---

<!-- richness-exempt: license and attribution reference; a short table needs no interactivity -->

# Credits

These are pipelinekit's license and the projects it builds on.

## License

pipelinekit is MIT licensed. See [`LICENSE`](https://github.com/Bruce188/pipelinekit/blob/main/LICENSE).

## Upstreams

pipelinekit v0.1.0 contains no vendored third-party source. The vendored agents and skills in 0.0.1 came from [wshobson/agents](https://github.com/wshobson/agents), [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills), [alirezarezvani/ClaudeForge](https://github.com/alirezarezvani/ClaudeForge) and [mattpocock/skills](https://github.com/mattpocock/skills). All of them were removed with the pipeline. Their notices are still in the git history of earlier releases.

| Project | Role |
|---------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | The runtime that the hooks, skills and agent plug into |
| [serena](https://github.com/oraios/serena) | MCP server for symbol navigation, installed at a pinned commit |
| [context7](https://github.com/upstash/context7) | Optional MCP server for library docs |
| [gitleaks](https://github.com/gitleaks/gitleaks) | Secret scanner used by the repo's pre-commit hook |
| [Python-Markdown](https://python-markdown.github.io/) and [Pygments](https://pygments.org/) | Used by the `docs-writer` renderer |
