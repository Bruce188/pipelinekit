# Getting started with pipelinekit

A tutorial-driven walkthrough. You'll install pipelinekit, run your first autonomous `/pipeline`, then work through three real-world scenarios — a TDD feature, a Vercel deploy, and a meta-walkthrough of how pipelinekit built one of its own features.

## What pipelinekit gives you

> [INFO] **pipelinekit** is an autonomous orchestrator for Claude Code. You write a one-line feature description; it ships a merged PR. Charter Discovery → Analyze → Plan → Implement → Review → Merge, all driven by multi-agent dispatch with no human in the loop unless you opt in.

The 30-second pitch:

- **43 skills + 31 agents + 24 hooks** wired together so `/pipeline` can take a feature from charter to merged PR without intervention.
- **5 cloud deployment providers** (Azure, Vercel, Railway, Render, DigitalOcean) on a shared `deployment-engineer.md` base — your charter selects one, /pipeline routes deployment automatically.
- **Sandbox-isolated execution** — every subprocess in a podman/docker/worktree sandbox with auto-detected provider chain.
- **TDD doctrine baked in** — `dev`-class features auto-route through `tdd-test-writer` → `tdd-implementer` for red/green pairing.
- **Multi-agent /review** — 2-6 specialized review agents (test-engineer, security-auditor, symbol-verifier, spec-tracer, code-reviewer) with charter-aware finding classification + Path A/B/M/N routing.
- **No CDN, no remote assets** — every documentation page you're reading is a single self-contained HTML file. Clone the repo, open `documentation/index.html` directly via `file://`, no server needed.

## Prerequisites

- A POSIX shell environment: Linux, macOS, or WSL2 on Windows. (Native Windows via Git Bash works for most things; some hooks assume bash/POSIX semantics.)
- [Claude Code](https://code.claude.com) installed. Pipelinekit currently floor-pins Claude Code `>= 2.1.72` for `EnterWorktree` / `ExitWorktree` and other native surfaces.
- Node.js 20+ (recommended) for some MCP servers and tooling.
- `git` and `gh` (GitHub CLI), authenticated against your GitHub account if you want /pipeline to open and merge PRs.
- Python 3.11+ for hooks and the docs-writer renderer.

## Install

```bash
# 1. Clone
git clone https://github.com/Bruce188/pipelinekit ~/pipelinekit
cd ~/pipelinekit

# 2. Run the installer (sets up ~/.claude/ skills/agents/hooks/configs)
bash scripts/install.sh

# 3. Verify
ls ~/.claude/skills/pipeline ~/.claude/agents/code-reviewer

# 4. Open the documentation index
xdg-open documentation/index.html    # Linux
open documentation/index.html         # macOS
start documentation/index.html        # Windows / WSL
```

For headless / VPS install (Oracle Cloud, Hetzner, Codespaces), see [cloud-setup.html](cloud-setup.html). For per-host install variants (mobile, devcontainer), see [installation.html](installation.html).

## Choose your tutorial

<div data-snippet="tutorial-cards"></div>

## Tutorial 1 — Hello world: ship a one-line feature autonomously

The smallest possible /pipeline run. You write a one-line feature description; /pipeline ships a merged PR.

### Setup

In any git repo (your own, or a sandbox), create a `docs/features.md` with a single feature:

```markdown
## fix/readme-typo

**Description:** Fix the typo in README.md where "occured" should be "occurred".

**Constraints:** Single-file edit. No new tests. Non-dev feature class (no TDD routing). Verify the fix landed by re-reading README.md.

### Run Log
```

### Run

```bash
cd ~/your-repo
claude    # open an interactive Claude Code session
```

In the Claude session:

```
/pipeline docs/features.md
```

### What happens

> [INFO] Charter Discovery (Step 0) opens with 10 structured questions to align you and the pipeline on what you're building. For a one-line typo fix you can answer with `--no-charter` to skip discovery, or `ship the charter now` partway through to write whatever's collected and continue.

Behind the scenes:

1. **Analyze** subagent reads `docs/features.md`, identifies `README.md` as the target, finds "occured", produces `docs/analysis-v1.md`.
2. **Plan** subagent writes a 1-task plan and prompts file.
3. **Branch** — `fix/readme-typo` created from `main` via the `new-branch` skill.
4. **Implement** subagent edits README, commits with conventional-commit prefix.
5. **Review** subagent runs a (lightweight, since it's a tiny diff) review pass; 0 blockers expected.
6. **Path A** — push the branch, open the PR via `gh pr create`, squash-merge via `gh pr merge --auto --delete-branch`.

Total runtime: ~3–5 minutes. You watch the orchestrator's state transitions in real time.

### Inspect the artifacts

After the merge:

```bash
git log main --oneline -3      # the typo fix should be the latest commit
cat docs/analysis-v1.md         # the analyze phase's output
cat docs/plan-v1.md             # the plan
cat docs/review-v1.md           # the review pass
```

The `docs/` artifacts are gitignored — they're per-feature scratch that won't pollute your PR.

## Tutorial 2 — TDD: add a unit-aware temperature parser

Demonstrates the `dev`-class TDD routing. /pipeline detects this is a `dev` feature and pairs `tdd-test-writer` (red phase: failing tests first) with `tdd-implementer` (green phase: implementation that passes the tests).

### Setup

Imagine a Python project that already has a `weather/` module. Create the feature:

```markdown
## feat/temperature-parser

**Type:** dev

**Description:** Add a `parse_temperature` function that takes a string like `"23.5°C"` or `"74°F"` and returns a `Temperature` dataclass with `value: float` and `unit: Literal["C", "F"]`. Round to one decimal place. Raise `ValueError` for unparseable input (e.g., `"hot"`, `""`, `"23 degrees"`).

**Constraints:** Add `weather/temperature.py` with the function + dataclass. Add `weather/tests/test_temperature.py` with at least 8 test cases covering: valid Celsius, valid Fahrenheit, whitespace tolerance, decimal precision, missing unit symbol, invalid string, empty string, and the rounding boundary. Use `pytest` test framework (already in this project). No new dependencies.

### Run Log
```

### Run

```
/pipeline docs/features.md
```

### What happens differently from Tutorial 1

The orchestrator detects `**Type:** dev` and routes the implement phase through the TDD pairing:

1. **Plan** phase produces tasks tagged with `worker: tdd-test-writer` for test tasks and `worker: tdd-implementer` for implementation tasks.
2. **Implement** dispatches `tdd-test-writer` first, with strict instructions to ONLY write failing tests (it cannot modify the implementation).
3. Once red-phase tests are in place, **Implement** dispatches `tdd-implementer` with the failing tests as input. The implementer can ONLY edit implementation files, not the tests, until tests pass.
4. **`tdd-red-phase-gate.sh` hook** enforces the contract: any commit that touches both test files and implementation files in a TDD phase is rejected.
5. **Review** then runs across the full feature, with `test-engineer` in the agent pool verifying coverage and test quality.

### Inspect

```bash
git log main --oneline -3      # both tdd-test-writer's "test:" commits and tdd-implementer's "feat:" commits
cat weather/tests/test_temperature.py
cat weather/temperature.py
```

You'll see the test file landed first (red), then implementation (green), with separate commits.

## Tutorial 3 — Ship a Next.js app to Vercel

Demonstrates end-to-end cloud-provider integration. Charter targets `vercel`; /pipeline wires deployment automatically through the `vercel-deployment-engineer` agent and the `vercel-ops` skill.

### Setup

```bash
npx create-next-app@latest my-app
cd my-app
git init && git add . && git commit -m "feat: initial Next.js scaffold"

# Pipelinekit-init: write a charter that targets Vercel
mkdir -p docs
cat > docs/charter.md <<'CHARTER'
---
created: 2026-05-19
status: ratified
---
# Project charter

## Goal
A Next.js landing page for my SaaS.

## Users
Visitors evaluating the product.

## Problem
We need a fast, SEO-friendly landing page deployed to a global edge network.

## Success
First-paint < 800ms in Lighthouse mobile.

## Non-goals
- Authentication (separate app)
- Server-side databases (use a 3rd-party API)

## Constraints
- Tailwind for styling
- Server components by default

## MVP boundary
- One landing route
- Hero + features + CTA + footer

## Prior art
- Vercel "Solid Templates" gallery

## Open questions
- Final brand colors (deferred)

## Deployment target
`vercel`

## Review style
orchestrator decides
CHARTER

# Write the feature
cat > docs/features.md <<'FEATURES'
## feat/landing-hero

**Description:** Add a hero section to the landing page with a headline, subhead, and primary CTA button. Use Tailwind for styling. Server component.

**Constraints:** Edit `app/page.tsx`. No new dependencies. Lighthouse first-paint must not regress.

### Run Log
FEATURES
```

### Run

```bash
# Authenticate Vercel first (one-time, browser-based)
vercel login

# Then in Claude Code:
claude
```

In the session:

```
/pipeline docs/features.md --charter docs/charter.md
```

### What happens

1. **Step 0 Charter Discovery** is skipped because `--charter` was provided.
2. **Step 0 Topic 10 auto-detect** finds `vercel.json` (or `next.config.js` with Next.js signals) in the working tree and auto-selects Vercel without asking.
3. **Implement** phase ships the hero component.
4. **`/pipeline` Step 7 "deploy" phase** dispatches the `@vercel-deployment-engineer` agent, which:
   - Runs `vercel whoami` to confirm auth posture (refuses to proceed if not logged in).
   - Runs `vercel --prod` to deploy to production.
   - Runs `vercel inspect` for deployment verification.
   - Polls `$VERCEL_URL/_health` (or the landing route directly) until 200.
5. **Review** then runs across the full diff with `vercel-deployment-engineer` consulted for any deployment-related findings.

### Inspect

```bash
vercel ls                       # the new deployment shows up
git log main --oneline -3       # the merged PR
cat docs/review-v1.md           # the review findings
```

For non-Vercel deployment, replace `vercel` with `railway` / `render` / `digitalocean` / `azure` in the charter's `## Deployment target` section. See the [provider guides](index.html#deployment-providers).

## Tutorial 4 — Meta: how pipelinekit built one of its own features

The most revealing tutorial: walk through `/pipeline`'s actual output for a feature shipped in this very repo. You'll read the real artifacts.

### The feature: `feat/pipeline-renew-charter-revalidation` (PR #44)

Per the v0.0.1 development log, this feature extended `/pipeline --renew` to revalidate charter lines against current repo state before regenerating feature files. Key constraint: drift detection had to be repo-introspection-only (no network calls).

### Read the artifacts

Each artifact is on `main`. They show what each phase produced.

| Phase | Artifact | What it contains |
|------|----------|------------------|
| Analyze | (would be `docs/analysis-v42.md` — gitignored, but in the [PR description](https://github.com/Bruce188/pipelinekit/pull/44)) | Audit-first findings: F12 EXTENDS an existing surface, gap analysis vs current implementation, 3 gaps to close |
| Plan | (`docs/plan-v43.md`) | 3 phases / 8 tasks / 23 ACs; Phase 1 sequential ×4; Phase 2 parallel-safe ×3; Phase 3 sequential gate |
| Implement | 7 commits squashed into PR #44 | charter_revalidate.py extension + reference.md sub-step 6.5 + SKILL.md --auto flag + tests |
| Review | (`docs/review-v44.md` to `review-v47.md`) | 4 review cycles, ended 0 blocking / 4 NB / 2 nits / 38/38 ACs PASS |
| Merge | [#44 a203c93](https://github.com/Bruce188/pipelinekit/commit/267f0bf) | Path A direct merge |

### Read the PR

Open [#44 on GitHub](https://github.com/Bruce188/pipelinekit/pull/44). The PR body has the AC matrix and the final review summary inline.

### Read the SKILL changes

```bash
git show 267f0bf -- claude/skills/pipeline/SKILL.md          # the --auto flag wire-up
git show 267f0bf -- claude/skills/pipeline/reference.md      # sub-step 6.5 extension
git show 267f0bf -- claude/lib/pipeline/charter_revalidate.py # 3-valued status + freshness
```

### What this tells you

A real /pipeline run is not magic. It's:

1. A subagent reading the feature spec + the relevant repo files (analyze phase).
2. A subagent producing a structured plan with tasks, ACs, and per-phase parallelism hints (plan phase).
3. A subagent (or multiple, when phases are parallel-safe) editing source files and committing (implement phase).
4. A subagent (or 5 in `--teams` mode) reading the diff and producing findings (review phase).
5. The orchestrator routing based on findings: Path A (merge), Path B (re-implement), Path M (inline fix), Path N (nit-only).
6. Push, PR, squash-merge.

Each artifact is on disk for you to read. The whole flow is auditable.

## Where to go next

| Topic | Read |
|------|------|
| Full per-feature documentation | [Documentation index](index.html) |
| /pipeline workflow reference | [pipeline.html](pipeline.html) |
| Install variants (devcontainer, mobile, etc.) | [installation.html](installation.html) |
| Cloud / VPS bootstrap | [cloud-setup.html](cloud-setup.html) |
| Cloud deployment providers | [Vercel](deployment-vercel.html) · [Azure](deployment-azure.html) · [Railway](deployment-railway.html) · [Render](deployment-render.html) · [DigitalOcean](deployment-digitalocean.html) |
| Research loop (`/research` skill) | [tsv-viewer.html](tsv-viewer.html) · [/ppr --research](ppr-research-flag.html) |
| GitHub Issues integration (`--issues` mode) | [github-issues-integration.html](github-issues-integration.html) |
| Charter revalidation (`--renew`) | [pipeline-charter-revalidation.html](pipeline-charter-revalidation.html) |
| CI on Blacksmith runners | [ci-blacksmith.html](ci-blacksmith.html) |
| Full changelog (v0.0.1) | [changelog.html](changelog.html) |
| Reference: skill authoring standard | [docs/SKILL-AUTHORING-STANDARD.html](docs/SKILL-AUTHORING-STANDARD.html) |
| Reference: SKILL pipeline lifecycle | [docs/SKILL_PIPELINE.html](docs/SKILL_PIPELINE.html) |

## Status

> [WARN] **Pre-release.** This is v0.0.1 — actively developed, API not yet stable. Pin to a specific commit SHA when integrating into your own workflows. Breaking changes may land in v0.0.2.

## Troubleshooting

### `/pipeline` not found in my Claude Code session

The skill resolution is `$HOME/.claude/skills/`. If `bash scripts/install.sh` ran but the skills aren't visible, check:

- Did `~/.claude/skills/pipeline/SKILL.md` get written? `ls -la ~/.claude/skills/pipeline/`
- Is your Claude Code session new (not a resumed one from before install)? Skill discovery happens at session start.
- On Windows + WSL: a Claude Desktop session running under Windows has `HOME=C:\Users\<you>`, which is a different skills root than your WSL `/home/<you>`. Install into both, or run Claude from inside WSL.

### `/pipeline` halted at a cloud-provider step

The provider's CLI auth is the user's responsibility. Run `vercel login` / `railway login` / `render login` / `doctl auth init` / `az login` interactively (outside Claude), then resume:

```
/pipeline docs/features.md --restart-from implement
```

### Review keeps cycling without converging

Path B has a default cap of 5 cycles. If you're hitting it, the planned scope is likely too large for an autonomous one-shot. Split the feature into smaller pieces with explicit ACs, or run with `--teams` for a wider review pool.

### A specific skill isn't firing when I expect

Check `~/.claude/skills/<name>/SKILL.md` frontmatter — the `description` is what Claude reads to decide when to invoke the skill. Strengthen the keywords if it's misfiring.
