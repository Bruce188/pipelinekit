"""Tests for ``claude/lib/pipeline/charter_summary.py``.

Contract:
    extract_charter_summary(charter_field, docs_dir="docs", max_chars=800) -> str

Branches covered:
    1. ``charter_field is None``                                  -> "(no charter)"
    2. ``charter_field == "(none)"``                              -> "(no charter)"
    3. ``charter_field == ""`` (or whitespace)                     -> "(no charter)"
    4. Nonexistent path                                           -> "(no charter)"
    5. Charter with short ``## Goal`` body                         -> body returned
    6. Charter with > max_chars ``## Goal`` body                   -> ``len == max_chars``
    7. Charter missing ``## Goal`` H2                              -> "(no charter)"
    8. Numeric-prefixed ``## 1. Goal`` header                      -> body returned
"""

from __future__ import annotations

import os

import pytest

from claude.lib.pipeline.charter_summary import extract_charter_summary


def _write_charter(tmp_path, body: str) -> str:
    """Helper: write a charter file and return its path."""
    path = tmp_path / "charter.md"
    path.write_text(body, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Branches 1-3: sentinel / missing input
# ---------------------------------------------------------------------------

def test_none_returns_no_charter():
    assert extract_charter_summary(None) == "(no charter)"


def test_explicit_none_sentinel_returns_no_charter():
    assert extract_charter_summary("(none)") == "(no charter)"


def test_empty_string_returns_no_charter():
    assert extract_charter_summary("") == "(no charter)"


def test_whitespace_only_returns_no_charter():
    assert extract_charter_summary("   \n  ") == "(no charter)"


# ---------------------------------------------------------------------------
# Branch 4: nonexistent path
# ---------------------------------------------------------------------------

def test_nonexistent_path_returns_no_charter(tmp_path):
    bogus = str(tmp_path / "does-not-exist.md")
    assert extract_charter_summary(bogus) == "(no charter)"


# ---------------------------------------------------------------------------
# Branch 5: short Goal body
# ---------------------------------------------------------------------------

def test_short_goal_body_returned_verbatim(tmp_path):
    body = (
        "---\nversion: 1\n---\n\n"
        "# Charter\n\n"
        "## Goal\n"
        "Make the system fast and correct.\n\n"
        "## Users\n"
        "Internal team.\n"
    )
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path)
    assert "Make the system fast and correct." in out
    assert out.startswith("Make the system fast and correct.")
    # Body ends at the next ## header, so 'Internal team' must not leak.
    assert "Internal team" not in out


# ---------------------------------------------------------------------------
# Branch 6: hard truncation at max_chars
# ---------------------------------------------------------------------------

def test_long_goal_hard_truncated_at_max_chars(tmp_path):
    big = "X" * 5000  # well over 800
    body = "# Charter\n\n## Goal\n" + big + "\n\n## Users\nnext\n"
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path, max_chars=800)
    assert len(out) == 800
    assert out == "X" * 800


def test_truncation_does_not_respect_word_boundary(tmp_path):
    # Build a body where char 800 lands mid-word; assert the slice is taken
    # exactly at the byte boundary regardless.
    word = "abcdefghij"  # 10 chars
    body_text = word * 200  # 2000 chars; char 800 sits inside the 81st word.
    body = "# Charter\n\n## Goal\n" + body_text + "\n"
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path, max_chars=800)
    assert len(out) == 800
    # Slice must equal text[:800] exactly — no word-boundary nudging.
    assert out == body_text[:800]


def test_custom_max_chars_respected(tmp_path):
    big = "Y" * 3000
    body = "# Charter\n\n## Goal\n" + big + "\n"
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path, max_chars=42)
    assert len(out) == 42
    assert out == "Y" * 42


# ---------------------------------------------------------------------------
# Branch 7: missing Goal H2
# ---------------------------------------------------------------------------

def test_missing_goal_header_returns_no_charter(tmp_path):
    body = (
        "# Charter\n\n"
        "## Users\nInternal team.\n\n"
        "## Problem\nSlow tests.\n"
    )
    path = _write_charter(tmp_path, body)
    assert extract_charter_summary(path) == "(no charter)"


def test_empty_goal_body_returns_no_charter(tmp_path):
    body = "# Charter\n\n## Goal\n\n## Users\nfoo\n"
    path = _write_charter(tmp_path, body)
    assert extract_charter_summary(path) == "(no charter)"


# ---------------------------------------------------------------------------
# Branch 8: numeric-prefixed Goal header
# ---------------------------------------------------------------------------

def test_numeric_prefixed_goal_header_extracted(tmp_path):
    body = (
        "# Charter\n\n"
        "## 1. Goal\n"
        "Numeric-prefixed body content.\n\n"
        "## 2. Users\nfoo\n"
    )
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path)
    assert "Numeric-prefixed body content." in out


def test_paren_numeric_prefixed_goal_header_extracted(tmp_path):
    body = (
        "# Charter\n\n"
        "## 1) Goal\n"
        "Paren-numeric body.\n\n"
        "## 2) Users\nfoo\n"
    )
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path)
    assert "Paren-numeric body." in out


# ---------------------------------------------------------------------------
# Docs-dir relative resolution
# ---------------------------------------------------------------------------

def test_docs_dir_relative_resolution(tmp_path):
    body = "# Charter\n\n## Goal\nRelative-path body.\n"
    # Write under a custom docs_dir; pass only the basename.
    docs_dir = tmp_path / "altdocs"
    docs_dir.mkdir()
    path = docs_dir / "charter.md"
    path.write_text(body, encoding="utf-8")

    out = extract_charter_summary(
        "charter.md",
        docs_dir=str(docs_dir),
    )
    assert "Relative-path body." in out


# ---------------------------------------------------------------------------
# Case-insensitive Goal matching (precedent: _extract_h2_body)
# ---------------------------------------------------------------------------

def test_case_insensitive_goal_header(tmp_path):
    body = "# Charter\n\n## goal\nLowercased header body.\n"
    path = _write_charter(tmp_path, body)
    out = extract_charter_summary(path)
    assert "Lowercased header body." in out
