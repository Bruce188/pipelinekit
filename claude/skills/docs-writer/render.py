#!/usr/bin/env python3
"""
docs-writer/2 renderer — markdown to rich-template HTML.

Usage:
    render.py <input.md> <output.html> [--title TITLE] [--description DESC] [--source-link URL]

Reads markdown from <input.md>, renders to semantic HTML via the python-markdown
library with codehilite (Pygments) syntax highlighting, generates an in-page
table of contents from H2/H3 headings, and wraps the output in
claude/skills/docs-writer/template.html.

The template ships its own CSS + JS (inline, self-contained, no CDN). The
output is a single .html file that renders identically when served from any
origin, copied to disk, or viewed via the file:// URL scheme.

Required deps (install via: pip install --user --break-system-packages markdown pygments):
    - markdown (>= 3.10)
    - pygments (>= 2.17)
"""
from __future__ import annotations

import argparse
import html as html_lib
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

# H2 / H3 capture regex (used to build the ToC and to seed `id=` attrs)
HEADING_RE = re.compile(r'^(#{2,3})\s+(.+?)\s*$', re.MULTILINE)


def slugify(text: str) -> str:
    """Lowercase, replace non-alphanumeric runs with '-', strip leading/trailing '-'."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def extract_toc(md_text: str) -> str:
    """Build a ToC <li>...</li> list (no enclosing <ul>) from H2/H3 headings."""
    seen = set()
    items = []
    for match in HEADING_RE.finditer(md_text):
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


def fix_heading_ids(html_body: str, slug_map: dict[str, str]) -> str:
    """
    python-markdown's 'toc' extension already adds id= to headings via slugify.
    But we want OUR slug scheme. So we rewrite ids in the rendered HTML to match.
    """
    # Match <h2>Foo</h2> -> <h2 id="foo">Foo</h2>, and similar for h3/h4
    def replace(match):
        tag = match.group(1)
        existing_attrs = match.group(2) or ""
        inner = match.group(3)
        # Strip any existing id= from existing_attrs
        existing_attrs = re.sub(r'\s*id="[^"]*"', "", existing_attrs)
        # Compute slug from inner text (strip tags)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        slug = slug_map.get(text, slugify(text))
        return f'<{tag} id="{slug}"{existing_attrs}>{inner}</{tag}>'

    return re.sub(r"<(h[234])([^>]*)>(.*?)</\1>", replace, html_body, flags=re.DOTALL)


def build_slug_map(md_text: str) -> dict[str, str]:
    """Build {clean_heading_text: slug} mapping used by both ToC and heading-id rewrite."""
    seen = set()
    mapping = {}
    for match in HEADING_RE.finditer(md_text):
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
) -> str:
    """Substitute {{PLACEHOLDERS}} in the template."""
    return (
        template.replace("{{TITLE}}", html_lib.escape(title))
        .replace("{{DESCRIPTION}}", html_lib.escape(description))
        .replace("{{TOC}}", "\n" + toc_html + "\n    ")
        .replace("{{CONTENT}}", content_html)
        .replace("{{META}}", meta_html)
        .replace("{{FOOTER_RIGHT}}", footer_right)
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
    """Build ToC from h2/h3 ids (or text if id missing) in rendered HTML."""
    items = []
    for match in re.finditer(
        r"<(h[23])([^>]*)>(.*?)</\1>", html_text, re.DOTALL | re.IGNORECASE
    ):
        tag = match.group(1).lower()
        attrs = match.group(2) or ""
        inner = match.group(3)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        id_match = re.search(r'id="([^"]+)"', attrs)
        slug = id_match.group(1) if id_match else slugify(text)
        lvl = "lvl-2" if tag == "h2" else "lvl-3"
        items.append(f'      <li class="{lvl}"><a href="#{slug}">{html_lib.escape(text)}</a></li>')
    return "\n".join(items)


def ensure_heading_ids(html_text: str) -> str:
    """Ensure all h2/h3/h4 have id= attributes (slug-derived if absent)."""
    seen = set()

    def replace(match):
        tag = match.group(1)
        attrs = match.group(2) or ""
        inner = match.group(3)
        if 'id="' in attrs:
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
    """First non-empty paragraph after H1 (or anywhere if no H1); otherwise fallback."""
    # Skip the H1 line if present
    body = re.sub(r"^#\s+.+\n?", "", md_text, count=1, flags=re.MULTILINE)
    # Find first paragraph that isn't a heading/list/code-fence/blockquote
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if para.startswith(("#", "-", "*", "+", "```", ">", "|")):
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

    Returns (new_html, snippet_names_used). Raises FileNotFoundError on
    missing snippet unless missing_ok=True (in which case the placeholder
    is left in place and the missing name is still recorded).
    """
    used: list[str] = []

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
        # Forward extra data-attrs to the snippet's mount root by injecting
        # them into the first element with `data-snippet-mount`. If the
        # snippet has no mount marker, just prepend a wrapping comment.
        if extra_attrs:
            content = re.sub(
                r'(data-snippet-mount="[^"]+")',
                rf'\1 {extra_attrs}',
                content,
                count=1,
            )
        return content

    new_html = _SNIPPET_PLACEHOLDER_RE.sub(replace, html_body)
    return new_html, used


def strip_first_paragraph(html_body: str) -> str:
    """Remove the first <p>...</p> from the rendered body (used when description was auto-derived from it)."""
    return re.sub(r"<p[^>]*>.*?</p>\s*", "", html_body, count=1, flags=re.DOTALL)


def main() -> int:
    parser = argparse.ArgumentParser(description="pipelinekit docs-writer/2 renderer")
    parser.add_argument("input", help="Input .md (or .html with --from-html) file (or '-' for stdin)")
    parser.add_argument("output", help="Output .html file (or '-' for stdout)")
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

    # Read input
    if args.input == "-":
        md_text = sys.stdin.read()
        input_stem = "stdin"
    else:
        input_path = Path(args.input)
        md_text = input_path.read_text(encoding="utf-8")
        input_stem = input_path.stem

    # Read template
    if not TEMPLATE_PATH.exists():
        print(f"error: template not found at {TEMPLATE_PATH}", file=sys.stderr)
        return 2
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    if args.from_html:
        # HTML rewrap mode: keep semantic HTML, just slot into the new template.
        title = args.title or derive_title_from_html(
            md_text, input_stem.replace("-", " ").title()
        )
        description = args.description or derive_description_from_html(
            md_text, f"{title} — pipelinekit application documentation"
        )
        body_html = extract_html_body(md_text)
        body_html = ensure_heading_ids(body_html)
        # Strip lead paragraph if it duplicates the description we derived
        # (only when description was auto-derived from body)
        if args.description is None:
            first_p = re.search(r"<p[^>]*>(.*?)</p>", body_html, re.DOTALL | re.IGNORECASE)
            if first_p:
                first_text = re.sub(r"<[^>]+>", "", first_p.group(1)).strip()
                first_text = re.sub(r"\s+", " ", first_text)
                if first_text[:120] == description[:120]:
                    body_html = strip_first_paragraph(body_html)
        body_html, snippets_used = substitute_snippets(body_html)
        toc_html = extract_toc_from_html(body_html)
    else:
        # Markdown render mode (default).
        title = args.title or derive_title(md_text, input_stem.replace("-", " ").title())
        description_was_derived = args.description is None
        description = args.description or derive_description(
            md_text, f"{title} — pipelinekit application documentation"
        )

        slug_map = build_slug_map(md_text)
        body_html = render_markdown(md_text)
        body_html = strip_first_h1(body_html)
        if description_was_derived:
            body_html = strip_first_paragraph(body_html)
        body_html = fix_heading_ids(body_html, slug_map)
        body_html, snippets_used = substitute_snippets(body_html)
        toc_html = extract_toc(md_text)

    # Log snippets used to stderr (visible to caller, not embedded in output)
    if snippets_used:
        print(f"  snippets: {', '.join(snippets_used)}", file=sys.stderr)

    # Meta-line items
    meta_items = []
    if args.source_link:
        meta_items.append(
            f'<span class="meta-item">Source: <a href="{html_lib.escape(args.source_link)}">{html_lib.escape(args.source_link)}</a></span>'
        )
    for item in args.meta:
        if ":" in item:
            label, value = item.split(":", 1)
            meta_items.append(
                f'<span class="meta-item"><strong>{html_lib.escape(label.strip())}:</strong> {html_lib.escape(value.strip())}</span>'
            )
        else:
            meta_items.append(f'<span class="meta-item">{html_lib.escape(item)}</span>')
    meta_html = " · ".join(meta_items)

    footer_right = "Self-contained HTML · no CDN · no remote assets"

    # Fill template
    html_output = fill_template(
        template,
        title=title,
        description=description,
        toc_html=toc_html,
        content_html=body_html,
        meta_html=meta_html,
        footer_right=footer_right,
    )

    # Write output
    if args.output == "-":
        sys.stdout.write(html_output)
    else:
        Path(args.output).write_text(html_output, encoding="utf-8")
        print(f"Rendered {args.input} → {args.output} ({len(html_output)} bytes)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
