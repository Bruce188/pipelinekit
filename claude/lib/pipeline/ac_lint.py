"""AC lint utilities for the pipeline.

Public API:
    lint_noisy_baseline(ac_file, baseline_diff) -> list[str]
    lint_plan_overcapture(ac_file, plan_text) -> list[str]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

__all__ = ["lint_noisy_baseline", "lint_plan_overcapture"]


def _load_patterns(path: str) -> List[str]:
    """Read AC regex patterns from path, stripping blank and #-prefixed lines."""
    text = Path(path).read_text(encoding="utf-8")
    patterns: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def lint_noisy_baseline(ac_file: str, baseline_diff: str) -> List[str]:
    """Return patterns from ac_file that match baseline_diff (noisy patterns).

    A pattern is considered noisy if it fires even when no relevant change
    is present. The most common invocation uses baseline_diff="" (empty diff):
    any regex matching the empty string is by definition noisy.

    Returns a list of regex strings that produced a match.  Empty list → clean.
    """
    patterns = _load_patterns(ac_file)
    noisy: List[str] = []
    for pat in patterns:
        try:
            if re.search(pat, baseline_diff) is not None:
                noisy.append(pat)
        except re.error:
            # Malformed pattern — skip silently; linting is best-effort.
            pass
    return noisy


def lint_plan_overcapture(ac_file: str, plan_text: str) -> List[str]:
    """Return patterns from ac_file that over-capture plan_text.

    A pattern over-captures if it produces at least one match against the
    plan's own meta-prose, meaning it would fire spuriously whenever the
    plan file is included in a diff.

    Returns a list of regex strings whose match count > 0.  Empty list → clean.
    """
    patterns = _load_patterns(ac_file)
    overcapturing: List[str] = []
    for pat in patterns:
        try:
            if re.findall(pat, plan_text):
                overcapturing.append(pat)
        except re.error:
            pass
    return overcapturing
