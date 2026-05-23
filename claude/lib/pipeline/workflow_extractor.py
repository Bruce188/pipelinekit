#!/usr/bin/env python3
"""workflow_extractor — hybrid (RICH ∥ EMBEDDED) reader for pipelinekit workflow state.

Single source of truth for both `dashboard_renderer.py` and `decisions_renderer.py`.
Returns structured records ONLY — never free-text answer prose from charter or
analysis (counts / dates / IDs / status enums / OQ resolution headlines only).

Mode resolution:
    glob('docs/analysis-v*.md') non-empty → RICH (reads workflow files).
    Otherwise                              → EMBEDDED (reads docs-source/feature-history.md
                                              <details><summary>Decisions</summary> blocks).

Honours PIPELINE_HYGIENE_OFF=1 (early-return; importers may still call functions
which then return empty dicts/lists).

Usage:
    python3 claude/lib/pipeline/workflow_extractor.py --self-test   # smoke
    # Library use:
    from workflow_extractor import (
        detect_mode, extract_pipeline_state, extract_charter_snapshot,
        extract_features_md_run_log, extract_cost_events,
        extract_analysis_resolutions, extract_embedded_decisions,
        extract_hero_state, extract_documentation_index,
        extract_test_inventory, extract_skill_inventory,
        extract_hook_denial_summary, extract_memory_inventory,
        extract_iteration_archive,
    )
"""
from __future__ import annotations

import glob
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MODE_RICH = "rich"
MODE_EMBEDDED = "embedded"

OQ_HEADER_RE = re.compile(r"^##\s+(OQ|SubQ).*[Rr]esolution", re.MULTILINE | re.IGNORECASE)
PIPELINE_LOG_RE = re.compile(
    r"^\[PIPELINE\]\s+feat=(?P<idx>\d+/\d+)\s+step=(?P<step>\w+)\s+"
    r"cycle=(?P<cycle>\d+)\s+worker=(?P<worker>\w+)\s+::\s+(?P<message>.+)$",
    re.MULTILINE,
)
FEATURE_H2_RE = re.compile(r"^##\s+(?P<name>\S.*?)\s*$", re.MULTILINE)


def is_disabled() -> bool:
    return os.environ.get("PIPELINE_HYGIENE_OFF") == "1"


def repo_root() -> Path:
    return Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
    )


def detect_mode(repo: Path | None = None) -> str:
    """RICH if any docs/analysis-v*.md exists; else EMBEDDED."""
    repo = repo or repo_root()
    return MODE_RICH if glob.glob(str(repo / "docs" / "analysis-v*.md")) else MODE_EMBEDDED


def extract_pipeline_state(repo: Path | None = None) -> dict:
    """Parse docs/pipeline-state.md into a dict of {field_label: value} pairs.
    Returns {} on missing file or parse error. NEVER raises.
    """
    repo = repo or repo_root()
    path = repo / "docs" / "pipeline-state.md"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = re.match(r"^\*\*(?P<k>[^:]+):\*\*\s+(?P<v>.*)$", line)
        if m:
            out[m.group("k").strip()] = m.group("v").strip()
    return out


def extract_charter_snapshot(repo: Path | None = None) -> dict:
    """Return counts only — NEVER free-text answer prose.

    Returns:
        {
          "topics_present": int,        # count of ## H2 headers
          "deployment_target": str,     # "any"/"vercel"/.../"(unset)"
          "review_style": str,
          "decisions_logged": int,      # rows in ## Decision Log table
          "non_goals_count": int,
          "open_questions_count": int,
        }
    """
    repo = repo or repo_root()
    path = repo / "docs" / "charter.md"
    if not path.is_file():
        return {}
    text = path.read_text()
    h2s = re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    # Pull deployment target / review style from the structured fields
    dt_m = re.search(r"^##\s+Deployment target\s*\n+([^\n#]+)", text, re.MULTILINE)
    rs_m = re.search(r"^##\s+Review style\s*\n+([^\n#]+)", text, re.MULTILINE)
    # Count Decision Log table rows (skip header + separator)
    dl_section_m = re.search(r"^##\s+Decision Log\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    dl_rows = 0
    if dl_section_m:
        for ln in dl_section_m.group(1).splitlines():
            if re.match(r"^\|[^|]+\|", ln) and not re.match(r"^\|\s*-+\s*\|", ln):
                dl_rows += 1
        dl_rows = max(0, dl_rows - 1)  # subtract header row
    # Count Open Questions list items
    oq_section_m = re.search(r"^##\s+Open Questions\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    oq_count = 0
    if oq_section_m:
        oq_count = sum(1 for ln in oq_section_m.group(1).splitlines()
                       if re.match(r"^\s*[-*]\s+", ln))
    ng_section_m = re.search(r"^##\s+Non-Goals\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    ng_count = 0
    if ng_section_m:
        ng_count = sum(1 for ln in ng_section_m.group(1).splitlines()
                       if re.match(r"^\s*[-*]\s+", ln))
    return {
        "topics_present": len(h2s),
        "deployment_target": (dt_m.group(1).strip() if dt_m else "(unset)"),
        "review_style": (rs_m.group(1).strip() if rs_m else "(unset)"),
        "decisions_logged": dl_rows,
        "non_goals_count": ng_count,
        "open_questions_count": oq_count,
    }


def extract_features_md_run_log(repo: Path | None = None, *, tail: int = 20) -> list[dict]:
    """Tail last `tail` [PIPELINE] log lines from docs/features.md.
    Returns list of dicts: {"idx", "step", "cycle", "worker", "message"}.
    Empty list on missing file.
    """
    repo = repo or repo_root()
    path = repo / "docs" / "features.md"
    if not path.is_file():
        return []
    text = path.read_text()
    hits = [m.groupdict() for m in PIPELINE_LOG_RE.finditer(text)]
    return hits[-tail:]


def extract_cost_events(*, log_path: str | None = None) -> dict:
    """Parse ~/.claude/logs/cost-events.jsonl. Returns:
        {"total_events": int, "total_usd": float, "avg_usd": float, "available": bool}
    `available` is False when the log is missing or empty — caller emits
    "no cost data available" placeholder.
    """
    p = Path(log_path or os.path.expanduser("~/.claude/logs/cost-events.jsonl"))
    if not p.is_file():
        return {"total_events": 0, "total_usd": 0.0, "avg_usd": 0.0, "available": False}
    total = 0
    usd_sum = 0.0
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        usd_sum += float(ev.get("estimated_usd", 0.0) or 0.0)
    if total == 0:
        return {"total_events": 0, "total_usd": 0.0, "avg_usd": 0.0, "available": False}
    return {
        "total_events": total,
        "total_usd": round(usd_sum, 2),
        "avg_usd": round(usd_sum / total, 4),
        "available": True,
    }


def extract_analysis_resolutions(repo: Path | None = None) -> list[dict]:
    """RICH mode: scan docs/analysis-v*.md and return per-feature resolution records.

    Each record: {
      "feature_index": "13/13",
      "feature_name": "feat/...",
      "analysis_file": "docs/analysis-v91.md",
      "merged_iso": "2026-05-23",
      "feature_class": "non-dev" | "dev" | "unknown",
      "oq_resolutions": [{"id": "OQ-1", "headline": "12-section budget"} ...],
      "subq_resolutions": [{"id": "SubQ-A", "headline": "Hybrid extractor"} ...],
    }

    Headlines are extracted as the FIRST sentence (split on first period or em-dash
    after the colon) following the "OQ-N resolved:" / "SubQ-X resolved:" marker.
    NEVER full reasoning prose — strict structural extraction only.
    Last-analysis-per-feature wins (replan cycles collapsed).
    """
    repo = repo or repo_root()

    def _vkey(p: str) -> int:
        m = re.search(r"v(\d+)\.md$", p)
        return int(m.group(1)) if m else 0

    paths = sorted(glob.glob(str(repo / "docs" / "analysis-v*.md")), key=_vkey)
    records_by_feature: dict[str, dict] = {}
    for ap in paths:
        text = Path(ap).read_text()
        # YAML front-matter feature + index
        fm = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not fm:
            continue
        fm_text = fm.group(1)
        feat_m = re.search(r"^feature:\s*(.+)$", fm_text, re.MULTILINE)
        idx_m = re.search(r"^feature_index:\s*(.+)$", fm_text, re.MULTILINE)
        feat = feat_m.group(1).strip() if feat_m else "unknown"
        idx = idx_m.group(1).strip() if idx_m else "?/?"
        created_m = re.search(r"^created:\s*(\S+)", fm_text, re.MULTILINE)
        # Extract OQ resolutions
        oqs: list[dict] = []
        for m in re.finditer(r"(?:^|\n)\s*[-*]?\s*\*?\*?(OQ-\d+)\s+resolved:?\*?\*?\s+(.+)",
                             text):
            oid = m.group(1)
            headline = _first_sentence(m.group(2))
            oqs.append({"id": oid, "headline": headline})
        # Extract SubQ resolutions
        subqs: list[dict] = []
        for m in re.finditer(r"(?:^|\n)###\s*(SubQ-[A-Z])[^\n]*?\n+([^\n]+)", text):
            sid = m.group(1)
            headline = _first_sentence(m.group(2))
            subqs.append({"id": sid, "headline": headline})
        records_by_feature[feat] = {
            "feature_index": idx,
            "feature_name": feat,
            "analysis_file": os.path.relpath(ap, str(repo)),
            "merged_iso": (created_m.group(1) if created_m else ""),
            "feature_class": "unknown",
            "oq_resolutions": oqs,
            "subq_resolutions": subqs,
        }
    return list(records_by_feature.values())


def extract_embedded_decisions(repo: Path | None = None) -> list[dict]:
    """EMBEDDED mode: parse docs-source/feature-history.md for per-feature
    <details><summary>Decisions</summary>...</details> blocks. Returns the same
    schema as extract_analysis_resolutions().
    """
    repo = repo or repo_root()
    path = repo / "docs-source" / "feature-history.md"
    if not path.is_file():
        return []
    text = path.read_text()
    # Split on F-prefixed H2 sections
    records: list[dict] = []
    # Match `## F<N> — <feature-name>` H2 then capture body up to next ## H2
    for m in re.finditer(
        r"^##\s+(F\d+)\s+[—-]\s+(\S.+?)\s*$(?P<body>.*?)(?=^##\s|\Z)",
        text, re.MULTILINE | re.DOTALL,
    ):
        f_idx = m.group(1)
        f_name = m.group(2).strip()
        body = m.group("body")
        # Find embedded <details><summary>Decisions</summary>...</details>
        dec_m = re.search(
            r"<details>\s*<summary>\s*Decisions\s*</summary>(.*?)</details>",
            body, re.DOTALL,
        )
        oqs: list[dict] = []
        subqs: list[dict] = []
        if dec_m:
            blk = dec_m.group(1)
            for mm in re.finditer(r"\*\*?(OQ-\d+)\*\*?:?\s+(.+)", blk):
                oqs.append({"id": mm.group(1),
                            "headline": _first_sentence(mm.group(2))})
            for mm in re.finditer(r"\*\*?(SubQ-[A-Z])\*\*?:?\s+(.+)", blk):
                subqs.append({"id": mm.group(1),
                              "headline": _first_sentence(mm.group(2))})
        records.append({
            "feature_index": f_idx,
            "feature_name": f_name,
            "analysis_file": "(embedded snapshot in docs-source/feature-history.md)",
            "merged_iso": "",
            "feature_class": "unknown",
            "oq_resolutions": oqs,
            "subq_resolutions": subqs,
        })
    return records


def extract_hero_state(repo: Path | None = None) -> dict | None:
    """Return {"feature_name", "step", "cycle"} or None if unreadable."""
    st = extract_pipeline_state(repo)
    if not st:
        return None
    return {
        "feature_name": st.get("Name", "(unknown)"),
        "step": st.get("Step", "(unknown)"),
        "cycle": st.get("Review cycles", "0"),
    }


def extract_documentation_index(repo: Path | None = None) -> dict:
    """Count documentation/*.html pages + return top-5 most-recently modified."""
    repo = repo or repo_root()
    docs = sorted((repo / "documentation").glob("*.html"))
    return {
        "total_pages": len(docs),
        "top_recent": [p.name for p in
                       sorted(docs, key=lambda p: (-p.stat().st_mtime, p.name))[:5]],
    }


def extract_test_inventory(repo: Path | None = None) -> dict:
    """Count test_*.sh files under claude/ grouped by parent directory."""
    repo = repo or repo_root()
    by_dir: dict[str, int] = {}
    for p in (repo / "claude").rglob("test_*.sh"):
        rel = str(p.parent.relative_to(repo))
        by_dir[rel] = by_dir.get(rel, 0) + 1
    return {"total": sum(by_dir.values()), "by_directory": by_dir}


def extract_skill_inventory(repo: Path | None = None) -> dict:
    """Count claude/skills/<name>/SKILL.md files."""
    repo = repo or repo_root()
    skills = list((repo / "claude" / "skills").glob("*/SKILL.md"))
    return {"total": len(skills), "names": sorted(p.parent.name for p in skills)}


def extract_hook_denial_summary(repo: Path | None = None) -> dict:
    """Return counts from the denial-tracker log if present; graceful fallback."""
    repo = repo or repo_root()
    log_path = repo / "docs" / "hook-denials.jsonl"
    if not log_path.is_file():
        return {"available": False, "total": 0, "by_hook": {}}
    by_hook: dict[str, int] = {}
    total = 0
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        hk = ev.get("hook", "(unknown)")
        by_hook[hk] = by_hook.get(hk, 0) + 1
        total += 1
    return {"available": True, "total": total, "by_hook": by_hook}


def extract_memory_inventory() -> dict:
    """Count memory files under ~/.claude/memory/ by type prefix.
    Local-only — returns {"available": False, ...} if dir absent.
    """
    mem_dir = Path(os.path.expanduser("~/.claude/memory"))
    if not mem_dir.is_dir():
        return {"available": False, "total": 0, "by_type": {}}
    by_type: dict[str, int] = {}
    total = 0
    for p in mem_dir.glob("*.md"):
        prefix = p.stem.split("_", 1)[0]
        by_type[prefix] = by_type.get(prefix, 0) + 1
        total += 1
    return {"available": True, "total": total, "by_type": by_type}


def extract_iteration_archive(repo: Path | None = None) -> dict:
    """Count docs/archive/progress-v*.md files."""
    repo = repo or repo_root()
    arc = repo / "docs" / "archive"
    if not arc.is_dir():
        return {"count": 0}
    return {"count": len(list(arc.glob("progress-v*.md")))}


def _first_sentence(s: str, *, max_len: int = 180) -> str:
    """Strip markdown emphasis + return first sentence (up to first '.', '—' or `\\n`).
    Hard ceiling of `max_len` chars to suppress paragraph spill.
    """
    s = s.strip()
    # Strip markdown emphasis tokens
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Cut at first period (not in URL), em-dash, or newline
    m = re.search(r"([.—]|\n)", s)
    if m:
        s = s[: m.start()]
    if len(s) > max_len:
        cut = s[: max_len]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        s = cut[: max_len - 1] + "…"
    return s.strip()[:max_len]


# CLI self-test entry-point — invoked by the verification command sequence.
def _self_test() -> int:
    repo = repo_root()
    mode = detect_mode(repo)
    print(f"workflow_extractor: mode={mode}", file=sys.stderr)
    state = extract_pipeline_state(repo)
    print(f"  pipeline-state fields: {len(state)}", file=sys.stderr)
    charter = extract_charter_snapshot(repo)
    print(f"  charter topics: {charter.get('topics_present', 0)}", file=sys.stderr)
    log = extract_features_md_run_log(repo)
    print(f"  recent activity entries: {len(log)}", file=sys.stderr)
    cost = extract_cost_events()
    print(f"  cost events available: {cost.get('available')}", file=sys.stderr)
    if mode == MODE_RICH:
        recs = extract_analysis_resolutions(repo)
        print(f"  RICH features extracted: {len(recs)}", file=sys.stderr)
    else:
        recs = extract_embedded_decisions(repo)
        print(f"  EMBEDDED features extracted: {len(recs)}", file=sys.stderr)
    return 0


def main() -> int:
    if is_disabled():
        print("PIPELINE_HYGIENE_OFF=1 — workflow_extractor skipped", file=sys.stderr)
        return 0
    if "--self-test" in sys.argv[1:]:
        return _self_test()
    # Default: dump the full extraction as JSON to stdout for consumers.
    repo = repo_root()
    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": detect_mode(repo),
        "pipeline_state": extract_pipeline_state(repo),
        "charter_snapshot": extract_charter_snapshot(repo),
        "features_md_run_log": extract_features_md_run_log(repo),
        "cost_events": extract_cost_events(),
        "documentation_index": extract_documentation_index(repo),
        "test_inventory": extract_test_inventory(repo),
        "skill_inventory": extract_skill_inventory(repo),
        "hook_denial_summary": extract_hook_denial_summary(repo),
        "memory_inventory": extract_memory_inventory(),
        "iteration_archive": extract_iteration_archive(repo),
        "hero_state": extract_hero_state(repo),
    }
    if detect_mode(repo) == MODE_RICH:
        out["resolutions"] = extract_analysis_resolutions(repo)
    else:
        out["resolutions"] = extract_embedded_decisions(repo)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    # 5s watchdog for the library's own CLI entry
    def _timeout_handler(*_args):
        raise TimeoutError("workflow_extractor exceeded 5s budget")
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(5)
    try:
        sys.exit(main())
    finally:
        signal.alarm(0)
