#!/usr/bin/env python3
"""Red-phase unit tests for claude/lib/pipeline/charter_revalidate.py.

Contract source: docs/plan-v25.md § Task 1.1 (acceptance criteria) and
docs/analysis-v24.md § 5 (drift-detection algorithm).

This file must FAIL on base `main` because
`claude/lib/pipeline/charter_revalidate.py` does not exist yet. Once the
Task 1.2 implementation lands, every assertion below MUST pass.

Run directly:
    python3 claude/lib/pipeline/tests/test_charter_revalidate.py
Or via unittest from the repo root:
    python3 -m unittest claude.lib.pipeline.tests.test_charter_revalidate

Stdlib only — pipelinekit avoids third-party deps.
"""

from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path

# Place the repo root on sys.path so `from claude.lib.pipeline import ...`
# resolves when running this file directly. From this file:
#   parents[0] = .../claude/lib/pipeline/tests
#   parents[1] = .../claude/lib/pipeline
#   parents[2] = .../claude/lib
#   parents[3] = .../claude
#   parents[4] = repo root
# But the regular-package layout under claude/lib/ uses `claude/lib/...`
# as the importable package path, so the repo root (which contains the
# `claude/` directory) needs to be on sys.path. parents[4] is the repo
# root when the file lives at claude/lib/pipeline/tests/<file>.py.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# This import is intentionally at module load time. On base `main` it must
# raise ImportError / ModuleNotFoundError, which is the red-phase signal.
from claude.lib.pipeline import charter_revalidate  # noqa: E402


def _charter(non_goals_body: str = "", mvp_boundary_body: str = "") -> str:
    """Build a minimal charter text with two H2 sections.

    Bodies are inserted verbatim between the section header and the next H2.
    Pass empty string to leave a section body empty (Case D).
    """
    return textwrap.dedent(
        f"""\
        # Charter

        ## Non-Goals

        {non_goals_body}

        ## MVP Boundary

        {mvp_boundary_body}

        ## Next Section

        unused tail
        """
    )


def _feature(header: str, description: str, constraints: str | None = None) -> str:
    """Build a single H2 feature block matching the renew/features-renewed format."""
    body = f"## {header}\n\n**Description:** {description}\n"
    if constraints is not None:
        body += f"**Constraints:** {constraints}\n"
    return body + "\n"


class TestDetectDrift(unittest.TestCase):
    """Cases A through F per docs/plan-v25.md § Task 1.1."""

    # ---- Case A — Non-Goal substring match ---------------------------------

    def test_case_a_non_goal_substring_match(self):
        """Non-Goal `- no logging changes` flags a feature about logging."""
        charter_text = _charter(non_goals_body="- no logging changes\n")
        features_text = _feature(
            "feat/structured-logging",
            "Add structured logging across worker pool",
        )

        result = charter_revalidate.detect_drift(charter_text, features_text)

        self.assertIsInstance(result, list)
        self.assertGreater(
            len(result), 0,
            "expected at least one drift entry for the logging feature against "
            "the 'no logging changes' Non-Goal",
        )
        first = result[0]
        self.assertIsInstance(first, tuple)
        # F12: detect_drift returns 4-tuples (header, reason, status, evidence).
        # The semantic invariant Case A asserts (reason mentions 'Non-Goal' +
        # 'logging') is preserved on the new shape.
        self.assertEqual(
            len(first), 4,
            "F12 contract: drift entries are (header, reason, status, evidence)",
        )
        _header, reason, _status, _evidence = first
        reason_lower = reason.lower()
        self.assertIn(
            "non-goal", reason_lower,
            "Case A: reason must mention 'Non-Goal' (case-insensitive). "
            f"got: {reason!r}",
        )
        self.assertIn(
            "logging", reason_lower,
            "Case A: reason must mention 'logging' (case-insensitive). "
            f"got: {reason!r}",
        )

    # ---- Case B — MVP Boundary `Out (deferred):` match ---------------------

    def test_case_b_mvp_boundary_out_deferred_match(self):
        """MVP `**Out (deferred):**\n- mobile app sync` flags a mobile-app feature."""
        charter_text = _charter(
            mvp_boundary_body="**Out (deferred):**\n- mobile app sync\n",
        )
        features_text = _feature(
            "feat/mobile-sync",
            "Build mobile app sync layer",
        )

        result = charter_revalidate.detect_drift(charter_text, features_text)

        self.assertGreater(
            len(result), 0,
            "expected drift entry for mobile-app feature against the MVP 'Out' list",
        )
        # F12: 4-tuples (header, reason, status, evidence) — unpack accordingly.
        _header, reason, _status, _evidence = result[0]
        # Plan Task 1.1 Case B: reason contains 'MVP Boundary' or 'Out'.
        self.assertTrue(
            ("MVP Boundary" in reason) or ("Out" in reason),
            "Case B: reason must contain 'MVP Boundary' or 'Out'. "
            f"got: {reason!r}",
        )

    # ---- Case C — Unrelated feature ----------------------------------------

    def test_case_c_unrelated_feature_no_drift(self):
        """Non-Goal `- no GUI` does NOT flag an unrelated backend cron feature."""
        charter_text = _charter(non_goals_body="- no GUI components\n")
        features_text = _feature(
            "feat/nightly-recon",
            "Backend cron job for nightly reconciliation",
        )

        result = charter_revalidate.detect_drift(charter_text, features_text)

        self.assertEqual(
            result, [],
            "Case C: unrelated feature must yield empty drift list. "
            f"got: {result!r}",
        )

    # ---- Case D — Empty constraints ----------------------------------------

    def test_case_d_empty_constraints_no_drift(self):
        """Both Non-Goals and MVP Boundary empty -> empty drift regardless of features."""
        # Body strings explicitly empty -> _charter leaves the section body blank.
        charter_text = _charter(non_goals_body="", mvp_boundary_body="")
        features_text = (
            _feature("feat/anything", "Add structured logging across worker pool")
            + _feature("feat/gui", "Build a GUI dashboard with rich animations")
            + _feature("feat/mobile", "Build mobile app sync layer")
        )

        result = charter_revalidate.detect_drift(charter_text, features_text)

        self.assertEqual(
            result, [],
            "Case D: empty Non-Goals and empty MVP Boundary must yield empty drift "
            "list even when features describe topics commonly used as Non-Goals. "
            f"got: {result!r}",
        )

    # ---- Case E — Case-insensitive match -----------------------------------

    def test_case_e_case_insensitive_match(self):
        """Non-Goal `- NO LOGGING` (uppercase) flags a feature mentioning 'add logging'."""
        charter_text = _charter(non_goals_body="- NO LOGGING\n")
        features_text = _feature(
            "feat/observability",
            "add logging",
        )

        result = charter_revalidate.detect_drift(charter_text, features_text)

        self.assertGreater(
            len(result), 0,
            "Case E: uppercase Non-Goal phrase must still match a lowercase "
            "feature description (case-insensitive comparison required)",
        )

    # ---- Case F — Token-overlap floor --------------------------------------

    def test_case_f_token_overlap_floor_rejects_short_phrase(self):
        """Non-Goal `- no` (single raw token) MUST NOT flag a feature that contains 'no'."""
        charter_text = _charter(non_goals_body="- no\n")
        features_text = _feature(
            "feat/cleanup",
            "There is no doubt this is a useful cleanup feature",
        )

        result = charter_revalidate.detect_drift(charter_text, features_text)

        self.assertEqual(
            result, [],
            "Case F: a Non-Goal phrase below the token-overlap floor (here, a "
            "single-token phrase 'no') must NOT trigger drift even though the "
            "word 'no' appears in the feature description. "
            f"got: {result!r}",
        )


class TestPublicSurface(unittest.TestCase):
    """Smoke imports for the other two public names listed in plan-v25 Task 1.2.

    These assertions are intentionally minimal — Task 1.1 only requires that
    the names exist and are callable. Detailed behavior of parse_charter_sections
    and parse_features is covered indirectly by the detect_drift cases above.
    """

    def test_parse_charter_sections_is_exported(self):
        self.assertTrue(
            hasattr(charter_revalidate, "parse_charter_sections"),
            "charter_revalidate must export parse_charter_sections",
        )
        self.assertTrue(
            callable(charter_revalidate.parse_charter_sections),
            "parse_charter_sections must be callable",
        )

    def test_parse_features_is_exported(self):
        self.assertTrue(
            hasattr(charter_revalidate, "parse_features"),
            "charter_revalidate must export parse_features",
        )
        self.assertTrue(
            callable(charter_revalidate.parse_features),
            "parse_features must be callable",
        )

    def test_detect_drift_is_exported(self):
        self.assertTrue(
            hasattr(charter_revalidate, "detect_drift"),
            "charter_revalidate must export detect_drift",
        )
        self.assertTrue(
            callable(charter_revalidate.detect_drift),
            "detect_drift must be callable",
        )


# ---------------------------------------------------------------------------
# F12 — status enum / freshness / frontmatter / legacy-shim coverage.
# Each class targets a discrete new symbol introduced by F12. The original
# Case A-F drift cases above continue to cover the substring + token-floor
# semantics; these cases pin the new public surface.
# ---------------------------------------------------------------------------


class TestStatusEnum(unittest.TestCase):
    def test_detect_drift_returns_4_tuple_with_status(self):
        charter_text = _charter(non_goals_body="- no logging changes\n")
        features_text = _feature(
            "feat/structured-logging",
            "Add structured logging across worker pool",
        )
        result = charter_revalidate.detect_drift(charter_text, features_text)
        self.assertGreater(len(result), 0)
        first = result[0]
        self.assertEqual(
            len(first), 4,
            f"detect_drift must return 4-tuple post-F12; got len={len(first)}",
        )
        _header, _reason, status, evidence = first
        self.assertIn(
            status,
            (charter_revalidate.STATUS_CURRENT,
             charter_revalidate.STATUS_DRIFTED,
             charter_revalidate.STATUS_OBSOLETE),
            f"status must be one of the enum constants; got {status!r}",
        )
        self.assertIsInstance(evidence, str)
        self.assertGreater(
            len(evidence), 0,
            "evidence field must be a non-empty string",
        )


class TestFreshness(unittest.TestCase):
    def test_is_fresh_true_for_recent_charter(self):
        # 2026-05-15 vs probe 2026-05-18 = 3 days < 7
        charter = "---\ncreated: 2026-05-15\n---\n# Charter\n"
        self.assertTrue(charter_revalidate.is_fresh(charter, "2026-05-18"))

    def test_is_fresh_false_for_old_charter(self):
        # 2026-04-01 vs probe 2026-05-18 = 47 days >= 7
        charter = "---\ncreated: 2026-04-01\n---\n# Charter\n"
        self.assertFalse(charter_revalidate.is_fresh(charter, "2026-05-18"))

    def test_is_fresh_false_when_no_frontmatter(self):
        charter = "# Charter\n\n## Goal\n\nFoo.\n"
        self.assertFalse(charter_revalidate.is_fresh(charter, "2026-05-18"))

    def test_is_fresh_respects_threshold_days_argument(self):
        # 4 days ago, threshold 3 → not fresh
        charter = "---\ncreated: 2026-05-14\n---\n# Charter\n"
        self.assertFalse(
            charter_revalidate.is_fresh(charter, "2026-05-18", threshold_days=3)
        )
        # 4 days ago, threshold 5 → fresh
        self.assertTrue(
            charter_revalidate.is_fresh(charter, "2026-05-18", threshold_days=5)
        )


class TestFrontmatterParse(unittest.TestCase):
    def test_parse_charter_frontmatter_extracts_created(self):
        charter = "---\ncreated: 2026-05-15\nstatus: draft\n---\n# Body\n"
        meta = charter_revalidate.parse_charter_frontmatter(charter)
        self.assertEqual(meta.get("created"), "2026-05-15")

    def test_parse_charter_frontmatter_empty_returns_empty_dict(self):
        charter = "# Body without frontmatter\n"
        self.assertEqual(
            charter_revalidate.parse_charter_frontmatter(charter), {}
        )


class TestLegacyShim(unittest.TestCase):
    def test_detect_drift_legacy_returns_2_tuples(self):
        charter_text = _charter(non_goals_body="- no logging changes\n")
        features_text = _feature(
            "feat/structured-logging",
            "Add structured logging across worker pool",
        )
        result = charter_revalidate.detect_drift_legacy(
            charter_text, features_text
        )
        self.assertGreater(len(result), 0)
        for entry in result:
            self.assertEqual(
                len(entry), 2,
                f"detect_drift_legacy must return 2-tuples; got len={len(entry)}",
            )


if __name__ == "__main__":
    unittest.main()
