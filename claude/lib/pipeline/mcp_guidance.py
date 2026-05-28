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
- ``connected_mcps`` is empty / ``None`` (nothing is wired right now)
- the charter HAS a ``## MCP Routing`` section but all entries are
  ``none``/``skip`` opt-outs OR no declared+connected entry applies to ``phase``
- the charter HAS a ``## MCP Routing`` section with no surviving entries

When the charter file EXISTS but lacks a ``## MCP Routing`` section AND
``connected_mcps`` is non-empty, the resolver falls back to the BUILT-IN
DEFAULT MAP (see ``_DEFAULT_ROUTING`` below), intersected with
``connected_mcps`` and filtered to ``phase``. This means connected MCPs surface
into phase subagents even without hand-editing the charter. The explicit
charter section wins ENTIRELY when present — the default map is never merged
in with an explicit section.

Built-in default routing map (mirrors Feature 3's phase-applicability):

    context7        analyze, plan, implement, review
                    resolve-library-id then query-docs for framework/library
                    API verification

    serena          analyze, implement, review
                    symbol navigation and cross-file refs

    agentmemory     all phases
                    memory_recall for prior context at phase start;
                    memory_save for durable findings

    sequential-     plan, review
    thinking        structured multi-step reasoning for complex decisions

Precedence (most-specific first):
    1. Empty / None ``connected_mcps`` -> ``(no MCP routing)`` (runs first).
    2. Sentinel / missing / unreadable charter path -> ``(no MCP routing)``.
    3. Charter has explicit ``## MCP Routing`` section -> use it ENTIRELY.
       3a. Section present but all entries are ``none``/``skip`` or no entry
           survives connected+phase intersection -> ``(no MCP routing)``.
           The default map is NOT consulted (opt-out preserved).
    4. Charter file exists, section ABSENT, ``connected_mcps`` non-empty ->
       built-in default map intersected with ``connected_mcps``, filtered to
       ``phase``.  If no entry survives -> ``(no MCP routing)``.

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
    - serena: symbol navigation and cross-file refs | phases: analyze, implement, review
    - agentmemory: memory_recall at phase start; memory_save for durable findings | phases: all
    - sequential-thinking: structured multi-step reasoning for complex decisions | phases: plan, review

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

# Built-in default routing map. Each value is (purpose_text, phase_set).
# phase_set {"all"} means every phase (mirrors the "all" literal in charter bullets).
# Phase applicability mirrors Feature 3's detect_applicable_mcps.sh built-in map.
_DEFAULT_ROUTING: dict[str, tuple[str, frozenset[str]]] = {
    "context7": (
        "resolve-library-id then query-docs for framework/library API verification",
        frozenset({"analyze", "plan", "implement", "review"}),
    ),
    "serena": (
        "symbol navigation and cross-file refs",
        frozenset({"analyze", "implement", "review"}),
    ),
    "agentmemory": (
        "memory_recall for prior context at phase start; memory_save for durable findings",
        frozenset({"all"}),
    ),
    "sequential-thinking": (
        "structured multi-step reasoning for complex decisions",
        frozenset({"plan", "review"}),
    ),
}


def _render_block(lines: list[str], max_chars: int) -> str:
    """Assemble the guidance block from surviving entry lines and apply the hard cap."""
    block = _BLOCK_PREAMBLE + "\n" + "\n".join(lines)
    return block[:max_chars]


def _default_map_block(
    want_phase: str,
    connected: set[str],
    max_chars: int,
) -> str:
    """Build a guidance block from the built-in default routing map.

    Intersects ``_DEFAULT_ROUTING`` with ``connected`` (case-insensitive) and
    filters to ``want_phase``.  Returns ``_NO_ROUTING`` when nothing survives.
    """
    lines = []
    for name, (purpose, phase_set) in _DEFAULT_ROUTING.items():
        if name.lower() not in connected:
            continue
        applies = ("all" in phase_set) or (want_phase in phase_set)
        if not applies:
            continue
        lines.append(f"- {name}: {purpose}")
    if not lines:
        return _NO_ROUTING
    return _render_block(lines, max_chars)


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

    want_phase = (phase or "").strip().lower()

    body = _extract_h2_body(text, _HEADER)
    if not body or not body.strip():
        # Section ABSENT — fall back to the built-in default map (precedence branch 4).
        return _default_map_block(want_phase, connected, max_chars)

    # 5. Parse bullets from the EXPLICIT section; keep declared-AND-connected
    #    entries that apply to phase.  If the section yields no survivors (e.g.
    #    opt-out with "- none" or "- skip: ..."), return (no MCP routing)
    #    WITHOUT falling through to the default map (precedence branch 3a).
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
        # Explicit section present but no entries survived (opt-out or all
        # declared servers disconnected / phase-excluded). Do NOT consult the
        # default map — the operator explicitly wrote a section.
        return _NO_ROUTING

    return _render_block(lines, max_chars)
