#!/usr/bin/env python3
"""
docs-writer/2 richness checker — enforce the "rich content" rule.

Scans documentation/*.html, scores each
page on interactive richness, and flags pages below the threshold.

Pages can opt out by including a richness-exempt marker in their <head>:

    <!-- richness-exempt: reason text -->

Usage:
    richness_check.py [paths...]                # check specified files
    richness_check.py --staged                  # check only files in git index
    richness_check.py --all                     # check every documentation/*.html

Exits 0 if all pages meet the bar (or are exempt); exits 1 with a
per-file report if any page fails.

The threshold is `min_richness_score: int = 1` — a page must contain at
least one of the recognized rich-interactive patterns. Scoring is
designed to be a quality floor, not a fine-grained metric.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTATION_DIR = REPO_ROOT / "documentation"

# Each pattern is a tuple of (label, regex). A page's richness score is the
# count of DISTINCT patterns that match. Patterns are chosen to identify
# the canonical rich-content building blocks; markdown CANNOT produce any
# of them. Plain `<style>` + `<script>` + `<table>` + `<svg>` (icons only) do
# NOT count — those exist on every templated page regardless of richness.
RICHNESS_PATTERNS: list[tuple[str, str]] = [
    ("snippet:pipeline-phase-diagram", r'data-snippet-mount="pipeline-phase-diagram"'),
    ("snippet:cost-calculator", r'data-snippet-mount="cost-calculator"'),
    ("snippet:tutorial-cards", r'data-snippet-mount="tutorial-cards"'),
    ("snippet:architecture-diagram", r'data-snippet-mount="architecture-diagram"'),
    ("snippet:comparison-tabs", r'data-snippet-mount="comparison-tabs"'),
    ("snippet:terminal-simulator", r'data-snippet-mount="terminal-simulator"'),
    ("snippet:timeline-scrubber", r'data-snippet-mount="timeline-scrubber"'),
    ("snippet:chooser-quiz", r'data-snippet-mount="chooser-quiz"'),
    ("snippet:diff-viewer", r'data-snippet-mount="diff-viewer"'),
    ("snippet:playground-2col", r'data-snippet-mount="playground-2col"'),
    ("snippet:live-linter", r'data-snippet-mount="live-linter"'),
    ("snippet:skill-catalog-grid", r'data-snippet-mount="skill-catalog-grid"'),
    ("snippet:agent-catalog-grid", r'data-snippet-mount="agent-catalog-grid"'),
    ("snippet:deployment-provider-quiz", r'data-snippet-mount="deployment-provider-quiz"'),
    ("snippet:path-routing-diagram",      r'data-snippet-mount="path-routing-diagram"'),
    ("snippet:command-cheatsheet",        r'data-snippet-mount="command-cheatsheet"'),
    ("snippet:cost-budget-meter",         r'data-snippet-mount="cost-budget-meter"'),
    ("snippet:before-after-slider",       r'data-snippet-mount="before-after-slider"'),
    ("snippet:governance-roles-table",    r'data-snippet-mount="governance-roles-table"'),
    # Generic detection — any registered snippet mount.
    # Falls back to catch a page that uses ANY data-snippet-mount even if
    # the specific snippet isn't in the known catalog. Counted once.
    ("snippet:any", r'data-snippet-mount="[^"]+"'),
    # Custom interactive SVG (not template icons — those use stroke-width=2 and live in the topbar).
    # A real custom SVG is large (multiple shapes, viewBox != standard icon size).
    # Detect viewBox >= 200 in either dimension.
    ("custom-svg-diagram", r'viewBox="0 0 (?:[2-9]\d{2}|\d{4,})\s+(?:[1-9]\d{2}|\d{3,})"'),
    # Form inputs that imply interactivity (sliders, radios, checkboxes, selects, textareas).
    # The template's search box doesn't count (it's a type="search" with id="page-search").
    ("interactive-form-control", r'<input\s+type="(range|number|color)"|<select(?:\s|>)|<textarea(?:\s|>)'),
    # Custom <details>/<summary> blocks in the body. Excludes the no-results block in template.
    ("collapsible-details", r'<details(?:\s|>)'),
]

# ---------------------------------------------------------------------------
# Topic-affinity layer.
#
# The richness scan above only checks that a rich pattern is PRESENT, not that
# its content fits the page. A page could clear the gate by pasting any snippet
# regardless of relevance — which is how a cost/turns budget meter ended up on a
# coverage score-card and a whole-system architecture diagram on a
# rendering-rubric page.
#
# For snippets whose rendered content is baked-in and topic-specific (as opposed
# to generic containers like comparison-tabs / terminal-simulator that are
# customized per page via data-attributes), require the page's AUTHOR PROSE to
# mention at least one of the snippet's topic keywords. Author prose is read from
# the page's markdown source — the rendered HTML is deliberately NOT used because
# it contains the widget's own baked text, which would self-match and defeat the
# check.
#
# Generic/neutral snippets are intentionally absent from this map: they carry no
# baked topic, so affinity cannot be judged by keyword and is not enforced.
#
# A page overrides one snippet's affinity requirement with:
#     <!-- topic-affinity-ok: <snippet-name> reason text -->
# Keywords are matched with a left word boundary + prefix (`\bkw`), so "deploy"
# matches "deployment" but "turn" does not match "return".
SNIPPET_TOPIC_KEYWORDS: dict[str, set[str]] = {
    "cost-budget-meter": {"usd", "dollar", "spend", "cost"},
    "cost-calculator": {"usd", "dollar", "cost", "price", "calculat"},
    "architecture-diagram": {"architectur", "taxonom", "topolog"},
    "pipeline-phase-diagram": {"phase", "lifecycle"},
    "path-routing-diagram": {"path", "routing", "route"},
    "governance-roles-table": {"governance", "raci", "role", "responsib", "accountab"},
    "deployment-provider-quiz": {"deploy", "provider"},
    "skill-catalog-grid": {"skill"},
    "agent-catalog-grid": {"agent"},
}

DOCS_SOURCE_DIR = REPO_ROOT / "docs-source"
AFFINITY_OK_RE = re.compile(r'<!--\s*topic-affinity-ok:\s*([A-Za-z0-9_-]+)[^>]*-->', re.IGNORECASE)
_MOUNT_RE = re.compile(r'data-snippet-mount="([^"]+)"')
# Scrub from author prose before keyword matching: HTML comments (frontmatter,
# commented-out usage examples) and the whole snippet placeholder tag (its
# data-* attributes — e.g. data-max-usd — would otherwise leak topic keywords).
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_SNIPPET_TAG_RE = re.compile(r'<[^>]*\bdata-snippet="[^"]*"[^>]*>')

# Pages that legitimately cannot be rich (reference / archive content).
#
# The v0.0.1 baseline-pending group is now empty — every reader-facing page
# has been enriched with at least one interactive snippet. New entries here
# should be rare and require justification (audit reports and vendored
# attribution are the only natural fits).
DEFAULT_EXEMPT_FILES: set[str] = {
    # Vendored attribution — not a reader experience, just a license + SHA pin.
    "documentation/NOTICE.html",
}

EXEMPT_MARKER_RE = re.compile(r'<!--\s*richness-exempt:\s*([^>]+?)\s*-->', re.IGNORECASE)

_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _body_word_count(html: str) -> int:
    """Count words inside <body>...</body> after stripping HTML tags."""
    match = _BODY_RE.search(html)
    if not match:
        return 0
    text = _TAG_RE.sub(" ", match.group(1))
    return len(text.split())


@dataclass
class Result:
    path: str
    score: int
    matched: list[str]
    exempt: bool
    exempt_reason: str = ""
    body_words: int = 0
    affinity_violations: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        if self.exempt:
            return True
        if self.affinity_violations:
            return False
        threshold = 2 if self.body_words > 1500 else 1
        return self.score >= threshold


def _affinity_prose(html_path: Path) -> str | None:
    """Author prose for affinity checks, lowercased — or None if no source found.

    Read from the page's markdown source, NOT the rendered HTML: the rendered
    widget carries its own baked text (e.g. a cost meter literally prints
    "Cost (USD)"), which would self-match and defeat the check. Resolution order:
    a sibling ``<stem>.md`` beside the HTML (used by test fixtures), then
    ``docs-source/<stem>.md``. The ``data-snippet`` placeholder attribute is
    scrubbed so the snippet's own NAME (e.g. cost-budget-meter) does not count as
    prose.
    """
    candidates = [html_path.with_suffix(".md"), DOCS_SOURCE_DIR / f"{html_path.stem}.md"]
    for src in candidates:
        if src.exists():
            text = src.read_text(encoding="utf-8", errors="replace")
            text = _HTML_COMMENT_RE.sub(" ", text)
            text = _SNIPPET_TAG_RE.sub(" ", text)
            return text.lower()
    return None


def _affinity_violations(html_path: Path, content: str) -> list[str]:
    """Flag baked-content snippets mounted on a page whose prose never discusses them."""
    signature_mounts = {m for m in _MOUNT_RE.findall(content) if m in SNIPPET_TOPIC_KEYWORDS}
    if not signature_mounts:
        return []
    overridden = {name.strip().lower() for name in AFFINITY_OK_RE.findall(content)}
    prose = _affinity_prose(html_path)
    if prose is None:
        return []  # no source to judge against — do not enforce
    violations: list[str] = []
    for snippet in sorted(signature_mounts):
        if snippet in overridden:
            continue
        keywords = SNIPPET_TOPIC_KEYWORDS[snippet]
        if not any(re.search(r"\b" + re.escape(kw), prose) for kw in keywords):
            kws = ", ".join(sorted(keywords))
            violations.append(
                f"off-topic snippet '{snippet}': page prose mentions none of {{{kws}}}"
            )
    return violations


def check_file(path: Path, repo_root: Path) -> Result:
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        # Path is outside the repo (e.g. test fixture in /tmp).
        # Use the basename so default-exempt allowlist still matches when relevant.
        rel = path.name
    content = path.read_text(encoding="utf-8", errors="replace")
    body_words = _body_word_count(content)

    # Exemption check
    exempt_match = EXEMPT_MARKER_RE.search(content)
    if exempt_match:
        return Result(rel, 0, [], exempt=True, exempt_reason=exempt_match.group(1).strip(), body_words=body_words)
    if rel in DEFAULT_EXEMPT_FILES:
        return Result(rel, 0, [], exempt=True, exempt_reason="(default-exempt)", body_words=body_words)

    matched: list[str] = []
    for label, pattern in RICHNESS_PATTERNS:
        if re.search(pattern, content):
            matched.append(label)

    # Dedup: if "snippet:any" matched but it's the only "snippet:*" hit, count it.
    # If a specific snippet:X already matched, drop "snippet:any" to avoid double-counting.
    has_specific = any(m.startswith("snippet:") and m != "snippet:any" for m in matched)
    if has_specific and "snippet:any" in matched:
        matched.remove("snippet:any")

    affinity = _affinity_violations(path, content)
    return Result(rel, len(matched), matched, exempt=False, body_words=body_words, affinity_violations=affinity)


def gather_staged_html() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [
        REPO_ROOT / line.strip()
        for line in out.stdout.splitlines()
        if line.strip().endswith(".html") and line.strip().startswith("documentation/")
    ]


def gather_all_html() -> list[Path]:
    return sorted(DOCUMENTATION_DIR.rglob("*.html"))


def main() -> int:
    parser = argparse.ArgumentParser(description="docs-writer/2 richness checker")
    parser.add_argument("paths", nargs="*", help="Specific HTML files to check (under documentation/)")
    parser.add_argument("--staged", action="store_true", help="Check only files in the git index")
    parser.add_argument("--all", action="store_true", help="Check every documentation/**/*.html")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show match details for every page")
    args = parser.parse_args()

    if args.staged:
        targets = gather_staged_html()
        if not targets:
            print("No staged documentation HTML files.", file=sys.stderr)
            return 0
    elif args.all:
        targets = gather_all_html()
    elif args.paths:
        targets = [Path(p).resolve() for p in args.paths]
    else:
        parser.error("Specify file paths, --staged, or --all")

    results = [check_file(p, REPO_ROOT) for p in targets if p.exists()]

    failed = [r for r in results if not r.passes]
    passed = [r for r in results if r.passes]

    if args.verbose or failed:
        for r in results:
            mark = "OK" if r.passes else "FAIL"
            extra = ""
            if r.exempt:
                extra = f"  [exempt: {r.exempt_reason}]"
            elif r.matched:
                extra = f"  [{', '.join(r.matched)}]"
            print(f"  {mark:4} {r.path}  score={r.score}{extra}")
            for violation in r.affinity_violations:
                print(f"         off-topic: {violation}")

    print()
    print(f"Total: {len(passed)} pass, {len(failed)} fail (of {len(results)} checked)")

    if failed:
        print()
        print("To fix a failing page, add at least one snippet placeholder", file=sys.stderr)
        print('to its markdown source: <div data-snippet="<name>"></div>', file=sys.stderr)
        print("See claude/skills/docs-writer/SKILL.md § Snippets catalog.", file=sys.stderr)
        print()
        print("To exempt a page (use sparingly), add to its <head>:", file=sys.stderr)
        print("    <!-- richness-exempt: reason text -->", file=sys.stderr)
        print(file=sys.stderr)
        print("An 'off-topic' line means a baked-content snippet was mounted on a", file=sys.stderr)
        print("page whose prose never discusses it. Swap it for an on-topic snippet,", file=sys.stderr)
        print("or override (rarely) with:", file=sys.stderr)
        print("    <!-- topic-affinity-ok: <snippet-name> reason text -->", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
