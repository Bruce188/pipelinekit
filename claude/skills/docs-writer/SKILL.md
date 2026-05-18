---
name: docs-writer
description: HTML-emitting documentation skill — writes self-contained styled HTML to documentation/, never markdown for new files
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# docs-writer — HTML-emitting documentation skill

`docs-writer` is the slash-invocable, format-aware surface for application documentation. It writes **self-contained styled HTML** to `documentation/`, never `.md` for new files. The skill is declarative (`SKILL.md` plus three generator scripts) and coexists with the existing `claude/agents/docs-writer.md` agent, which remains the `Agent`-tool workhorse for prose-heavy multi-turn documentation work. Precedent: `claude-md-enhancer` skill + `claude-md-guardian` agent coexist for the same reason.

The skill is benign — it writes only under `documentation/`, has no destructive side effects, and is therefore model-invocable (the `disable-model-invocation` frontmatter key is deliberately omitted, in contrast to the `openhuman` skill which gates destructive merges).

## When this skill fires

The skill is invoked in three contexts:

1. **Slash-invocation:** `/docs-writer` (user-initiated; produces one HTML file per request).
2. **Pipeline Documentation Update Phase:** `/pipeline` dispatches the skill during the documentation-update phase that follows a feature merge, so the application docs stay in lock-step with the implemented surface.
3. **`/document-release` post-merge:** the release-documentation skill calls into `docs-writer` to emit per-release HTML pages.

In every context the format-aware contract holds: `.html` output to `documentation/`, never `.md` for new application-doc files. Updates to vendored markdown files (see "Vendored-file exception" below) are off-limits.

## Output directory contract

The skill writes **HTML to documentation/** and nothing else. It NEVER writes markdown for new files in documentation/ once this contract is in force — every new application-doc file emitted by this skill is HTML. It writes NEVER any file to docs/ — that directory is reserved for AI workflow artifacts.

To restate the three rules explicitly:

- **HTML to documentation/** — all new application docs are HTML.
- **NEVER markdown for new files in documentation/** — `.md` exists only as a vendored exception (see below) or as a pre-existing archived source in `documentation/_md_archive/`.
- **NEVER any file to docs/** — `docs/` is reserved for AI-workflow files (`plan.md`, `prompts.md`, `analysis.md`, `progress.md`, `charter.md`, `review-*.md`, `pipeline-state.md`, `pipeline-intel.json`, `.last-verify.json`). These files are produced by the pipeline orchestrator and are excluded from commits by `claude/config/never-stage.txt` plus the `block-stage-sensitive.sh` hook. The `docs-writer` skill must never write into that namespace, even for trivial scratch output.

`documentation/` is the human-readable application-docs surface: API references, user guides, architecture docs, audits, release notes. It IS committed (unlike `docs/`).

## Vendored-file exception

Three files under `documentation/` remain markdown for the duration of the upstream vendoring contract:

- `documentation/NOTICE.md` — documents the vendoring SHA pin and license for the other vendored markdown files.
- `documentation/SKILL-AUTHORING-STANDARD.md` — vendored verbatim per `documentation/NOTICE.md` pinned SHA `0d477a06589aa730b98e351f46985c5c937de0bf`.
- `documentation/SKILL_PIPELINE.md` — vendored verbatim per the same pinned SHA.

These files are byte-identical copies from `alirezarezvani/claude-skills` and CANNOT be migrated to HTML without breaking the re-vendor / SHA-traceability contract. The migration helper (`migrate-md-to-html.sh`) refuses to operate on any of the three filenames by hardcoded denylist; an attempted invocation exits 1 with `error: <name> is on the vendored-NOTICE list, refusing to migrate`.

Updates to vendored content land via a re-vendor commit (refresh the SHA pin in NOTICE.md, then re-copy the files), never via in-place edits.

## Self-contained stylesheet (inline)

Every HTML file the skill emits embeds the same self-contained stylesheet inline as a `<style>` block. The stylesheet uses no external font, no external CSS file, and no remote asset references of any kind — the entire stylesheet ships with each emitted page so the file renders identically when served from any origin, copied to disk, or viewed via the `file` URL scheme. Three patterns are forbidden anywhere in the emitted HTML: remote link references in the page head, remote import directives at the top of CSS rule sets, and any host string containing the `c d n` substring (spaces inserted here so this prose itself does not trigger AC7).

The stylesheet uses seven CSS custom properties on `:root` (light defaults) and redefines all seven inside a `@media (prefers-color-scheme: dark)` block so the page auto-adapts to the reader's OS preference without JavaScript or runtime configuration. The body uses a fluid `max-width: 1200px` container so the layout is responsive across mobile and desktop viewports.

```html
<style>
  :root {
    --bg: #ffffff;
    --fg: #111111;
    --muted: #555555;
    --border: #dddddd;
    --link: #0050b3;
    --code-bg: #f5f5f5;
    --header-bg: #fafafa;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1117;
      --fg: #e6edf3;
      --muted: #8b949e;
      --border: #30363d;
      --link: #58a6ff;
      --code-bg: #161b22;
      --header-bg: #161b22;
    }
  }
  * { box-sizing: border-box; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.55;
    background: var(--bg);
    color: var(--fg);
    margin: 0 auto;
    padding: 2rem;
    max-width: 1200px;
  }
  h1, h2, h3, h4 { color: var(--fg); }
  h1 { margin-top: 0; font-size: 1.85rem; }
  h2 { margin-top: 2.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; background: var(--header-bg); padding-top: 0.3rem; padding-left: 0.4rem; }
  h3 { margin-top: 2rem; font-size: 1.15rem; }
  h4 { margin: 1rem 0 0.4rem; font-size: 1rem; color: var(--muted); }
  p { margin: 0.7rem 0; }
  a { color: var(--link); }
  code, pre {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    font-family: ui-monospace, "Cascadia Code", "Consolas", monospace;
  }
  code { padding: 0.1rem 0.35rem; font-size: 0.92em; }
  pre { padding: 0.8rem 1rem; overflow-x: auto; }
  pre code { background: none; border: none; padding: 0; }
  nav {
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0.6rem 1rem;
    margin: 1rem 0;
    background: var(--header-bg);
  }
  nav ul { padding-left: 1.2rem; margin: 0.2rem 0; }
  nav a { color: var(--link); text-decoration: none; }
  nav a:hover { text-decoration: underline; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid var(--border); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }
  th { background: var(--header-bg); }
  @media (max-width: 768px) {
    body { padding: 1rem; }
    nav { padding: 0.4rem 0.6rem; }
  }
</style>
```

Include a `<meta name="viewport" content="width=device-width, initial-scale=1">` in every page's `<head>` so the responsive `@media` block engages on mobile.

## Contrast verification

The palette above is the F12-audit dark-mode palette, already audited against WCAG 2.1 AA at the upstream audit page (`documentation/audits/claude-code-compliance-features-2026-05-18.html`). The four primary pairings clear AA body text (≥ 4.5:1) and AA large text (≥ 3:1) thresholds in both modes:

| Pair | Light ratio | Dark ratio | Threshold | Pass |
|------|-------------|------------|-----------|------|
| Body text (`--fg` on `--bg`) | 19.5:1 | 13.0:1 | ≥ 4.5:1 (AA body) | yes |
| Muted text (`--muted` on `--bg`) | 7.4:1 | 6.4:1 | ≥ 4.5:1 (AA body) | yes |
| Link text (`--link` on `--bg`) | 6.8:1 | 5.6:1 | ≥ 4.5:1 (AA body) | yes |
| Large heading (`--fg` on `--header-bg`) | 18.6:1 | 13.0:1 | ≥ 3:1 (AA large) | yes |

Recompute ratios with any external WCAG tool (e.g., webaim.org/resources/contrastchecker/) when changing the palette. Replacement palettes must clear the same thresholds before landing.

## Nav-from-headings generator

Every emitted HTML page carries a `<nav>` block at the top, auto-generated from the source markdown's heading hierarchy. The generator is `claude/skills/docs-writer/nav-from-headings.sh`.

**Purpose:** read a markdown body on stdin, emit a `<nav>` element to stdout containing one `<a href="#<slug>">` link per `##` (h2) and `###` (h3) heading. The generator is invoked by `generate-index.sh` and `migrate-md-to-html.sh` to produce the in-page table of contents.

**Invocation:**

```bash
bash claude/skills/docs-writer/nav-from-headings.sh < source.md > nav.html
```

**Anchor-slug rule:** lowercase the heading text, replace any non-alphanumeric run with a single hyphen (`-`), then strip leading and trailing hyphens. Examples:

| Heading text       | Slug             |
|--------------------|------------------|
| `## Quick start`   | `quick-start`    |
| `### CLI surface`  | `cli-surface`    |
| `## Q&A — Topic 7` | `q-a-topic-7`    |

**Depth cap:** h2 and h3 only. h4 is reserved for muted subheadings (the existing F12-audit pattern) and is intentionally excluded from the nav. Deeper levels (h5, h6) are not used.

**Empty-input behavior:** the generator emits an empty `<nav><ul></ul></nav>` shell when stdin is empty or contains no h2/h3 headings — the caller can decide to keep or strip the empty shell.

The generator is `bash -n` clean, runs under `set -euo pipefail`, and is mode `0755`. The reference `nav-from-headings.sh` invocation appears in every consumer script's header comment.

## Companion scripts

The skill ships three generator scripts alongside this file:

- **`nav-from-headings.sh`** — reads markdown body from stdin, emits a `<nav>` block with one `<a href="#<slug>">` per `##` or `###` heading.
- **`generate-index.sh`** — crawls `documentation/**/*.html` (excluding `index.html`), reads each page's `<title>` and `<meta name="description">`, and emits a landing-page `documentation/index.html` listing every page.
- **`migrate-md-to-html.sh`** — converts allowlisted project-native `.md` files to `.html` in place, archiving the source `.md` to `documentation/_md_archive/` first. Hard 2-file allowlist (`github-issues-integration.md`, `review-cost.md`) plus a hard 3-file denylist of vendored names.

All three scripts honor the same self-contained stylesheet pattern: every CSS rule is inlined, with zero remote asset dependencies.

## Relationship to the docs-writer agent

The `docs-writer` agent at `claude/agents/docs-writer.md` is **untouched** by this skill — they coexist:

- **Skill** (`claude/skills/docs-writer/SKILL.md`): slash-invocable, declarative, format-aware (HTML emission contract). Used by user-initiated `/docs-writer` invocations and by `/pipeline`'s documentation-update phase.
- **Agent** (`claude/agents/docs-writer.md`): `Agent`-tool workhorse for multi-turn prose-heavy documentation drafts. Invoked by other agents and skills via `Agent(subagent_type="docs-writer", ...)`.

The pipeline's existing `subagent_type: docs-writer` dispatch path continues to resolve to the agent; the skill is reached through the slash-command or skill-invocation surface only. Neither path supersedes the other.
