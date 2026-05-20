# Agent Inventory Audit — 2026-05

**Date:** 2026-05-20
**Scope:** 13 `claude/agents/*.md` files with zero confirmed dispatch sites (per `docs/analysis-v72.md`)
**Outcome:** 8 deletions, 4 documented (already-wired or already-listed), 1 no-op special-case

## Summary

This audit reduced the callable agent inventory from 31 to 23 by deleting 8 vendored wshobson agents that had zero confirmed dispatch sites and no planned integration path. No new dispatch sites were added; the audit's purpose is to make the inventory's wired-vs-orphan boundary explicit so future maintainers can distinguish intentionally user-driven agents (mobile-dev, data-pipeline-engineer, trading-bot-developer, debugger via fix-issue) from orchestrator-driven agents (architect, code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer, karpathy-reviewer, refactor-expert, incident-responder, docs-writer, claude-md-guardian, tdd-test-writer, tdd-implementer, the 5 provider-variant deployment-engineers). The resulting `documentation/agent-audit-2026-05.md` becomes the canonical record of the 2026-05 inventory pass and the rationale for each decision.

## Methodology

- **Dispatch-site grep patterns used** (per `docs/analysis-v72.md` lines 107–108):
  - `subagent_type: 'X'` — Agent-tool dispatch parameter in orchestrator code
  - `dispatch the X agent` — English instruction in `claude/skills/**/SKILL.md` files
  - `@X` — named-agent invocation convention in prompts and skills
  - String literal mentions in `claude/skills/**/SKILL.md` and `claude/skills/**/agent-prompts.md`
- **Exclusions from dispatch-site count** (reference-only, not wiring):
  - Self-mention in the agent's own `.md` file
  - `claude/agents/NOTICE.md` vendor attribution rows
  - Top-level `README.md` inventory enumeration
  - `docs-source/credits.md` and `documentation/credits.html` credits table
  - `claude/skills/docs-writer/snippets/*.html` rendering pins (karpathy-reviewer / spec-tracer diagram pins only)
  - `claude/rules/workflow.md` routing tables
  - `claude/agents/README.md` H3 grouping (advertisement, not wiring)
- **Full evidence trail:** See `docs/analysis-v72.md` for per-agent grep methodology, dispatch-site grep hits, and reference-only mention lists.

## Dispatch-Site Map (13 rows)

| Agent | Vendor | Dispatch sites | Action | Rationale |
|-------|--------|----------------|--------|-----------|
| `api-documenter` | wshobson | 0 | DELETE | Two failures: zero dispatch sites + referenced as a non-existent skill in `docs-writer.md` and `architect.md`. Deleted with the dangling-reference cleanup folded in. |
| `architect-review` | wshobson | 0 | DELETE | The local `architect` agent — wired via `ascii-diagram/SKILL.md:30` — covers the architectural-review niche. Duplicate vendored agent. |
| `cloud-architect` | wshobson | 0 | DELETE | The 5 provider-variant `*-deployment-engineer` agents plus the `deployment-engineer` documentation-only base cover cloud architecture concretely. |
| `refactor-expert` | local | 1 (`claude/skills/code-health/SKILL.md:115`) | DOCUMENT | Already wired conditionally (dispatched when code-health flags refactor candidates). Already in `claude/agents/README.md:9` H3 grouping. No new action. |
| `terraform-specialist` | wshobson | 0 | DELETE | No pipelinekit skill invokes Terraform. Out-of-scope vendor inclusion. |
| `network-engineer` | wshobson | 0 | DELETE | No pipelinekit skill diagnoses network topology. Out-of-scope vendor inclusion. |
| `performance-engineer` | wshobson | 0 | DELETE | The LOCAL `performance-tuner` agent (Agent 4 of `/review`) covers performance-review. Vendored `performance-engineer` is duplicative. |
| `dx-optimizer` | wshobson | 0 | DELETE | No pipelinekit skill optimizes DX onboarding. Smallest file (2.1 KB). |
| `test-automator` | wshobson | 0 | DELETE | The LOCAL `test-engineer` agent (Agent 3 of `/review`) covers test-strategy review. Vendored `test-automator` is duplicative. |
| `mobile-dev` | local | 0 SKILL; 1 user-driven advert in `CLAUDE.md` | DOCUMENT | Protected per CLAUDE.md § Mobile App Workflows. Already in `claude/agents/README.md:26` under `### Mobile Development`. No new action. |
| `data-pipeline-engineer` | local | 0 SKILL; user-driven per `claude/rules/workflow.md` | DOCUMENT | Protected per feature constraint. Already in `claude/agents/README.md:23` H3 grouping. No new action. |
| `trading-bot-developer` | local | 0 SKILL; user-driven per `claude/rules/workflow.md` | DOCUMENT | Protected per feature constraint. Already in `claude/agents/README.md:22` H3 grouping. No new action. |
| `deployment-engineer` (base) | local | 0 (not a callable agent) | KEEP / NO-OP | Documentation-only base file with no `name:` frontmatter; shared-doc include referenced by the 5 provider-variant `*-deployment-engineer` files. NOT callable as `@deployment-engineer`; cannot be wired, cannot be deleted. |

## Action Rationale

### Deletions (8)

#### api-documenter

The `api-documenter` agent failed on two counts: (1) zero dispatch sites as a subagent — no pipelinekit skill invokes it via `subagent_type`, `dispatch the api-documenter agent`, or `@api-documenter`; (2) it is referenced 6 times in `claude/agents/docs-writer.md` (lines 33, 64, 80, 110, 127, 135) and once in `claude/agents/architect.md` (line 27) as a "SKILL" that does not exist on disk (`ls claude/skills/api-documenter` → ENOENT). This means every runtime invocation of the docs-writer agent instructed the model to invoke a non-existent skill, creating misleading and unactionable instructions.

Deletion resolves both failures. The `NOTICE.md` vendor row for `plugins/api-testing-observability/agents/api-documenter.md` is removed. The `docs-source/credits.md` and `documentation/credits.html` wshobson row count drops from 10 to 2 (this agent's deletion is bundled with the other 7). The cascading cleanup removes all 6 inline `api-documenter skill` references from `docs-writer.md` and the 1 parenthetical from `architect.md`. References in `claude/tresor-resources/README.md:88,342` and `claude/tresor-resources/examples/workflows/skills-in-action.md:48,176` are OUT of scope — that is a vendored third-party template library, not pipelinekit source.

#### architect-review

The `architect-review` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 17), the top-level `README.md` enumeration (line 126), `docs-source/credits.md` (line 11), and `documentation/credits.html` (line 568) — all of which are inventory-only references, not wiring.

The local `architect` agent is wired via `claude/skills/ascii-diagram/SKILL.md:30` and covers the architectural-review niche. Adding a separate `architect-review` lens would duplicate the existing `code-reviewer` (Agent 1 of `/review`) and `architect` (dispatched by ascii-diagram). The `NOTICE.md` vendor row for `plugins/comprehensive-review/agents/architect-review.md` is removed. Credits count drops with the bundle.

#### cloud-architect

The `cloud-architect` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 12), `README.md` line 126, `docs-source/credits.md`, and `documentation/credits.html` — inventory-only references.

The 5 provider-variant deployment-engineer agents (`azure-`, `vercel-`, `railway-`, `render-`, `digitalocean-deployment-engineer`) plus the `deployment-engineer` documentation-only base file cover cloud architecture comprehensively and concretely per provider. A generic `cloud-architect` adds no marginal value over these provider-specific specialists. The `NOTICE.md` vendor row for `plugins/cicd-automation/agents/cloud-architect.md` is removed.

#### terraform-specialist

The `terraform-specialist` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 11), `docs-source/credits.md`, and `documentation/credits.html`.

No pipelinekit skill invokes Terraform. The 5 provider-variant deployment-engineers and the provider-specific ops skills (`azure-ops`, `vercel-ops`, `railway-ops`, `render-ops`, `digitalocean-ops`) cover provider deployments via CLI, not Infrastructure-as-Code. Adding Terraform integration is out of scope for the current charter. The `NOTICE.md` vendor row for `plugins/cicd-automation/agents/terraform-specialist.md` is removed.

#### network-engineer

The `network-engineer` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 13), `README.md` line 126, `docs-source/credits.md`, and `documentation/credits.html`.

No pipelinekit skill diagnoses or designs network topology. The agent is an out-of-scope vendor inclusion with no identified integration path in the current charter. The `NOTICE.md` vendor row for `plugins/cloud-infrastructure/agents/network-engineer.md` is removed.

#### performance-engineer

The `performance-engineer` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 15), `docs-source/credits.md`, and `documentation/credits.html`. It is NOT in `claude/agents/README.md`.

The LOCAL `performance-tuner` agent (Agent 4 of `/review` medium/large tier, dispatched via `claude/skills/review/agent-prompts.md`) already covers the performance-review niche. Keeping the vendored `performance-engineer` alongside `performance-tuner` creates a confusing naming collision. The `NOTICE.md` vendor row for `plugins/application-performance/agents/performance-engineer.md` is removed.

#### dx-optimizer

The `dx-optimizer` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 10), `docs-source/credits.md`, and `documentation/credits.html`. It is NOT in `claude/agents/README.md`.

No pipelinekit skill optimizes DX onboarding workflows. At 2.1 KB, this is the smallest file deleted — minimal vendor cost, zero integration value. The `NOTICE.md` vendor row for `plugins/debugging-toolkit/agents/dx-optimizer.md` is removed.

#### test-automator

The `test-automator` agent has zero dispatch sites. References appear only in `NOTICE.md` (row 16), `docs-source/credits.md`, and `documentation/credits.html`. It is NOT in `claude/agents/README.md`.

The LOCAL `test-engineer` agent (Agent 3 of `/review` medium/large tier) covers test-strategy review. Keeping the vendored `test-automator` creates a naming collision with the local `test-engineer` and the `tdd-test-writer`/`tdd-implementer` pair. The `NOTICE.md` vendor row for `plugins/backend-development/agents/test-automator.md` is removed.

### Document — already wired / listed (4)

**refactor-expert** — Already dispatched conditionally by `claude/skills/code-health/SKILL.md:115` ("dispatch the `refactor-expert` agent with a prompt that includes..."). Also listed in `claude/agents/README.md:9` H3 grouping. No new source-code change required; audit artifact records this as a confirmed wired agent.

**mobile-dev** — Protected per `CLAUDE.md` § Mobile App Workflows. The `mobile-dev` agent is explicitly user-driven (the user invokes it by name in mobile-focused sessions). Already in `claude/agents/README.md:26` under `### Mobile Development`. No new source-code change required.

**data-pipeline-engineer** — Protected per feature constraint. Referenced in `claude/rules/workflow.md` Phase Tool Routing table. Already in `claude/agents/README.md:23` H3 grouping. No new source-code change required.

**trading-bot-developer** — Protected per feature constraint. Referenced in `claude/rules/workflow.md` Phase Tool Routing table. Already in `claude/agents/README.md:22` H3 grouping. No new source-code change required.

### Keep / no-op special-case (1)

**deployment-engineer (base)** — The `claude/agents/deployment-engineer.md` file is a documentation-only base file with no `name:` or `description:` frontmatter, explicitly declared at the top of the file as "NOT itself a callable agent." Its purpose is to provide shared documentation content included by the 5 provider-variant deployment-engineer files (`azure-deployment-engineer.md`, `vercel-deployment-engineer.md`, `railway-deployment-engineer.md`, `render-deployment-engineer.md`, `digitalocean-deployment-engineer.md`). It cannot be deleted (the provider variants depend on it as a shared-doc include), cannot be wired (it is not callable as `@deployment-engineer`), and cannot be listed in `claude/agents/README.md` in the same form as regular agents (it would mislead users into treating it as a callable agent). Its zero-dispatch-site status is intentional and permanent.

## Cascading Cleanups

This audit's commit lands the following coordinated edits alongside the 8 file deletions:

- **`claude/agents/NOTICE.md`** — drop 8 rows from the `**Upstream paths:**` block (currently lines 10–17). Keep the rows for `deployment-engineer` and `incident-responder`. The MIT license body + alirezarezvani section + re-vendor procedure are byte-identical.
- **`README.md` (top-level)** — line 126 Agents count `(31)` → `(23)`. Enumeration drops `` `cloud-architect`, `` and `` `architect-review`, ``. The trailing `..., ...` truncation is preserved.
- **`docs-source/credits.md` + `documentation/credits.html`** — count `10 specialist agents` → `2 specialist agents`; enumeration reduces to `(deployment-engineer, incident-responder)`.
- **`claude/agents/docs-writer.md`** — remove the `**1. api-documenter skill**` block at lines 33–37 and 5 other inline references at lines ~64, ~80, ~110, ~127, ~135. Renumber `**2. readme-updater skill**` → `**1. readme-updater skill**`. Net diff ~30 prose lines removed.
- **`claude/agents/architect.md`** — line 27 `- API documentation (api-documenter skill)` → `- API documentation`. Single 1-line edit.

## Verification Evidence

After feature commit, the following grep gates MUST return the indicated results (use these to validate the audit's accuracy post-merge):

- `ls claude/agents/*.md | grep -vE "(NOTICE|README)\\.md$" | wc -l` returns **23** (was 31).
- `grep -rln -E "api-documenter|architect-review|cloud-architect|terraform-specialist|network-engineer|performance-engineer|dx-optimizer|test-automator" --include="*.md" --include="*.html" --include="*.sh" --include="*.py" . 2>/dev/null | grep -v "^./docs/" | grep -v "^./.git/" | grep -v "^./claude/tresor-resources/" | grep -v "^./documentation/agent-audit-2026-05.md$"` returns **0 lines**. (Allowed exception: this audit file itself; `claude/tresor-resources/` is vendored third-party template content out of audit scope.)
- `grep -c "^- plugins/" claude/agents/NOTICE.md` returns **2** (was 10).
- `grep -c "Agents\\*\\* (23)" README.md` returns **1** hit on line 126.
- `grep "10 specialist agents" docs-source/credits.md documentation/credits.html` returns **0 hits**.
- `grep "api-documenter" claude/agents/docs-writer.md claude/agents/architect.md` returns **0 hits**.
- `git log -1 --pretty=%s` returns **`chore: audit and remove 8 orphan vendored agents per agent-audit-2026-05`** exactly.

For the full audit evidence trail (per-agent grep methodology + dispatch-site grep hits + reference-only mention list), see `docs/analysis-v72.md`.
