# pipelinekit documentation

The complete user-facing documentation for pipelinekit \(autonomous `/pipeline` orchestrator + skills + agents + hooks\). Every page below is self-contained HTML \(no CDN, no remote assets\) — clone the repo and open any page directly via `file://` URL, or serve the folder via any static HTTP server.

## System architecture

<div data-snippet="architecture-diagram"></div>

## Start here

- **[Getting started](getting-started.html)** — the master guide. Install + 4 worked tutorials \(hello-world / TDD / Vercel deploy / meta-walkthrough\). Read this first.
- [Changelog \(v0.0.1\)](changelog.html) — every PR shipped during v0.0.1 development, organized by theme.

## Reference

- [Installation](installation.html) — install pipelinekit locally, Codespaces, devcontainer, or cloud bootstrap.
- [Cloud setup](cloud-setup.html) — VPS bootstrap \(Oracle, Hetzner\) for headless Claude Code execution.
- [Pipeline workflow](pipeline.html) — the `/pipeline` autonomous orchestrator: charter discovery, analyze, plan, implement, review, merge.
- [Codebase map](codebase-map.html) — top-level repo layout with one-line purpose per directory + root file.
- [MCP LSP Setup](mcp-lsp-setup.html) — symbol-level Go-to-Definition via the serena MCP.

## Deployment + CI providers

- [Deployment + CI provider chooser](deployment-chooser.html) — not sure which provider fits? Answer six questions to find out.
- [Vercel](deployment-vercel.html) — serverless / edge / Next.js / SvelteKit / Astro.
- [Azure](deployment-azure.html) — App Service / Container Apps / Function Apps / AKS.
- [Railway](deployment-railway.html) — container-based PaaS with zero-Dockerfile deploys.
- [Render](deployment-render.html) — container-based PaaS with managed services.
- [DigitalOcean App Platform](deployment-digitalocean.html) — container-based PaaS on DO.
- [CI on Blacksmith](ci-blacksmith.html) — Blacksmith runner registration, env-var overrides, drop-in actions.

## Skills + features

> Full catalogs: [Skills](skills.html) · [Agents](agents.html)

- [`/ppr` push-PR flow](ppr.html) — everyday push + PR-open closing step of every pipeline feature.
- [`/ppr --research` flag](ppr-research-flag.html) — publish research keep-rows to a dedicated branch.
- [Research TSV viewer](tsv-viewer.html) — sortable / filterable HTML viewer for research-results TSVs.
- [GitHub Issues integration](github-issues-integration.html) — `--issues` mode for `/pipeline`.
- [`/pipeline --renew` charter revalidation](pipeline-charter-revalidation.html) — drift detection with 3-valued status + `--auto` bypass.
- [Stop self-reflection hook](stop-self-reflect-hook.html) — Stop hook proposes `CLAUDE.md` amendments per session; opt out via `PIPELINE_NO_SELF_REFLECT=1`.
- [Skills scope policy](skills-scope-policy.html) — authoring rules for the `paths:` frontmatter field and the global-by-design allowlist.

## Cost + observability

- [`/review` cost profile](review-cost.html) — token + cost characteristics of the multi-agent review surface.

## Reference standards \(vendored\)

- [SKILL authoring standard](SKILL-AUTHORING-STANDARD.html) — the 10-pattern skill DNA template, originally vendored from alirezarezvani/claude-skills.
- [SKILL pipeline lifecycle](SKILL_PIPELINE.html) — Intent → ... → Verify lifecycle.
- [Vendoring notice](NOTICE.html) — attribution + license.

## Built with / Inspired by

Pipelinekit is MIT-licensed and stands on the shoulders of several upstream projects, plus inspiration from individual researchers and the Claude platform itself.

- **[Andrej Karpathy](https://karpathy.ai/)** — the autoresearch-loop pattern (`/research`). The `symbol-verifier` anti-hallucination agent is inspired by the same first-principles verification ethos.
- **[Anthropic](https://www.anthropic.com/)** — the entire runtime: Claude Code, the Agent SDK, multi-agent dispatch, Skills, Hooks, MCP, `PushNotification`, and the underlying Claude models that every pipelinekit phase calls.

See the **[Credits page](credits.html)** for the full table of vendored upstreams (with pinned SHAs, licenses, scope, and re-vendor procedures) — wshobson/agents, alirezarezvani/{claude-skills, ClaudeForge}, mattpocock/skills.

