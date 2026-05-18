"""Decomposition compliance gate for /create-plan Step 4.6.

Public surface:
    audit_plan(plan_path, charter_path=None) -> dict
    render_compliance_section(audit_result) -> str
    format_ac_line(audit_result) -> str
    should_block(env=None) -> bool

Stdlib-only: re, os, pathlib, typing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER_TESTS = re.compile(
    r"^\s*(n/a|tbd|-|none|covered by)\b",
    re.IGNORECASE,
)

_TASK_HEADER = re.compile(r"^### Task \d+\.\d+:", re.MULTILINE)
_PHASE_HEADER = re.compile(r"^## Phase (\d+)([^\n]*)", re.MULTILINE)
_PARALLEL_KEYWORDS = re.compile(
    r"parallel-safe|parallel-eligible|zero file overlap|PARALLEL_DISPATCH",
    re.IGNORECASE,
)


def _parse_field(block: str, field: str) -> Optional[str]:
    """Return the value of '**field:** value' from a block, or None."""
    pattern = re.compile(
        r"^\*\*" + re.escape(field) + r":\*\*\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    )
    m = pattern.search(block)
    return m.group(1).strip() if m else None


def _parse_files(block: str) -> List[str]:
    """Return list of file paths from **Files:** line (comma-separated, strip backticks)."""
    raw = _parse_field(block, "Files")
    if not raw:
        return []
    return [f.strip().strip("`") for f in raw.split(",") if f.strip()]


def _parse_touches(block: str) -> List[str]:
    """Return list of layer tokens from **Touches:** line."""
    raw = _parse_field(block, "Touches")
    if not raw:
        return []
    # Split on +, comma, or ' and '
    return [t.strip() for t in re.split(r"[+,]| and ", raw) if t.strip()]


def _split_into_task_blocks(text: str) -> List[str]:
    """Split plan text into per-task blocks (from ### Task header to next ### Task header)."""
    positions = [m.start() for m in _TASK_HEADER.finditer(text)]
    blocks = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        blocks.append(text[pos:end])
    return blocks


def _parse_slice_strategy(charter_path: Optional[Union[str, os.PathLike]]) -> str:
    """Read ## Slice Strategy value from charter. Default 'flexible'."""
    if charter_path is None:
        return "flexible"
    p = Path(charter_path)
    if not p.exists():
        return "flexible"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^## Slice Strategy\s*\n(.*?)(?=^##|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return "flexible"
    raw = m.group(1).strip().strip("`").strip("-").strip().lower()
    if not raw:
        return "flexible"
    return raw


# ---------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------

def _audit_tdd_pairing(text: str) -> tuple[bool, List[str]]:
    """TDD pairing axis: every Testable=yes task must have non-placeholder Tests."""
    blocks = _split_into_task_blocks(text)
    details: List[str] = []
    for block in blocks:
        testable = _parse_field(block, "Testable")
        if testable is None or testable.lower() != "yes":
            continue
        tests_val = _parse_field(block, "Tests")
        # Header line for error messages
        header_m = re.match(r"### (Task \d+\.\d+:[^\n]*)", block)
        header = header_m.group(1) if header_m else "unknown task"
        if tests_val is None or not tests_val.strip():
            details.append(f"{header}: **Tests:** missing or empty")
        elif _PLACEHOLDER_TESTS.match(tests_val):
            details.append(f"{header}: **Tests:** is a placeholder ({tests_val!r})")
    return (len(details) == 0), details


def _audit_parallel_marked(text: str) -> tuple[bool, List[str]]:
    """Parallel-marked axis: phases with >1 task and zero file overlap must be marked."""
    # Find phase headers and their positions
    phase_matches = list(_PHASE_HEADER.finditer(text))
    details: List[str] = []

    for i, pm in enumerate(phase_matches):
        phase_num = pm.group(1)
        phase_header_line = pm.group(0)
        # Phase body: from end of this header line to start of next phase header
        body_start = pm.end()
        body_end = phase_matches[i + 1].start() if i + 1 < len(phase_matches) else len(text)
        phase_body = text[body_start:body_end]

        # Find task blocks within this phase body
        task_positions = [m.start() for m in _TASK_HEADER.finditer(phase_body)]
        if len(task_positions) < 2:
            continue  # only 1 task — no parallelism concern

        task_blocks = []
        for j, tp in enumerate(task_positions):
            tend = task_positions[j + 1] if j + 1 < len(task_positions) else len(phase_body)
            task_blocks.append(phase_body[tp:tend])

        # Build file sets per task
        file_sets = [set(_parse_files(tb)) for tb in task_blocks]

        # Check pairwise overlap
        has_overlap = False
        for a in range(len(file_sets)):
            for b in range(a + 1, len(file_sets)):
                if file_sets[a] & file_sets[b]:
                    has_overlap = True
                    break
            if has_overlap:
                break

        if has_overlap:
            # Tasks share files — not a parallel situation; no marking required
            continue

        # Zero overlap — check if phase header is marked
        if not _PARALLEL_KEYWORDS.search(phase_header_line):
            details.append(
                f"Phase {phase_num}: tasks have zero file overlap but phase header lacks "
                "'parallel-safe' / 'zero file overlap' / 'parallel-eligible' / 'PARALLEL_DISPATCH' marker"
            )

    return (len(details) == 0), details


def _audit_slice_strategy(
    text: str,
    charter_path: Optional[Union[str, os.PathLike]],
) -> tuple[bool, List[str]]:
    """Slice-strategy axis."""
    strategy = _parse_slice_strategy(charter_path)
    details: List[str] = []

    if strategy == "flexible":
        return True, []

    if strategy == "horizontal":
        # Overview section must have ≥20 non-whitespace chars or 'horizontal' keyword
        m = re.search(r"^## Overview\s*\n(.*?)(?=^##|\Z)", text, re.MULTILINE | re.DOTALL)
        if not m:
            details.append(
                "Slice strategy is 'horizontal' but plan has no ## Overview section with justification"
            )
            return False, details
        overview = m.group(1)
        non_ws = len(re.sub(r"\s", "", overview))
        if non_ws < 20 and "horizontal" not in overview.lower():
            details.append(
                "Slice strategy is 'horizontal' but Overview lacks justification paragraph (≥20 non-whitespace chars)"
            )
            return False, details
        return True, []

    if strategy == "vertical":
        # Each task must have **Touches:** with ≥2 layer tokens
        blocks = _split_into_task_blocks(text)
        for block in blocks:
            header_m = re.match(r"### (Task \d+\.\d+:[^\n]*)", block)
            header = header_m.group(1) if header_m else "unknown task"
            touches = _parse_touches(block)
            if len(touches) < 2:
                details.append(
                    f"{header}: slice strategy is 'vertical' but **Touches:** has fewer than 2 layers "
                    f"(found: {touches!r})"
                )
        return (len(details) == 0), details

    # Unrecognized value — treat as flexible
    details.append(f"Unrecognized slice strategy value {strategy!r} — treating as 'flexible' (auto-PASS)")
    return True, details


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def audit_plan(
    plan_path: Union[str, os.PathLike],
    charter_path: Optional[Union[str, os.PathLike]] = None,
) -> Dict:
    """Return {tdd_pairing: bool, parallel_marked: bool, slice_strategy: bool, details: list[str]}."""
    text = Path(plan_path).read_text(encoding="utf-8")

    tdd_ok, tdd_details = _audit_tdd_pairing(text)
    par_ok, par_details = _audit_parallel_marked(text)
    slc_ok, slc_details = _audit_slice_strategy(text, charter_path)

    return {
        "tdd_pairing": tdd_ok,
        "parallel_marked": par_ok,
        "slice_strategy": slc_ok,
        "details": tdd_details + par_details + slc_details,
    }


def render_compliance_section(audit_result: Dict) -> str:
    """Return markdown for the `## Decomposition Compliance` block (3-row table)."""

    def _pf(val: bool) -> str:
        return "PASS" if val else "FAIL"

    def _detail(key: str) -> str:
        # Pull first detail line that seems relevant, else "—"
        for d in audit_result.get("details", []):
            # Heuristic: TDD details mention 'Task', parallel mention 'Phase', slice mention 'vertical'/'horizontal'
            if key == "tdd" and "Task" in d and ("Tests" in d or "Testable" in d):
                return d[:80]
            if key == "par" and "Phase" in d:
                return d[:80]
            if key == "slc" and ("vertical" in d.lower() or "horizontal" in d.lower() or "slice" in d.lower()):
                return d[:80]
        return "—"

    tdd_pf = _pf(audit_result["tdd_pairing"])
    par_pf = _pf(audit_result["parallel_marked"])
    slc_pf = _pf(audit_result["slice_strategy"])

    tdd_det = _detail("tdd")
    par_det = _detail("par")
    slc_det = _detail("slc")

    return (
        "## Decomposition Compliance\n"
        "\n"
        "| Axis | Result | Detail |\n"
        "|------|--------|--------|\n"
        f"| TDD pairing | {tdd_pf} | {tdd_det} |\n"
        f"| parallel-marked | {par_pf} | {par_det} |\n"
        f"| slice-strategy | {slc_pf} | {slc_det} |\n"
        "\n"
        "Anti-horizontal-slicing rationale: see `claude/skills/tdd/SKILL.md` lines 26–49. "
        "Parallel-safe predicate: `claude/skills/pipeline/SKILL.md` Step 5.5.3a (F4 zero-overlap heuristic). "
        "Gate is informational on first release (`DECOMPOSITION_COMPLIANCE_BLOCKING` env flag, default `false`)."
    )


def format_ac_line(audit_result: Dict) -> str:
    """Return AC-DECOMP: TDD-pairing PASS|FAIL | parallel-marked PASS|FAIL | slice-strategy PASS|FAIL."""

    def _pf(val: bool) -> str:
        return "PASS" if val else "FAIL"

    return (
        f"AC-DECOMP: TDD-pairing {_pf(audit_result['tdd_pairing'])} | "
        f"parallel-marked {_pf(audit_result['parallel_marked'])} | "
        f"slice-strategy {_pf(audit_result['slice_strategy'])}"
    )


def should_block(env: Optional[Dict] = None) -> bool:
    """Return True iff env has DECOMPOSITION_COMPLIANCE_BLOCKING=true."""
    if env is None:
        env = os.environ
    val = env.get("DECOMPOSITION_COMPLIANCE_BLOCKING", "")
    return val.strip().lower() == "true"
