<!--
diataxis: explanation
-->
# HTML effectiveness principles

Canonical design rubric for pipelinekit's `documentation/*.html` corpus. Defines the four-category rubric, maps every shipped snippet to its category, and lists anti-patterns the rubric is meant to prevent.

## WHAT

The quadrant map below renders the rubric's own four categories spatially — Spatial, Live-rendered, Interactive, and Visual-token — each cell glossing the lever that category pulls.

<svg viewBox="0 0 660 420" role="img" aria-label="Two-by-two quadrant map of the four HTML-effectiveness categories" style="width:100%;height:auto;font-family:var(--sans);">
  <title>The four HTML-effectiveness rubric categories as a 2x2 quadrant map</title>
  <!-- outer frame -->
  <rect x="20" y="20" width="620" height="380" fill="none" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
  <!-- dividers -->
  <line x1="330" y1="20" x2="330" y2="400" stroke="var(--border)" stroke-width="1.5"></line>
  <line x1="20" y1="210" x2="640" y2="210" stroke="var(--border)" stroke-width="1.5"></line>
  <!-- top-left: Spatial (accent highlight) -->
  <rect x="26" y="26" width="298" height="178" fill="var(--accent-soft)" rx="4"></rect>
  <text x="48" y="70" fill="var(--fg)" font-size="20" font-weight="600">Spatial</text>
  <text x="48" y="100" fill="var(--fg-muted)" font-size="13">2D layout communicates structure</text>
  <text x="48" y="120" fill="var(--fg-muted)" font-size="13">prose cannot — grids, tables, diagrams.</text>
  <text x="48" y="150" fill="var(--fg-subtle)" font-size="12" font-style="italic">card grids · RACI matrices · stack diagrams</text>
  <!-- top-right: Live-rendered -->
  <text x="356" y="70" fill="var(--fg)" font-size="20" font-weight="600">Live-rendered</text>
  <text x="356" y="100" fill="var(--fg-muted)" font-size="13">Computes responsive output from</text>
  <text x="356" y="120" fill="var(--fg-muted)" font-size="13">user input — state is not static.</text>
  <text x="356" y="150" fill="var(--fg-subtle)" font-size="12" font-style="italic">cost calculators · live linters · playgrounds</text>
  <!-- bottom-left: Interactive -->
  <text x="48" y="262" fill="var(--fg)" font-size="20" font-weight="600">Interactive</text>
  <text x="48" y="292" fill="var(--fg-muted)" font-size="13">Click / toggle / scrub progressively</text>
  <text x="48" y="312" fill="var(--fg-muted)" font-size="13">reveals which subset is visible.</text>
  <text x="48" y="342" fill="var(--fg-subtle)" font-size="12" font-style="italic">comparison tabs · sliders · decision quizzes</text>
  <!-- bottom-right: Visual-token -->
  <text x="356" y="262" fill="var(--fg)" font-size="20" font-weight="600">Visual-token</text>
  <text x="356" y="292" fill="var(--fg-muted)" font-size="13">The visual element IS the content —</text>
  <text x="356" y="312" fill="var(--fg-muted)" font-size="13">reading it as prose would be lossy.</text>
  <text x="356" y="342" fill="var(--fg-subtle)" font-size="12" font-style="italic">dial gauges · swatch tables · type specimens</text>
</svg>

"HTML effectiveness" is a rubric for distinguishing HTML pages whose layout and interactivity *carry information* from HTML pages that are merely "rendered markdown with a sidebar." The rubric is taken from <https://thariqs.github.io/html-effectiveness/> and adopted as pipelinekit's canonical lens for evaluating any page rendered to `documentation/`.

pipelinekit ships 18 ready-to-embed snippets in `claude/skills/docs-writer/snippets/`. Each snippet implements one of the four rubric categories below. The richness gate (`claude/skills/docs-writer/richness_check.py`) refuses to stage a `documentation/*.html` page that scores below the threshold — `≥1` distinct pattern for body ≤ 1500 words, `≥2` distinct patterns for body > 1500 words. A page authored without a single rich-interactive primitive defeats the purpose of HTML-over-markdown and fails the gate. A companion topic-affinity check additionally rejects any page that mounts a baked-content snippet whose subject the page's prose never discusses — so a budget meter cannot sit on a coverage score-card, nor a system-architecture diagram on this rubric page.

The rubric is descriptive, not prescriptive. Designers can compose multiple categories on one page; the only contract is that *some* category must be present.

## RUBRIC

The four categories are non-overlapping. A snippet belongs to exactly one category — pick whichever lever dominates its content carrier.

- **Spatial** — uses 2D layout (grids, tables, diagrams) to communicate structure that prose cannot. A reader scanning the layout learns relationships before reading any individual cell. Examples: card grids, RACI matrices, architecture stack diagrams.
- **Live-rendered** — computes responsive output from user input. The page state is not static; sliders, textareas, or scripted playback drive the visible content. The reader interacts with the page to see different answers, not different views of the same answer. Examples: cost calculators, live linters, paste-and-score playgrounds.
- **Interactive** — clickable / toggleable / scrubable UI that progressively reveals information. Distinct from live-rendered in that the content is fixed; the interaction surfaces *which subset* is visible. Examples: comparison tabs, before/after sliders, decision-tree quizzes, animated SVG flows with hover tooltips.
- **Visual-token** — visualizes design tokens, scales, gauges, or other quantitative-visual primitives. The visual element *is* the content; reading it as prose would be lossy. Examples: dial-gauge meters showing budget consumption, swatch tables showing the canonical color tokens, type-scale specimens.

## SNIPPET MAP

The 18 snippets currently shipped, classified per the rubric. Counts: Spatial 6 / Interactive 7 / Live-rendered 4 / Visual-token 1.

| # | Snippet | Category | Rationale |
|---|---------|----------|-----------|
| 1 | `agent-catalog-grid` | Spatial | 2D card-grid layout with section-filter chips. |
| 2 | `architecture-diagram` | Spatial | 4-layer SVG taxonomy with layer-toggle filter. |
| 3 | `before-after-slider` | Interactive | Horizontal scrubber with clip-path reveal between two states. |
| 4 | `chooser-quiz` | Interactive | Multi-step decision tree leading to a recommendation. |
| 5 | `command-cheatsheet` | Spatial | Sortable, filterable command table. |
| 6 | `comparison-tabs` | Interactive | Click-tab side-by-side comparison. |
| 7 | `cost-budget-meter` | Visual-token | Twin dial-gauge SVG with CSS-animated fill. |
| 8 | `cost-calculator` | Live-rendered | Sliders compute dollar amounts in real time. |
| 9 | `deployment-provider-quiz` | Interactive | 6-question deployment-fit quiz. |
| 10 | `governance-roles-table` | Spatial | RACI matrix (6 tasks x 4 roles) with click-highlight. |
| 11 | `live-linter` | Live-rendered | Paste textarea, scored in real time. |
| 12 | `path-routing-diagram` | Interactive | Clickable decision-tree SVG mapped to pipeline path anchors. |
| 13 | `pipeline-phase-diagram` | Interactive | Animated SVG lifecycle flow with hover tooltips. |
| 14 | `playground-2col` | Live-rendered | Two-column textarea with live status indicator. |
| 15 | `skill-catalog-grid` | Spatial | Card-grid with section-filter chips. |
| 16 | `terminal-simulator` | Live-rendered | Scripted command playback with synthetic output. |
| 17 | `timeline-scrubber` | Interactive | Horizontal commit-history scrubber. |
| 18 | `tutorial-cards` | Spatial | 2x2 card-grid with colored top borders. |

The new `documentation/design-tokens.html` is the canonical Visual-token exemplar; before it, that category was thinly represented (only `cost-budget-meter`).

## ANTI-PATTERNS

Pages the rubric is designed to exclude — these defeat the purpose of HTML-over-markdown.

- **Walls of prose without visual aids.** A 4000-word essay with no diagrams, tables, or scrubable elements is markdown with extra steps. Either add a category-matching snippet, restructure with tables / lists, or render to markdown and link from the docs index instead.
- **Decorative non-functional images.** PNG screenshots that exist to look professional but do not convey information the prose does not already cover. The HTML-effectiveness rubric values *load-bearing* visuals — if the image vanished, the page should lose meaning.
- **Prose-only landing pages.** An `index.html` that is one big paragraph followed by a list of links. Use `architecture-diagram` or `tutorial-cards` to surface the structure visually.
- **Snippets that fight the page.** Over-decorated SVGs that animate while the reader is trying to read prose, a `cost-calculator` placed on a quickstart page where the reader has no decision to make, two interactive snippets stacked without coordinating their state. Pick the *minimum* snippet that carries the page intent; remove anything decorative. A baked-content snippet whose subject the page never discusses (a budget dial on a score-card, a whole-system architecture diagram on an unrelated rubric page) is now caught automatically by the topic-affinity layer in `richness_check.py` — author page-specific inline content instead.
- **Mixing Live-rendered + Interactive without state coordination.** A textarea-driven `live-linter` next to a tab-based `comparison-tabs` produces a confusing reading order — the reader doesn't know whether to type or click. Use one primary interaction surface per page.
- **Missing dark-mode theming.** Snippets that hard-code `#fff` / `#000` instead of consuming the template's CSS custom properties break in dark mode. The shipped snippets all use `var(--bg)`, `var(--fg)`, etc., so they auto-theme — new snippets must follow the same contract.

<details>
<summary>Rubric provenance and adoption notes (click to expand)</summary>

The four-category framing is taken verbatim from Thariq Shihipar's *HTML effectiveness* essay (<https://thariqs.github.io/html-effectiveness/>). pipelinekit adopts the category names without translation. Two deltas worth flagging:

- **Snippet inventory is pipelinekit-specific.** The 18 snippets enumerated in the SNIPPET MAP table above are particular to this repo's `claude/skills/docs-writer/snippets/` directory. Forking projects should retain the four-category rubric but redraw their own inventory map.
- **Richness gate is pipelinekit-specific.** The `richness_check.py` thresholds (≥1 pattern for body ≤ 1500 words, ≥2 for body > 1500 words) are an enforcement layer on top of the rubric — the rubric itself prescribes no quantitative floor. Other adopters can keep the rubric without adopting the gate.

The rubric has been stable since pipelinekit v0.0.1 and is not expected to change without a documented ADR.

</details>

## SEE ALSO

- [Design tokens](design-tokens.html) — pipelinekit's canonical Visual-token exemplar; visualizes the 41 template custom properties (22 light + 19 dark) plus typography, radii, syntax, and motion tokens.
- [Codebase map](codebase-map.html) — full site structure including all of `documentation/`.
- [docs-writer SKILL.md](../claude/skills/docs-writer/SKILL.md) — authoring conventions, snippet catalog, output directory contract.
- <https://thariqs.github.io/html-effectiveness/> — the source rubric this page adopts.
