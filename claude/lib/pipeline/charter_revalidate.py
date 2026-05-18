"""Charter re-validation helpers for `/pipeline --renew`.

Public surface (all importable):
    parse_charter_sections(charter_text) -> dict[str, str]
    parse_features(features_text)        -> list[dict]
    detect_drift(charter_text, features_text) -> list[tuple[str, str]]

The drift detector is the deterministic prefilter described in
docs/analysis-v24.md § 5 step 1-2: extract Non-Goal bullets from the
charter's `## Non-Goals` section and `**Out (deferred):**` bullets from
the `## MVP Boundary` section, normalize, and flag any feature whose
Description + Constraints blob shares at least one token with a
multi-token phrase. The exact token-floor is **>= 2** so that two-token
Non-Goals (e.g. ``NO LOGGING``) participate in matching, while single
tokens (e.g. ``no``) are rejected as too noisy. This implements the
red-phase contract bound by
``claude/lib/pipeline/tests/test_charter_revalidate.py``.

LLM fallback gated by `PIPELINE_CHARTER_LLM_CHECK` is deferred — v1 is deterministic-only.

Pure stdlib (`re`, `typing`); no module-level I/O.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

__all__ = [
    "parse_charter_sections",
    "parse_features",
    "detect_drift",
]


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

# Match an H2 section header line. Captures the trimmed title text.
# Leading whitespace is tolerated so that markdown blocks indented for
# layout (or quoted into f-strings without uniform dedent) still parse.
_H2_HEADER_RE = re.compile(r"^[ \t]*##[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# Word-like tokens for token-overlap comparison. Keeps ASCII + unicode word
# chars (underscores included — harmless for the drift use case).
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Token-overlap floor (see module docstring). Two-token phrases participate;
# single-token phrases are rejected as too noisy.
_TOKEN_FLOOR = 2


def parse_charter_sections(charter_text: str) -> Dict[str, str]:
    """Return the ``Non-Goals`` and ``MVP Boundary`` section bodies.

    Body is the verbatim slice between the matching ``## <title>`` H2 header
    and the next ``## `` H2 header (or EOF). A missing section yields an
    empty string for that key. Leading/trailing whitespace inside the body
    is preserved so downstream bullet extraction sees the original layout.
    """
    sections: Dict[str, str] = {"non_goals": "", "mvp_boundary": ""}
    if not charter_text:
        return sections

    # Collect (title_lower, body_start, body_end) tuples for every H2 found.
    headers = list(_H2_HEADER_RE.finditer(charter_text))
    if not headers:
        return sections

    for idx, match in enumerate(headers):
        title = match.group(1).strip().lower()
        body_start = match.end()
        # Body terminates at the next H2 header, or EOF.
        if idx + 1 < len(headers):
            body_end = headers[idx + 1].start()
        else:
            body_end = len(charter_text)
        body = charter_text[body_start:body_end]
        # Drop the single newline that immediately follows the header line
        # so the body starts at the first content line. Preserve everything
        # else verbatim.
        if body.startswith("\n"):
            body = body[1:]

        if title == "non-goals":
            sections["non_goals"] = body
        elif title == "mvp boundary":
            sections["mvp_boundary"] = body

    return sections


# ---------------------------------------------------------------------------
# Feature parsing
# ---------------------------------------------------------------------------

# H2 feature header: `## type/name`. We accept any non-empty title.
_FEATURE_HEADER_RE = re.compile(r"^[ \t]*##[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _extract_field(body: str, label: str) -> str:
    r"""Extract ``**label:**`` value from a feature body.

    Captures everything after the label up to the next ``**Foo:**`` field or
    EOF. Returns the trimmed body, or empty string when the field is absent.
    """
    # The label may appear at the start of any line. Capture the rest of that
    # line plus any following lines until we hit another `**Word:**` field or
    # the end of the body.
    pattern = re.compile(
        r"^\*\*" + re.escape(label) + r":\*\*[ \t]*(.*?)(?=^\*\*[A-Za-z][\w\- ]*:\*\*|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return ""
    return match.group(1).strip()


def parse_features(features_text: str) -> List[Dict[str, str]]:
    """Parse a renew/features-renewed style document into feature dicts.

    Each H2 header (``## <type>/<name>``) begins a new feature block. We
    extract ``**Description:**`` and ``**Constraints:**`` line bodies. The
    constraints field defaults to the empty string when absent.
    """
    results: List[Dict[str, str]] = []
    if not features_text:
        return results

    headers = list(_FEATURE_HEADER_RE.finditer(features_text))
    for idx, match in enumerate(headers):
        title = match.group(1).strip()
        body_start = match.end()
        if idx + 1 < len(headers):
            body_end = headers[idx + 1].start()
        else:
            body_end = len(features_text)
        body = features_text[body_start:body_end]

        description = _extract_field(body, "Description")
        constraints = _extract_field(body, "Constraints")

        results.append(
            {
                "header": f"## {title}",
                "description": description,
                "constraints": constraints,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

# Bullet line in a markdown list: ``- `` or ``* `` prefix.
_BULLET_LINE_RE = re.compile(r"^[ \t]*[-*][ \t]+(.+?)[ \t]*$", re.MULTILINE)

# `**Out (deferred):**` marker introducing the MVP "Out" sub-list.
_OUT_DEFERRED_RE = re.compile(r"\*\*Out\s*\(deferred\)\s*:\*\*", re.IGNORECASE)


def _tokenize(text: str) -> List[str]:
    """Lower-case word-token tokenizer."""
    return _WORD_RE.findall(text.lower())


def _normalize_phrase(raw: str) -> str:
    """Lower-case + collapse whitespace for display in drift reasons."""
    return re.sub(r"\s+", " ", raw.strip().lower())


def _extract_non_goal_bullets(body: str) -> List[str]:
    """Return every top-level bullet line in the Non-Goals body (raw text)."""
    return [m.group(1).strip() for m in _BULLET_LINE_RE.finditer(body)]


def _extract_out_deferred_bullets(body: str) -> List[str]:
    """Return bullets that follow a `**Out (deferred):**` marker in the body.

    Bullets are collected until the next non-bullet, non-blank line that
    isn't itself a continuation of the list, or until another bold-field
    marker (e.g. `**In:**`) is encountered.
    """
    marker = _OUT_DEFERRED_RE.search(body)
    if not marker:
        return []

    tail = body[marker.end():]
    bullets: List[str] = []
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped:
            # Blank line — keep walking; markdown lists may include them.
            continue
        # Stop on a new bold field marker such as `**In:**` or `**Next:**`.
        if re.match(r"^\*\*[A-Za-z][\w\- ]*:\*\*", stripped):
            break
        m = _BULLET_LINE_RE.match(line)
        if m:
            bullets.append(m.group(1).strip())
            continue
        # Stop on the first non-bullet content line (heading, paragraph, ...).
        break
    return bullets


def _surviving_phrases(raw_phrases: List[str]) -> List[Tuple[str, List[str]]]:
    """Filter phrases that meet the token-floor (>= 2 tokens).

    Returns ``[(normalized_phrase, token_list), ...]`` for use by the
    matcher. The normalized phrase preserves the original bullet text for
    display in drift reasons (single-spaced, lower-cased).
    """
    survivors: List[Tuple[str, List[str]]] = []
    for raw in raw_phrases:
        normalized = _normalize_phrase(raw)
        if not normalized:
            continue
        tokens = _tokenize(normalized)
        if len(tokens) < _TOKEN_FLOOR:
            continue
        survivors.append((normalized, tokens))
    return survivors


def _phrase_matches_blob(phrase_tokens: List[str], blob_tokens: set) -> bool:
    """Return True when any phrase token appears as a token in the blob.

    This is the token-overlap matcher described in
    docs/analysis-v24.md § 5 step 1 ("substring or token-overlap match
    against the feature's Description + Constraints"). Single-token
    overlap is sufficient — the token-floor on the phrase side prevents
    trivial single-word Non-Goals from creating noise.
    """
    for token in phrase_tokens:
        if token in blob_tokens:
            return True
    return False


def detect_drift(
    charter_text: str, features_text: str
) -> List[Tuple[str, str]]:
    """Return drift entries for every feature outside the charter scope.

    Algorithm (deterministic, v1):

    1. Parse charter sections via :func:`parse_charter_sections`.
    2. Extract Non-Goal bullets (lines beginning ``- `` or ``* `` in the
       Non-Goals body) and ``**Out (deferred):**`` bullets in the MVP
       Boundary body.
    3. Normalize each phrase (lower-case, whitespace-collapsed) and reject
       phrases with fewer than ``_TOKEN_FLOOR`` tokens.
    4. For each feature, build a normalized blob from
       ``description + " " + constraints`` and tokenize it.
    5. For each surviving Non-Goal phrase whose token set overlaps the
       feature blob: emit
       ``(header, "matches Non-Goal: '<phrase>'")`` and skip remaining
       Non-Goal phrases for that feature.
    6. Otherwise, for each surviving MVP-Out phrase whose token set
       overlaps the feature blob: emit
       ``(header, "described as 'Out' in MVP Boundary: '<phrase>'")``.

    No I/O. No third-party dependencies. Reproducible per analysis-v24.md
    § 5 step 4.
    """
    drift: List[Tuple[str, str]] = []
    if not charter_text or not features_text:
        return drift

    sections = parse_charter_sections(charter_text)
    non_goal_bullets = _extract_non_goal_bullets(sections["non_goals"])
    mvp_out_bullets = _extract_out_deferred_bullets(sections["mvp_boundary"])

    non_goal_phrases = _surviving_phrases(non_goal_bullets)
    mvp_out_phrases = _surviving_phrases(mvp_out_bullets)

    if not non_goal_phrases and not mvp_out_phrases:
        return drift

    features = parse_features(features_text)
    for feature in features:
        blob_text = f"{feature['description']} {feature['constraints']}"
        blob_tokens = set(_tokenize(blob_text))
        if not blob_tokens:
            continue

        matched = False
        for normalized_phrase, phrase_tokens in non_goal_phrases:
            if _phrase_matches_blob(phrase_tokens, blob_tokens):
                drift.append(
                    (
                        feature["header"],
                        f"matches Non-Goal: '{normalized_phrase}'",
                    )
                )
                matched = True
                break

        if matched:
            continue

        for normalized_phrase, phrase_tokens in mvp_out_phrases:
            if _phrase_matches_blob(phrase_tokens, blob_tokens):
                drift.append(
                    (
                        feature["header"],
                        f"described as 'Out' in MVP Boundary: '{normalized_phrase}'",
                    )
                )
                break

    return drift
