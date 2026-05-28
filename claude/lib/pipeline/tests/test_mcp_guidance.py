"""Tests for ``claude/lib/pipeline/mcp_guidance.py``.

Contract:
    extract_mcp_guidance(charter_field, phase, connected_mcps,
                         docs_dir="docs", max_chars=1500) -> str

Branches covered:
    1.  ``connected_mcps`` empty / None                          -> "(no MCP routing)"
    2.  ``charter_field is None`` / "(none)" / "" / whitespace   -> "(no MCP routing)"
    3.  Nonexistent path                                         -> "(no MCP routing)"
    4.  Charter missing ``## MCP Routing`` H2 + non-empty        -> default map intersected
        connected                                                   with connected, phase-filtered
    5.  Entry connected, no phases clause                        -> included (any phase)
    6.  Entry connected, phases clause includes phase            -> included
    7.  Entry connected, phases clause excludes phase            -> excluded
    8.  Entry declared but NOT connected                         -> dropped
    9.  ``phases: all``                                          -> included (any phase)
    10. Case-insensitive server-name match                       -> included
    11. Numeric-prefixed ``## 1. MCP Routing`` header            -> parsed
    12. Mixed entries (connect/phase filters)                    -> only survivors
    13. Block preamble present when any entry survives           -> preamble line
    14. > max_chars body                                         -> ``len <= max_chars``
    15. docs_dir-relative path resolution                        -> resolved
    16. Explicit ``## MCP Routing`` with only none/skip entries  -> "(no MCP routing)"
        (opt-out preserved; default map NOT consulted)
    17. No-section charter, connected intersected with default   -> only connected entries
        map                                                         from default map
"""

from __future__ import annotations

import pytest

from claude.lib.pipeline.mcp_guidance import extract_mcp_guidance


_SECTION = """---
version: 1
status: ratified
---

## Goal
Build a thing.

## MCP Routing
- context7: resolve-library-id then query-docs for API verification | phases: analyze, plan, implement, review
- serena: symbol navigation and cross-file refs | phases: analyze, implement
- agentmemory: memory_recall at phase start; memory_save for durable findings | phases: all
- local-rag: query_documents for niche docs

## Decision Log
| Date | Question | Decision | Reason |
|------|----------|----------|--------|
"""


def _write(tmp_path, body: str) -> str:
    path = tmp_path / "charter.md"
    path.write_text(body, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Branch 1: no connected servers -> nothing wired
# ---------------------------------------------------------------------------

def test_empty_connected_returns_empty(tmp_path):
    p = _write(tmp_path, _SECTION)
    assert extract_mcp_guidance(p, "analyze", []) == "(no MCP routing)"


def test_none_connected_returns_empty(tmp_path):
    p = _write(tmp_path, _SECTION)
    assert extract_mcp_guidance(p, "analyze", None) == "(no MCP routing)"


def test_whitespace_only_connected_names_ignored(tmp_path):
    p = _write(tmp_path, _SECTION)
    assert extract_mcp_guidance(p, "analyze", ["  ", ""]) == "(no MCP routing)"


# ---------------------------------------------------------------------------
# Branch 2: sentinel / missing charter field
# ---------------------------------------------------------------------------

def test_charter_none_returns_empty():
    assert extract_mcp_guidance(None, "analyze", ["context7"]) == "(no MCP routing)"


def test_charter_sentinel_returns_empty():
    assert extract_mcp_guidance("(none)", "analyze", ["context7"]) == "(no MCP routing)"


def test_charter_empty_returns_empty():
    assert extract_mcp_guidance("", "analyze", ["context7"]) == "(no MCP routing)"


def test_charter_whitespace_returns_empty():
    assert extract_mcp_guidance("   \n ", "analyze", ["context7"]) == "(no MCP routing)"


# ---------------------------------------------------------------------------
# Branch 3: nonexistent path
# ---------------------------------------------------------------------------

def test_nonexistent_path_returns_empty(tmp_path):
    bogus = str(tmp_path / "nope.md")
    assert extract_mcp_guidance(bogus, "analyze", ["context7"]) == "(no MCP routing)"


# ---------------------------------------------------------------------------
# Branch 4: missing section -> default map intersected with connected
# ---------------------------------------------------------------------------

def test_missing_section_uses_default_map(tmp_path):
    p = _write(tmp_path, "## Goal\nNo routing here.\n")
    # context7 is in default map for analyze -> should surface
    out = extract_mcp_guidance(p, "analyze", ["context7"])
    assert out.startswith("MCP tools wired for this phase")
    assert "context7:" in out
    # serena not applicable to plan in default map -> (no MCP routing)
    assert extract_mcp_guidance(p, "plan", ["serena"]) == "(no MCP routing)"
    # serena IS applicable to implement -> should surface
    assert "serena:" in extract_mcp_guidance(p, "implement", ["serena"])


# ---------------------------------------------------------------------------
# Branches 5-7: phase filtering
# ---------------------------------------------------------------------------

def test_no_phase_clause_applies_to_any_phase(tmp_path):
    p = _write(tmp_path, _SECTION)
    # local-rag has no phases clause -> applies everywhere.
    out = extract_mcp_guidance(p, "uat", ["local-rag"])
    assert "local-rag: query_documents for niche docs" in out


def test_phase_clause_includes_phase(tmp_path):
    p = _write(tmp_path, _SECTION)
    out = extract_mcp_guidance(p, "implement", ["serena"])
    assert "serena: symbol navigation and cross-file refs" in out


def test_phase_clause_excludes_phase(tmp_path):
    p = _write(tmp_path, _SECTION)
    # serena's clause is "analyze, implement" -> excluded for review.
    out = extract_mcp_guidance(p, "review", ["serena"])
    assert out == "(no MCP routing)"


# ---------------------------------------------------------------------------
# Branch 8: declared but not connected
# ---------------------------------------------------------------------------

def test_declared_but_not_connected_dropped(tmp_path):
    p = _write(tmp_path, _SECTION)
    # context7 is declared for analyze but not in the connected set.
    out = extract_mcp_guidance(p, "analyze", ["serena"])
    assert "context7" not in out
    assert "serena" in out


# ---------------------------------------------------------------------------
# Branch 9: phases: all
# ---------------------------------------------------------------------------

def test_phases_all_applies_everywhere(tmp_path):
    p = _write(tmp_path, _SECTION)
    for phase in ("analyze", "plan", "implement", "review", "docs", "uat"):
        out = extract_mcp_guidance(p, phase, ["agentmemory"])
        assert "agentmemory: memory_recall" in out


# ---------------------------------------------------------------------------
# Branch 10: case-insensitive name match
# ---------------------------------------------------------------------------

def test_case_insensitive_server_match(tmp_path):
    p = _write(tmp_path, _SECTION)
    out = extract_mcp_guidance(p, "analyze", ["Context7"])
    assert "context7: resolve-library-id" in out


# ---------------------------------------------------------------------------
# Branch 11: numeric-prefixed header
# ---------------------------------------------------------------------------

def test_numeric_prefixed_header(tmp_path):
    body = _SECTION.replace("## MCP Routing", "## 7. MCP Routing")
    p = _write(tmp_path, body)
    out = extract_mcp_guidance(p, "analyze", ["context7"])
    assert "context7: resolve-library-id" in out


# ---------------------------------------------------------------------------
# Branch 12: mixed survivors
# ---------------------------------------------------------------------------

def test_mixed_entries_only_survivors(tmp_path):
    p = _write(tmp_path, _SECTION)
    # analyze phase; connect context7 + serena + agentmemory; local-rag absent.
    out = extract_mcp_guidance(
        p, "analyze", ["context7", "serena", "agentmemory"]
    )
    assert "context7:" in out
    assert "serena:" in out
    assert "agentmemory:" in out
    assert "local-rag" not in out  # not connected


# ---------------------------------------------------------------------------
# Branch 13: preamble present
# ---------------------------------------------------------------------------

def test_preamble_present_when_entries_survive(tmp_path):
    p = _write(tmp_path, _SECTION)
    out = extract_mcp_guidance(p, "analyze", ["context7"])
    assert out.startswith("MCP tools wired for this phase")


# ---------------------------------------------------------------------------
# Branch 14: hard cap
# ---------------------------------------------------------------------------

def test_hard_cap(tmp_path):
    long_purpose = "x" * 5000
    body = (
        "## MCP Routing\n"
        f"- context7: {long_purpose} | phases: all\n"
    )
    p = _write(tmp_path, body)
    out = extract_mcp_guidance(p, "analyze", ["context7"], max_chars=200)
    assert len(out) == 200


# ---------------------------------------------------------------------------
# Branch 15: docs_dir-relative resolution
# ---------------------------------------------------------------------------

def test_docs_dir_relative_resolution(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "charter.md").write_text(_SECTION, encoding="utf-8")
    # Pass a bare basename that does not exist in cwd; resolver falls back to docs_dir.
    out = extract_mcp_guidance(
        "charter.md", "analyze", ["context7"], docs_dir=str(docs)
    )
    assert "context7: resolve-library-id" in out


# ---------------------------------------------------------------------------
# Branch 16: explicit ## MCP Routing with only none/skip entries -> opt-out
# ---------------------------------------------------------------------------

def test_explicit_none_section_opt_out(tmp_path):
    # Charter WITH ## MCP Routing containing only "- none"
    none_body = "## Goal\nA thing.\n\n## MCP Routing\n- none\n"
    p = _write(tmp_path, none_body)
    # Even with real connected servers, the explicit opt-out wins
    result = extract_mcp_guidance(p, "analyze", ["context7", "serena", "agentmemory"])
    assert result == "(no MCP routing)"

    # Variant: "- skip: operator opts out" also suppresses default
    skip_body = "## Goal\nA thing.\n\n## MCP Routing\n- skip: operator opts out\n"
    p2 = _write(tmp_path, skip_body)
    result2 = extract_mcp_guidance(p2, "analyze", ["context7", "serena", "agentmemory"])
    assert result2 == "(no MCP routing)"


# ---------------------------------------------------------------------------
# Branch 17: no-section charter, default map intersected with connected
# ---------------------------------------------------------------------------

def test_default_map_intersects_connected(tmp_path):
    # No ## MCP Routing section; only agentmemory connected
    p = _write(tmp_path, "## Goal\nA thing.\n")
    out = extract_mcp_guidance(p, "docs", ["agentmemory"])
    # agentmemory has phases: all -> should be present
    assert "agentmemory:" in out
    # Other default-map servers not connected -> absent
    assert "context7" not in out
    assert "serena" not in out
    assert "sequential-thinking" not in out
