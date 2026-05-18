"""Charter re-validation helpers for `/pipeline --renew`.

Public surface (all importable):
    parse_charter_sections(charter_text) -> dict[str, str]
    parse_features(features_text)        -> list[dict]
    detect_drift(charter_text, features_text) -> list[tuple[str, str, str, str]]
    detect_drift_legacy(charter_text, features_text) -> list[tuple[str, str]]
    parse_charter_frontmatter(charter_text) -> dict[str, str]
    is_fresh(charter_text, today_iso, threshold_days=7) -> bool
    write_drift_report(drift_entries, docs_dir) -> pathlib.Path
    probe_narrative(section_body) -> list[tuple[str, str, str]]
    probe_success(section_body, repo_root) -> list[tuple[str, str, str]]
    probe_constraints(section_body, repo_root) -> list[tuple[str, str, str]]
    probe_prior_art(section_body, repo_root) -> list[tuple[str, str, str]]
    STATUS_CURRENT / STATUS_DRIFTED / STATUS_OBSOLETE — status enum constants

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

F12 extension: ``detect_drift`` now returns 4-tuples
``(header, reason, status, evidence)`` with status in the enum
{STATUS_CURRENT, STATUS_DRIFTED, STATUS_OBSOLETE}. Legacy 2-tuple
consumers use ``detect_drift_legacy`` (shim). New helpers cover charter
frontmatter parsing, 7-day freshness skip, per-section probes, and a
drift-report writer that emits ``docs/charter-drift.md`` (versioned).

LLM fallback gated by `PIPELINE_CHARTER_LLM_CHECK` is deferred — v1 is deterministic-only.

Pure stdlib (`re`, `pathlib`, `datetime`, `typing`); no module-level I/O.
Read-only probe surface: no network, no charter writes — the single
filesystem write is ``write_drift_report`` → ``docs/charter-drift*.md``.
"""

from __future__ import annotations

import datetime
import pathlib
import re
from typing import Dict, List, Tuple

__all__ = [
    "parse_charter_sections",
    "parse_features",
    "detect_drift",
    "detect_drift_legacy",
    "parse_charter_frontmatter",
    "is_fresh",
    "write_drift_report",
    "probe_narrative",
    "probe_success",
    "probe_constraints",
    "probe_prior_art",
    "STATUS_CURRENT",
    "STATUS_DRIFTED",
    "STATUS_OBSOLETE",
]


# ---------------------------------------------------------------------------
# Status enum (F12)
# ---------------------------------------------------------------------------
#
# 3-valued status carried by every drift entry:
#   STATUS_CURRENT  — fact still holds in the repo.
#   STATUS_DRIFTED  — fact partially holds (file exists, claim inaccurate).
#   STATUS_OBSOLETE — the referenced entity no longer exists at all.

STATUS_CURRENT = "current"
STATUS_DRIFTED = "drifted"
STATUS_OBSOLETE = "obsolete"


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
    """Return the ``Non-Goals``, ``MVP Boundary``, and ``Deployment target`` bodies.

    Body is the verbatim slice between the matching ``## <title>`` H2 header
    and the next ``## `` H2 header (or EOF). A missing section yields an
    empty string for that key. Leading/trailing whitespace inside the body
    is preserved so downstream bullet extraction sees the original layout.

    F14 — ``deployment_target`` is the body of the ``## Deployment target``
    H2 section (charter Topic 10). Consumed by
    :func:`charter_classifier.classify_finding_two_axis` to demote findings
    that name a deployment provider OTHER than the charter target.
    """
    sections: Dict[str, str] = {
        "non_goals": "",
        "mvp_boundary": "",
        "deployment_target": "",
    }
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
        elif title == "deployment target":
            sections["deployment_target"] = body

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
) -> List[Tuple[str, str, str, str]]:
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
       ``(header, "matches Non-Goal: '<phrase>'", STATUS_DRIFTED, evidence)``
       and skip remaining Non-Goal phrases for that feature.
    6. Otherwise, for each surviving MVP-Out phrase whose token set
       overlaps the feature blob: emit
       ``(header, "described as 'Out' in MVP Boundary: '<phrase>'",
       STATUS_DRIFTED, evidence)``.

    F12 extension: each emitted tuple is now a 4-tuple
    ``(feature_header, drift_reason, status, evidence)`` where status is
    one of :data:`STATUS_CURRENT` / :data:`STATUS_DRIFTED` /
    :data:`STATUS_OBSOLETE` and ``evidence`` is a free-form non-empty
    string explaining why the entry was flagged. Legacy 2-tuple
    consumers should use :func:`detect_drift_legacy`.

    No I/O. No third-party dependencies. Reproducible per analysis-v24.md
    § 5 step 4.
    """
    drift: List[Tuple[str, str, str, str]] = []
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
                        STATUS_DRIFTED,
                        f"feature blob token-overlaps Non-Goal phrase "
                        f"'{normalized_phrase}'",
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
                        STATUS_DRIFTED,
                        f"feature blob token-overlaps 'Out (deferred)' phrase "
                        f"'{normalized_phrase}'",
                    )
                )
                break

    return drift


def detect_drift_legacy(
    charter_text: str, features_text: str
) -> List[Tuple[str, str]]:
    """Backward-compat wrapper that strips the status + evidence fields.

    Returns the original 2-tuple ``(header, reason)`` shape so any consumer
    that has not yet migrated to the 4-tuple return shape keeps working.
    New code should prefer :func:`detect_drift`.
    """
    return [
        (header, reason)
        for (header, reason, _status, _evidence) in detect_drift(
            charter_text, features_text
        )
    ]


# ---------------------------------------------------------------------------
# Charter frontmatter + freshness (F12)
# ---------------------------------------------------------------------------

# Matches the first fenced YAML-ish frontmatter block at the very top of the
# charter text: a leading line of exactly `---`, body lines, and a closing
# `---` line. The body capture is greedy-up-to-the-first-`---` via a
# non-greedy quantifier; the `^---` anchors at the very start of the text.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)",
    re.DOTALL,
)

# Matches a `key: value` line inside the frontmatter body. Keys are word-like
# (letters / digits / underscores / dashes); values capture the rest of the
# line. Whitespace around the colon is permitted.
_FRONTMATTER_KV_RE = re.compile(
    r"^[ \t]*([A-Za-z][A-Za-z0-9_\-]*)[ \t]*:[ \t]*(.*?)[ \t]*$",
    re.MULTILINE,
)


def parse_charter_frontmatter(charter_text: str) -> Dict[str, str]:
    """Extract YAML-like frontmatter delimited by two ``---`` fences.

    Returns ``{}`` when no fenced frontmatter is present at the top of
    ``charter_text``. Keys / values are plain strings (no type coercion);
    values are stripped of surrounding whitespace. Quoted values are not
    unwrapped — callers that need typed access can post-process.
    """
    if not charter_text:
        return {}
    match = _FRONTMATTER_RE.match(charter_text)
    if not match:
        return {}
    body = match.group(1)
    result: Dict[str, str] = {}
    for kv in _FRONTMATTER_KV_RE.finditer(body):
        key = kv.group(1).strip()
        value = kv.group(2).strip()
        if key:
            result[key] = value
    return result


def is_fresh(
    charter_text: str,
    today_iso: str,
    threshold_days: int = 7,
) -> bool:
    """Return True when the charter's ``created:`` field is < threshold_days
    before ``today_iso``.

    Both arguments are ISO-format date strings (``YYYY-MM-DD``). Returns
    ``False`` when frontmatter is absent, ``created:`` is missing, the date
    fails to parse, or the delta is >= ``threshold_days``. A negative delta
    (charter dated in the future) also returns ``False`` — treat anomalous
    dates as not-fresh so the re-validation pass still runs.
    """
    meta = parse_charter_frontmatter(charter_text)
    created_raw = meta.get("created")
    if not created_raw:
        return False
    try:
        created = datetime.date.fromisoformat(created_raw)
        today = datetime.date.fromisoformat(today_iso)
    except (ValueError, TypeError):
        return False
    delta_days = (today - created).days
    if delta_days < 0:
        return False
    return delta_days < threshold_days


# ---------------------------------------------------------------------------
# Per-section probes (F12)
# ---------------------------------------------------------------------------

# Filename-like token regex. Captures e.g. ``orchestrate.sh``,
# ``claude/lib/pipeline/foo.py``, ``pyproject.toml``. Used by the Success +
# Constraints + Prior Art probes to find filesystem references inside bullets.
_FILENAME_TOKEN_RE = re.compile(
    r"\b([\w./\-]+\.(?:sh|py|md|json|yaml|yml|toml|txt|cfg|ini|js|ts))\b"
)

# Package-manager / language-version marker filenames the Constraints probe
# treats as an "exists" signal for library mentions. Order is stable for
# deterministic evidence strings.
_PKG_MANAGER_MARKERS: Tuple[str, ...] = (
    "pyproject.toml",
    "requirements.txt",
    ".python-version",
    "package.json",
    "Cargo.toml",
    "go.mod",
)


def _bullet_lines(section_body: str) -> List[str]:
    """Return every top-level bullet line in a section body (raw text)."""
    return [m.group(1).strip() for m in _BULLET_LINE_RE.finditer(section_body)]


def probe_narrative(section_body: str) -> List[Tuple[str, str, str]]:
    """Narrative-only probe: every bullet resolves to ``STATUS_CURRENT``.

    Returns ``[(bullet_text, STATUS_CURRENT, evidence), ...]``. When the
    section has no bullets, emits a single synthetic entry referencing the
    section header itself so callers can still tally a row in the drift
    report (status remains ``current``).
    """
    bullets = _bullet_lines(section_body)
    evidence = "narrative section, no fact probes"
    if not bullets:
        return [("(section body)", STATUS_CURRENT, evidence)]
    return [(bullet, STATUS_CURRENT, evidence) for bullet in bullets]


def probe_success(
    section_body: str, repo_root: pathlib.Path
) -> List[Tuple[str, str, str]]:
    """Probe a ``## Success`` section against the working tree.

    For each bullet:
      - If it mentions a filename pattern (``foo.sh``, ``path/bar.py``):
        check existence under ``repo_root``. File present →
        ``STATUS_CURRENT`` with evidence noting the file path. File
        absent → ``STATUS_OBSOLETE``.
      - Bullets without a filename token → ``STATUS_CURRENT`` with
        evidence ``"no file reference; narrative claim"``.

    Pure read-only: ``pathlib.Path.exists`` + regex extraction. No Glob
    walks beyond direct path existence — keeps the probe O(bullets).
    """
    results: List[Tuple[str, str, str]] = []
    for bullet in _bullet_lines(section_body):
        filename_match = _FILENAME_TOKEN_RE.search(bullet)
        if not filename_match:
            results.append((bullet, STATUS_CURRENT,
                            "no file reference; narrative claim"))
            continue
        rel = filename_match.group(1)
        target = repo_root / rel
        if target.exists():
            results.append((bullet, STATUS_CURRENT,
                            f"file exists at {rel}"))
        else:
            results.append((bullet, STATUS_OBSOLETE,
                            f"file `{rel}` absent under repo root"))
    return results


def probe_constraints(
    section_body: str, repo_root: pathlib.Path
) -> List[Tuple[str, str, str]]:
    """Probe a ``## Constraints`` section.

    Per analysis § 3.c:
      - Filename mentions → existence probe (file present →
        ``STATUS_CURRENT``; absent → ``STATUS_OBSOLETE``).
      - Library / language mentions are recognised by the presence of a
        known package-manager marker file in the repo (``pyproject.toml``,
        ``package.json``, ``.python-version``, etc.). When the bullet
        matches a known library pattern and **no** marker file exists,
        emit ``STATUS_OBSOLETE`` with evidence pointing at the missing
        marker. When a marker exists, emit ``STATUS_CURRENT``.
      - Pure-narrative bullets → ``STATUS_CURRENT``.
    """
    library_re = re.compile(
        r"\b(?:python|node|nodejs|npm|yarn|rust|cargo|go(?:lang)?)\b",
        re.IGNORECASE,
    )
    results: List[Tuple[str, str, str]] = []
    for bullet in _bullet_lines(section_body):
        filename_match = _FILENAME_TOKEN_RE.search(bullet)
        if filename_match:
            rel = filename_match.group(1)
            target = repo_root / rel
            if target.exists():
                results.append((bullet, STATUS_CURRENT,
                                f"file exists at {rel}"))
            else:
                results.append((bullet, STATUS_OBSOLETE,
                                f"file `{rel}` absent under repo root"))
            continue
        if library_re.search(bullet):
            present_markers = [
                m for m in _PKG_MANAGER_MARKERS if (repo_root / m).exists()
            ]
            if present_markers:
                results.append((bullet, STATUS_CURRENT,
                                f"package-manager marker present: "
                                f"{present_markers[0]}"))
            else:
                results.append((bullet, STATUS_OBSOLETE,
                                "no package-manager marker found "
                                "(pyproject.toml / package.json / etc.)"))
            continue
        results.append((bullet, STATUS_CURRENT,
                        "narrative constraint, no fact probe"))
    return results


def probe_prior_art(
    section_body: str, repo_root: pathlib.Path
) -> List[Tuple[str, str, str]]:
    """Probe a ``## Prior Art`` section.

    Heuristic:
      - Bullets containing a URL-ish token (``http://`` / ``https://``)
        are treated as external references → ``STATUS_CURRENT`` with
        evidence ``"external ref, no probe"``.
      - Bullets containing an internal-path token (any path with ``/``
        and an extension) → check existence under ``repo_root``.
        Present → ``STATUS_CURRENT``. Absent → ``STATUS_OBSOLETE``.
      - Other bullets → ``STATUS_CURRENT`` (narrative).
    """
    url_re = re.compile(r"https?://")
    internal_path_re = re.compile(r"\b([\w\-./]+/[\w\-./]+\.\w+)\b")
    results: List[Tuple[str, str, str]] = []
    for bullet in _bullet_lines(section_body):
        if url_re.search(bullet):
            results.append((bullet, STATUS_CURRENT,
                            "external ref, no probe"))
            continue
        path_match = internal_path_re.search(bullet)
        if path_match:
            rel = path_match.group(1)
            target = repo_root / rel
            if target.exists():
                results.append((bullet, STATUS_CURRENT,
                                f"internal path exists at {rel}"))
            else:
                results.append((bullet, STATUS_OBSOLETE,
                                f"internal path `{rel}` absent"))
            continue
        results.append((bullet, STATUS_CURRENT,
                        "narrative prior-art reference"))
    return results


# ---------------------------------------------------------------------------
# Drift report writer (F12)
# ---------------------------------------------------------------------------

# Match a charter-section hint inside a drift_reason string. The detector
# emits two canonical phrasings:
#   "matches Non-Goal: '<phrase>'"
#   "described as 'Out' in MVP Boundary: '<phrase>'"
# This regex pulls out the section name for the artifact's `section` column.
_REASON_SECTION_RE = re.compile(
    r"(Non-Goal|MVP Boundary|Success|Constraints|Prior Art|Goal|Users|Problem|Open Questions|Decision Log)",
    re.IGNORECASE,
)


def _section_from_reason(reason: str) -> str:
    """Best-effort: pull the charter section name out of a drift_reason."""
    if not reason:
        return "(unknown)"
    match = _REASON_SECTION_RE.search(reason)
    if not match:
        return "(unknown)"
    label = match.group(1)
    # Canonicalise capitalisation for the artifact.
    canon = {
        "non-goal": "Non-Goals",
        "mvp boundary": "MVP Boundary",
        "success": "Success",
        "constraints": "Constraints",
        "prior art": "Prior Art",
        "goal": "Goal",
        "users": "Users",
        "problem": "Problem",
        "open questions": "Open Questions",
        "decision log": "Decision Log",
    }
    return canon.get(label.lower(), label)


def _resolve_drift_report_path(docs_dir: pathlib.Path) -> pathlib.Path:
    """Pick the next drift-report path per the Versioning Convention.

    If ``charter-drift.md`` is absent, return that path. Otherwise return
    ``charter-drift-vN.md`` where N is one higher than the highest
    existing version, or 2 if no versioned files exist yet (current
    unversioned file consumes slot v1 conceptually but is not renamed
    here — the writer leaves the existing file alone).
    """
    base = docs_dir / "charter-drift.md"
    if not base.exists():
        return base
    highest = 1
    for path in docs_dir.glob("charter-drift-v*.md"):
        stem = path.stem  # e.g. "charter-drift-v3"
        match = re.match(r"^charter-drift-v(\d+)$", stem)
        if match:
            try:
                n = int(match.group(1))
            except ValueError:
                continue
            if n > highest:
                highest = n
    return docs_dir / f"charter-drift-v{highest + 1}.md"


def write_drift_report(
    drift_entries: List[Tuple[str, str, str, str]],
    docs_dir: pathlib.Path,
) -> pathlib.Path:
    """Write a markdown drift report to ``docs_dir`` and return the path.

    Table columns: ``section | line | status | evidence``. Section is
    derived from the drift_reason text (``_section_from_reason``). The
    ``line`` column carries the feature header (lower-cased,
    whitespace-collapsed). When ``drift_entries`` is empty the writer
    still emits a header + empty-table marker so the artifact's presence
    is unambiguous.

    Follows the Versioning Convention: first write lands as
    ``charter-drift.md``; subsequent writes land as
    ``charter-drift-vN.md`` (N = highest existing version + 1, starting
    at 2). The writer never modifies the charter or any other file —
    only the resolved drift-report path.
    """
    docs_dir = pathlib.Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = _resolve_drift_report_path(docs_dir)

    lines: List[str] = []
    lines.append("# Charter drift report")
    lines.append("")
    lines.append("Generated by `claude/lib/pipeline/charter_revalidate.py` "
                 "`write_drift_report`.")
    lines.append("")
    lines.append("| section | line | status | evidence |")
    lines.append("|---------|------|--------|----------|")
    if not drift_entries:
        lines.append("| (none) | (no drift detected) | current | empty report |")
    else:
        for entry in drift_entries:
            if len(entry) != 4:
                # Defensive: skip malformed rows rather than raise.
                continue
            header, reason, status, evidence = entry
            section = _section_from_reason(reason)
            line_text = _normalize_phrase(header)
            # Replace pipe characters inside the cells so the table parses.
            cells = [
                section.replace("|", "\\|"),
                line_text.replace("|", "\\|"),
                str(status).replace("|", "\\|"),
                str(evidence).replace("|", "\\|"),
            ]
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target
