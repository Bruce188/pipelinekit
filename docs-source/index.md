# pipelinekit documentation

The complete user-facing documentation for pipelinekit \(autonomous `/pipeline` orchestrator + skills + agents + hooks\). Every page below is self-contained HTML \(no CDN, no remote assets\) — clone the repo and open any page directly via `file://` URL, or serve the folder via any static HTTP server.

## Start here

- **[Getting started](getting-started.html)** — the master guide. Install + 4 worked tutorials \(hello-world / TDD / Vercel deploy / meta-walkthrough\). Read this first.
- [Changelog \(v0.0.1\)](changelog.html) — every PR shipped during v0.0.1 development, organized by theme.

## Reference

- [Installation](installation.html) — install pipelinekit locally, Codespaces, devcontainer, or cloud bootstrap.
- [Cloud setup](cloud-setup.html) — VPS bootstrap \(Oracle, Hetzner\) for headless Claude Code execution.
- [Pipeline workflow](pipeline.html) — the `/pipeline` autonomous orchestrator: charter discovery, analyze, plan, implement, review, merge.

## Deployment providers

- [Vercel](deployment-vercel.html) — serverless / edge / Next.js / SvelteKit / Astro.
- [Azure](deployment-azure.html) — App Service / Container Apps / Function Apps / AKS.
- [Railway](deployment-railway.html) — container-based PaaS with zero-Dockerfile deploys.
- [Render](deployment-render.html) — container-based PaaS with managed services.
- [DigitalOcean App Platform](deployment-digitalocean.html) — container-based PaaS on DO.

## Skills + features

- [`/ppr --research` flag](ppr-research-flag.html) — publish research keep-rows to a dedicated branch.
- [Research TSV viewer](tsv-viewer.html) — sortable / filterable HTML viewer for research-results TSVs.
- [GitHub Issues integration](github-issues-integration.html) — `--issues` mode for `/pipeline`.
- [`/pipeline --renew` charter revalidation](pipeline-charter-revalidation.html) — drift detection with 3-valued status + `--auto` bypass.

## Infrastructure

- [CI on Blacksmith](ci-blacksmith.html) — Blacksmith runner registration, env-var overrides, drop-in actions.
- [`/review` cost profile](review-cost.html) — token + cost characteristics of the multi-agent review surface.

## Audits

- [Claude Code compliance audit — 2026-05-19](audits/claude-code-compliance-2026-05-19.html) — 9-dimension audit of pipelinekit against Claude Code 2.1.144.
- [Feature-entries audit — 2026-05-18](audits/claude-code-compliance-features-2026-05-18.html) — earlier per-feature compliance slice.

## Reference standards \(vendored\)

- [SKILL authoring standard](docs/SKILL-AUTHORING-STANDARD.html) — the 10-pattern skill DNA template, originally vendored from alirezarezvani/claude-skills.
- [SKILL pipeline lifecycle](docs/SKILL_PIPELINE.html) — Intent → ... → Verify lifecycle.
- [Vendoring notice](docs/NOTICE.html) — attribution + license.

