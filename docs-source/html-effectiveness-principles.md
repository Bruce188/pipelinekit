<!--
diataxis: explanation
-->
# HTML effectiveness principles

Canonical design rubric for pipelinekit's `documentation/*.html` corpus. Defines the four-category rubric, maps every shipped snippet to its category, and lists anti-patterns the rubric is meant to prevent.

## WHAT

"HTML effectiveness" is a rubric for distinguishing HTML pages whose layout and interactivity *carry information* from HTML pages that are merely "rendered markdown with a sidebar." The rubric is taken from <https://thariqs.github.io/html-effectiveness/> and adopted as pipelinekit's canonical lens for evaluating any page rendered to `documentation/`.

pipelinekit ships 18 ready-to-embed snippets in `claude/skills/docs-writer/snippets/`. Each snippet implements one of the four rubric categories below. The richness gate (`claude/skills/docs-writer/richness_check.py`) refuses to stage a `documentation/*.html` page that scores below the threshold — `≥1` distinct pattern for body ≤ 1500 words, `≥2` distinct patterns for body > 1500 words. A page authored without a single rich-interactive primitive defeats the purpose of HTML-over-markdown and fails the gate.

The rubric is descriptive, not prescriptive. Designers can compose multiple categories on one page; the only contract is that *some* category must be present.

## RUBRIC

The four categories are non-overlapping. A snippet belongs to exactly one category — pick whichever lever dominates its content carrier.

- **Spatial** — uses 2D layout (grids, tables, diagrams) to communicate structure that prose cannot. A reader scanning the layout learns relationships before reading any individual cell. Examples: card grids, RACI matrices, architecture stack diagrams.
- **Live-rendered** — computes responsive output from user input. The page state is not static; sliders, textareas, or scripted playback drive the visible content. The reader interacts with the page to see different answers, not different views of the same answer. Examples: cost calculators, live linters, paste-and-score playgrounds.
- **Interactive** — clickable / toggleable / scrubable UI that progressively reveals information. Distinct from live-rendered in that the content is fixed; the interaction surfaces *which subset* is visible. Examples: comparison tabs, before/after sliders, decision-tree quizzes, animated SVG flows with hover tooltips.
- **Visual-token** — visualizes design tokens, scales, gauges, or other quantitative-visual primitives. The visual element *is* the content; reading it as prose would be lossy. Examples: dial-gauge meters showing budget consumption, swatch tables showing the canonical color tokens, type-scale specimens.

## SNIPPET MAP

The 18 snippets currently shipped, classified per the rubric. Counts: Spatial 6 / Interactive 7 / Live-rendered 4 / Visual-token 1.

<div data-snippet="command-cheatsheet"></div>

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
- **Snippets that fight the page.** Over-decorated SVGs that animate while the reader is trying to read prose, a `cost-calculator` placed on a quickstart page where the reader has no decision to make, two interactive snippets stacked without coordinating their state. Pick the *minimum* snippet that carries the page intent; remove anything decorative.
- **Mixing Live-rendered + Interactive without state coordination.** A textarea-driven `live-linter` next to a tab-based `comparison-tabs` produces a confusing reading order — the reader doesn't know whether to type or click. Use one primary interaction surface per page.
- **Missing dark-mode theming.** Snippets that hard-code `#fff` / `#000` instead of consuming the template's CSS custom properties break in dark mode. The shipped snippets all use `var(--bg)`, `var(--fg)`, etc., so they auto-theme — new snippets must follow the same contract.

## SEE ALSO

<div data-snippet="comparison-tabs"></div>

- [Design tokens](design-tokens.html) — pipelinekit's canonical Visual-token exemplar; visualizes the 41 template custom properties (22 light + 19 dark) plus typography, radii, syntax, and motion tokens.
- [Codebase map](codebase-map.html) — full site structure including all of `documentation/`.
- [docs-writer SKILL.md](../claude/skills/docs-writer/SKILL.md) — authoring conventions, snippet catalog, output directory contract.
- <https://thariqs.github.io/html-effectiveness/> — the source rubric this page adopts.
