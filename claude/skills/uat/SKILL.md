---
name: uat
description: Run user-acceptance UAT / E2E checks — drive a real headless browser through RBAC role flows and every button via the reused playwright_controller, diff-scoped per feature or full sweep. Non-blocking.
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
paths:
  - "e2e/**"
  - "tests/e2e/**"
  - "playwright.config.*"
  - "uat/**"
model: sonnet
---

# uat — browser-driven user-acceptance (E2E + RBAC) checks

This skill orchestrates `claude/skills/playwright/scripts/playwright_controller.py` to RENDER and CLICK real user journeys — RBAC role flows plus every button — in a headless browser. It runs as a NON-BLOCKING tail phase: it never reverts or blocks a merged feature; failures are recorded as renewable `## UAT Findings` rows for the outer loop to pick up. It ships NO executable code and NO `tests/` directory — the browser-driving code already exists in the playwright skill; this skill only documents how to reuse it.

## Step 1: Web-surface detect (silent-skip idiom)

Before doing anything, probe whether the repo even has a browser surface to exercise. Mirror the silent-skip idiom of `claude/skills/landing-report/SKILL.md` ("Fires only when a marker is present; otherwise the skill silently skips") — this is a prose probe, NOT a copied `xcrun` shell snippet (no such guard exists anywhere; the detect is prose probe-logic).

Probe these three signals:

1. A `playwright.config.*` file is present at the repo root (`playwright.config.ts` / `.js` / `.mjs` / `.cjs`).
2. `package.json` contains `@playwright/test` (in `dependencies` or `devDependencies`).
3. An `e2e/` directory exists.

Also confirm the Playwright runtime is importable (`python3 -c "import playwright"` succeeds). If NONE of the three signals is present — or the runtime is not importable — silently skip and log exactly:

```
UAT: SKIPPED (no web surface)
```

pipelinekit itself has none of these signals, so the phase skips here. The skill's own `paths` block-list (`e2e/**`, `tests/e2e/**`, `playwright.config.*`, `uat/**`) gives a second routing-layer skip for free — when the active edit target falls outside every glob the loader filters this skill out of routing entirely, exactly as the `ios` skill's `paths` block does for non-Xcode repos.

## Step 2: Session model — in-process module-reuse

UAT drives the browser by REUSING the existing `PlaywrightNative` class in-process. It does NOT add a second browser stack, does NOT extend the controller, and ships no browser code.

The runner writes a short THROWAWAY Python driver to a temp/scratch path (never committed, never staged), imports the existing class, and holds ONE browser session across the WHOLE flow:

```python
import sys
sys.path.insert(0, "claude/skills/playwright/scripts")
from playwright_controller import PlaywrightNative

with PlaywrightNative() as pw:          # ONE browser session for the whole flow
    pw.navigate(base_url + "/login")
    pw.fill_form([...])                 # role credentials
    pw.click("button[type=submit]")
    pw.wait_for_selector("...")         # session/cookies persist across every call
    buttons = pw.evaluate(
        "[...document.querySelectorAll('button,[role=button]')].map(e=>e.textContent)"
    )
    for sel in button_selectors:
        pw.click(sel)                   # exercise each button in the same session
```

Why in-process and not chained CLI calls: `playwright_controller.py`'s `main()` wraps a single `with PlaywrightNative() as pw:` context manager that starts a fresh headless Chromium and `close()`s it per process invocation, and exposes only a handful of subcommands. Chaining separate `python3 playwright_controller.py <cmd>` calls therefore LOSES all cookie/auth state between steps — a multi-step RBAC `login → navigate → click` journey CANNOT be expressed as scattered CLI calls. Holding one `PlaywrightNative` session in a single process is the only way the journey survives.

Rules:

- DO reuse the EXISTING `PlaywrightNative` class (`navigate` / `fill_form` / `click` / `wait_for_selector` / `evaluate` and the other stateful methods).
- DO hold exactly ONE `with PlaywrightNative() as pw:` session across the entire flow.
- DO NOT chain separate `python3 playwright_controller.py <cmd>` CLI calls — the session is lost between processes.
- DO NOT extend or modify `playwright_controller.py` — its existing test suite stays green.
- DO NOT introduce Cypress, Selenium, Puppeteer, Detox, or Maestro.

## Step 3: Two modes — diff-scoped (default) and full sweep

- **Diff-scoped (DEFAULT).** Exercise only the routes/flows whose source files appear in the feature diff. Map changed files under route/component/view directories to navigable URLs + selectors heuristically. When the file→route mapping is uncertain (no clear file→route mapping), FALL BACK to the full sweep for that feature — coarse but safe.
- **Full sweep.** Exercise all RBAC role flows and all buttons regardless of the diff. The pipeline runs the full sweep once at run/loop end, or per feature when `--uat-full-every-feature` is set.

Button enumeration in either mode: `evaluate("[...document.querySelectorAll('button,[role=button]')].map(e=>e.textContent)")`, then `click` each enumerated button within the same session and record per-button PASS/FAIL.

## Step 4: Base-URL resolution precedence

Resolve the journey base URL in this order, stopping at the first match:

1. `UAT_BASE_URL` environment variable.
2. `baseURL` from `playwright.config.*`.
3. A dev-server start command (start it, wait for readiness, drive against the local port).

Unresolvable → silently skip and log:

```
UAT: SKIPPED (no base URL)
```

## Step 5: No-overlap boundary (HARD requirement)

> UAT RENDERS and CLICKS real user journeys (RBAC role flows + all buttons) in a headless browser via `claude/skills/playwright/scripts/playwright_controller.py` (reused in-process). It does NOT: re-run unit/integration suites (the implement-plan test-run inner loop, Step 2e.5, does that); statically analyse coverage (the review `test-engineer` agent does that, without executing); critique UI from diff text (the review web/UI design agent does that); or curl/health-probe endpoints (the production-probe + Post-Merge Verification Gate do that). UAT is the ONLY layer that renders + clicks a real browser journey.

| Existing layer | Home | UAT does NOT duplicate because |
|----------------|------|-------------------------------|
| implement-plan test-run inner loop (Step 2e.5) | `implement-plan/SKILL.md`; gated by `--no-test-loop` | UAT does not re-run unit/integration suites — it drives the rendered UI |
| review `test-engineer` agent | `claude/agents/test-engineer.md` | UAT executes journeys; test-engineer statically analyses coverage |
| review web/UI design-pass agent | `claude/skills/review/SKILL.md` (charter-gated) | UAT verifies behaviour by clicking; the web/UI agent critiques from diff text |
| production-probe + Post-Merge Verification Gate | `reference.md` probe spec; `pipeline/SKILL.md` Post-Merge Verification Gate | UAT drives full journeys; the probe/gate health-probe endpoints |

## Reporting

On failure, the runner records per-flow PASS/FAIL and surfaces failures to the orchestrator (it does NOT write to `docs/`). The pipeline orchestrator transcribes failures into a `## UAT Findings` table in the feature file (`docs/features-*.md`), columns `| Flow | Role | Button/Step | Failure | Source feature |`, which the existing renew flow consumes (see `claude/skills/pipeline/reference.md` step 3.5). The phase is non-blocking — a merged feature is never reverted.
