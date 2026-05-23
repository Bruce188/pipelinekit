---
name: docs-writer
description: Documentation skill — renders markdown to rich, interactive, self-contained HTML for documentation/. Uses the shipped template + render.py. Refuses to write markdown to documentation/.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
paths:
  - claude/skills/docs-writer/**
  - docs-source/**
  - documentation/**
---

# docs-writer — rich-template HTML documentation skill

`docs-writer` is the canonical surface for application documentation in pipelinekit. It renders markdown source to **interactive, self-contained HTML** wrapped in the shipped template, with sticky-ToC sidebar, in-page search, code-copy buttons, sortable tables, scrollspy, smooth-scroll anchors, light/dark theme toggle, mobile responsiveness, and Pygments syntax highlighting. Every emitted file is a single self-contained `.html` (no CDN, no remote assets) that renders identically when served from any origin, copied to disk, or opened via `file://` URL.

The skill ships three assets:

- **`claude/skills/docs-writer/template.html`** — the canonical HTML shell. Inlines all CSS + JS + SVG icons (~30 KB). Placeholders: `{{TITLE}}`, `{{DESCRIPTION}}`, `{{TOC}}`, `{{CONTENT}}`, `{{META}}`, `{{FOOTER_RIGHT}}`.
- **`claude/skills/docs-writer/render.py`** — Python renderer. Reads markdown (or HTML in rewrap mode), generates ToC from headings, expands `data-snippet` placeholders, fills the template, writes the output file.
- **`claude/skills/docs-writer/snippets/`** — library of self-contained rich-interactive HTML fragments (SVG flowcharts, calculators, decision trees, card grids, …). Markdown sources reference them via `<div data-snippet="<name>"></div>` placeholders; `render.py` inlines them. See § Snippets catalog below.

## The four rules

These are non-negotiable. The compliance hook (see § Enforcement) blocks staging of any file that violates them.

1. **Every page in `documentation/` is HTML.** No `.md` files. No exceptions — vendored standards live as HTML at the `documentation/` root alongside reader-facing pages.
2. **Every page is generated via `render.py`.** Do not hand-write HTML files; do not bypass the template. Hand-edits to emitted files are tolerated for small fixes but the page must remain template-compliant (the `<meta name="generator" content="pipelinekit docs-writer/2 — rich-template">` tag is the marker).
3. **`docs/` is AI-workflow-only and gitignored.** Never write reader-facing content to `docs/`. AI-internal artifacts (`analysis-vN.md`, `plan-vN.md`, `prompts-vN.md`, `review-vN.md`, `charter.md`, `progress.md`, `pipeline-state.md`, `features.md`, `features-vN.md`, `features-master.md`, `pipeline-intel.json`, `.last-verify.json`, `context-dump.md`) are local-only, never committed. User-authored feature lists may be committed only via explicit `git add -f`.
4. **Rich-content contract: every reader-facing page MUST include ≥1 interactive snippet from the catalog.** A page that is just "rendered markdown with a sidebar" defeats the purpose of HTML over markdown. Acceptable patterns: SVG flowchart, calculator widget, decision-tree quiz, comparison-tabs, card grid, timeline scrubber, live linter playground, custom diff viewer. The `richness_check.py` linter enforces this; staging fails for pages below the bar unless `# richness-exempt: <reason>` appears in the page's `<head>`.

## Usage

### Render a new page from markdown

```bash
python3 claude/skills/docs-writer/render.py docs-source/my-page.md documentation/my-page.html
```

### Render with explicit metadata

```bash
python3 claude/skills/docs-writer/render.py \
  docs-source/my-page.md \
  documentation/my-page.html \
  --title "Custom title" \
  --description "Custom description for OpenGraph + sidebar" \
  --source-link "https://github.com/Bruce188/pipelinekit/blob/main/path/to/source" \
  --meta "Section: deployment" \
  --meta "Version: 0.0.1"
```

### Rewrap existing HTML (when source markdown isn't available)

```bash
python3 claude/skills/docs-writer/render.py --from-html \
  documentation/some-page.html \
  documentation/some-page.html.new && \
  mv documentation/some-page.html.new documentation/some-page.html
```

Used during the bulk regeneration that brought existing pages onto the template. Going forward, prefer the markdown render path — rewrap mode preserves semantic HTML but can't generate syntax highlighting or other Pygments-rendered elements that markdown-mode produces.

### Generate the landing-page index

The landing page at `documentation/index.html` is generated like any other page — from a hand-curated markdown source listing all documentation pages by section. Re-render it whenever you add a new page:

```bash
# Edit /tmp/index-source.md (or commit a stable docs-source/index.md), then:
python3 claude/skills/docs-writer/render.py docs-source/index.md documentation/index.html \
  --title "pipelinekit documentation" \
  --description "Complete user-facing documentation for pipelinekit."
```

## Snippets catalog (mandatory for rich content)

The `claude/skills/docs-writer/snippets/` directory ships ready-to-embed
interactive HTML components. Each is self-contained: inline `<style>` (scoped
to its mount root), inline `<script>` (IIFE), inline SVG icons. All snippets
inherit the parent template's CSS custom properties (`--bg`, `--accent`,
`--fg-muted`, etc.) so they auto-theme with the page.

Reference a snippet in any markdown source with:

```html
<div data-snippet="<snippet-name>"></div>
```

…and `render.py` inlines the snippet content at render time. Extra
`data-*` attributes on the placeholder are forwarded to the snippet's
mount root for per-instance configuration.

### Available snippets

| Snippet name | Demonstrates HTML > markdown via | Use on |
|--------------|----------------------------------|--------|
| `pipeline-phase-diagram` | Animated SVG flow, hover tooltips, click-to-scroll, path-filter buttons | `pipeline.html` (and anywhere explaining /pipeline) |
| `cost-calculator` | Live sliders + toggles + dropdowns; real-time numeric output; export-as-JSON | `review-cost.html`, any cost/budget reference |
| `tutorial-cards` | Card grid with hover effects + colored top borders + meta badges; click-to-anchor | `getting-started.html`, any tutorial index |
| `architecture-diagram` | 4-layer stack visualization with hover-tooltips and layer-filter | `index.html`, `architecture.html` |
| `deployment-provider-quiz` | Multi-step quiz w/ provider-fit recommendation, observability + region + CI-runner axis (6 questions, recommends Vercel/Railway/Render/DigitalOcean/Azure plus Blacksmith for CI). Cross-ref: extends `chooser-quiz` deploy set — keep both until embeds settle. | `deployment-chooser.html`, all `deployment-*.html` |
| `path-routing-diagram`     | Decision-tree SVG for Path A/B/C/M/N routing logic w/ clickable nodes scrolling to `pipeline.html` § Path anchors. Cross-ref: complementary to `pipeline-phase-diagram` (lifecycle flow). | `pipeline.html` |
| `command-cheatsheet`       | Searchable ≥40-row slash-command table; scoped `<input type="search">` filter with 120ms debounce; arguments + defaults + one-line description. JSON island data (hand-maintained). | `pipeline.html`, `getting-started.html` |
| `cost-budget-meter`        | Twin dial-gauge SVG showing `$ spent / max-usd` + `turns / max-turns`; CSS-animated fill; degrades to open-ended bar when cap is `unlimited`. Config via `data-spent-usd`/`data-max-usd`/`data-spent-turns`/`data-max-turns` attributes. | `review-cost.html` |
| `before-after-slider`      | Generic horizontal scrubber with clip-path reveal between two arbitrary content regions; ARIA-compliant `<input type="range">`; respects `prefers-reduced-motion`. Reusable shell. | (optional — future release-notes pages) |

When a use case isn't covered, build a new snippet rather than falling back to
plain markdown. See § Authoring a new snippet below for the contract.

### Authoring a new snippet

1. Create `claude/skills/docs-writer/snippets/<kebab-case-name>.html`.
2. The root element MUST carry `class="pkit-<short-tag>"` and
   `data-snippet-mount="<name>"` (matches the file basename without `.html`).
3. Inline `<style>` immediately after the root element open; scope all
   selectors to `.pkit-<short-tag>` to avoid cross-snippet collisions.
4. Inline `<script>` immediately after the root element close; wrap as an IIFE
   `(function() { 'use strict'; … })();`. Use
   `document.querySelectorAll('[data-snippet-mount="<name>"]')` to find the
   instance(s); guard against double-init via `dataset.pkitInit`.
5. Use ONLY the parent template's CSS custom properties for colors / radii /
   transitions / fonts. Do not hard-code colors; do not import fonts.
6. No remote assets. No CDN scripts. No `<link rel="stylesheet">`.
7. Add a one-line header comment with usage and a row to the catalog table
   above.
8. Add at least one richness test case to
   `claude/skills/docs-writer/tests/test_render.sh` that confirms the snippet
   substitutes cleanly.

## Output directory contract

The skill writes to **`documentation/`** only.

| Path | Use case | Examples |
|------|----------|----------|
| `documentation/*.html` | Reader-facing pages and vendored reference standards. | `installation.html`, `pipeline.html`, `deployment-vercel.html`, `SKILL-AUTHORING-STANDARD.html`, `SKILL_PIPELINE.html`, `NOTICE.html` |

Never write to `docs/`. Never write `.md` to `documentation/`. Compliance audit reports are workflow artifacts and belong under `docs/` (workflow-only) or `.claude/audits/`, not `documentation/`.

## Template features (what the reader gets)

Every emitted page automatically has:

- **Top bar** with brand, breadcrumb, in-page search (`/` keyboard shortcut), and theme toggle (Auto / Light / Dark — preference persisted to `localStorage`).
- **Sticky sidebar ToC** auto-generated from H2/H3 headings, with active-section highlighting via IntersectionObserver (scrollspy).
- **Mobile drawer** — ToC collapses below 900px and surfaces via a "Contents" button.
- **Code blocks** — Pygments syntax highlighting (language inferred from fenced-code language hint), copy-to-clipboard button on hover, language label.
- **Tables** — sortable by clicking any column header (ascending → descending → no sort), responsive horizontal-scroll wrapper.
- **Headings** — automatic `id=` attributes (slug-derived), hover anchor `#` for permalinks, smooth-scroll to fragment.
- **Callouts** — blockquotes beginning with `[INFO]`, `[NOTE]`, `[TIP]`, `[WARN]`, `[WARNING]`, `[DANGER]`, `[ALERT]`, `[SUCCESS]`, `[OK]` are auto-styled with color-coded left border and icon.
- **Details/Summary** — `<details><summary>` blocks render as collapsible sections with rotating arrow.
- **Search filter** — `/` focuses the search box; typing highlights matches in body text and hides non-matching table rows. `Esc` clears.
- **Theme** — 7 CSS custom properties for light + 7 for dark, with `prefers-color-scheme` respected as the default and user override persisted. WCAG 2.1 AA contrast on all primary text pairings (verified in [NOTICE.html](../../../documentation/NOTICE.html)).
- **Self-contained** — no CDN, no external stylesheet, no remote font, no remote script. Reader can clone the repo and open `documentation/index.html` directly via `file://`.

## When this skill fires

1. **Slash-invocation** — `/docs-writer <markdown-path> <html-path>` (user-initiated).
2. **`/pipeline` Documentation Update Phase** — after a feature merges, `/pipeline` dispatches the skill to update any documentation/ pages affected by the change.
3. **`/document-release` post-merge** — release-documentation calls into `docs-writer` to emit per-release HTML pages.
4. **Author-triggered** — when committing a new feature, the implementer or follow-up author runs `render.py` directly to produce the user-facing page.

## Enforcement

The compliance contract is enforced via the existing `block-stage-sensitive.sh` PreToolUse hook and its data file `claude/config/never-stage.txt`. The following patterns refuse staging:

- `documentation/**/*.md` — no markdown in documentation tree.
- `docs/*` — no commits into docs/ (AI-workflow-only).

If you have a legitimate need to commit a file matching either pattern (e.g., a docs-source markdown file that gets converted; or a user feature list under `docs/`), bypass the hook with `git add -f <path>` after confirming the intent.

## Migration from docs-writer/1

v0.0.1 introduced the docs-writer/2 rich template (this skill). The previous version shipped three helper scripts and a basic stylesheet:

- `migrate-md-to-html.sh` (wrapped markdown in `<pre>`) — REMOVED. Replaced by `render.py` which parses markdown into semantic HTML.
- `generate-index.sh` (basic index) — REMOVED. Replaced by `render.py` on a markdown index source.
- `nav-from-headings.sh` (ToC generator) — REMOVED. ToC generation moved into `render.py`.

If you have a checkout from before v0.0.1, regenerate any pages produced by the old scripts via:

```bash
for f in documentation/*.html; do
  python3 claude/skills/docs-writer/render.py --from-html "$f" "$f.new" && mv "$f.new" "$f"
done
```

## Related

- The shipped template `claude/skills/docs-writer/template.html` — open it in a browser to see the CSS / JS surface.
- The renderer `claude/skills/docs-writer/render.py` — `--help` for the full CLI.
- [SKILL authoring standard](../../../documentation/SKILL-AUTHORING-STANDARD.html) — the 10-pattern skill DNA template.
- [Vendoring notice](../../../documentation/NOTICE.html) — attribution + license for vendored standards.
