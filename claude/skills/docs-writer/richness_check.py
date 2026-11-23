#!/usr/bin/env python3
"""
docs-writer richness checker (advisory) — flags rendered pages with no
interactive content.

A page passes if it contains at least one rich pattern (a snippet mount, a
large custom SVG, an interactive form control, or a <details> block). Long
pages (over 1500 words of prose) need two distinct patterns.

Pages can opt out with a marker anywhere in the HTML:

    <!-- richness-exempt: reason text -->

Usage:
    richness_check.py [paths...]          # check specified files
    richness_check.py --all [--root DIR]  # every <root>/documentation/**/*.html
    richness_check.py --staged [--root DIR]  # staged documentation/*.html in git

--root defaults to the current directory. Exits 0 if every page passes or is
exempt, 1 otherwise.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# (label, regex). A page's score is the number of DISTINCT labels that match.
# Plain <style>/<script>/<table>/icon <svg> do not count: every templated page has them.
RICHNESS_PATTERNS: list[tuple[str, str]] = [
    ("snippet", r'data-snippet-mount="[^"]+"'),
    # Custom SVG diagram: viewBox >= 200 wide and >= 100 tall (template icons are 24x24).
    ("custom-svg-diagram", r'viewBox="0 0 (?:[2-9]\d{2}|\d{4,})\s+(?:[1-9]\d{2}|\d{4,})"'),
    # The template's search box is type="search", so it does not count.
    ("interactive-form-control", r'<input\s+type="(?:range|number|color)"|<select(?:\s|>)|<textarea(?:\s|>)'),
    ("collapsible-details", r'<details(?:\s|>)'),
]

EXEMPT_MARKER_RE = re.compile(r'<!--\s*richness-exempt:\s*([^>]+?)\s*-->', re.IGNORECASE)
_MOUNT_RE = re.compile(r'data-snippet-mount="([^"]+)"')
_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
# Inline JS/CSS is not prose: drop it (and comments) before counting words.
_NON_PROSE_RE = re.compile(r"<(script|style)\b.*?</\1\s*>|<!--.*?-->", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _body_word_count(html: str) -> int:
    """Count prose words inside <body>, ignoring tags, comments, <script> and <style>."""
    match = _BODY_RE.search(html)
    if not match:
        return 0
    text = _NON_PROSE_RE.sub(" ", match.group(1))
    return len(_TAG_RE.sub(" ", text).split())


@dataclass
class Result:
    path: str
    score: int
    matched: list[str]
    exempt: bool
    exempt_reason: str = ""
    body_words: int = 0

    @property
    def passes(self) -> bool:
        if self.exempt:
            return True
        return self.score >= (2 if self.body_words > 1500 else 1)


def check_file(path: Path, root: Path) -> Result:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = str(path)
    content = path.read_text(encoding="utf-8", errors="replace")
    words = _body_word_count(content)

    exempt = EXEMPT_MARKER_RE.search(content)
    if exempt:
        return Result(rel, 0, [], exempt=True, exempt_reason=exempt.group(1).strip(), body_words=words)

    matched = [label for label, pattern in RICHNESS_PATTERNS if re.search(pattern, content)]
    if "snippet" in matched:
        names = sorted(set(_MOUNT_RE.findall(content)))
        matched[matched.index("snippet")] = "snippet:" + "+".join(names)
    return Result(rel, len(matched), matched, exempt=False, body_words=words)


def gather_staged_html(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=root, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [
        root / line.strip()
        for line in out.stdout.splitlines()
        if line.strip().endswith(".html") and line.strip().startswith("documentation/")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="docs-writer richness checker (advisory)")
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--staged", action="store_true", help="Check staged documentation/*.html")
    parser.add_argument("--all", action="store_true", help="Check every documentation/**/*.html")
    parser.add_argument("--root", type=Path, default=None, help="Project root (default: cwd)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show details for every page")
    args = parser.parse_args()
    root = (args.root or Path.cwd()).resolve()

    if args.staged:
        targets = gather_staged_html(root)
        if not targets:
            print("No staged documentation HTML files.", file=sys.stderr)
            return 0
    elif args.all:
        targets = sorted((root / "documentation").rglob("*.html"))
    elif args.paths:
        targets = [Path(p).resolve() for p in args.paths]
    else:
        parser.error("Specify file paths, --staged, or --all")

    missing = [p for p in targets if not p.exists()]
    for p in missing:
        print(f"error: not found: {p}", file=sys.stderr)
    results = [check_file(p, root) for p in targets if p.exists()]
    failed = [r for r in results if not r.passes]

    if args.verbose or failed:
        for r in results:
            mark = "OK" if r.passes else "FAIL"
            extra = f"  [exempt: {r.exempt_reason}]" if r.exempt else (
                f"  [{', '.join(r.matched)}]" if r.matched else "")
            print(f"  {mark:4} {r.path}  score={r.score} words={r.body_words}{extra}")

    print(f"\nTotal: {len(results) - len(failed)} pass, {len(failed)} fail (of {len(results)} checked)")

    if failed:
        print("\nTo fix a failing page, add a snippet placeholder to its markdown source,", file=sys.stderr)
        print('e.g. <div data-snippet="comparison-tabs">...</div> (see the docs-writer SKILL.md).', file=sys.stderr)
        print("To exempt a page (use sparingly): <!-- richness-exempt: reason text -->", file=sys.stderr)
    return 1 if failed or missing else 0


if __name__ == "__main__":
    sys.exit(main())
