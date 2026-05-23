# pipelinekit dashboard

Generated: 2026-05-23T13:27:19+00:00

<!-- richness budget: collapsible-details (sections 4-12) + interactive timeline svg + visual-token status pills -->

[Decisions log →](decisions.html) &nbsp; · &nbsp; [Feature history →](feature-history.html) &nbsp; · &nbsp; [Workflow hygiene →](workflow-hygiene.html)

<svg viewBox="0 0 800 50" data-snippet-mount="timeline-scrubber" aria-label="pipelinekit activity timeline">
  <line x1="20" y1="25" x2="780" y2="25" stroke="currentColor" stroke-width="2"/>
</svg>

## 1. Pipeline state

| Field | Value |
|-------|-------|
| Charter | docs/charter.md |
| Conv guard logged | 0 |
| Feature | 13 / 13 |
| Feature class | non-dev |
| Feature file | docs/features.md |
| Inline cycles | 0 |
| Max USD | unlimited |
| Max turns | unlimited |
| Name | feat/dashboard-and-decisions-log |
| Non-converging cycles | 0 |
| Phase Mode | subagent |
| Prior finding count | 0 |
| Replan count | 0 |
| Review cycles | 0 |
| Review style | orchestrator decides |
| Started | 2026-05-23 |
| Step | implement |

## 2. Recent activity

- `feat=10/11` `step=ppr` `cycle=0` — ppr-start
- `feat=10/11` `step=ppr` `cycle=0` — ppr-done — PR #106 squashed; F10 ✓
- `feat=11/11` `step=analyze` `cycle=0` — analyze-start
- `feat=12/12` `step=analyze` `cycle=0` — analyze-start (rolled back premature terminal — F12 fix/docs-workflow-hygiene queued)
- `feat=12/12` `step=analyze` `cycle=0` — analyze-done — analysis-v90.md written; 4 OQs + 5 SubQs resolved; data corrections (39 orphans / 62 iterations)
- `feat=12/12` `step=plan` `cycle=0` — plan-start
- `feat=12/12` `step=plan` `cycle=0` — plan-done — plan-v91.md written (1563L); 2 phases / 8 tasks; 17 ACs
- `feat=12/12` `step=branch` `cycle=0` — branch-created fix/docs-workflow-hygiene
- `feat=12/12` `step=implement` `cycle=0` — implement-start phase-1 (code+tests+docs)
- `feat=12/12` `step=implement` `cycle=0` — phase-1-done — commit 5b065f2; 14 files (10 new + 4 edited); 4/4 tests PASS; 35/35 richness PASS; collateral: live pruner wiped F12 block, restored manually
- `feat=12/12` `step=implement` `cycle=0` — phase-2-done — commit 9951938; 11 backfill entries + 62 archive + 0 orphans
- `feat=12/12` `step=review` `cycle=0` — review-start (teams — 2991L/14F)
- `feat=12/12` `step=review` `cycle=0` — review-done — verdict PASS; 17/17 ACs PASS; 0 findings
- `feat=12/12` `step=ppr` `cycle=0` — ppr-done — PR #108 squashed (6b997bb); F12 ✓
- `feat=13/13` `step=analyze` `cycle=0` — analyze-start (F13 dashboard + decisions log queued — extends pipeline)
- `feat=13/13` `step=analyze` `cycle=0` — analyze-done analysis-v91.md written (5 OQs + 7 SubQs resolved, 2 phases / 10 tasks, hybrid extractor)
- `feat=13/13` `step=plan` `cycle=0` — plan-start
- `feat=13/13` `step=plan` `cycle=0` — plan-done plan-v92.md written (11 tasks, 2 phases, 2353 lines)
- `feat=13/13` `step=branch` `cycle=0` — branch-create feat/dashboard-and-decisions-log
- `feat=13/13` `step=implement` `cycle=0` — implement-start

## 3. Recent features

- **?/?** `feat/deployment-provider-render` (OQs: 0, SubQs: 0)
- **?/?** `feat/deployment-provider-digitalocean` (OQs: 0, SubQs: 0)
- **?/?** `chore/native-surface-docs-and-bundled-nbs` (OQs: 0, SubQs: 0)
- **?/?** `feat/charter-ai-layer-topics` (OQs: 0, SubQs: 0)
- **13/13** `feat/dashboard-and-decisions-log` (OQs: 5, SubQs: 7)

<details>
<summary>4. Iteration archive</summary>

`docs/archive/progress-v*.md` count: **62**
</details>

<details>
<summary>5. Cost trajectory</summary>

- Events: **82**
- Total USD: **$0.00**
- Average per event: **$0.0000**
</details>

<details>
<summary>6. Documentation hub</summary>

Total pages: **37**

Top 5 most recent:
- [feature-history.html](feature-history.html)
- [workflow-hygiene.html](workflow-hygiene.html)
- [index.html](index.html)
- [decisions.html](decisions.html)
- [dashboard.html](dashboard.html)

</details>

<details>
<summary>7. Charter snapshot</summary>

- Topics present: **13**
- Deployment target: ``none` — pipelinekit is a workflow toolkit, not a deployed application. No CI/CD deployment phase needed.`
- Review style: ``orchestrator decides` (default) — let the heuristic pick `--teams` per feature based on diff size and feature class.`
- Decisions logged: **3**
- Non-Goals: **5**
- Open Questions: **0**
</details>

<details>
<summary>8. Test sweep</summary>

Total `test_*.sh` files: **48**

By directory:
- `claude/hooks/tests` — 5
- `claude/host-adapters/tests` — 1
- `claude/lib/pipeline/tests` — 2
- `claude/lib/sandbox/tests` — 5
- `claude/skills/analyze/tests` — 1
- `claude/skills/caveman-mode/tests` — 1
- `claude/skills/create-plan/tests` — 2
- `claude/skills/docs-writer/tests` — 2
- `claude/skills/pipeline/tests` — 15
- `claude/skills/post-merge/tests` — 2
- `claude/skills/ppr/tests` — 2
- `claude/skills/research/tests` — 5
- `claude/skills/review/tests` — 3
- `claude/skills/secret-scanner/tests` — 1
- `claude/skills/write-a-skill/tests` — 1

</details>

<details>
<summary>9. Skill inventory</summary>

Total SKILL.md files: **42**
</details>

<details>
<summary>10. Hook denial summary</summary>

_No denial-tracker log present._
</details>

<details>
<summary>11. Memory inventory</summary>

Total memory files: **2**

By type:
- `MEMORY` — 1
- `project` — 1

</details>

<details>
<summary>12. Quick links</summary>

- [workflow-hygiene](workflow-hygiene.html)
- [html-effectiveness-principles](html-effectiveness-principles.html)
- [design-tokens](design-tokens.html)
- [codebase-map](codebase-map.html)
- [feature-history](feature-history.html)
- [decisions](decisions.html)
- [skills](skills.html)
- [agents](agents.html)
</details>

