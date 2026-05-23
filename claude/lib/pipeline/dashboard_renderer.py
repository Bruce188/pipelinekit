#!/usr/bin/env python3
"""dashboard_renderer — emit docs-source/dashboard.md + documentation/dashboard.html.

12-section layout (NOT 8 — analysis OQ-1 resolution supersedes spec line 559):

    Always-visible (above-the-fold):
        1. Pipeline state
        2. Recent activity
        3. Recent features teaser

    Collapsible <details> (sections 4-12):
        4. Iteration archive
        5. Cost trajectory
        6. Documentation hub
        7. Charter snapshot
        8. Test sweep
        9. Skill inventory
       10. Hook denial summary
       11. Memory inventory
       12. Quick links

Hard 12-section cap. Adding a 13th REQUIRES dropping an earlier one.

Honours PIPELINE_HYGIENE_OFF=1. 5-second wall-time budget (logs
DASHBOARD_BUDGET_EXCEEDED and exits 0 on timeout — never blocks /post-merge).
Atomic temp-file + os.replace() writes for both .md and .html outputs.
Idempotent: byte-identical output on identical state.

Usage:
    python3 claude/lib/pipeline/dashboard_renderer.py        # normal pass
    PIPELINE_HYGIENE_OFF=1 python3 ... dashboard_renderer.py # opt-out no-op
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add this directory to sys.path so we can import workflow_extractor as a sibling.
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


def _section_1_pipeline_state(state: dict) -> str:
    if not state:
        return ("## 1. Pipeline state\n\n"
                "_No `docs/pipeline-state.md` found — pipeline has not run in this clone._\n")
    rows = [f"| {k} | {v} |" for k, v in sorted(state.items())]
    return ("## 1. Pipeline state\n\n"
            "| Field | Value |\n|-------|-------|\n" + "\n".join(rows) + "\n")


def _section_2_recent_activity(log: list[dict]) -> str:
    if not log:
        return ("## 2. Recent activity\n\n"
                "_No `[PIPELINE]` log entries in `docs/features.md`._\n")
    items = [f"- `feat={e['idx']}` `step={e['step']}` `cycle={e['cycle']}` — {e['message']}"
             for e in log]
    return "## 2. Recent activity\n\n" + "\n".join(items) + "\n"


def _section_3_recent_features(resolutions: list[dict]) -> str:
    if not resolutions:
        return ("## 3. Recent features\n\n"
                "_No feature resolution records found._\n")
    rows = []
    for r in resolutions[-5:]:
        rows.append(f"- **{r['feature_index']}** `{r['feature_name']}` "
                    f"(OQs: {len(r['oq_resolutions'])}, SubQs: {len(r['subq_resolutions'])})")
    return "## 3. Recent features\n\n" + "\n".join(rows) + "\n"


def _details(title: str, body_md: str) -> str:
    return (f"<details>\n<summary>{title}</summary>\n\n"
            f"{body_md}\n</details>\n")


def _section_4_iteration_archive(arc: dict) -> str:
    return _details("4. Iteration archive",
                    f"`docs/archive/progress-v*.md` count: **{arc.get('count', 0)}**")


def _section_5_cost_trajectory(cost: dict) -> str:
    if not cost.get("available"):
        return _details("5. Cost trajectory",
                        "_No cost data available — `~/.claude/logs/cost-events.jsonl` "
                        "is out-of-repo and absent on this clone._")
    return _details(
        "5. Cost trajectory",
        f"- Events: **{cost['total_events']}**\n"
        f"- Total USD: **${cost['total_usd']:.2f}**\n"
        f"- Average per event: **${cost['avg_usd']:.4f}**"
    )


def _section_6_documentation_hub(d: dict) -> str:
    top = d.get("top_recent", [])
    body = f"Total pages: **{d.get('total_pages', 0)}**"
    if top:
        body += "\n\nTop 5 most recent:\n"
        for name in top:
            body += f"- [{name}]({name})\n"
    return _details("6. Documentation hub", body)


def _section_7_charter_snapshot(c: dict) -> str:
    if not c:
        return _details("7. Charter snapshot", "_No `docs/charter.md` found._")
    return _details(
        "7. Charter snapshot",
        f"- Topics present: **{c.get('topics_present', 0)}**\n"
        f"- Deployment target: `{c.get('deployment_target', '?')}`\n"
        f"- Review style: `{c.get('review_style', '?')}`\n"
        f"- Decisions logged: **{c.get('decisions_logged', 0)}**\n"
        f"- Non-Goals: **{c.get('non_goals_count', 0)}**\n"
        f"- Open Questions: **{c.get('open_questions_count', 0)}**"
    )


def _section_8_test_sweep(t: dict) -> str:
    body = f"Total `test_*.sh` files: **{t.get('total', 0)}**"
    by_dir = t.get("by_directory", {})
    if by_dir:
        body += "\n\nBy directory:\n"
        for d, n in sorted(by_dir.items()):
            body += f"- `{d}` — {n}\n"
    return _details("8. Test sweep", body)


def _section_9_skill_inventory(s: dict) -> str:
    return _details(
        "9. Skill inventory",
        f"Total SKILL.md files: **{s.get('total', 0)}**"
    )


def _section_10_hook_denial(h: dict) -> str:
    if not h.get("available"):
        return _details("10. Hook denial summary",
                        "_No denial-tracker log present._")
    body = f"Total denials: **{h['total']}**"
    if h.get("by_hook"):
        body += "\n\nBy hook:\n"
        for hk, n in sorted(h["by_hook"].items()):
            body += f"- `{hk}` — {n}\n"
    return _details("10. Hook denial summary", body)


def _section_11_memory(m: dict) -> str:
    if not m.get("available"):
        return _details("11. Memory inventory",
                        "_No memory data — `~/.claude/memory/` absent on this host._")
    body = f"Total memory files: **{m['total']}**"
    if m.get("by_type"):
        body += "\n\nBy type:\n"
        for t, n in sorted(m["by_type"].items()):
            body += f"- `{t}` — {n}\n"
    return _details("11. Memory inventory", body)


def _section_12_quick_links() -> str:
    return _details(
        "12. Quick links",
        "- [workflow-hygiene](workflow-hygiene.html)\n"
        "- [html-effectiveness-principles](html-effectiveness-principles.html)\n"
        "- [design-tokens](design-tokens.html)\n"
        "- [codebase-map](codebase-map.html)\n"
        "- [feature-history](feature-history.html)\n"
        "- [decisions](decisions.html)\n"
        "- [skills](skills.html)\n"
        "- [agents](agents.html)"
    )


def _build_markdown() -> str:
    repo = wfe.repo_root()
    mode = wfe.detect_mode(repo)
    if mode == wfe.MODE_RICH:
        resolutions = wfe.extract_analysis_resolutions(repo)
    else:
        resolutions = wfe.extract_embedded_decisions(repo)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sections = [
        f"# pipelinekit dashboard\n",
        f"Generated: {ts}",
        "",
        "<!-- richness budget: collapsible-details (sections 4-12) + interactive timeline svg + visual-token status pills -->",
        "",
        "[Decisions log →](decisions.html) &nbsp; · &nbsp; "
        "[Feature history →](feature-history.html) &nbsp; · &nbsp; "
        "[Workflow hygiene →](workflow-hygiene.html)",
        "",
        "<svg viewBox=\"0 0 800 50\" data-snippet-mount=\"timeline-scrubber\" "
        "aria-label=\"pipelinekit activity timeline\">\n"
        "  <line x1=\"20\" y1=\"25\" x2=\"780\" y2=\"25\" stroke=\"currentColor\" stroke-width=\"2\"/>\n"
        "</svg>",
        "",
        _section_1_pipeline_state(wfe.extract_pipeline_state(repo)),
        _section_2_recent_activity(wfe.extract_features_md_run_log(repo)),
        _section_3_recent_features(resolutions),
        _section_4_iteration_archive(wfe.extract_iteration_archive(repo)),
        _section_5_cost_trajectory(wfe.extract_cost_events()),
        _section_6_documentation_hub(wfe.extract_documentation_index(repo)),
        _section_7_charter_snapshot(wfe.extract_charter_snapshot(repo)),
        _section_8_test_sweep(wfe.extract_test_inventory(repo)),
        _section_9_skill_inventory(wfe.extract_skill_inventory(repo)),
        _section_10_hook_denial(wfe.extract_hook_denial_summary(repo)),
        _section_11_memory(wfe.extract_memory_inventory()),
        _section_12_quick_links(),
    ]
    return "\n".join(sections) + "\n"


def _render_html(repo: Path, md_path: Path, html_path: Path) -> int:
    render = repo / "claude" / "skills" / "docs-writer" / "render.py"
    if not render.is_file():
        print(f"dashboard-renderer: render.py absent at {render} — skipping HTML render",
              file=sys.stderr)
        return 0
    proc = subprocess.run(
        ["python3", str(render), str(md_path), str(html_path),
         "--title", "pipelinekit dashboard",
         "--description", "Live current-state snapshot of the pipelinekit workflow."],
        check=False,
    )
    return proc.returncode


def _rewrite_index_hero(repo: Path, hero: dict | None) -> None:
    """Idempotently update <!-- BEGIN PIPELINEKIT HERO --> ... <!-- END PIPELINEKIT HERO -->
    in documentation/index.html. If markers absent → no-op (Task 1.6 installs them).
    """
    idx = repo / "documentation" / "index.html"
    if not idx.is_file():
        return
    text = idx.read_text(encoding="utf-8")
    if "<!-- BEGIN PIPELINEKIT HERO -->" not in text:
        return
    if hero:
        pills = (f'<span class="status-pill">{hero["feature_name"]}</span>\n'
                 f'    <span class="status-pill">Step: {hero["step"]}</span>\n'
                 f'    <span class="status-pill">Cycle: {hero["cycle"]}</span>')
    else:
        pills = '<span class="status-pill">no live state — see dashboard</span>'
    new_block = (
        '<!-- BEGIN PIPELINEKIT HERO -->\n'
        '<section class="dashboard-hero" id="dashboard-hero">\n'
        '  <h1>pipelinekit</h1>\n'
        '  <p class="hero-tagline">Workflow toolkit for Claude Code.</p>\n'
        '  <div class="hero-state">\n'
        f'    {pills}\n'
        '  </div>\n'
        '  <a class="hero-cta" href="dashboard.html">View dashboard →</a>\n'
        '  <a class="hero-cta-secondary" href="decisions.html">Decisions log →</a>\n'
        '</section>\n'
        '<!-- END PIPELINEKIT HERO -->'
    )
    import re
    new_text = re.sub(
        r"<!-- BEGIN PIPELINEKIT HERO -->.*?<!-- END PIPELINEKIT HERO -->",
        new_block,
        text,
        flags=re.DOTALL,
    )
    if new_text != text:
        _atomic_write(idx, new_text)


def main() -> int:
    if is_disabled():
        print("PIPELINE_HYGIENE_OFF=1 — dashboard_renderer skipped", file=sys.stderr)
        return 0
    repo = wfe.repo_root()
    md_path = repo / "docs-source" / "dashboard.md"
    html_path = repo / "documentation" / "dashboard.html"
    content = _build_markdown()
    _atomic_write(md_path, content)
    _render_html(repo, md_path, html_path)
    _rewrite_index_hero(repo, wfe.extract_hero_state(repo))
    print(f"dashboard-renderer: wrote {md_path.relative_to(repo)} + "
          f"{html_path.relative_to(repo)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    def _timeout_handler(*_args):
        print("DASHBOARD_BUDGET_EXCEEDED — dashboard_renderer exceeded 5s budget",
              file=sys.stderr)
        sys.exit(0)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(5)
    try:
        sys.exit(main())
    finally:
        signal.alarm(0)
