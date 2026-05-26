"""Extract a short charter summary for injection into per-phase subagent prompts.

Public surface:
    extract_charter_summary(charter_field, docs_dir="docs", max_chars=800) -> str

Returns the first ``max_chars`` characters of the charter's ``## Goal`` body
when a charter is present, or the literal string ``(no charter)`` when:

- ``charter_field`` is ``None``, empty, or the pipeline-state sentinel ``(none)``
- the resolved path does not exist or is not a file
- the file lacks a ``## Goal`` (or ``## N. Goal``) section
- the ``## Goal`` body is empty after stripping

Truncation is a HARD slice via ``text[:max_chars]`` — NOT word-bounded —
matching the contract in
``docs/features-pipelinekit-refresh.md`` § ``feat/charter-in-subagent-prompts``.

Substitution is performed at dispatch time by the pipeline orchestrator
(see ``claude/skills/pipeline/SKILL.md`` § "Charter summary placeholder
substitution"). The helper itself is pure stdlib — no subprocess, no LLM,
no network.

Contract bound by ``claude/lib/pipeline/tests/test_charter_summary.py``.
"""

from __future__ import annotations

import os
from typing import Optional

from claude.lib.pipeline.charter_extractor import _extract_h2_body

__all__ = ["extract_charter_summary"]


_NO_CHARTER = "(no charter)"


def extract_charter_summary(
    charter_field: Optional[str],
    docs_dir: str = "docs",
    max_chars: int = 800,
) -> str:
    """Resolve a `**Charter:**` field value to a ≤ ``max_chars`` summary string.

    Parameters
    ----------
    charter_field
        The string value of the ``**Charter:**`` field in
        ``docs/pipeline-state.md``. Typically a path (``docs/charter.md``),
        the sentinel ``(none)``, or ``None`` when the line is absent.
    docs_dir
        Directory to resolve relative paths against. Defaults to ``docs``.
    max_chars
        Hard upper bound on the returned summary length. Defaults to 800
        per the feature spec.

    Returns
    -------
    str
        Either ``"(no charter)"`` or the first ``max_chars`` characters of
        the charter's ``## Goal`` body.
    """
    # 1. Sentinel: missing / explicit `(none)` / empty.
    if charter_field is None:
        return _NO_CHARTER
    cleaned = charter_field.strip()
    if cleaned == "" or cleaned == "(none)":
        return _NO_CHARTER

    # 2. Resolve path. Accept absolute, cwd-relative, or docs_dir-relative.
    path = cleaned
    if not os.path.isabs(path) and not os.path.exists(path):
        candidate = os.path.join(docs_dir, os.path.basename(path))
        if os.path.exists(candidate):
            path = candidate

    if not os.path.isfile(path):
        return _NO_CHARTER

    # 3. Read file; extract `## Goal` body (case-insensitive,
    #    numeric-prefix tolerant via the shared `_extract_h2_body` helper).
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return _NO_CHARTER

    body = _extract_h2_body(text, "Goal")
    if not body or not body.strip():
        return _NO_CHARTER

    # 4. Hard truncate (text[:max_chars]) — NOT word boundary.
    return body[:max_chars]
