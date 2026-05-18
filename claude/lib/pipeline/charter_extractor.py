"""Auto-extracts a draft charter from prior workflow artifacts (docs/analysis*.md, docs/plan*.md, docs/prp.md).
Best-effort: unmappable sections render as empty bodies.
Never overwrites an existing charter.
Subprocess-mode safe (skip gate).

Public surface:
    discover_artifact_paths(docs_dir) -> dict[str, str | None]
    should_auto_extract(docs_dir)     -> tuple[bool, str]
    extract_draft_charter(...)        -> dict
    render_charter_markdown(draft, today) -> str

Contract bound by claude/lib/pipeline/tests/test_charter_extractor.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from claude.lib.pipeline.charter_revalidate import (
    parse_charter_sections,
    _BULLET_LINE_RE,
)

__all__ = [
    "discover_artifact_paths",
    "should_auto_extract",
    "extract_draft_charter",
    "render_charter_markdown",
    "subprocess_mode_skip_check",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _first_paragraph(body: str) -> str:
    """Return the body up to the first blank line; trim leading/trailing whitespace."""
    lines = body.split("\n")
    paragraph_lines: List[str] = []
    for line in lines:
        if line.strip() == "":
            if paragraph_lines:
                break
            # skip leading blank lines
        else:
            paragraph_lines.append(line)
    return " ".join(paragraph_lines).strip()


def _extract_h2_body(text: str, header_name: str) -> str:
    """Return the body of the H2 section named header_name.

    Case-insensitive match. Tolerates numeric prefixes like '## 1. Name' and
    '## 1) Name' via a leading optional group. Returns empty string when the
    header is absent.
    """
    if not text:
        return ""
    # Pattern: '## ' followed by optional numeric prefix, then the header_name (case-insensitive).
    # We match from the header line to the next H2 or EOF.
    pattern = re.compile(
        r"^[ \t]*##[ \t]+(?:\d+[.)]\s*)?" + re.escape(header_name) + r"[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""

    body_start = match.end()
    # Find the next H2 header
    next_h2 = re.compile(r"^[ \t]*##[ \t]+", re.MULTILINE)
    next_match = next_h2.search(text, body_start)
    if next_match:
        body = text[body_start:next_match.start()]
    else:
        body = text[body_start:]

    # Drop leading newline
    if body.startswith("\n"):
        body = body[1:]
    return body


def _extract_sublist_bullets(body: str, marker_label: str) -> List[str]:
    """Extract bullet lines following a **marker_label:** bold marker.

    Case-insensitive marker match. Uses _BULLET_LINE_RE (re-imported from
    charter_revalidate, not redefined). Stops on the next **Foo:** bold-field
    marker or first non-bullet content line.
    """
    if not body:
        return []
    marker_re = re.compile(
        r"\*\*" + re.escape(marker_label) + r"\s*:\*\*",
        re.IGNORECASE,
    )
    marker = marker_re.search(body)
    if not marker:
        return []

    tail = body[marker.end():]
    bullets: List[str] = []
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Stop on a new bold field marker like **In:** or **PRESERVE:**
        if re.match(r"^\*\*[A-Za-z][\w\- ]*:\*\*", stripped):
            break
        m = _BULLET_LINE_RE.match(line)
        if m:
            bullets.append(m.group(1).strip())
            continue
        # Stop on first non-bullet content line (heading, paragraph, etc.)
        break
    return bullets


def _find_highest_versioned(docs_dir: str, prefix: str) -> Optional[str]:
    """Return path of the highest-versioned file matching <prefix>*.md.

    The unversioned form <prefix>.md is treated as version 0.
    Returns None when neither exists.
    """
    if not os.path.isdir(docs_dir):
        return None

    versioned_re = re.compile(r"-v(\d+)\.md$")
    best_version = -1
    best_path: Optional[str] = None

    for fname in os.listdir(docs_dir):
        if not fname.startswith(prefix):
            continue
        if not fname.endswith(".md"):
            continue
        full_path = os.path.join(docs_dir, fname)
        # Check for versioned form
        vm = versioned_re.search(fname)
        if vm:
            version = int(vm.group(1))
        elif fname == prefix + ".md":
            version = 0
        else:
            # e.g. 'analysis_something.md' — skip
            # Only accept exact prefix + optional -vN + .md
            stripped = fname[len(prefix):]
            if stripped == ".md":
                version = 0
            elif versioned_re.fullmatch(stripped):
                version = int(versioned_re.fullmatch(stripped).group(1))
            else:
                continue

        if version > best_version:
            best_version = version
            best_path = full_path

    return best_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_artifact_paths(docs_dir: str = "docs") -> Dict[str, Optional[str]]:
    """Return paths to the highest-versioned analysis, plan, and prp files.

    Keys: 'analysis', 'plan', 'prp'. Each value is the resolved path string
    or None if no matching file exists.
    """
    analysis = _find_highest_versioned(docs_dir, "analysis")
    plan = _find_highest_versioned(docs_dir, "plan")

    # prp.md is unversioned — the canonical single name
    prp_path = os.path.join(docs_dir, "prp.md")
    prp = prp_path if os.path.exists(prp_path) else None

    return {"analysis": analysis, "plan": plan, "prp": prp}


def should_auto_extract(docs_dir: str = "docs") -> Tuple[bool, str]:
    """Return (should_extract, reason).

    should_extract is True only when ALL of:
    - docs/charter.md does NOT exist
    - At least one of analysis or plan is present

    When False, reason is 'CHARTER_AUTO_EXTRACT_SKIPPED: <reason>'.
    """
    charter_path = os.path.join(docs_dir, "charter.md")
    if os.path.exists(charter_path):
        return (False, "CHARTER_AUTO_EXTRACT_SKIPPED: docs/charter.md already exists")

    paths = discover_artifact_paths(docs_dir)
    if paths["analysis"] is None and paths["plan"] is None:
        return (False, "CHARTER_AUTO_EXTRACT_SKIPPED: no prior analysis or plan")

    return (True, "")


def extract_draft_charter(
    analysis_text: str = "",
    plan_text: str = "",
    prp_text: str = "",
) -> Dict:
    """Pure function. Returns a dict with the 9 charter section keys.

    All keys are always present. Empty-string or empty-list defaults when
    the source section is absent. Best-effort: no exceptions on missing data.
    """
    # 1. Goal from analysis Objective body, first paragraph
    objective_body = _extract_h2_body(analysis_text, "Objective")
    goal = _first_paragraph(objective_body) if objective_body else ""

    # 2. non_goals from AVOID bullets, constraints from PRESERVE bullets
    constraints_body = _extract_h2_body(analysis_text, "Constraints")
    non_goals: List[str] = _extract_sublist_bullets(constraints_body, "AVOID")
    constraints: List[str] = _extract_sublist_bullets(constraints_body, "PRESERVE")

    # 3. users, problem, success from prp if provided
    users = ""
    problem = ""
    success = ""
    if prp_text:
        users = _extract_h2_body(prp_text, "Users").strip()
        problem = _extract_h2_body(prp_text, "Problem").strip()
        success = _extract_h2_body(prp_text, "Success Criteria").strip()

    # 4. Problem fallback from first AVOID bullet
    if not problem and non_goals:
        problem = f"Existing workflow allows: {non_goals[0]}"

    # 5. mvp_boundary verbatim from plan MVP Boundary section
    mvp_boundary = _extract_h2_body(plan_text, "MVP Boundary").strip()

    # 6. prior_art from analysis Prior Art section
    prior_art = _extract_h2_body(analysis_text, "Prior Art").strip()

    # 7. open_questions from analysis Open Questions section
    open_questions = _extract_h2_body(analysis_text, "Open Questions").strip()

    return {
        "goal": goal,
        "users": users,
        "problem": problem,
        "success": success,
        "non_goals": non_goals,
        "constraints": constraints,
        "mvp_boundary": mvp_boundary,
        "prior_art": prior_art,
        "open_questions": open_questions,
    }


def render_charter_markdown(draft: Dict, today: Optional[str] = None) -> str:
    """Render a 9-section + Decision Log charter conforming to the Charter File Template.

    Frontmatter is fixed status: draft. today defaults to date.today().isoformat().
    Empty-list / empty-string fields render the section header followed by ONE blank line.
    """
    from datetime import date
    if today is None:
        today = date.today().isoformat()

    def _render_section(header: str, content) -> str:
        if isinstance(content, list):
            body = "\n".join(f"- {item}" for item in content) if content else ""
        else:
            body = str(content) if content else ""
        if body:
            return f"## {header}\n{body}\n"
        else:
            return f"## {header}\n\n"

    goal_text = draft.get("goal", "")
    goal_oneliner = goal_text.split("\n")[0][:80] if goal_text else "Draft"

    lines = [
        "---",
        "version: 1",
        f"created: {today}",
        "status: draft",
        "---",
        "",
        f"# Charter — {goal_oneliner}",
        "",
        "> Auto-extracted draft from prior workflow artifacts. Review and edit before ratifying.",
        "",
        _render_section("Goal", draft.get("goal", "")),
        _render_section("Users", draft.get("users", "")),
        _render_section("Problem", draft.get("problem", "")),
        _render_section("Success", draft.get("success", "")),
        _render_section("Non-Goals", draft.get("non_goals", [])),
        _render_section("Constraints", draft.get("constraints", [])),
        _render_section("MVP Boundary", draft.get("mvp_boundary", "")),
        _render_section("Prior Art", draft.get("prior_art", "")),
        _render_section("Open Questions", draft.get("open_questions", "")),
        "## Decision Log",
        "| Date | Question | Decision | Reason |",
        "|------|----------|----------|--------|",
        "",
    ]

    return "\n".join(lines)


def subprocess_mode_skip_check(env: Optional[Dict] = None) -> Tuple[bool, str]:
    """Return (skip, log_line).

    Skip is True when AskUserQuestion is unavailable (subprocess driver).
    Detection: read env.get("CLAUDE_INTERACTIVE"); unset or literal "0" means
    subprocess mode. Default env is os.environ. Log token:
      "CHARTER_AUTO_EXTRACT_SKIPPED: subprocess mode"
    Returns (False, "") in interactive mode.
    """
    if env is None:
        env = os.environ
    value = env.get("CLAUDE_INTERACTIVE")
    if value in (None, "", "0"):
        return (True, "CHARTER_AUTO_EXTRACT_SKIPPED: subprocess mode")
    return (False, "")
