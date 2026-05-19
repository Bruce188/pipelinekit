#!/usr/bin/env python3
"""
docs-writer/2 richness checker — enforce the "rich content" rule.

Scans documentation/*.html and documentation/docs/*.html, scores each
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
from dataclasses import dataclass
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

# Pages that legitimately cannot be rich (reference / archive content) OR that
# are baseline-v0.0.1 pending enrichment in a follow-up PR.
#
# The "v0.0.1 baseline" group should be migrated to per-page <!-- richness-exempt: ... -->
# markers OR (preferably) actually enriched with appropriate snippets. Each page below
# should be reviewed for the most fitting snippet pattern:
#   - changelog.html        → timeline-scrubber (filterable by theme + date)
#   - cloud-setup.html      → chooser-quiz (which provider + which size)
#   - installation.html     → tutorial-cards (per-platform: Linux / macOS / WSL / Codespaces)
#   - ci-blacksmith.html    → cost-calculator (runner cost vs GitHub-hosted)
#   - deployment-*.html (5) → cost-calculator + comparison-tabs (vs other providers)
#   - github-issues-integration.html → playground (paste a label query, see filtered issues)
#   - pipeline-charter-revalidation.html → 3-status playground (charter line + repo state)
#   - ppr-research-flag.html → terminal-simulator (dry-run output preview)
#   - tsv-viewer.html       → live demo (the viewer IS the rich content; consider auto-pass)
#   - SKILL-AUTHORING-STANDARD / SKILL_PIPELINE → live-linter (paste SKILL.md, get scored)
DEFAULT_EXEMPT_FILES: set[str] = {
    # Legitimately exempt
    "documentation/docs/NOTICE.html",                                       # Attribution-only
    "documentation/audits/claude-code-compliance-features-2026-05-18.html", # Archived earlier audit
    # v0.0.1 baseline — remove from this set as each page is enriched
    "documentation/audits/claude-code-compliance-2026-05-19.html",
    "documentation/changelog.html",
    "documentation/ci-blacksmith.html",
    "documentation/cloud-setup.html",
    "documentation/deployment-azure.html",
    "documentation/deployment-digitalocean.html",
    "documentation/deployment-railway.html",
    "documentation/deployment-render.html",
    "documentation/deployment-vercel.html",
    "documentation/docs/SKILL-AUTHORING-STANDARD.html",
    "documentation/docs/SKILL_PIPELINE.html",
    "documentation/github-issues-integration.html",
    "documentation/installation.html",
    "documentation/pipeline-charter-revalidation.html",
    "documentation/ppr-research-flag.html",
    "documentation/tsv-viewer.html",
}

EXEMPT_MARKER_RE = re.compile(r'<!--\s*richness-exempt:\s*([^>]+?)\s*-->', re.IGNORECASE)


@dataclass
class Result:
    path: str
    score: int
    matched: list[str]
    exempt: bool
    exempt_reason: str = ""

    @property
    def passes(self) -> bool:
        return self.exempt or self.score >= 1


def check_file(path: Path, repo_root: Path) -> Result:
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        # Path is outside the repo (e.g. test fixture in /tmp).
        # Use the basename so default-exempt allowlist still matches when relevant.
        rel = path.name
    content = path.read_text(encoding="utf-8", errors="replace")

    # Exemption check
    exempt_match = EXEMPT_MARKER_RE.search(content)
    if exempt_match:
        return Result(rel, 0, [], exempt=True, exempt_reason=exempt_match.group(1).strip())
    if rel in DEFAULT_EXEMPT_FILES:
        return Result(rel, 0, [], exempt=True, exempt_reason="(default-exempt)")

    matched: list[str] = []
    snippet_any_only = False
    for label, pattern in RICHNESS_PATTERNS:
        if re.search(pattern, content):
            matched.append(label)

    # Dedup: if "snippet:any" matched but it's the only "snippet:*" hit, count it.
    # If a specific snippet:X already matched, drop "snippet:any" to avoid double-counting.
    has_specific = any(m.startswith("snippet:") and m != "snippet:any" for m in matched)
    if has_specific and "snippet:any" in matched:
        matched.remove("snippet:any")

    return Result(rel, len(matched), matched, exempt=False)


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
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
