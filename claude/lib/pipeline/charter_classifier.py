"""Charter scope classifier for review findings.

Classifies review findings against the charter Non-Goals + MVP Boundary into in_scope | out_of_scope | scope_creep tags. Advisory only — never auto-promotes blocking severity.

Public surface:
    classify_finding(finding, charter_sections)         -> str
    classify_findings(findings, charter_text)           -> list[dict]
    classifier_should_skip(progress_md_path, charter_path) -> tuple[bool, str]

DRY: charter parsing + token-overlap matching is re-imported from
`charter_revalidate` rather than redefined. Only the `**In:**` extractor is
new (NEW helper unique to this module — `_extract_in_bullets`).

Pure stdlib (`re`, `os`, `typing`); no module-level I/O.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

from claude.lib.pipeline.charter_revalidate import (
    _BULLET_LINE_RE,
    _extract_non_goal_bullets,
    _extract_out_deferred_bullets,
    _phrase_matches_blob,
    _surviving_phrases,
    _tokenize,
    parse_charter_sections,
)

__all__ = [
    "classify_finding",
    "classify_findings",
    "classifier_should_skip",
    "append_out_of_scope_to_deferred",
    "CharterScopeConflictError",
    "classify_finding_two_axis",
    "INTENT_VALUES",
    "SCOPE_VALUES",
]

# ---------------------------------------------------------------------------
# Two-axis classification constants (Task 1.1)
# ---------------------------------------------------------------------------

INTENT_VALUES: frozenset = frozenset({"correctness", "polish", "design", "unrelated"})
SCOPE_VALUES: frozenset = frozenset({"in", "out", "adjacent"})

_LEGACY_SCOPE_TAG_TO_SCOPE: Dict[str, str] = {
    "in_scope": "in",
    "out_of_scope": "out",
    "scope_creep": "adjacent",
}


def _validate_intent(value) -> str:
    """Return ``value`` if it is a canonical intent, else ``"unrelated"``.

    Case-sensitive — reviewer-emitted strings are lower-case per the
    agent-prompt schema. Non-string inputs always normalize to
    ``"unrelated"``.
    """
    if isinstance(value, str) and value in INTENT_VALUES:
        return value
    return "unrelated"


def _scope_tag_to_scope(scope_tag: str) -> str:
    """Map legacy ``scope_tag`` value to new two-axis ``scope`` value.

    ``in_scope -> "in"``, ``out_of_scope -> "out"``, ``scope_creep -> "adjacent"``.
    Unknown values fall through to ``"in"`` (default-allow, consistent with
    ``_tag_for_match`` rule 3d).
    """
    return _LEGACY_SCOPE_TAG_TO_SCOPE.get(scope_tag, "in")


# ---------------------------------------------------------------------------
# Module-level regex constants (compiled once)
# ---------------------------------------------------------------------------

# _BULLET_LINE_RE is re-imported from charter_revalidate (DRY — analysis-v25
# § 4 "Internal helpers ... re-imported"). Using the same compiled object
# ensures future edits to the bullet pattern need only happen in one place.

# `**In:**` marker introducing the MVP "In" sub-list. Case-insensitive so
# `**in:**` / `**IN:**` also match. The parallel in `charter_revalidate` is
# `_OUT_DEFERRED_RE`.
_IN_MARKER_RE = re.compile(r"\*\*In\s*:\*\*", re.IGNORECASE)

# Stop marker for bullet-list collection: any subsequent `**Foo:**` bold
# field marker terminates the current list.
_BOLD_FIELD_RE = re.compile(r"^\*\*[A-Za-z][\w\- ]*:\*\*")

# `**Charter:** <pointer>` line in progress.md. Captures the trimmed
# pointer text.
_CHARTER_POINTER_RE = re.compile(
    r"^\*\*Charter:\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_in_bullets(mvp_body: str) -> List[str]:
    """Return bullets that follow a ``**In:**`` marker in the MVP Boundary body.

    Parallels :func:`charter_revalidate._extract_out_deferred_bullets`. Bullets
    are collected until the next non-bullet, non-blank line that isn't itself
    a continuation of the list, or until another bold-field marker (e.g.
    ``**Out (deferred):**``) is encountered. Returns ``[]`` when the body
    has no ``**In:**`` marker.
    """
    marker = _IN_MARKER_RE.search(mvp_body)
    if not marker:
        return []

    tail = mvp_body[marker.end():]
    bullets: List[str] = []
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped:
            # Blank line — keep walking; markdown lists may include them.
            continue
        # Stop on a new bold field marker such as `**Out (deferred):**`.
        if _BOLD_FIELD_RE.match(stripped):
            break
        m = _BULLET_LINE_RE.match(line)
        if m:
            bullets.append(m.group(1).strip())
            continue
        # Stop on the first non-bullet content line (heading, paragraph, ...).
        break
    return bullets


def _tag_for_match(finding_severity: str, match_source: str) -> str:
    """Map (severity, match_source) -> scope_tag per analysis-v25 § 3 rules.

    ``match_source`` must be one of ``{"mvp_in", "non_goal", "mvp_out", "none"}``.

    Rules:
      - ``mvp_in`` → ``"in_scope"`` (rule 3a — short-circuit allowlist)
      - ``non_goal`` + ``severity == "blocking"`` → ``"scope_creep"`` (rule 3b)
      - ``non_goal`` + non-blocking | nit → ``"out_of_scope"`` (rule 3b)
      - ``mvp_out`` → ``"out_of_scope"`` (rule 3c — severity-agnostic)
      - ``none`` → ``"in_scope"`` (rule 3d — default-allow)
    """
    if match_source == "mvp_in":
        return "in_scope"
    if match_source == "non_goal":
        if finding_severity == "blocking":
            return "scope_creep"
        # non-blocking, nit, or any other severity falls into the
        # advisory-out-of-scope bucket.
        return "out_of_scope"
    if match_source == "mvp_out":
        return "out_of_scope"
    # match_source == "none" or any unrecognized value falls through to
    # default-allow.
    return "in_scope"


def _build_finding_blob_tokens(finding: dict) -> set:
    """Build the token-set used for charter-phrase overlap matching.

    Concatenates ``finding['text']`` plus any of the optional keys
    (``file``, ``line``, ``agent``, ``task_id``) that are present and
    non-empty. Tokenizes via ``_tokenize`` from ``charter_revalidate`` so the
    matcher behaves identically to the drift detector.
    """
    parts: List[str] = [str(finding.get("text", ""))]
    for key in ("file", "line", "agent", "task_id"):
        value = finding.get(key)
        if value:
            parts.append(str(value))
    blob = " ".join(parts)
    return set(_tokenize(blob))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_finding(finding: dict, charter_sections: dict) -> str:
    """Return one of ``"in_scope"`` | ``"out_of_scope"`` | ``"scope_creep"``.

    ``finding`` must contain at minimum ``severity`` and ``text``. Optional
    keys (``file``, ``line``, ``agent``, ``task_id``) are concatenated into
    the matching blob when present and non-empty.

    ``charter_sections`` is the dict returned by
    ``charter_revalidate.parse_charter_sections`` — keys ``non_goals`` and
    ``mvp_boundary``. Missing/empty sections are tolerated (treated as no
    constraint on that dimension).

    Decision flow (STRICT priority, short-circuit on first hit):

    1. ``**In:**`` bullets in MVP Boundary → ``"in_scope"``
    2. Non-Goal bullets → severity-aware tag (``"scope_creep"`` for
       blocking, ``"out_of_scope"`` otherwise)
    3. ``**Out (deferred):**`` bullets in MVP Boundary → ``"out_of_scope"``
    4. Default-allow → ``"in_scope"``
    """
    severity = finding.get("severity", "")
    blob_tokens = _build_finding_blob_tokens(finding)

    # Empty blob can never match anything — short-circuit to default-allow.
    if not blob_tokens:
        return _tag_for_match(severity, "none")

    non_goals_body = charter_sections.get("non_goals", "") or ""
    mvp_body = charter_sections.get("mvp_boundary", "") or ""

    # Rule 3a — `**In:**` bullets, short-circuit on hit.
    mvp_in_phrases = _surviving_phrases(_extract_in_bullets(mvp_body))
    for _normalized, phrase_tokens in mvp_in_phrases:
        if _phrase_matches_blob(phrase_tokens, blob_tokens):
            return _tag_for_match(severity, "mvp_in")

    # Rule 3b — Non-Goal bullets, severity-aware.
    non_goal_phrases = _surviving_phrases(_extract_non_goal_bullets(non_goals_body))
    for _normalized, phrase_tokens in non_goal_phrases:
        if _phrase_matches_blob(phrase_tokens, blob_tokens):
            return _tag_for_match(severity, "non_goal")

    # Rule 3c — `**Out (deferred):**` bullets, severity-agnostic.
    mvp_out_phrases = _surviving_phrases(_extract_out_deferred_bullets(mvp_body))
    for _normalized, phrase_tokens in mvp_out_phrases:
        if _phrase_matches_blob(phrase_tokens, blob_tokens):
            return _tag_for_match(severity, "mvp_out")

    # Rule 3d — default-allow.
    return _tag_for_match(severity, "none")


def classify_findings(
    findings: List[dict], charter_text: str
) -> List[dict]:
    """Decorate each finding with a ``scope_tag`` field; return a NEW list.

    Pure function — does not mutate the input dicts. Each output dict is a
    shallow copy of the corresponding input dict with one extra key
    (``scope_tag``).

    Edge cases:
      * Empty ``findings`` -> ``[]``
      * Empty/missing ``charter_text`` -> returns the input list unchanged
        (a new list, same item references; no ``scope_tag`` field added).
        The caller detects classifier-skip via
        ``'scope_tag' not in result[0]``.
    """
    if not findings:
        return []

    if not charter_text:
        # Tolerate empty charter — caller is expected to detect the skip
        # path via classifier_should_skip(). Return a NEW list to be
        # consistent with the non-empty branch's "no mutation" contract,
        # but leave each item untagged.
        return list(findings)

    sections = parse_charter_sections(charter_text)

    decorated: List[dict] = []
    for finding in findings:
        copy = dict(finding)
        copy["scope_tag"] = classify_finding(finding, sections)
        decorated.append(copy)
    return decorated


def classifier_should_skip(
    progress_md_path: str = "docs/progress.md",
    charter_path: str = "docs/charter.md",
) -> Tuple[bool, str]:
    """Inline skip-check (analysis-v25 § 6). Returns ``(skip_bool, log_line)``.

    Skip is True when ANY of:
      * ``progress_md_path`` does not exist
      * progress.md has no ``**Charter:**`` pointer line
      * pointer value literally equals ``"(none)"``
      * resolved charter file does not exist on disk

    The canonical log token is
    ``"CHARTER_ABSENT_CLASSIFIER_SKIPPED: <reason>"``. When skip is False the
    second element is the empty string.

    ``charter_path`` is the fallback used only when the progress.md pointer
    is absent or empty (it is NOT consulted when the pointer parses cleanly;
    the pointer takes precedence so the per-pipeline charter wiring stays
    authoritative).
    """
    if not os.path.exists(progress_md_path):
        return (True, "CHARTER_ABSENT_CLASSIFIER_SKIPPED: progress.md not found")

    try:
        with open(progress_md_path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        # Treat a read failure the same as missing — the gate prefers
        # graceful degradation over an exception.
        return (True, "CHARTER_ABSENT_CLASSIFIER_SKIPPED: progress.md not found")

    match = _CHARTER_POINTER_RE.search(content)
    if not match:
        return (
            True,
            "CHARTER_ABSENT_CLASSIFIER_SKIPPED: no charter pointer in progress.md",
        )

    pointer = match.group(1).strip()
    if pointer == "(none)":
        return (
            True,
            "CHARTER_ABSENT_CLASSIFIER_SKIPPED: charter pointer is (none)",
        )

    if not pointer:
        # `**Charter:**` line exists but the value is empty — treat as
        # "no pointer" for the purpose of the skip gate.
        return (
            True,
            "CHARTER_ABSENT_CLASSIFIER_SKIPPED: no charter pointer in progress.md",
        )

    # Resolve the pointer relative to the current working directory when not
    # absolute. This mirrors how every caller site in pipelinekit accesses
    # charter and progress files — both `docs/progress.md` and
    # `docs/charter.md` are CWD-relative paths from the repo root. Resolving
    # against progress.md's parent directory would produce
    # `<repo>/docs/docs/charter.md` for the canonical `**Charter:** docs/charter.md`
    # pointer format, which is always wrong.
    if os.path.isabs(pointer):
        resolved = pointer
    else:
        resolved = os.path.abspath(pointer)

    if not os.path.exists(resolved):
        return (
            True,
            f"CHARTER_ABSENT_CLASSIFIER_SKIPPED: charter pointer references missing file: {resolved}",
        )

    return (False, "")


# Heading marker for the Deferred section. Case-sensitive per analysis-v25 § 8
# spec; a line that *starts* with this token anchors the section.
_DEFERRED_HEADING = "## Deferred"

# 4-column table header + separator emitted when the Deferred section is absent.
_DEFERRED_TABLE_HEADER = "| Item | Source | Reason | Target Iteration |"
_DEFERRED_TABLE_SEPARATOR = "|------|--------|--------|-----------------|"

# Max width for the Item column. Longer text is truncated with a single U+2026
# ellipsis char (analysis-v25 § 8 — keeps the row width predictable).
_ITEM_MAX_LEN = 80
_ELLIPSIS = "…"


def append_out_of_scope_to_deferred(
    progress_md_path: str,
    findings: List[dict],
    review_file_name: str,
) -> int:
    """Append one Deferred-table row per out_of_scope finding.

    Returns the number of rows appended (0 when no out_of_scope findings
    or all candidates are already present). Idempotent on (Item, Source).
    Creates ``## Deferred`` section + table header when absent.

    Item column: ``finding['text']`` truncated to 80 chars with an ellipsis
    char (U+2026) if longer. Source: ``review_file_name``. Reason:
    ``f"out-of-scope of charter ({review_file_name.removesuffix('.md')})"``.
    Target Iteration: ``"Next"``.
    """
    # Step 1 — filter to out_of_scope findings. Empty -> no-op, no file touch.
    out_of_scope = [
        f for f in findings if f.get("scope_tag") == "out_of_scope"
    ]
    if not out_of_scope:
        return 0

    # Step 2 — read file body. Caller is expected to have created progress.md
    # before invoking us; an OSError here is a legitimate failure to surface.
    with open(progress_md_path, "r", encoding="utf-8") as handle:
        body = handle.read()

    # Step 3 — ensure the `## Deferred` section + table header exist. The
    # heading test is a line-start substring check so we are robust to
    # trailing whitespace and to the heading appearing mid-document.
    has_heading = any(
        line.startswith(_DEFERRED_HEADING) for line in body.splitlines()
    )
    if not has_heading:
        # Build the new section. Leading blank line ensures one-empty-line
        # separation from any prior content; we add it only when the existing
        # body does not already end with "\n\n" or is non-empty without a
        # trailing newline.
        prefix = ""
        if body and not body.endswith("\n"):
            prefix += "\n"
        if not body.endswith("\n\n"):
            prefix += "\n"
        section = (
            prefix
            + _DEFERRED_HEADING
            + "\n\n"
            + _DEFERRED_TABLE_HEADER
            + "\n"
            + _DEFERRED_TABLE_SEPARATOR
            + "\n"
        )
        body = body + section

    # Step 4 — build candidate rows and filter for idempotency.
    source = review_file_name
    reason = f"out-of-scope of charter ({review_file_name.removesuffix('.md')})"
    target = "Next"

    existing_lines = body.splitlines()
    new_rows: List[str] = []
    for finding in out_of_scope:
        text = str(finding.get("text", "")).strip()
        # Escape pipe characters BEFORE truncation so internal `|` chars do
        # not create extra columns in the markdown table. This matches the
        # standard markdown escape convention (`\|`). The replacement is
        # applied first so truncation measures the post-escape length
        # accurately — the few extra `\` characters are part of the stored
        # cell value and must be within the 80-char budget.
        text = text.replace("|", "\\|")
        if len(text) <= _ITEM_MAX_LEN:
            item = text
        else:
            item = text[:_ITEM_MAX_LEN] + _ELLIPSIS

        # Idempotency: skip when any existing line already contains BOTH the
        # Item value AND the Source value as substrings. Matches the
        # analysis-v25 § 8 "line-presence check before appending" semantics.
        already_present = any(
            (item in line and source in line) for line in existing_lines
        )
        if already_present:
            continue

        row = f"| {item} | {source} | {reason} | {target} |"
        new_rows.append(row)
        # Track the freshly-appended row so a duplicate finding within the
        # same call also dedupes (two findings with identical text → one row).
        existing_lines.append(row)

    if not new_rows:
        # All candidates already present. We may have added the section
        # header above, but only when no heading existed. The contract for
        # this case (case 3 of test_deferred_append.sh) is "no edit when no
        # out_of_scope findings" — which we honored at Step 1. With
        # idempotent skips here, the safe path is to NOT write back when
        # nothing new was added, preserving byte-equality.
        return 0

    # Step 5 — append rows and write back.
    if not body.endswith("\n"):
        body += "\n"
    body += "\n".join(new_rows) + "\n"

    with open(progress_md_path, "w", encoding="utf-8") as handle:
        handle.write(body)

    return len(new_rows)
