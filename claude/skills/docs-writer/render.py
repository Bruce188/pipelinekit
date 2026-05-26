#!/usr/bin/env python3
"""
docs-writer/2 renderer — markdown to rich-template HTML.

Usage:
    render.py <input.md> <output.html> [--title TITLE] [--description DESC] [--source-link URL]
    render.py                  # batch mode: render every docs-source/*.md → documentation/*.html
                               # and emit documentation/search.json

Reads markdown from <input.md>, renders to semantic HTML via the python-markdown
library with codehilite (Pygments) syntax highlighting, generates an in-page
table of contents from H2/H3 headings, and wraps the output in
claude/skills/docs-writer/template.html.

The template ships its own CSS + JS (inline, self-contained, no CDN). The
output is a single .html file that renders identically when served from any
origin, copied to disk, or viewed via the file:// URL scheme.

Diataxis frontmatter (optional, supported in either YAML or HTML-comment form):

    ---
    diataxis: reference
    ---

    <!-- diataxis: reference -->

When absent, the renderer classifies the page via the slug-based heuristic
in `classify_diataxis()`. The resolved quadrant is rendered as a `.diataxis-chip`
above the page H1.

Required deps (install via: pip install --user --break-system-packages markdown pygments):
    - markdown (>= 3.10)
    - pygments (>= 2.17)
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    print("error: python markdown library not installed", file=sys.stderr)
    print("  install: pip install --user --break-system-packages markdown pygments", file=sys.stderr)
    sys.exit(2)

SKILL_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SKILL_DIR / "template.html"
SNIPPETS_DIR = SKILL_DIR / "snippets"

# Repo root resolved from the skill dir: pipelinekit/claude/skills/docs-writer → pipelinekit/
REPO_ROOT = SKILL_DIR.parents[2]
DOCS_SOURCE_DIR = REPO_ROOT / "docs-source"
DOCS_OUTPUT_DIR = REPO_ROOT / "documentation"

VALID_DIATAXIS = {"tutorial", "how-to", "reference", "explanation"}

# Heuristic: slug-stem → diataxis quadrant when frontmatter is absent.
# Order matters: more-specific patterns first. Tested against every current
# docs-source/*.md filename at module import time? No — just dispatched
# per-file by classify_diataxis().
_DIATAXIS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(getting-started|tutorial-)"), "tutorial"),
    (re.compile(r"(installation|cloud-setup|mcp-lsp-setup|deployment-|ci-blacksmith|memory-graph-stack)"), "how-to"),
    (re.compile(r"^(governance|workflow-hygiene|pipeline|html-effectiveness-principles|skills-scope-policy|design-tokens|review-cost|decisions|harness-paths-investigation|memory-migration-notes|pipeline-charter-revalidation|supply-chain|ppr-research-flag)$"), "explanation"),
]


def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """Parse a leading YAML frontmatter block or HTML-comment metadata block.

    Recognised forms (both at the very top of the file):

        ---
        diataxis: reference
        key: value
        ---

        <!--
        diataxis: reference
        -->

    Returns (metadata_dict, remaining_body). Unrecognised top-of-file content
    leaves the input unchanged and returns an empty dict.
    """
    # YAML frontmatter
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", md_text, re.DOTALL)
    if m:
        meta = _parse_kv_block(m.group(1))
        return meta, md_text[m.end():]
    # HTML-comment frontmatter (used when YAML frontmatter would conflict with
    # downstream tooling that doesn't strip it before rendering).
    m = re.match(r"^<!--\s*\n?(.*?)\n?-->\s*\n", md_text, re.DOTALL)
    if m:
        meta = _parse_kv_block(m.group(1))
        # Only treat as frontmatter if it actually contains key:value lines we recognise.
        if meta:
            return meta, md_text[m.end():]
    return {}, md_text


def _parse_kv_block(block: str) -> dict:
    """Parse a flat `key: value` block (one pair per line). Ignores blank lines
    and lines that don't match the pattern."""
    out: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kv = re.match(r"^([a-zA-Z][\w-]*)\s*:\s*(.+?)\s*$", line)
        if kv:
            out[kv.group(1)] = kv.group(2)
    return out


def classify_diataxis(stem: str) -> str:
    """Map a source-file stem to its Diataxis quadrant via the slug heuristic.

    Default: 'reference'. The default reflects that most pages in pipelinekit
    documentation describe a stable surface (schemas, field tables, glossary
    entries) rather than a step-by-step or conceptual narrative.
    """
    for pattern, quadrant in _DIATAXIS_PATTERNS:
        if pattern.search(stem):
            return quadrant
    return "reference"


def resolve_diataxis(meta: dict, stem: str) -> str:
    """Frontmatter wins; heuristic falls back. Unknown values fall back too."""
    explicit = meta.get("diataxis", "").strip().lower()
    if explicit in VALID_DIATAXIS:
        return explicit
    return classify_diataxis(stem)


def build_diataxis_chip(quadrant: str) -> str:
    """Return the HTML for the chip placed above the page H1.

    Empty string when quadrant is empty (so callers can opt out by passing '')."""
    if not quadrant:
        return ""
    return (
        f'<span class="diataxis-chip diataxis-{html_lib.escape(quadrant)}">'
        f'{html_lib.escape(quadrant)}</span>'
    )


def derive_excerpt(md_text: str, length: int = 200) -> str:
    """Extract the first ~length chars of the first paragraph after H1 for
    indexing. Strips markdown inline syntax (backticks, bold, italic, links)
    so the excerpt reads cleanly in the search-widget result list."""
    body = re.sub(r"^#\s+.+\n?", "", md_text, count=1, flags=re.MULTILINE)
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if para.startswith(("#", "-", "*", "+", "```", ">", "|", "<")):
            continue
        text = re.sub(r"\s+", " ", para)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        if len(text) > length:
            text = text[:length].rsplit(" ", 1)[0] + "…"
        return text
    return ""

# H2 / H3 capture regex (used to build the ToC and to seed `id=` attrs)
HEADING_RE = re.compile(r'^(#{2,3})\s+(.+?)\s*$', re.MULTILINE)

# Fenced code block regex. Matches ``` and ~~~ fences (any language tag).
# Used to strip code-fenced content before scanning for headings so that
# `## MVP boundary` inside a bash heredoc doesn't become a ToC entry.
_CODE_FENCE_RE = re.compile(r'^(```|~~~)[^\n]*\n.*?^\1[ \t]*$', re.MULTILINE | re.DOTALL)


def strip_code_fences(md_text: str) -> str:
    """Remove fenced code blocks (```...``` and ~~~...~~~). Preserves
    surrounding whitespace and line counts (replaces with blank lines)
    so subsequent heading-line offsets remain meaningful for debugging.
    """
    def blank_out(match: re.Match) -> str:
        # Replace the matched block with the same number of newlines so
        # downstream regex line semantics survive.
        return "\n" * match.group(0).count("\n")
    return _CODE_FENCE_RE.sub(blank_out, md_text)


def slugify(text: str) -> str:
    """Lowercase, replace non-alphanumeric runs with '-', strip leading/trailing '-'."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def extract_toc(md_text: str) -> str:
    """Build a ToC <li>...</li> list (no enclosing <ul>) from H2/H3 headings.
    Strips fenced code blocks first so heading-shaped lines inside code don't
    pollute the ToC (e.g., `## MVP boundary` inside a bash heredoc demo)."""
    src = strip_code_fences(md_text)
    seen = set()
    items = []
    for match in HEADING_RE.finditer(src):
        level = len(match.group(1))  # 2 or 3
        title = match.group(2)
        # Strip markdown inline syntax (backticks, bold, italic, links) for ToC label
        clean = re.sub(r"`([^`]+)`", r"\1", title)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
        clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
        slug = slugify(clean)
        base = slug
        n = 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        seen.add(slug)
        cls = f"lvl-{level}"
        items.append(
            f'      <li class="{cls}"><a href="#{slug}">{html_lib.escape(clean)}</a></li>'
        )
    return "\n".join(items)


def fix_heading_ids(html_body: str, slug_sequence: list[str]) -> str:
    """
    python-markdown's 'toc' extension already adds id= to headings via slugify.
    But we want OUR slug scheme. We rewrite ids in the rendered HTML by walking
    headings in document order and assigning slugs from `slug_sequence` in the
    same order — this preserves the per-occurrence dedup that the ToC builder
    used (e.g. three identical "### Run" headings get "run", "run-2", "run-3").
    """
    counter = {"i": 0}

    def replace(match):
        tag = match.group(1)
        existing_attrs = match.group(2) or ""
        inner = match.group(3)
        # Strip any existing id= from existing_attrs
        existing_attrs = re.sub(r'\s*id="[^"]*"', "", existing_attrs)
        # Assign the next slug from the sequence (matches document order).
        idx = counter["i"]
        if idx < len(slug_sequence):
            slug = slug_sequence[idx]
            counter["i"] += 1
        else:
            # Fallback if HTML has more headings than markdown sequence
            # (shouldn't happen in practice).
            text = re.sub(r"<[^>]+>", "", inner).strip()
            slug = slugify(text)
        return f'<{tag} id="{slug}"{existing_attrs}>{inner}</{tag}>'

    # Walk only H2 + H3 — matches HEADING_RE / build_slug_sequence / extract_toc scope.
    # H4 keeps python-markdown's default toc-extension slug; H4s are not surfaced in
    # the ToC sidebar so divergent slugs are harmless. Walking H4 here would consume
    # a slug-sequence slot per H4 and shift all subsequent IDs (issue surfaced by
    # docs-source/cloud-setup.md where bash code-fence content sits between H3s).
    return re.sub(r"<(h[23])([^>]*)>(.*?)</\1>", replace, html_body, flags=re.DOTALL)


def build_slug_sequence(md_text: str) -> list[str]:
    """Build an ordered list of slugs for H2/H3 headings in markdown source.
    Slugs are dedup'd by appending -2, -3, etc. when the same text repeats.
    Returns one slug per heading occurrence, in document order.

    Code-fenced content is stripped before scanning so that heading-shaped
    lines inside code blocks (e.g., `## MVP boundary` in a heredoc demo)
    don't appear in the sequence.
    """
    src = strip_code_fences(md_text)
    seen: set[str] = set()
    sequence: list[str] = []
    for match in HEADING_RE.finditer(src):
        title = match.group(2)
        clean = re.sub(r"`([^`]+)`", r"\1", title)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
        clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
        slug = slugify(clean)
        base = slug
        n = 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        seen.add(slug)
        sequence.append(slug)
    return sequence


# Backwards-compat alias for the dict-based slug_map (no longer used by fix_heading_ids
# but kept available in case any caller imports it).
def build_slug_map(md_text: str) -> dict[str, str]:
    """Deprecated: prefer build_slug_sequence (sequence preserves dedup correctly)."""
    src = strip_code_fences(md_text)
    seen: set[str] = set()
    mapping: dict[str, str] = {}
    for match in HEADING_RE.finditer(src):
        title = match.group(2)
        clean = re.sub(r"`([^`]+)`", r"\1", title)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
        clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
        slug = slugify(clean)
        base = slug
        n = 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        seen.add(slug)
        # Note: this overwrites earlier identical text — known-bad,
        # use build_slug_sequence instead.
        mapping[clean] = slug
    return mapping


def render_markdown(md_text: str) -> str:
    """Render markdown to HTML with syntax highlighting and standard extensions."""
    md = markdown.Markdown(
        extensions=[
            "fenced_code",
            "tables",
            "codehilite",
            "attr_list",
            "def_list",
            "footnotes",
            "md_in_html",
            "sane_lists",
        ],
        extension_configs={
            "codehilite": {
                "css_class": "codehilite",
                "guess_lang": False,
                "noclasses": False,
            },
        },
        output_format="html5",
    )
    return md.convert(md_text)


def fill_template(
    template: str,
    title: str,
    description: str,
    toc_html: str,
    content_html: str,
    meta_html: str = "",
    footer_right: str = "",
    diataxis_chip: str = "",
) -> str:
    """Substitute {{PLACEHOLDERS}} in the template."""
    return (
        template.replace("{{TITLE}}", html_lib.escape(title))
        .replace("{{DESCRIPTION}}", html_lib.escape(description))
        .replace("{{TOC}}", "\n" + toc_html + "\n    ")
        .replace("{{CONTENT}}", content_html)
        .replace("{{META}}", meta_html)
        .replace("{{FOOTER_RIGHT}}", footer_right)
        .replace("{{DIATAXIS_CHIP}}", diataxis_chip)
    )


def extract_html_body(html_text: str) -> str:
    """Extract the inner content of <body>...</body>. Used for --from-html rewrap mode."""
    m = re.search(r"<body[^>]*>(.*?)</body>", html_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return html_text  # no body tag → assume input is already a body fragment
    inner = m.group(1)
    # Strip <h1>...</h1> (we put title in page-header)
    inner = re.sub(r"<h1[^>]*>.*?</h1>\s*", "", inner, count=1, flags=re.DOTALL)
    return inner.strip()


def derive_title_from_html(html_text: str, fallback: str) -> str:
    """Extract title from <title> or first <h1>."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.DOTALL | re.IGNORECASE)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        # Strip trailing " — pipelinekit" suffix
        t = re.sub(r"\s*[—|-]\s*pipelinekit.*$", "", t)
        if t:
            return t
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL | re.IGNORECASE)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    return fallback


def derive_description_from_html(html_text: str, fallback: str) -> str:
    """Extract from <meta name='description'> or first <p>."""
    m = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"', html_text, re.IGNORECASE
    )
    if m:
        return html_lib.unescape(m.group(1)).strip()
    body = extract_html_body(html_text)
    m = re.search(r"<p[^>]*>(.*?)</p>", body, re.DOTALL | re.IGNORECASE)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        t = re.sub(r"\s+", " ", t)
        if len(t) > 240:
            t = t[:240].rsplit(" ", 1)[0] + "…"
        return t
    return fallback


def extract_toc_from_html(html_text: str) -> str:
    """Build ToC from h2/h3 ids (or text if id missing) in rendered HTML.
    Skips snippet-internal headings (class="pkit-*") so the page sidebar
    doesn't pick up visual sub-headings from embedded snippets."""
    items = []
    for match in re.finditer(
        r"<(h[23])([^>]*)>(.*?)</\1>", html_text, re.DOTALL | re.IGNORECASE
    ):
        tag = match.group(1).lower()
        attrs = match.group(2) or ""
        if _is_snippet_internal(attrs):
            continue
        inner = match.group(3)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        id_match = re.search(r'id="([^"]+)"', attrs)
        slug = id_match.group(1) if id_match else slugify(text)
        lvl = "lvl-2" if tag == "h2" else "lvl-3"
        items.append(f'      <li class="{lvl}"><a href="#{slug}">{html_lib.escape(text)}</a></li>')
    return "\n".join(items)


# Heading classes that mark snippet-internal hierarchy (h2/h3 used for VISUAL
# structure inside a snippet, not as page-level sections). These are skipped
# by the ToC builder and the id-dedup pass so:
#   1. The page sidebar doesn't list snippet-internal headings like "Quiz"
#      from chooser-quiz or "Compare" from comparison-tabs.
#   2. The snippet's own id="pkit-cq-title" (used by its inline JS for
#      hooks) isn't stripped or reassigned.
_SNIPPET_INTERNAL_RE = re.compile(r'class="[^"]*\bpkit-[\w-]+\b')


def _is_snippet_internal(attrs: str) -> bool:
    """True if a heading's attrs mark it as snippet-internal (class="pkit-*")."""
    return bool(_SNIPPET_INTERNAL_RE.search(attrs))


def ensure_heading_ids(html_text: str, *, force_dedup: bool = True) -> str:
    """Ensure page-level h2/h3/h4 have id= attributes (slug-derived from heading text).

    When force_dedup=True (the default), STRIPS any existing id= and reassigns
    via sequential dedup — fixes pages where the prior render produced
    collisions (e.g., two `<h3 id="bootstrap-2">` from two parallel sections
    that both contain a "### Bootstrap"). When False, preserves existing ids.

    Snippet-internal headings (class="pkit-*") are left untouched — their ids
    are used by the snippet's inline JS and must not change."""
    seen = set()

    def replace(match):
        tag = match.group(1)
        attrs = match.group(2) or ""
        inner = match.group(3)
        if _is_snippet_internal(attrs):
            return match.group(0)
        if force_dedup:
            attrs = re.sub(r'\s*id="[^"]*"', "", attrs)
        elif 'id="' in attrs:
            return match.group(0)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        slug = slugify(text)
        base = slug
        n = 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        seen.add(slug)
        return f'<{tag} id="{slug}"{attrs}>{inner}</{tag}>'

    return re.sub(
        r"<(h[234])([^>]*)>(.*?)</\1>",
        replace,
        html_text,
        flags=re.DOTALL | re.IGNORECASE,
    )


def derive_title(md_text: str, fallback: str) -> str:
    """First H1 wins; otherwise the fallback (typically the filename stem)."""
    m = re.search(r"^#\s+(.+?)\s*$", md_text, re.MULTILINE)
    if m:
        title = m.group(1)
        # Strip markdown inline syntax
        title = re.sub(r"`([^`]+)`", r"\1", title)
        title = re.sub(r"\*\*([^*]+)\*\*", r"\1", title)
        return title.strip()
    return fallback


def derive_description(md_text: str, fallback: str) -> str:
    """First non-empty paragraph after H1 (or anywhere if no H1); otherwise fallback.
    Skips paragraphs that are:
      - Headings, lists, code-fences, blockquotes, tables
      - Raw HTML snippet placeholders (e.g., `<div data-snippet="...">`)
      - Raw HTML tags in general (anything starting with `<`)
    """
    # Skip the H1 line if present
    body = re.sub(r"^#\s+.+\n?", "", md_text, count=1, flags=re.MULTILINE)
    # Find first paragraph that isn't markdown structure or a raw HTML tag
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if para.startswith(("#", "-", "*", "+", "```", ">", "|", "<")):
            continue
        # Take first sentence (up to 240 chars)
        sentence = re.sub(r"\s+", " ", para)
        sentence = re.sub(r"`([^`]+)`", r"\1", sentence)
        sentence = re.sub(r"\*\*([^*]+)\*\*", r"\1", sentence)
        sentence = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sentence)
        if len(sentence) > 240:
            cut = sentence[:240].rsplit(" ", 1)[0]
            sentence = cut + "…"
        return sentence
    return fallback


def strip_first_h1(html_body: str) -> str:
    """Remove the first <h1>...</h1> from the rendered body (we put title in page-header)."""
    return re.sub(r"<h1[^>]*>.*?</h1>\s*", "", html_body, count=1, flags=re.DOTALL)


# Snippet substitution
# Replaces `<div data-snippet="<name>" ...></div>` (in markdown or HTML source)
# with the inlined content of `snippets/<name>.html`. Data attributes other
# than `data-snippet` are forwarded to the snippet's mount root, so a source
# can pass per-instance config:
#   <div data-snippet="chooser-quiz" data-question-set="cloud"></div>

_SNIPPET_PLACEHOLDER_RE = re.compile(
    r'<div\s+data-snippet="([^"]+)"([^>]*)></div>',
    re.IGNORECASE,
)


def substitute_snippets(html_body: str, *, missing_ok: bool = False) -> tuple[str, list[str]]:
    """Replace <div data-snippet="..."> placeholders with the corresponding
    snippet content from claude/skills/docs-writer/snippets/<name>.html.

    HTML comments are stashed before substitution so that placeholder examples
    inside snippet documentation comments (e.g., `<!-- usage: <div data-snippet=...> -->`)
    don't get re-substituted on subsequent renders — that would compound
    exponentially across re-renders.

    Returns (new_html, snippet_names_used). Raises FileNotFoundError on
    missing snippet unless missing_ok=True (in which case the placeholder
    is left in place and the missing name is still recorded).
    """
    used: list[str] = []

    # Stash HTML comments to keep substitution from matching placeholder examples
    # inside `<!-- ... -->`. Replace each with a sentinel; restore after substitution.
    comments: list[str] = []

    def stash(m: re.Match) -> str:
        comments.append(m.group(0))
        return f"\x00CMT_{len(comments) - 1}\x00"

    stripped = re.sub(r"<!--.*?-->", stash, html_body, flags=re.DOTALL)

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        extra_attrs = match.group(2).strip()
        snippet_path = SNIPPETS_DIR / f"{name}.html"
        if not snippet_path.exists():
            if missing_ok:
                used.append(name + " (MISSING)")
                return match.group(0)
            raise FileNotFoundError(
                f"snippet not found: {snippet_path} (referenced from data-snippet={name!r})"
            )
        used.append(name)
        content = snippet_path.read_text(encoding="utf-8")
        # The snippet content itself may have HTML comments containing
        # placeholder examples; stash those too so the same substitution pass
        # (over the assembled output) doesn't re-trigger on them.
        content = re.sub(r"<!--.*?-->", stash, content, flags=re.DOTALL)
        # Forward extra data-attrs to the snippet's mount root by injecting
        # them into the first element with `data-snippet-mount`.
        if extra_attrs:
            content = re.sub(
                r'(data-snippet-mount="[^"]+")',
                lambda m: m.group(1) + " " + extra_attrs,
                content,
                count=1,
            )
        return content

    new_html = _SNIPPET_PLACEHOLDER_RE.sub(replace, stripped)

    # Restore stashed comments.
    for i, c in enumerate(comments):
        new_html = new_html.replace(f"\x00CMT_{i}\x00", c)

    return new_html, used


def strip_first_paragraph(html_body: str) -> str:
    """Remove the first <p>...</p> from the rendered body (used when description was auto-derived from it)."""
    return re.sub(r"<p[^>]*>.*?</p>\s*", "", html_body, count=1, flags=re.DOTALL)


def render_one(
    md_text: str,
    *,
    input_stem: str,
    template: str,
    from_html: bool = False,
    title_arg: str | None = None,
    description_arg: str | None = None,
    source_link: str | None = None,
    extra_meta: list[str] | None = None,
) -> tuple[str, dict]:
    """Render a single document. Returns (html_output, search_record).

    The search_record is `{title, slug, excerpt, quadrant}` and is suitable
    for inclusion in the search.json index.
    """
    extra_meta = extra_meta or []

    # Parse frontmatter (only meaningful in markdown mode; harmless in HTML mode).
    if not from_html:
        meta_dict, md_text = parse_frontmatter(md_text)
    else:
        meta_dict = {}

    quadrant = resolve_diataxis(meta_dict, input_stem)

    if from_html:
        title = title_arg or derive_title_from_html(
            md_text, input_stem.replace("-", " ").title()
        )
        description = description_arg or derive_description_from_html(
            md_text, f"{title} — pipelinekit application documentation"
        )
        body_html = extract_html_body(md_text)
        body_html = ensure_heading_ids(body_html)
        if description_arg is None:
            first_p = re.search(r"<p[^>]*>(.*?)</p>", body_html, re.DOTALL | re.IGNORECASE)
            if first_p:
                first_text = re.sub(r"<[^>]+>", "", first_p.group(1)).strip()
                first_text = re.sub(r"\s+", " ", first_text)
                if first_text[:120] == description[:120]:
                    body_html = strip_first_paragraph(body_html)
        body_html, snippets_used = substitute_snippets(body_html)
        toc_html = extract_toc_from_html(body_html)
    else:
        title = title_arg or derive_title(md_text, input_stem.replace("-", " ").title())
        description_was_derived = description_arg is None
        description = description_arg or derive_description(
            md_text, f"{title} — pipelinekit application documentation"
        )
        slug_sequence = build_slug_sequence(md_text)
        body_html = render_markdown(md_text)
        body_html = strip_first_h1(body_html)
        if description_was_derived:
            body_html = strip_first_paragraph(body_html)
        body_html = fix_heading_ids(body_html, slug_sequence)
        body_html, snippets_used = substitute_snippets(body_html)
        toc_html = extract_toc(md_text)

    if snippets_used:
        print(f"  snippets: {', '.join(snippets_used)}", file=sys.stderr)

    meta_items = []
    if source_link:
        meta_items.append(
            f'<span class="meta-item">Source: <a href="{html_lib.escape(source_link)}">{html_lib.escape(source_link)}</a></span>'
        )
    for item in extra_meta:
        if ":" in item:
            label, value = item.split(":", 1)
            meta_items.append(
                f'<span class="meta-item"><strong>{html_lib.escape(label.strip())}:</strong> {html_lib.escape(value.strip())}</span>'
            )
        else:
            meta_items.append(f'<span class="meta-item">{html_lib.escape(item)}</span>')
    meta_html = " · ".join(meta_items)
    footer_right = "Self-contained HTML · no CDN · no remote assets"

    diataxis_chip = build_diataxis_chip(quadrant)

    html_output = fill_template(
        template,
        title=title,
        description=description,
        toc_html=toc_html,
        content_html=body_html,
        meta_html=meta_html,
        footer_right=footer_right,
        diataxis_chip=diataxis_chip,
    )

    excerpt = derive_excerpt(md_text) if not from_html else description
    record = {
        "title": title,
        "slug": input_stem,
        "excerpt": excerpt,
        "quadrant": quadrant,
    }
    return html_output, record


def batch_render() -> int:
    """Render every docs-source/*.md → documentation/*.html and emit search.json.

    Pages that produce non-trivial sub-paths (e.g. `documentation/docs/<x>.html`)
    are NOT auto-rendered by batch mode — those have explicit invocations in
    upstream tooling (typically a separate makefile target or one-off CLI call).
    Batch mode only walks the flat `docs-source/*.md` slate.
    """
    if not TEMPLATE_PATH.exists():
        print(f"error: template not found at {TEMPLATE_PATH}", file=sys.stderr)
        return 2
    if not DOCS_SOURCE_DIR.is_dir():
        print(f"error: docs-source/ not found at {DOCS_SOURCE_DIR}", file=sys.stderr)
        return 2
    DOCS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    records: list[dict] = []
    sources = sorted(DOCS_SOURCE_DIR.glob("*.md"))
    if not sources:
        print(f"warning: no markdown sources in {DOCS_SOURCE_DIR}", file=sys.stderr)

    for src in sources:
        md_text = src.read_text(encoding="utf-8")
        out_path = DOCS_OUTPUT_DIR / (src.stem + ".html")
        try:
            html_output, record = render_one(
                md_text,
                input_stem=src.stem,
                template=template,
            )
        except FileNotFoundError as exc:
            # Missing snippet: log and continue so a single broken page doesn't
            # halt the whole batch. The page is skipped (no HTML written, no
            # search record emitted) so the existing rendered copy survives.
            print(f"  skip {src.name}: {exc}", file=sys.stderr)
            continue
        out_path.write_text(html_output, encoding="utf-8")
        print(
            f"Rendered {src.relative_to(REPO_ROOT)} → {out_path.relative_to(REPO_ROOT)} "
            f"({len(html_output)} bytes, diataxis={record['quadrant']})",
            file=sys.stderr,
        )
        records.append(record)

    search_path = DOCS_OUTPUT_DIR / "search.json"
    search_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote search index {search_path.relative_to(REPO_ROOT)} "
        f"({len(records)} entries)",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="pipelinekit docs-writer/2 renderer")
    parser.add_argument(
        "input",
        nargs="?",
        help=(
            "Input .md (or .html with --from-html) file (or '-' for stdin). "
            "Omit BOTH input and output to trigger batch mode: every docs-source/*.md "
            "renders to documentation/*.html and documentation/search.json is emitted."
        ),
    )
    parser.add_argument("output", nargs="?", help="Output .html file (or '-' for stdout)")
    parser.add_argument("--title", help="Page title (default: derived from first H1)")
    parser.add_argument("--description", help="Meta description (default: derived from first paragraph)")
    parser.add_argument("--source-link", help="Source link added to meta line (e.g., a GitHub URL)")
    parser.add_argument(
        "--meta",
        action="append",
        default=[],
        help="Extra meta-line item, in the form 'Label: value'. Can be repeated.",
    )
    parser.add_argument(
        "--from-html",
        action="store_true",
        help="Treat input as HTML (not markdown) and rewrap in the template. Body content is extracted from <body>...</body>; ToC is built from existing h2/h3 ids.",
    )
    args = parser.parse_args()

    # Batch mode: no positional args → render every docs-source/*.md and emit search.json.
    if args.input is None and args.output is None:
        return batch_render()

    if args.input is None or args.output is None:
        parser.error("both input and output are required (or omit both for batch mode)")

    if args.input == "-":
        md_text = sys.stdin.read()
        input_stem = "stdin"
    else:
        input_path = Path(args.input)
        md_text = input_path.read_text(encoding="utf-8")
        input_stem = input_path.stem

    if not TEMPLATE_PATH.exists():
        print(f"error: template not found at {TEMPLATE_PATH}", file=sys.stderr)
        return 2
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    html_output, _record = render_one(
        md_text,
        input_stem=input_stem,
        template=template,
        from_html=args.from_html,
        title_arg=args.title,
        description_arg=args.description,
        source_link=args.source_link,
        extra_meta=args.meta,
    )

    if args.output == "-":
        sys.stdout.write(html_output)
    else:
        Path(args.output).write_text(html_output, encoding="utf-8")
        print(f"Rendered {args.input} → {args.output} ({len(html_output)} bytes)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
