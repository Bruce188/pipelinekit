<!--
diataxis: explanation
-->
# Design tokens

Canonical visual reference for pipelinekit's `claude/skills/docs-writer/template.html` design tokens. Every page rendered via `render.py` consumes these CSS custom properties — modifying them retheme every shipped page atomically.

## What

The `docs-writer/2` template ships with **41 CSS custom properties** (22 light-theme + 19 dark-theme overrides, plus shared typography / radii / syntax / motion tokens). All snippets, all content blocks, and the topbar / sidebar / footer chrome consume these tokens — there are zero hard-coded colors in production. Dark mode is a token swap; print mode skips them entirely.

This page is the canonical Visual-token exemplar referenced from [HTML effectiveness principles](html-effectiveness-principles.html). It shows every token rendered, side-by-side light vs dark where applicable, with the exact property name. Use it as a reference when authoring a new snippet (snippets MUST use only these tokens — see § Authoring a new snippet in [docs-writer SKILL.md](../claude/skills/docs-writer/SKILL.md)).

## Color swatch

The 22 light tokens (top) and the 19 dark-mode overrides (bottom). The dark scheme overrides backgrounds, foregrounds, borders, accent, semantic, shadow, and the 7 syntax tokens; radii / typography / motion are shared and do not flip.

<div data-snippet="comparison-tabs"></div>

### Backgrounds (4)

| Token | Light | Dark |
|-------|-------|------|
| `--bg` | <code style="background:#ffffff;color:#1a1d23;padding:0 .4em;border:1px solid #e1e5eb">#ffffff</code> page background | <code style="background:#0b0f1a;color:#e8ecf3;padding:0 .4em;border:1px solid #1f2638">#0b0f1a</code> |
| `--bg-elev` | <code style="background:#fafbfc;color:#1a1d23;padding:0 .4em;border:1px solid #e1e5eb">#fafbfc</code> elevated surfaces (topbar / cards) | <code style="background:#131825;color:#e8ecf3;padding:0 .4em;border:1px solid #1f2638">#131825</code> |
| `--bg-code` | <code style="background:#f4f5f7;color:#1a1d23;padding:0 .4em;border:1px solid #e1e5eb">#f4f5f7</code> code-block fill | <code style="background:#161c2c;color:#e8ecf3;padding:0 .4em;border:1px solid #1f2638">#161c2c</code> |
| `--bg-sel` | <code style="background:#e3f2fd;color:#1a1d23;padding:0 .4em;border:1px solid #e1e5eb">#e3f2fd</code> text-selection highlight | <code style="background:#1e3a5f;color:#e8ecf3;padding:0 .4em;border:1px solid #1f2638">#1e3a5f</code> |

### Foregrounds (3)

| Token | Light | Dark |
|-------|-------|------|
| `--fg` | <code style="background:#ffffff;color:#1a1d23;padding:0 .4em;border:1px solid #e1e5eb">#1a1d23</code> primary text | <code style="background:#0b0f1a;color:#e8ecf3;padding:0 .4em;border:1px solid #1f2638">#e8ecf3</code> |
| `--fg-muted` | <code style="background:#ffffff;color:#5a6172;padding:0 .4em;border:1px solid #e1e5eb">#5a6172</code> secondary text | <code style="background:#0b0f1a;color:#9aa3b3;padding:0 .4em;border:1px solid #1f2638">#9aa3b3</code> |
| `--fg-subtle` | <code style="background:#ffffff;color:#8b94a3;padding:0 .4em;border:1px solid #e1e5eb">#8b94a3</code> tertiary / placeholder | <code style="background:#0b0f1a;color:#6b7589;padding:0 .4em;border:1px solid #1f2638">#6b7589</code> |

### Borders (2)

| Token | Light | Dark |
|-------|-------|------|
| `--border` | <code style="background:#e1e5eb;color:#1a1d23;padding:0 .4em">#e1e5eb</code> default dividers | <code style="background:#1f2638;color:#e8ecf3;padding:0 .4em">#1f2638</code> |
| `--border-strong` | <code style="background:#c5cbd4;color:#1a1d23;padding:0 .4em">#c5cbd4</code> emphasized borders | <code style="background:#2a3349;color:#e8ecf3;padding:0 .4em">#2a3349</code> |

### Accents (3)

| Token | Light | Dark |
|-------|-------|------|
| `--accent` | <code style="background:#2563eb;color:#ffffff;padding:0 .4em">#2563eb</code> links, focus rings | <code style="background:#60a5fa;color:#0b0f1a;padding:0 .4em">#60a5fa</code> |
| `--accent-hover` | <code style="background:#1d4ed8;color:#ffffff;padding:0 .4em">#1d4ed8</code> link hover | <code style="background:#93c5fd;color:#0b0f1a;padding:0 .4em">#93c5fd</code> |
| `--accent-soft` | <code style="background:#dbeafe;color:#1a1d23;padding:0 .4em">#dbeafe</code> active-ToC backgrounds | <code style="background:#1e3a8a;color:#e8ecf3;padding:0 .4em">#1e3a8a33</code> |

### Semantic (3)

| Token | Light | Dark |
|-------|-------|------|
| `--success` | <code style="background:#059669;color:#ffffff;padding:0 .4em">#059669</code> callout success / OK | <code style="background:#34d399;color:#0b0f1a;padding:0 .4em">#34d399</code> |
| `--warn` | <code style="background:#d97706;color:#ffffff;padding:0 .4em">#d97706</code> callout warning | <code style="background:#fbbf24;color:#0b0f1a;padding:0 .4em">#fbbf24</code> |
| `--danger` | <code style="background:#dc2626;color:#ffffff;padding:0 .4em">#dc2626</code> callout danger | <code style="background:#f87171;color:#0b0f1a;padding:0 .4em">#f87171</code> |

### Shadows (2)

| Token | Light | Dark |
|-------|-------|------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.04)` | `0 1px 2px rgba(0,0,0,0.3)` |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.08)` | `0 4px 12px rgba(0,0,0,0.4)` |

## Type scale

pipelinekit ships a **2-family type scale** — one monospace stack, one humanist sans stack. Font sizes are NOT tokenized; they live inline at `h1` 2rem / `h2` 1.6rem / `h3` 1.25rem / `body` 15px / `code` 0.88em. Adding a third family or token-izing sizes is out of scope per analysis-v88 OQ-5.

| Token | Stack | Used for |
|-------|-------|----------|
| `--mono` | `ui-monospace, "JetBrains Mono", "SF Mono", "Cascadia Code", "Consolas", monospace` | `<code>`, `<pre>`, syntax-highlighted blocks |
| `--sans` | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif` | body text, headings, UI chrome |

## Spacing & radii scale

Radii are tokenized; spacing is not. Spacing follows an observed inline `0.4 / 0.5 / 1.0 / 1.5 / 2.0 rem` scale — present consistently across the template and shipped snippets but never bound to a custom property. Per analysis-v88 OQ-5 this is "scale observed, not tokenized"; deferring a `--spacing-*` token series is intentional until a real cross-page inconsistency surfaces.

| Token | Value | Used for |
|-------|-------|----------|
| `--radius` | `6px` | default rounded corners (buttons, cards, codeblocks, table wrappers) |
| `--radius-sm` | `4px` | smaller inline elements (inline `<code>`, sortable-header indicators) |

## Syntax highlighting tokens

Seven tokens drive Pygments class output. They consume the `.codehilite .<class>` selector set generated by `render.py` from fenced code blocks.

```python
def example(value: int) -> str:
    """Doc string demonstrating syntax-highlight tokens."""
    keyword = True            # number token
    message = "hello"         # string token
    return f"{message}::{value}"
```

| Token | Light | Dark | Pygments class(es) |
|-------|-------|------|--------------------|
| `--syn-kw` | <code style="background:#f4f5f7;color:#7c3aed;padding:0 .4em">#7c3aed</code> | <code style="background:#161c2c;color:#c084fc;padding:0 .4em">#c084fc</code> | `.k`, `.kn`, `.kd`, `.kr`, `.kt` |
| `--syn-str` | <code style="background:#f4f5f7;color:#059669;padding:0 .4em">#059669</code> | <code style="background:#161c2c;color:#4ade80;padding:0 .4em">#4ade80</code> | `.s`, `.s1`, `.s2`, `.sb` |
| `--syn-num` | <code style="background:#f4f5f7;color:#d97706;padding:0 .4em">#d97706</code> | <code style="background:#161c2c;color:#fbbf24;padding:0 .4em">#fbbf24</code> | `.mi`, `.mf`, `.mh`, `.mo` |
| `--syn-com` | <code style="background:#f4f5f7;color:#6b7280;padding:0 .4em">#6b7280</code> | <code style="background:#161c2c;color:#94a3b8;padding:0 .4em">#94a3b8</code> | `.c`, `.c1`, `.cm`, `.ch` |
| `--syn-fn` | <code style="background:#f4f5f7;color:#2563eb;padding:0 .4em">#2563eb</code> | <code style="background:#161c2c;color:#60a5fa;padding:0 .4em">#60a5fa</code> | `.nf`, `.fm`, `.nv`, `.nb` |
| `--syn-cls` | <code style="background:#f4f5f7;color:#db2777;padding:0 .4em">#db2777</code> | <code style="background:#161c2c;color:#f472b6;padding:0 .4em">#f472b6</code> | `.nc`, `.ne` |
| `--syn-op` | <code style="background:#f4f5f7;color:#1f2937;padding:0 .4em">#1f2937</code> | <code style="background:#161c2c;color:#e8ecf3;padding:0 .4em">#e8ecf3</code> | `.o`, `.ow` |

## Motion

One motion token. Used by hover / focus transitions on links, buttons, ToC items, theme toggle, and code-copy buttons.

| Token | Value | Used for |
|-------|-------|----------|
| `--transition` | `150ms ease` | hover-state colour swaps, border swaps, accent ring fade-in |

Snippets respect `prefers-reduced-motion: reduce` per the accessibility contract — animations are dampened, never the `--transition` token itself.

## Light vs dark scrubber

Scrub the slider below to compare the same primary token surface under the light theme and the dark theme — the swap operates entirely through CSS custom properties.

<div data-snippet="before-after-slider"></div>

## See also

- [HTML effectiveness principles](html-effectiveness-principles.html) — the four-category rubric that places this page in the Visual-token slot.
- [docs-writer SKILL.md](../claude/skills/docs-writer/SKILL.md) — § "Authoring a new snippet" and the Snippet catalog.
- `claude/skills/docs-writer/template.html` lines 12-67 — the canonical source for every token enumerated here.
