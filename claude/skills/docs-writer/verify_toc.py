#!/usr/bin/env python3
"""docs-writer/2 ToC integrity checker.

Audits every documentation/*.html (recursive) for:
  1. Sidebar ToC `href="#xxx"` links that don't resolve to a heading id in the body.
  2. Duplicate heading ids (two `<h2 id="X">` is a bug).

Snippet-internal headings (class="pkit-*") are intentionally excluded from
the page ToC by the renderer and from this audit — they're visual sub-headings
inside embedded snippets and never appear in the sidebar.

Exits 0 if every page is clean; exits 1 with a per-page report on any failure.

Usage:
    verify_toc.py            # scan documentation/ in the repo root
    verify_toc.py path...    # scan specific .html files
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTATION_DIR = REPO_ROOT / "documentation"

_TOC_ASIDE_RE = re.compile(
    r'<aside[^>]*class="toc"[^>]*>(.+?)</aside>', re.DOTALL
)
_TOC_LINK_RE = re.compile(r'href="#([^"]+)"')
_HEADING_ID_RE = re.compile(r'<h[234]\s+id="([^"]+)"')


def check_file(path: Path) -> tuple[int, list[str], list[tuple[str, int]]]:
    """Return (n_toc_links, broken_links, [(id, count)] of duplicates)."""
    html = path.read_text(encoding="utf-8", errors="replace")
    aside = _TOC_ASIDE_RE.search(html)
    if not aside:
        return 0, [], []
    toc_links = sorted(set(_TOC_LINK_RE.findall(aside.group(1))))
    body_ids = set(_HEADING_ID_RE.findall(html))
    broken = sorted(set(toc_links) - body_ids)

    id_counts: dict[str, int] = {}
    for m in _HEADING_ID_RE.finditer(html):
        id_counts[m.group(1)] = id_counts.get(m.group(1), 0) + 1
    dups = sorted([(k, v) for k, v in id_counts.items() if v > 1])

    return len(toc_links), broken, dups


def main() -> int:
    if len(sys.argv) > 1:
        targets = [Path(p).resolve() for p in sys.argv[1:]]
    else:
        targets = sorted(DOCUMENTATION_DIR.rglob("*.html"))

    total_pages = 0
    total_links = 0
    total_broken = 0
    issues: list[tuple[Path, int, list[str], list[tuple[str, int]]]] = []

    for path in targets:
        if not path.exists():
            continue
        total_pages += 1
        n_links, broken, dups = check_file(path)
        total_links += n_links
        total_broken += len(broken)
        if broken or dups:
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path
            issues.append((rel, n_links, broken, dups))

    for rel, n_links, broken, dups in issues:
        print(f"\n{rel}  ({n_links} ToC entries)")
        if broken:
            print(f"  {len(broken)} broken ToC links:")
            for b in broken[:10]:
                print(f"    #{b}")
            if len(broken) > 10:
                print(f"    ... and {len(broken) - 10} more")
        if dups:
            print(f"  {len(dups)} duplicate heading ids:")
            for k, n in dups[:10]:
                print(f"    id={k!r} appears {n}x")
            if len(dups) > 10:
                print(f"    ... and {len(dups) - 10} more")

    print(f"\n{'=' * 60}")
    print(f"Scanned {total_pages} pages, {total_links} ToC links total, {total_broken} broken")
    print(f"Pages with issues: {len(issues)}")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
