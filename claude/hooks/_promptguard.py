#!/usr/bin/env python3
"""Advisory prompt-injection scanner for tool output.

`scan(text: str) -> list[Finding]` returns a list of `Finding(pattern, position,
severity)` for each match in the catalogue below. v1 is advisory-only — every
finding carries `severity="warn"`. Hard-block lands in a follow-up feature once
the false-positive rate is empirically known.

Pattern catalogue (case-insensitive unless noted):
    <system> / </system>            -- XML-shape system-message injection
    IGNORE PREVIOUS INSTRUCTIONS    -- canonical jailbreak phrase
    DISREGARD ABOVE                 -- ditto, second canonical form
    New instructions:               -- preface for instruction-override attempt
    You are now                     -- role-reassignment preface
    Assistant: / Human:             -- role-impersonation prefixes, column 0 only
    <|im_start|> / <|im_end|>       -- ChatML role markers

Performance budget: < 50 ms per scan for inputs up to 1 MB (asserted in tests).

Strategy. Profiling shows three regimes:
    (1) `str.find` on lowercased text is the fastest path (sub-ms per
        needle for 1 MB inputs) — used for fixed literals.
    (2) Individual single-pattern `re.finditer` calls (each ~1 ms for 1 MB)
        beat a combined alternation regex (~165 ms) because Python's regex
        engine cannot share prefix optimization across alternatives.
    (3) Column-0 anchoring via `^` + `re.MULTILINE` is ~13 ms per pattern.
        A newline-walk + `str.startswith` pre-screen drops that to sub-ms.

So `scan` runs:
    - lowercase the text once
    - `str.find` loop for each literal needle
    - individual `re.finditer` for whitespace-flexible literals
    - newline-walk for column-0 role prefixes

Pure stdlib — `re`, `dataclasses`, `typing` only. No third-party imports per
`claude/hooks/CLAUDE.md` python-stdlib mandate.

Allowlist (docs-source/ corpus, scanned during test development):
    None. Zero hits across all markdown files in docs-source/ at feature
    landing. The doctrine page that documents this scanner
    (docs-source/governance.md) describes the catalogue behaviorally
    rather than enumerating the literal pattern strings -- the
    source-of-truth catalogue lives below in this file. Readers who need
    the exact strings consult _LITERAL_PATTERNS / _FLEX_PATTERNS /
    _ROLE_PREFIXES.
    If a future doctrine doc legitimately needs one of these strings in
    plain text (for instance, a security/prompt-injection case study),
    append it here as
    `<relative-path>:<line> -- <pattern> -- <reason>` and bump
    `claude/hooks/tests/test_promptguard.py::TestDocsSourceCorpus.THRESHOLD`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Finding:
    """One prompt-injection pattern hit in scanned text."""

    pattern: str
    position: int
    severity: str  # "warn" only in v1


# Fixed-literal patterns: (lowercase_needle, display_name). Scanned via
# `str.find` on the lowercased text.
_LITERAL_PATTERNS: Final[list[tuple[str, str]]] = [
    ("<system>", "<system>"),
    ("</system>", "</system>"),
    ("<|im_start|>", "<|im_start|>"),
    ("<|im_end|>", "<|im_end|>"),
]

# Whitespace-flexible patterns: individual single-pattern regexes. Each is
# scanned with its own `finditer` — combining them into one alternation
# regresses perf by ~20x due to Python regex engine internals.
_FLEX_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"ignore\s+previous\s+instructions"), "IGNORE PREVIOUS INSTRUCTIONS"),
    (re.compile(r"disregard\s+above"), "DISREGARD ABOVE"),
    (re.compile(r"new\s+instructions\s*:"), "New instructions:"),
    (re.compile(r"you\s+are\s+now"), "You are now"),
]

# Role prefixes — column 0 only. Walked via newline + `str.startswith` rather
# than MULTILINE regex (~30x faster). Each entry is (lowercase_prefix,
# display_name); the runtime extra colon-and-whitespace tolerance is handled
# inline.
_ROLE_PREFIXES: Final[list[tuple[str, str]]] = [
    ("assistant", "Assistant:"),
    ("human", "Human:"),
]


def _role_prefix_finds(lower: str) -> list[Finding]:
    """Return findings for `Assistant:` / `Human:` anchored at column 0."""
    out: list[Finding] = []
    # Line-start positions: column 0 of the text itself + every char after
    # a newline.
    line_starts = [0]
    nl_pos = lower.find("\n")
    while nl_pos >= 0:
        line_starts.append(nl_pos + 1)
        nl_pos = lower.find("\n", nl_pos + 1)
    for ls in line_starts:
        for prefix, display in _ROLE_PREFIXES:
            plen = len(prefix)
            if not lower.startswith(prefix, ls):
                continue
            # Look for an optional whitespace run then ':' immediately after.
            j = ls + plen
            while j < len(lower) and lower[j] in (" ", "\t"):
                j += 1
            if j < len(lower) and lower[j] == ":":
                out.append(Finding(pattern=display, position=ls, severity="warn"))
    return out


def scan(text: str) -> list[Finding]:
    """Return every catalogue match in `text` as a `Finding`.

    Empty / non-matching input returns `[]`. Severity is always `"warn"` in v1.

    Positions are reported against the *original* text. Lowercasing is
    purely an internal acceleration; ASCII case-folding preserves character
    offsets one-to-one so the recorded position matches what a human reader
    would see in the un-lowercased payload.
    """
    if not text:
        return []
    lower = text.lower()
    findings: list[Finding] = []
    # Pass 1 — fixed literals via str.find (fastest).
    for needle, display in _LITERAL_PATTERNS:
        start = 0
        while True:
            i = lower.find(needle, start)
            if i < 0:
                break
            findings.append(Finding(pattern=display, position=i, severity="warn"))
            start = i + 1  # allow overlapping matches (defensive)
    # Pass 2 — whitespace-flexible patterns via individual finditer calls.
    for rx, display in _FLEX_PATTERNS:
        for m in rx.finditer(lower):
            findings.append(Finding(pattern=display, position=m.start(), severity="warn"))
    # Pass 3 — role prefixes via newline walk + startswith.
    findings.extend(_role_prefix_finds(lower))
    return findings


__all__ = ["Finding", "scan"]
