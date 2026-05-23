# pipelinekit

> **Autonomous orchestrator for Claude Code.** Write a one-line feature description; pipelinekit ships a merged PR. Charter → Analyze → Plan → Implement → Review → Merge, all driven by multi-agent dispatch with no human in the loop unless you opt in.

> ⚠️ **v0.0.1 — pre-release.** Actively developed; API not yet stable. Pin to a specific commit SHA when integrating into your own workflows.

---

## Read the docs

The complete documentation lives in [`documentation/`](documentation/). **Every page is a single self-contained HTML file** — no CDN, no remote assets, no build step. After cloning, open any page directly via `file://` URL:

```bash
xdg-open documentation/index.html    # Linux
open documentation/index.html         # macOS
start documentation/index.html        # Windows / WSL
```

Or download just the `documentation/` folder as a zip and open `index.html` — same result, no clone needed.

**Start with the master guide:** [documentation/getting-started.html](documentation/getting-started.html) — install + 4 worked tutorials (hello-world, TDD, Vercel deploy, meta-walkthrough).

---

## What pipelinekit gives you

- **42 skills + 31 agents + 24 hooks** wired together so `/pipeline` can take a feature from charter to merged PR without intervention.
- **5 cloud deployment providers** (Azure, Vercel, Railway, Render, DigitalOcean) on a shared `deployment-engineer.md` base. Your charter selects one; /pipeline routes deployment automatically.
- **Sandbox-isolated execution** — every subprocess in a podman/docker/worktree sandbox with auto-detected provider chain.
- **TDD doctrine baked in** — `dev`-class features auto-route through `tdd-test-writer` → `tdd-implementer` for red/green pairing, enforced by `tdd-red-phase-gate.sh` hook.
- **Multi-agent /review** — 2–6 specialized review agents (test-engineer, security-auditor, symbol-verifier, spec-tracer, code-reviewer) with charter-aware finding classification + Path A/B/M/N routing.
- **Research loop** — Karpathy-style autoresearch via `/research`: hypothesize → mutate → benchmark → keep-or-reset, with optional auto-publish to a branch via `/ppr --research`.
- **GitHub-native** — `--issues` mode pulls features from open issues; PR bodies auto-include `Closes #N`; squash-merge via `gh pr merge --auto --delete-branch`.

---

## Quick install

### Local (any Linux / WSL / macOS bash)

```bash
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
./scripts/install.sh
```

`install.sh` is idempotent. Re-run to update.

### Cloud cold-start (Oracle / Hetzner)

```bash
# Oracle Cloud Free Tier ARM A1 (aarch64, 24 GB RAM):
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh | bash

# Hetzner CX22 (x86_64, 4 GB RAM — swap auto-created):
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/hetzner-bootstrap.sh | bash
```

Both scripts are idempotent. Secrets read from env, never baked in. Full walkthrough: [documentation/cloud-setup.html](documentation/cloud-setup.html).

### GitHub Codespaces

Open the repo in Codespaces — the devcontainer post-create runs `install.sh` automatically. Then `claude` in the terminal to start.

### Add to an existing Claude Code session

```
"Clone https://github.com/Bruce188/pipelinekit.git into ~/work,
 cd into it, and run ./scripts/install.sh non-interactively."
```

Full install variants (devcontainer, mobile, headless, etc.): [documentation/installation.html](documentation/installation.html).

---

## First run

After install, drop a feature file in a target repo:

```bash
mkdir -p docs
cat > docs/features.md <<'EOF'
## fix/readme-typo

**Description:** Fix the typo in README.md where "occured" should be "occurred".

**Constraints:** Single-file edit. No new tests. Non-dev feature class.

### Run Log
EOF

claude
```

In the Claude session:

```
/pipeline docs/features.md --no-charter
```

That's it. The orchestrator handles the rest: analyze → plan → branch → implement → review → push → PR → squash-merge. Watch state transitions in real time. Total runtime: ~3–5 minutes for a typo fix; ~15–30 minutes for a real feature.

Full tutorial set: [documentation/getting-started.html](documentation/getting-started.html).

---

## Pipeline modes

`/pipeline` routes per feature based on `<type>/<name>` prefix in `docs/features.md`:

| Prefix | Mode | TDD |
|--------|------|-----|
| `feat`, `fix`, `refactor`, `perf`, `test` | dev | yes — tdd-test-writer → tdd-implementer |
| `docs`, `chore`, `style`, `build`, `ci`, `content`, `ops`, `research` | non-dev | skipped |

Override with `**Type:** dev|non-dev` per-feature.

---

## What's inside

| Layer | Contents |
|-------|----------|
| **Rules** | `claude/CLAUDE.md.template`, `claude/rules/workflow.md`, `claude/rules/agents-worktrees.md` |
| **Skills** (42) | `pipeline`, `analyze`, `create-plan`, `implement-plan`, `review`, `ppr`, `research`, `tdd`, `incident`, `landing-report`, `learn`, `azure-ops`, `vercel-ops`, `railway-ops`, `render-ops`, `digitalocean-ops`, `expo`, `ios`, `docs-writer`, `document-release`, `claude-md-enhancer`, `write-a-skill`, `zoom-out`, `simplify`, `caveman-mode`, ... |
| **Agents** (23) | `architect`, `code-reviewer`, `security-auditor`, `symbol-verifier`, `spec-tracer`, `tdd-test-writer`, `tdd-implementer`, `mobile-dev`, `deployment-engineer` (base), `azure-deployment-engineer`, `vercel-deployment-engineer`, `railway-deployment-engineer`, `render-deployment-engineer`, `digitalocean-deployment-engineer`, `incident-responder`, `claude-md-guardian`, ... |
| **Hooks** (24) | `validate-commit-msg`, `strip-ai-attribution`, `block-push-main`, `block-stage-sensitive`, `block-dangerous-commands`, `tdd-order-check`, `tdd-red-phase-gate`, `claude-md-guard`, `env-scrub`, `notify-emit`, `context-warning`, `context-budget-advisor`, `verify-worktree-commit`, ... |
| **MCP** | `context7`, `serena`, `sequential-thinking`, optional `local-rag` + `claude-context` |
| **LSP** | pyright, typescript, csharp, gopls, rust-analyzer |
| **Model overlays** | Per-model tuning for opus-4-7, sonnet-4-6, haiku-4-5 (consumed by phase skills) |
| **Host adapters** | claude (concrete), codex/cursor/gemini (stubs) — interface scaffold for multi-host dispatch |
| **Sandbox** | Pluggable `SandboxProvider.sh` (worktree-only default, podman, docker) with `sandbox_wrap` shared helper |

---

## Cloud deployment

Five providers, all driven from Charter Topic 10:

| Agent | Skill | Provider | Guide |
|-------|-------|----------|-------|
| `@azure-deployment-engineer` | `azure-ops` | Azure App Service / Container Apps / Function Apps / AKS | [docs](documentation/deployment-azure.html) |
| `@vercel-deployment-engineer` | `vercel-ops` | Vercel (Next.js / SvelteKit / Astro / Remix) | [docs](documentation/deployment-vercel.html) |
| `@railway-deployment-engineer` | `railway-ops` | Railway (zero-Dockerfile container PaaS) | [docs](documentation/deployment-railway.html) |
| `@render-deployment-engineer` | `render-ops` | Render (managed container PaaS) | [docs](documentation/deployment-render.html) |
| `@digitalocean-deployment-engineer` | `digitalocean-ops` | DigitalOcean App Platform | [docs](documentation/deployment-digitalocean.html) |

`claude/agents/deployment-engineer.md` is a documentation-only base describing the shared contract (auth posture, secret hygiene, health-check polling, no-direct-REST). Each named agent extends it for its provider.

---

## `/ppr --research`

Publish research keep-rows from a TSV to a dedicated branch. Dry-run by default; pass `--no-dry-run` to publish:

```bash
/ppr --research                          # dry-run (default)
/ppr --research --no-dry-run --research-tag my-experiment
```

Reference: [documentation/ppr-research-flag.html](documentation/ppr-research-flag.html).

---

## Layout

```
pipelinekit/
├── .devcontainer/         # Codespaces / VS Code devcontainer
├── claude/                # Overlay installed to ~/.claude/
│   ├── CLAUDE.md.template
│   ├── rules/
│   ├── skills/            # 42 native skills
│   │   ├── pipeline/      # The autonomous orchestrator
│   │   ├── docs-writer/   # template.html + render.py (rich-template HTML)
│   │   ├── research/      # Karpathy autoresearch loop + tsv-viewer.sh
│   │   ├── {railway,render,digitalocean}-ops/  # Cloud provider ops skills
│   │   └── ...
│   ├── agents/            # 31 specialized agents (incl. deployment-engineer base)
│   ├── hooks/             # 24 production hooks
│   ├── lib/
│   │   ├── pipeline/      # ac_lint, charter_revalidate, decomposition_check, ...
│   │   └── sandbox/       # SandboxProvider.sh + providers/ + sandbox_wrap.sh
│   ├── model-overlays/    # opus-4-7.md, sonnet-4-6.md, haiku-4-5.md, claude.md
│   ├── host-adapters/     # claude.sh (concrete), codex.sh / cursor.sh / gemini.sh (stubs)
│   ├── memory/            # MEMORY.md scaffold (empty by design; populated per project)
│   └── config/            # never-stage.txt, etc.
├── scripts/
│   ├── install.sh         # Idempotent installer
│   ├── sandbox/           # Container base image (Containerfile + Dockerfile + build.sh)
│   └── cloud/             # Oracle + Hetzner bootstrap scripts
├── documentation/         # User-facing docs — all self-contained HTML
│   ├── index.html         # Landing page
│   ├── getting-started.html  # Master guide (start here)
│   ├── changelog.html     # v0.0.1 dev log
│   ├── installation.html, pipeline.html, cloud-setup.html
│   ├── deployment-{azure,vercel,railway,render,digitalocean}.html
│   ├── docs/              # Vendored reference standards (converted to HTML in v0.0.1)
│   │   ├── SKILL-AUTHORING-STANDARD.html
│   │   ├── SKILL_PIPELINE.html
│   │   └── NOTICE.html    # Attribution + license for vendored content
│   └── audits/            # Compliance audit reports
├── .mcp.json.template     # MCP server config (copy to project root on install)
├── LICENSE                # MIT
└── README.md
```

**Note:** `docs/` is intentionally NOT in the repo tree above — it's gitignored and exclusively for AI-workflow artifacts (`analysis-vN.md`, `plan-vN.md`, `prompts-vN.md`, `review-vN.md`, `charter.md`, `progress.md`, `pipeline-state.md`, `features-vN.md`, etc.). User-facing docs live in `documentation/` and are committed as HTML.

---

## Caveman mode (wenyan-ultra)

Default verbosity in pipelinekit sessions: caveman wenyan-ultra. Drops articles, filler, hedging. Code, commits, and security-critical text remain normal English.

```
/caveman lite | full | ultra
stop caveman     # revert to normal
```

---

## Memory

Memory ships as an empty scaffold. After install, Claude builds memory in `~/.claude/projects/<project-slug>/memory/`. See [`claude/memory/MEMORY.md`](claude/memory/MEMORY.md) for the schema reference (recency-weighted confidence decay, four memory types: user / feedback / project / reference).

---

## Reference

- **[Master guide](documentation/getting-started.html)** — install + 4 worked tutorials (start here)
- [Documentation index](documentation/index.html) — every reader-facing page
- [Changelog v0.0.1](documentation/changelog.html) — every PR organized by theme
- [Pipeline workflow](documentation/pipeline.html) — /pipeline phase-by-phase reference
- [SKILL authoring standard](documentation/SKILL-AUTHORING-STANDARD.html) — vendored standard (10-pattern skill DNA)
- [SKILL pipeline lifecycle](documentation/SKILL_PIPELINE.html) — Intent → ... → Verify

---

## Credits

Pipelinekit stands on the shoulders of several upstream projects, plus inspiration from individual researchers and the Claude platform itself.

**Inspirational-but-not-vendored:**

- **[Andrej Karpathy](https://karpathy.ai/)** — the autoresearch-loop pattern (hypothesize → mutate one file → benchmark → keep-or-reset → append row → repeat) is the design behind `/research`. The `symbol-verifier` anti-hallucination agent (Agent 6 of `/review` on medium+ diffs) is inspired by the same first-principles verification ethos.
- **[Anthropic](https://www.anthropic.com/)** — the entire runtime: Claude Code, the Agent SDK, multi-agent dispatch, Skills, Hooks, MCP, `PushNotification`, and the underlying Claude models that every pipelinekit phase calls. Pipelinekit is a workflow overlay on Claude Code — without Anthropic's platform, there's no pipelinekit.

**Vendored upstreams** (full table with pinned SHAs + licenses + scope + re-vendor procedures at [documentation/credits.html](documentation/credits.html)):

- [wshobson/agents](https://github.com/wshobson/agents) — 10 specialist agents (MIT, © 2024 Seth Hobson)
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) — skill-authoring DNA + lifecycle reference + personas (MIT, © 2025 Alireza Rezvani)
- [alirezarezvani/ClaudeForge](https://github.com/alirezarezvani/ClaudeForge) — claude-md-guardian + claude-md-enhancer (MIT, © 2025 Alireza Rezvani)
- [mattpocock/skills](https://github.com/mattpocock/skills) — TDD doctrine pack + write-a-skill + zoom-out (MIT, © Matt Pocock)
Per-directory `NOTICE.md` files carry the full upstream license text and re-vendor procedures.

---

## License

MIT. See [LICENSE](LICENSE). Pipelinekit's own original code (orchestrator, hooks, docs-writer, install scripts, documentation) is MIT-licensed; vendored upstream files retain their original licenses linked above.
