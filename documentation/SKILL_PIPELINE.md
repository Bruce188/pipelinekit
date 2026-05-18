<!--
Vendored from alirezarezvani/claude-skills @ 0d477a06589aa730b98e351f46985c5c937de0bf
Upstream path: SKILL_PIPELINE.md
License: MIT — Copyright (c) 2025 Alireza Rezvani
Source: https://github.com/alirezarezvani/claude-skills/blob/0d477a06589aa730b98e351f46985c5c937de0bf/SKILL_PIPELINE.md
Do not edit in place — re-vendor from upstream and bump the SHA in documentation/NOTICE.md.
-->

# Skill Production Pipeline — claude-skills

> **Effective: 2026-03-07** | Applies to ALL new skills, improvements, and deployments.
> **Owner:** Leo (orchestrator) + Reza (final approval)

---

## Mandatory Pipeline

Every skill MUST go through this pipeline. No exceptions.

```
Intent → Research → Draft → Eval → Iterate → Compliance → Package → Deploy → Verify → Rollback-Ready
```

### Tool: Anthropic Skill Creator (v2025-03+)
**Location:** `~/.openclaw/workspace/skills/skill-creator/`
**Components:** SKILL.md, 3 agents (grader, comparator, analyzer), 10 scripts, eval-viewer, schemas

### Dependencies
| Tool | Version | Install | Fallback |
|------|---------|---------|----------|
| Tessl CLI | v0.70.0 | `tessl login` (auth: rezarezvani) | Manual 8-point compliance check |
| ClawHub CLI | latest | `npm i -g @openclaw/clawhub` | Skip OpenClaw publish, do manually later |
| Claude Code | 2.1+ | Already installed | Required, no fallback |
| Python | 3.10+ | System | Required for scripts |

### Iteration Limits
- **Max 5 iterations** per skill before escalation
- **Max 3 hours** per skill in eval loop
- If stuck → log issue, move to next skill, revisit in next batch

---

## Phase 1: Intent & Research

1. **Capture intent** — What should this skill enable? When should it trigger? Expected output format?
2. **Interview** — Edge cases, input/output formats, success criteria, dependencies
3. **Research** — Check competing skills, market gaps, related domain standards
4. **Define domain expertise level** — Skills must be POWERFUL tier (expert-level, not generic)

## Phase 2: Draft SKILL.md

Using Anthropic's skill-creator workflow:

### Required Structure
```
skill-name/
├── SKILL.md              # Core instructions (YAML frontmatter required)
│   ├── name: (kebab-case)
│   ├── description: (pushy triggers, when-to-use)
│   └── Body (<500 lines ideal)
├── scripts/              # Python CLI tools (no ML/LLM calls, stdlib only)
├── references/           # Expert knowledge bases (loaded on demand)
├── assets/               # Templates, sample data, expected outputs
├── agents/               # Sub-agent definitions (if applicable)
├── commands/             # Slash commands (if applicable)
└── evals/
    └── evals.json        # Test cases + assertions
```

### SKILL.md Rules
- YAML frontmatter: `name` + `description` required
- Description must be "pushy" — include trigger phrases, edge cases, competing contexts
- Under 500 lines; overflow → reference files with clear pointers
- Explain WHY, not just WHAT — theory of mind over rigid MUSTs
- Include examples with Input/Output patterns
- Define output format explicitly

## Phase 3: Eval & Benchmark

### 3a. Create Test Cases
- 2-3 realistic test prompts (what real users would actually say)
- Save to `evals/evals.json` (schema: `references/schemas.md`)
- Include `files` for file-dependent skills

### 3b. Run Evals
- Spawn with-skill AND baseline (without-skill) runs in parallel
- Save to `<skill>-workspace/iteration-N/eval-<ID>/`
- Capture `timing.json` from completion notifications
- Grade using `agents/grader.md` → `grading.json`

### 3c. Aggregate & Review
```bash
python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
python <skill-creator>/eval-viewer/generate_review.py <workspace>/iteration-N \
  --skill-name "<name>" --benchmark <workspace>/iteration-N/benchmark.json --static <output.html>
```
- Analyst pass (agents/analyzer.md): non-discriminating assertions, variance, tradeoffs
- User reviews outputs + benchmark in viewer
- Read `feedback.json` → improve → repeat

### 3d. Quality Gate
- **Pass rate ≥ 85%** with-skill
- **Delta vs baseline ≥ +30%** on key assertions
- No flaky evals (variance < 20%)

## Phase 4: Iterate Until Done
- Generalize from feedback (don't overfit to test cases)
- Keep prompt lean — remove what doesn't pull its weight
- Bundle repeated helper scripts into `scripts/`
- Repeat eval loop until user satisfied + metrics pass

## Phase 5: Description Optimization

After skill is finalized:

1. Generate 20 trigger eval queries (10 should-trigger, 10 should-not)
2. User reviews via `assets/eval_review.html`
3. Run optimization loop:
   ```bash
   python -m scripts.run_loop \
     --eval-set <trigger-eval.json> --skill-path <path> \
     --model anthropic/claude-opus-4-6 --max-iterations 5 --verbose
   ```
4. Apply `best_description` to SKILL.md frontmatter

## Phase 6: Compliance Check (Claude Code)

**Mandatory.** Every skill inspected by Claude Code before merge:

```bash
echo "Review this skill for Anthropic compliance:
1. No malware, exploit code, or security risks
2. No hardcoded secrets or credentials
3. Description is accurate (no surprise behavior)
4. Scripts are stdlib-only (no undeclared dependencies)
5. YAML frontmatter valid (name + description)
6. File references all resolve correctly
7. Under 500 lines SKILL.md (or justified)
8. Assets include sample data + expected output" | claude --output-format text
```

Additionally run Tessl quality check:
```bash
tessl skill review <skill-path>
```
**Minimum score: 85%**

## Phase 7: Package for All Platforms

### 7a. Claude Code Plugin
```
skill-name/
├── .claude-plugin/
│   └── plugin.json    # name, version, description, skills, commands, agents
├── SKILL.md
├── commands/          # /command-name.md definitions
├── agents/            # Agent definitions
└── (scripts, references, assets, evals)
```

**plugin.json format (STRICT):**
```json
{
  "name": "skill-name",
  "description": "One-line description",
  "version": "1.0.0",
  "author": "alirezarezvani",
  "homepage": "https://github.com/alirezarezvani/claude-skills",
  "repository": "https://github.com/alirezarezvani/claude-skills",
  "license": "MIT",
  "skills": "./"
}
```
**Only these fields. Nothing else.**

### 7b. Codex CLI Version
```
skill-name/
├── AGENTS.md          # Codex-compatible agent instructions
├── codex.md           # Codex CLI skill format
└── (same scripts, references, assets)
```
- Convert SKILL.md patterns to Codex-native format
- Test with `codex --full-auto "test prompt"`

### 7c. OpenClaw Skill
```
skill-name/
├── SKILL.md           # OpenClaw-compatible (same base)
├── openclaw.json      # OpenClaw skill metadata (optional)
└── (same scripts, references, assets)
```
- Ensure compatible with OpenClaw's skill loading (YAML frontmatter triggers)
- Publish to ClawHub: `clawhub publish ./skill-name`

### 7d. Gemini CLI Skill
```
skill-name/
├── SKILL.md           # Gemini-compatible (same base)
└── (same scripts, references, assets)
```
- Ensure compatible with Gemini CLI's `activate_skill` tool.
- Run `./scripts/gemini-install.sh` to update the local `.gemini/skills/` index.

## Phase 8: Deploy

### Marketplace
```bash
# Claude Code marketplace (via plugin in repo)
# Users install with:
/plugin marketplace add alirezarezvani/claude-skills
/plugin install skill-name@claude-code-skills
```

### Gemini CLI setup
```bash
# Users setup with:
./scripts/gemini-install.sh
```

### GitHub Release
- Feature branch from `dev` → PR to `dev` → merge → PR to `main`
- Conventional commits: `feat(category): add skill-name skill`
- Update category `plugin.json` skill count + version
- Update `marketplace.json` if new plugin entry

### ClawHub
```bash
clawhub publish ./category/skill-name
```

### Codex CLI Registry
```bash
# Users install with:
npx agent-skills-cli add alirezarezvani/claude-skills --skill skill-name
```

---

## Agent & Command Requirements

### Every Skill SHOULD Have:
- **Agent definition** (`agents/cs-<role>.md`) — persona, capabilities, workflows
- **Slash command** (`commands/<action>.md`) — simplified user entry point

### Agent Format:
```markdown
---
name: cs-<role-name>
description: <when to spawn this agent>
---
# cs-<role-name>
## Role & Expertise
## Core Workflows
## Tools & Scripts Available
## Output Standards
```

### Command Format:
```markdown
---
name: <command-name>
description: <what this command does>
---
# /<command-name>
## Usage
## Arguments
## Examples
```

---

## Phase 9: Real-World Verification (NEVER SKIP)

**Every skill must pass real-world testing before merge. No exceptions.**

### 9a. Marketplace Installation Test
```bash
# 1. Register marketplace (if not already)
# In Claude Code:
/plugin marketplace add alirezarezvani/claude-skills

# 2. Install the skill
/plugin install <skill-name>@claude-code-skills

# 3. Verify installation
/plugin list  # skill must appear

# 4. Load/reload test
/plugin reload  # must load without errors
```

### 9b. Trigger Test
- Send 3 realistic prompts that SHOULD trigger the skill
- Send 2 prompts that should NOT trigger it
- Verify correct trigger/no-trigger behavior

### 9c. Functional Test
- Execute the skill's primary workflow end-to-end
- Run each script with sample data
- Verify output format matches spec
- Check all file references resolve correctly

### 9d. Bug Fix Protocol
- **Every bug found → fix immediately** (no "known issues" parking)
- Document bug + fix in CHANGELOG.md
- Re-run full eval suite after fix
- Re-verify marketplace install after fix

### 9e. Cross-Platform Verify
- **Claude Code**: Install from marketplace, trigger, run workflow
- **Gemini CLI**: Run `scripts/gemini-install.sh`, activate skill, verify instructions
- **Codex CLI**: Load AGENTS.md, run test prompt
- **OpenClaw**: Load skill, verify frontmatter triggers

---

## Documentation Requirements (Continuous)

**All changes MUST update these files. Every commit, every merge.**

### Per-Commit Updates
| File | What to update |
|------|----------------|
| `CHANGELOG.md` | Every change, every fix, every improvement |
| Category `README.md` | Skill list, descriptions, install commands |
| Category `CLAUDE.md` | Navigation, skill count, architecture notes |

### Per-Skill Updates
| File | What to update |
|------|----------------|
| `SKILL.md` | Frontmatter, body, references |
| `plugin.json` | Version, description |
| `evals/evals.json` | Test cases + assertions |

### Per-Release Updates
| File | What to update |
|------|----------------|
| Root `README.md` | Total skill count, category summary, install guide |
| Root `CLAUDE.md` | Navigation map, architecture, skill counts |
| `agents/CLAUDE.md` | Agent catalog |
| `marketplace.json` | Plugin entries |
| `docs/` (GitHub Pages) | Run `scripts/generate-docs.py` |
| `STORE.md` | Marketplace listing |

### GitHub Pages
After every batch merge — generate docs and deploy:
```bash
cd ~/workspace/projects/claude-skills
# NOTE: generate-docs.py and static.yml workflow must be created first (Phase 0 task)
# If not yet available, manually update docs/ folder
python scripts/generate-docs.py 2>/dev/null || echo "generate-docs.py not yet created — update docs manually"
```

---

## Versioning

### Semantic Versioning (STRICT)

| Change Type | Version Bump | Example |
|-------------|-------------|---------|
| **Existing skill improvement** (Tessl optimization, trigger fixes, content trim) | **2.1.x** (patch) | 2.1.0 → 2.1.1 |
| **Enhancement + new skills** (new scripts, agents, commands, new skills) | **2.7.0** (minor) | 2.6.x → 2.7.0 |
| **Breaking changes** (restructure, removed skills, API changes) | **3.0.0** (major) | 2.x → 3.0.0 |

### Current Version Targets (update as releases ship)
- **v2.1.1** — Existing skill improvements (Tessl #285-#287, compliance fixes)
- **v2.7.0** — New skills + agents + commands + multi-platform packaging

### Rollback Protocol
If a deployed skill breaks:
1. **Immediate**: `git revert <commit>` on dev, fast-merge to main
2. **Marketplace**: Users re-install from updated main (auto-resolves)
3. **ClawHub**: `clawhub unpublish <skill-name>@<broken-version>` if published
4. **Notification**: Update CHANGELOG.md with `### Reverted` section
5. **Post-mortem**: Document what broke and why in the skill's evals/

### CHANGELOG.md Format
```markdown
## [2.7.0] - YYYY-MM-DD
### Added
- New skill: `category/skill-name` — description
- Agent: `cs-role-name` — capabilities
- Command: `/command-name` — usage

### Changed
- `category/skill-name` — what changed (Tessl: X% → Y%)

### Fixed
- Bug description — root cause — fix applied

### Verified
- Marketplace install: ✅ all skills loadable
- Trigger tests: ✅ X/Y correct triggers
- Cross-platform: ✅ Claude Code / Codex / OpenClaw
```

---

## Quality Tiers

| Tier | Score | Criteria |
|------|-------|----------|
| **POWERFUL** ⭐ | 85%+ | Expert-level, scripts, refs, evals pass, real-world utility |
| **SOLID** | 70-84% | Good knowledge, some automation, useful |
| **GENERIC** | 55-69% | Too general, needs domain depth |
| **WEAK** | <55% | Reject or complete rewrite |

**We only ship POWERFUL. Everything else goes back to iteration.**

---

*This pipeline is non-negotiable for all claude-skills repo work.*

---

## Checklist (copy per skill)

### Required (blocks merge)
```
[ ] SKILL.md drafted (<500 lines, YAML frontmatter, pushy description)
[ ] Scripts: Python CLI tools (stdlib only) — or justified exception
[ ] References: expert knowledge bases
[ ] Evals: evals.json with 2-3+ test cases + assertions (must fail without skill)
[ ] Tessl: score ≥85% (or manual 8-point check if tessl unavailable)
[ ] Claude Code compliance: 8-point check passed
[ ] Plugin: plugin.json (strict format)
[ ] Marketplace install: /plugin install works, /plugin reload no errors
[ ] Trigger test: 3 should-trigger + 2 should-not
[ ] Functional test: end-to-end workflow verified
[ ] Bug fixes: all resolved, re-tested
[ ] CHANGELOG.md updated
[ ] PR created: dev branch, conventional commit
```

### Recommended (nice-to-have, don't block)
```
[ ] Agent: cs-<role>.md defined
[ ] Command: /<action>.md defined
[ ] Assets: templates, sample data, expected outputs
[ ] Benchmark: with-skill vs baseline, pass rate ≥85%, delta ≥30%
[ ] Description optimization: run_loop.py, 20 trigger queries
[ ] Gemini CLI: ./scripts/gemini-install.sh, activate_skill(name="skill-name") verified
[ ] Codex: AGENTS.md / codex.md
[ ] OpenClaw: frontmatter triggers verified
[ ] README.md updated (category + root)
[ ] CLAUDE.md updated
[ ] docs/ regenerated
```

## Notifications

`/pipeline` surfaces push notifications when it reaches a state requiring user attention: budget breach, error, end-of-feature, human-review checkpoint, or permission prompt. Notifications use native Claude Code surfaces only — there is no custom config file or rate limiter.

### Enabling

1. **Mobile push notifications** — enable Remote Control in your Claude Code mobile app and toggle "Push when Claude decides" in your preferences. Requires Claude Code 2.1.110 or later. See the upstream Claude Code Remote Control settings page for the latest setup instructions.
2. **Desktop terminal notifications** — automatically emitted via the `Notification` hook's `terminalSequence` (OSC 777). No additional setup needed; works in any terminal that supports OSC 777 escape sequences.
3. **Channels (managed-org inbound delivery)** — set `channelsEnabled: true` in `~/.claude/settings.json` (Claude Code 2.1.121+, console-API-key auth orgs). Used for webhook-delivered events such as budget bump approvals.

### What gets notified

| Event | When | Surface |
|-------|------|---------|
| `feature-done` | End-of-feature (`Stop` hook fires) | PushNotification (interactive) or terminalSequence (fallback) |
| `question` | Pipeline about to request a permission grant (`PermissionRequest` hook) | terminalSequence |
| `error` / `budget-breach` / `dropped` | Budget breach, error halt, dropped-run watcher | terminalSequence (OSC 777) |
| `human-review` | Path B / Path C re-route (re-implement / re-plan), context-fill warning | terminalSequence |

### Per-run opt-out

Set `PIPELINE_NO_NOTIFICATIONS=1` in your environment for the duration of a `/pipeline` run to suppress all notifications. The pipeline emits no notification for that run, regardless of Remote Control / Channels settings.

### Reference

- Hook event mapping is documented in `~/.claude/CLAUDE.md § Notifications` (canonical user-side reference).
- Payload schema (6 fields, 200-char text cap) is documented in `~/.claude/skills/pipeline/reference.md § Notification payload schema`.
- The canonical emit helper lives at `claude/hooks/notify-emit.sh` — it is the cross-feature contract; `feat/integrate-openhuman` (F10) is the second consumer.

## Human-Review Gate

`/pipeline` ships an opt-in human-in-the-loop approval gate that pauses before destructive actions — today the only wired trigger is `git merge --squash` (the auto-merge step in Path A). When enabled, the pipeline waits for an out-of-band human approval signal before letting the merge proceed.

### Enabling

| Invocation | Behavior |
|------------|----------|
| `/pipeline` (no flag) | Gate disabled — squash-merge proceeds without pause. This is the default (0 minutes). |
| `/pipeline --human-review` | Gate enabled with **30-minute** timeout. |
| `/pipeline --human-review 60` | Gate enabled with **60-minute** timeout (any positive integer minutes). |
| `/pipeline --no-human-review` | Explicit-disable form. Same effect as flag absence. |

`--human-review` and `--no-human-review` are mutually exclusive — passing both stops the run with `ERROR: --human-review and --no-human-review are mutually exclusive`.

### Responding to the gate

When the gate fires, `/pipeline` emits a `human-review` notification (PushNotification when an interactive session has Remote Control enabled, terminalSequence OSC 777 otherwise) carrying the signal-file path in the `action_link` field. To approve, write a JSON file at the signal-file path:

```json
{"decision": "allow", "reason": "Reviewed diff; safe to merge.", "reviewer": "bruce", "ts": "2026-05-18T20:30:00Z"}
```

To deny: `{"decision": "deny"}`. Only `decision` is required; `reason`, `reviewer`, and `ts` are optional.

**Atomic write** (required to avoid the polling loop reading a half-written file):

```bash
printf '%s' "$JSON" > "$SIGNAL.tmp" && mv "$SIGNAL.tmp" "$SIGNAL"
```

Signal-file path convention: `.claude/openhuman/<feature-name>-<unix-timestamp>.json`. The `.claude/` directory is gitignored per the standard pipelinekit never-stage list — signal files are never committed.

### Timeout behavior

If no signal file is written within the timeout window, the gate **denies** the merge:

```json
{"hookSpecificOutput":{"permissionDecision":"deny",
                       "permissionDecisionReason":"OPENHUMAN_TIMEOUT: <minutes> minutes elapsed without approval"}}
```

This is **fail-safe** — the pipeline never auto-approves on timeout. The orchestrator routes the failure into Path B remediation (or feature-fail per Step 5.7).

The default of **0** minutes (gate off when the flag is absent) is intentional — per the 2026-05-18 native-Claude-Code-compliance audit, defaulting to a non-zero timeout with auto-approve would create a silent-auto-approve drift hazard.

### Reference

- Skill body: `~/.claude/skills/openhuman/SKILL.md` (canonical contract).
- Hook wiring + appendix: `~/.claude/skills/pipeline/reference.md § Human-Review Gate (--human-review)`.
- Upstream attribution (concept-only): `~/.claude/skills/openhuman/NOTICE.md`.
