#!/usr/bin/env python3
"""Tests for claude/lib/pipeline/ac_lint.py.

Test surface (minimum 4 cases):
- test_lint_noisy_baseline_empty_diff_tight_pattern_not_flagged
- test_lint_noisy_baseline_empty_diff_noisy_pattern_flagged
- test_lint_plan_overcapture_tight_pattern_not_flagged
- test_lint_plan_overcapture_overcapturing_pattern_flagged
"""

import os
import sys
import tempfile

# Locate ac_lint module — insert claude/lib/pipeline/ into path
_PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PIPELINE_DIR)

from ac_lint import lint_noisy_baseline, lint_plan_overcapture  # noqa: E402


def _write_patterns(patterns: list[str]) -> str:
    """Write patterns to a temp file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="ac_lint_test_")
    os.close(fd)
    with open(path, "w") as f:
        for p in patterns:
            f.write(p + "\n")
    return path


# ---------------------------------------------------------------------------
# lint_noisy_baseline tests
# ---------------------------------------------------------------------------

def test_lint_noisy_baseline_empty_diff_tight_pattern_not_flagged():
    """A tight pattern that cannot match the empty string should NOT be flagged."""
    path = _write_patterns([r"^\+    foo: bar$"])
    try:
        result = lint_noisy_baseline(path, "")
        assert result == [], f"Expected [], got {result!r}"
    finally:
        os.unlink(path)


def test_lint_noisy_baseline_empty_diff_noisy_pattern_flagged():
    """A pattern that matches the empty string is noisy and MUST be flagged."""
    noisy = r"^.*$"
    path = _write_patterns([noisy])
    try:
        result = lint_noisy_baseline(path, "")
        assert noisy in result, f"Expected {noisy!r} in result, got {result!r}"
    finally:
        os.unlink(path)


def test_lint_noisy_baseline_comment_and_blank_lines_ignored():
    """Lines starting with # or empty lines in the ac_file are ignored."""
    path = _write_patterns(["# This is a comment", "", r"^.*$"])
    try:
        result = lint_noisy_baseline(path, "")
        # Only the real pattern should appear, not the comment or blank
        assert "# This is a comment" not in result
        assert "" not in result
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# lint_plan_overcapture tests
# ---------------------------------------------------------------------------

def test_lint_plan_overcapture_tight_pattern_not_flagged():
    """A tight pattern that does not match the plan text should NOT be flagged."""
    path = _write_patterns([r"^\+    foo: bar$"])
    try:
        result = lint_plan_overcapture(path, "...feature X adds Y...")
        assert result == [], f"Expected [], got {result!r}"
    finally:
        os.unlink(path)


def test_lint_plan_overcapture_overcapturing_pattern_flagged():
    """A pattern matching the plan's own meta-prose IS flagged as over-capturing."""
    pat = r"Co-Authored-By"
    plan_text = "This plan was Co-Authored-By a developer."
    path = _write_patterns([pat])
    try:
        result = lint_plan_overcapture(path, plan_text)
        assert pat in result, f"Expected {pat!r} in result, got {result!r}"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# __all__ surface test
# ---------------------------------------------------------------------------

def test_all_exports():
    """__all__ must contain exactly the two public functions."""
    from ac_lint import __all__
    assert sorted(__all__) == ["lint_noisy_baseline", "lint_plan_overcapture"], (
        f"Unexpected __all__: {sorted(__all__)!r}"
    )
