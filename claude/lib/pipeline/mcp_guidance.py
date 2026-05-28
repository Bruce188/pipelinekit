"""Resolve per-phase MCP guidance for injection into subagent prompts.

Public surface:
    extract_mcp_guidance(charter_field, phase, connected_mcps,
                         docs_dir="docs", max_chars=1500) -> str

Reads the charter's ``## MCP Routing`` section, keeps only the entries whose
MCP server is BOTH declared in the charter AND currently connected (the
``connected_mcps`` set the orchestrator derives from ``claude mcp list``), and
that apply to the requested ``phase``. Returns a guidance block for the phase
subagent prompt, or the sentinel ``"(no MCP routing)"`` (a no-op substitution
that injects no actionable instruction — mirroring ``charter_summary``'s
``"(no charter)"``) when:

- ``charter_field`` is ``None``, empty, or the pipeline-state sentinel ``(none)``
- the resolved path does not exist or is not a file
- the file lacks a ``## MCP Routing`` section
- ``connected_mcps`` is empty / ``None`` (nothing is wired right now)
- no declared+connected entry applies to ``phase``

This is the PURE half of the contract — no subprocess, no LLM, no network.
The orchestrator owns the one ``claude mcp list`` probe per run and passes the
parsed connected-server names in (see ``claude/skills/pipeline/SKILL.md``
§ "MCP guidance resolution"). Keeping the probe out here makes the resolver
deterministic and unit-testable, mirroring ``charter_summary.py``.

Charter ``## MCP Routing`` line format (one MCP per bullet)::

    - <server>: <purpose text> | phases: <comma-list>

The ``| phases:`` clause is optional; absent (or the literal ``all``) means the
entry applies to every phase. Example section::

    ## MCP Routing
    - context7: resolve-library-id then query-docs for API verification | phases: analyze, plan, implement, review
    - serena: symbol navigation and cross-file refs | phases: analyze, implement
    - agentmemory: memory_recall at phase start; memory_save for durable findings | phases: all

The charter is committed source (operator-trust bucket), so — like
``charter_summary`` — the only bound applied is the ``max_chars`` hard cap on
the returned block. Server-name matching is case-insensitive.

Contract bound by ``claude/lib/pipeline/tests/test_mcp_guidance.py``.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional

from claude.lib.pipeline.charter_extractor import _extract_h2_body

__all__ = ["extract_mcp_guidance"]


_NO_ROUTING = "(no MCP routing)"
_HEADER = "MCP Routing"
_PHASES_MARKER = re.compile(r"\|\s*phases\s*:", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+(.*)$")
_BLOCK_PREAMBLE = (
    "MCP tools wired for this phase (per charter ## MCP Routing; use when "
    "relevant, skip silently if a call errors or the server is unavailable):"
)


def extract_mcp_guidance(
    charter_field: Optional[str],
    phase: str,
    connected_mcps: Optional[Iterable[str]],
    docs_dir: str = "docs",
    max_chars: int = 1500,
) -> str:
    """Resolve a ``{{MCP_GUIDANCE}}`` substitution for one phase.

    Parameters
    ----------
    charter_field
        Value of the ``**Charter:**`` field in ``docs/pipeline-state.md``.
        A path, the sentinel ``(none)``, or ``None`` when the line is absent.
    phase
        The dispatching phase: ``analyze`` | ``plan`` | ``implement`` |
        ``review`` | ``docs`` | ``uat``. Matched case-insensitively against
        each entry's ``phases:`` clause.
    connected_mcps
        Server names currently connected (the orchestrator parses these from
        ``claude mcp list``). Empty or ``None`` -> returns ``""``.
    docs_dir
        Directory to resolve relative charter paths against. Defaults ``docs``.
    max_chars
        Hard upper bound on the returned block length. Defaults 1500.

    Returns
    -------
    str
        A guidance block, or ``"(no MCP routing)"`` when nothing applies.
    """
    # 1. No connected servers -> nothing is wired, regardless of the charter.
    connected = {m.strip().lower() for m in (connected_mcps or []) if m and m.strip()}
    if not connected:
        return _NO_ROUTING

    # 2. Sentinel: missing / explicit `(none)` / empty charter field.
    if charter_field is None:
        return _NO_ROUTING
    cleaned = charter_field.strip()
    if cleaned == "" or cleaned == "(none)":
        return _NO_ROUTING

    # 3. Resolve path. Accept absolute, cwd-relative, or docs_dir-relative.
    path = cleaned
    if not os.path.isabs(path) and not os.path.exists(path):
        candidate = os.path.join(docs_dir, os.path.basename(path))
        if os.path.exists(candidate):
            path = candidate
    if not os.path.isfile(path):
        return _NO_ROUTING

    # 4. Read charter; extract the `## MCP Routing` body.
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return _NO_ROUTING

    body = _extract_h2_body(text, _HEADER)
    if not body or not body.strip():
        return _NO_ROUTING

    want_phase = (phase or "").strip().lower()

    # 5. Parse bullets; keep declared-AND-connected entries that apply to phase.
    lines = []
    for raw in body.splitlines():
        m = _BULLET_RE.match(raw)
        if not m:
            continue
        entry = m.group(1).strip()
        if ":" not in entry:
            continue
        name, rest = entry.split(":", 1)
        name = name.strip()
        if name.lower() not in connected:
            continue

        rest = rest.strip()
        phases_match = _PHASES_MARKER.search(rest)
        if phases_match:
            purpose = rest[: phases_match.start()].strip()
            phase_spec = rest[phases_match.end():].strip()
            phase_set = {p.strip().lower() for p in phase_spec.split(",") if p.strip()}
            applies = ("all" in phase_set) or (want_phase in phase_set)
        else:
            purpose = rest
            applies = True  # no clause -> every phase

        if not applies:
            continue
        if not purpose:
            continue
        lines.append(f"- {name}: {purpose}")

    if not lines:
        return _NO_ROUTING

    block = _BLOCK_PREAMBLE + "\n" + "\n".join(lines)
    return block[:max_chars]
