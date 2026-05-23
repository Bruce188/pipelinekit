#!/usr/bin/env python3
"""decisions_renderer — emit docs-source/decisions.md + documentation/decisions.html.

Newest-first per-feature emitter. Per OQ-2 resolution: F13 entries appear at
TOP, F1 at bottom. Each feature gets a <details class="decisions-card">
collapsible card with data-feature attribute for stable selection.

Honours PIPELINE_HYGIENE_OFF=1. 5-second wall-time budget (logs
DECISIONS_BUDGET_EXCEEDED and exits 0 on timeout — never blocks /post-merge,
matching the advisory-exit contract of dashboard_renderer + features_pruner).
Atomic temp-file + os.replace() writes for both .md and .html outputs.
Idempotent: byte-identical output on identical state.

Usage:
    python3 claude/lib/pipeline/decisions_renderer.py        # normal pass
    PIPELINE_HYGIENE_OFF=1 python3 ... decisions_renderer.py # opt-out no-op
"""
from __future__ import annotations

import html as html_lib
import os
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow_extractor as wfe  # noqa: E402  # pyright: ignore[reportMissingImports]


def is_disabled() -> bool:
    return os.environ.get("PIPELINE_HYGIENE_OFF") == "1"


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _newest_first(records: list[dict]) -> list[dict]:
    """Sort by trailing integer in feature_index (e.g., '13/13' → 13). Newest first.
    Records lacking a parseable index sort to the end in stable name order
    (avoids reliance on insertion order — defensive against upstream refactors).
    """
    def key(r: dict) -> tuple[int, int, str]:
        idx = r.get("feature_index", "")
        for token in idx.replace("F", "").replace("/", " ").split():
            if token.isdigit():
                return (0, -int(token), r.get("feature_name", ""))
        return (1, 0, r.get("feature_name", ""))
    return sorted(records, key=key)


def _render_card(r: dict) -> str:
    f_idx = html_lib.escape(r.get("feature_index", "?"))
    f_name = html_lib.escape(r.get("feature_name", "(unknown)"))
    merged = html_lib.escape(r.get("merged_iso", "") or "")
    source = html_lib.escape(r.get("analysis_file", ""))
    oqs = r.get("oq_resolutions", [])
    subqs = r.get("subq_resolutions", [])
    if not oqs and not subqs:
        body = (f"<p><em>decisions not recovered "
                f"(analysis file missing from workflow dir)</em></p>")
    else:
        items = []
        for oq in oqs:
            items.append(
                f'<li class="oq-resolution">'
                f'<strong>{html_lib.escape(oq["id"])}:</strong> '
                f'{html_lib.escape(oq["headline"])}</li>'
            )
        for sq in subqs:
            items.append(
                f'<li class="subq-resolution">'
                f'<strong>{html_lib.escape(sq["id"])}:</strong> '
                f'{html_lib.escape(sq["headline"])}</li>'
            )
        body = '<ul class="decisions-list">\n  ' + "\n  ".join(items) + "\n</ul>"
    return (
        f'<details class="decisions-card" data-feature="{f_idx}">\n'
        f'  <summary>{f_idx} · {f_name}'
        f'{(" · " + merged) if merged else ""}</summary>\n'
        f'  {body}\n'
        f'  <p class="decisions-source"><em>Source:</em> {source}</p>\n'
        f'</details>\n'
    )


def _build_markdown() -> str:
    repo = wfe.repo_root()
    mode = wfe.detect_mode(repo)
    if mode == wfe.MODE_RICH:
        records = wfe.extract_analysis_resolutions(repo)
    else:
        records = wfe.extract_embedded_decisions(repo)
    records = _newest_first(records)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parts = [
        "# pipelinekit decisions log\n",
        f"Generated: {ts}",
        "",
        "<!-- richness budget: collapsible-details cards (one per feature) + timeline-scrubber svg + visual-token classes -->",
        "",
        "Per-feature OQ + SubQ resolutions in newest-first order. "
        "Each card shows the resolution headline only — see the source "
        "`docs/analysis-v*.md` workflow file for the full reasoning.",
        "",
        "[Dashboard →](dashboard.html) &nbsp; · &nbsp; "
        "[Feature history →](feature-history.html)",
        "",
        "<svg viewBox=\"0 0 800 50\" data-snippet-mount=\"timeline-scrubber\" "
        "aria-label=\"pipelinekit decisions timeline\">\n"
        "  <line x1=\"20\" y1=\"25\" x2=\"780\" y2=\"25\" stroke=\"currentColor\" stroke-width=\"2\"/>\n"
        "</svg>",
        "",
        "## Cards",
        "",
    ]
    if not records:
        parts.append("_No feature decision records found._\n")
    else:
        for r in records:
            parts.append(_render_card(r))
    return "\n".join(parts) + "\n"


def _render_html(repo: Path, md_path: Path, html_path: Path) -> int:
    render = repo / "claude" / "skills" / "docs-writer" / "render.py"
    if not render.is_file():
        print(f"decisions-renderer: render.py absent — skipping HTML render",
              file=sys.stderr)
        return 0
    proc = subprocess.run(
        ["python3", str(render), str(md_path), str(html_path),
         "--title", "pipelinekit decisions log",
         "--description", "Per-feature OQ + SubQ resolutions in newest-first order."],
        check=False,
    )
    return proc.returncode


def main() -> int:
    if is_disabled():
        print("PIPELINE_HYGIENE_OFF=1 — decisions_renderer skipped", file=sys.stderr)
        return 0
    repo = wfe.repo_root()
    md_path = repo / "docs-source" / "decisions.md"
    html_path = repo / "documentation" / "decisions.html"
    content = _build_markdown()
    _atomic_write(md_path, content)
    _render_html(repo, md_path, html_path)
    print(f"decisions-renderer: wrote {md_path.relative_to(repo)} + "
          f"{html_path.relative_to(repo)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    def _timeout_handler(*_args):
        print("DECISIONS_BUDGET_EXCEEDED — decisions_renderer exceeded 5s budget",
              file=sys.stderr)
        sys.exit(0)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(5)
    try:
        sys.exit(main())
    finally:
        signal.alarm(0)
