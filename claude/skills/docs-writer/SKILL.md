---
name: docs-writer
description: Render a repository's project documentation as offline, self-contained HTML pages committed under its documentation/ folder (markdown sources in docs-source/, rendered with a bundled template that adds a sidebar ToC, search, code highlighting, theme toggle and optional interactive widgets). Use when the user wants to write, add, regenerate or restyle pages in a repo's documentation/ directory, or turn docs-source/*.md into HTML docs. Do NOT use for claude.ai documents or Artifacts, Word/PDF/slides, README.md or other plain markdown files, API docstrings, or docs/ AI-workflow notes.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
paths:
  - docs-source/**
  - documentation/**
---

# docs-writer

Turns markdown in `docs-source/` into self-contained HTML pages in `documentation/`. Each page inlines all CSS, JS and icons (no CDN, no remote fonts), so it works from any static host or straight from disk via `file://`.

Requires Python 3.9+ and `pip install markdown pygments` (`pyyaml` is optional, for YAML frontmatter). If an import fails, tell the user the install command; do not vendor the packages.

## Layout

| Path (in the target repo) | What |
|---|---|
| `docs-source/<page>.md` | Markdown source. Commit it. |
| `documentation/<page>.html` | Rendered page. Commit it. Never write `.md` here. |
| `documentation/search.json` | Search index written by batch mode (used by the `search-widget` snippet). |

The bundled assets live next to this file: `template.html`, `render.py`, `verify_toc.py`, `richness_check.py`, `snippets/`. Always call them through `${CLAUDE_SKILL_DIR}` and run from the target repo's root.

## Workflow

1. **Write the source** in `docs-source/<page>.md`. Start with one `# H1` (becomes the title) and a first paragraph (becomes the description). Use `##`/`###` for sections; they build the sidebar ToC.
2. **Render one page:**
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/render.py" docs-source/<page>.md documentation/<page>.html
   ```
   Optional flags: `--title`, `--description`, `--source-link URL`, `--meta "Label: value"` (repeatable). `-` reads stdin / writes stdout.
3. **Or render everything** (all `docs-source/*.md`, plus `documentation/search.json`):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/render.py"            # from the repo root
   python3 "${CLAUDE_SKILL_DIR}/render.py" --root /path/to/repo
   ```
4. **Check the ToC** (broken sidebar links, duplicate heading ids). Must exit 0:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/verify_toc.py"                       # all of ./documentation
   python3 "${CLAUDE_SKILL_DIR}/verify_toc.py" documentation/<page>.html
   ```
5. **Optional, advisory:** check that pages carry some interactive content (a snippet, a diagram SVG, a form control or a `<details>` block; long pages need two):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/richness_check.py" --all -v
   ```
   Add a snippet where it genuinely helps the reader. Reference pages that should stay plain can opt out with `<!-- richness-exempt: reason -->`.

Fix problems in the markdown source and re-render; do not hand-edit generated HTML. For HTML with no markdown source, `render.py --from-html in.html out.html` rewraps its `<body>` in the template.

## What every page gets

Top bar with in-page search (`/` to focus, `Esc` to clear) and an Auto/Light/Dark theme toggle; sticky sidebar ToC with scrollspy (a drawer under 900px); Pygments highlighting and copy buttons on fenced code; sortable tables; heading permalinks; callouts from blockquotes starting with `[NOTE]`, `[TIP]`, `[WARN]`, `[DANGER]` or `[SUCCESS]`; styled `<details>`. The footer links to `credits.html`; create that page or edit `template.html` if the repo has none.

## Interactive snippets

Embed a widget with a raw-HTML placeholder in the markdown (blank line before and after). The page supplies the widget's content as a JSON child; `render.py` inlines `snippets/<name>.html`, moves the children into the widget, and forwards extra attributes (e.g. `data-title`) to it:

```html
<div data-snippet="comparison-tabs">
<script type="application/json">
{"items": {"a": {"name": "SQLite", "rows": {"Setup": "None"}},
           "b": {"name": "Postgres", "rows": {"Setup": "Server"}}}}
</script>
</div>
```

| Snippet | Use for | Content supplied by the page |
|---|---|---|
| `architecture-diagram` | Layered system overview with tooltips and layer filter | JSON `layers` |
| `before-after-slider` | Drag-to-compare two panels | `<div data-bas-before>` and `<div data-bas-after>` children |
| `chooser-quiz` | "Which option fits me?" decision quiz | JSON `questions` + `recommend` |
| `command-cheatsheet` | Filterable CLI/command reference | JSON rows `name`, `args`, `description` |
| `comparison-tabs` | Compare one option against several others | JSON `items` |
| `live-linter` | Paste-and-check against regex rules | JSON `rules` (+ `example`) |
| `playground-2col` | Side-by-side input/output examples with presets | JSON `presets` |
| `search-widget` | Cross-page search (for an index page) | none; reads `search.json` from batch mode |
| `terminal-simulator` | Replayed terminal session | JSON step list (+ `data-title`) |
| `tutorial-cards` | Card grid linking to sections | JSON cards with `anchor` = a heading id |

Each snippet's header comment documents its full JSON schema. Read it before use: `head -30 "${CLAUDE_SKILL_DIR}/snippets/<name>.html"`. Only use a snippet when its content is about the page's subject; never paste placeholder data.

**New snippet:** add `snippets/<name>.html` with a header comment (purpose + usage), a root element carrying `class="pkit-<tag>"` and `data-snippet-mount="<name>"`, a `<style>` scoped to `.pkit-<tag>` using only the template's CSS variables (`--bg`, `--fg`, `--accent`, `--border`, ...), and an IIFE `<script>` that initialises every mount once (guard with `dataset.pkitInit`) and reads its data from `root.querySelector('script[type="application/json"]')`. No remote assets. Headings inside snippets use a `pkit-*` class so they stay out of the page ToC.

## When to use something else

- A shareable page in claude.ai, or a one-off explainer: use Artifacts / the claude.ai docs skill.
- `README.md`, CHANGELOG, or any markdown meant to be read on GitHub: edit the markdown directly.
- `docs/` holds local AI-workflow notes (plans, reviews); never render reader-facing pages there.

## Tests

```bash
bash "${CLAUDE_SKILL_DIR}/tests/test_render.sh"
bash "${CLAUDE_SKILL_DIR}/tests/test_richness_threshold.sh"
```
