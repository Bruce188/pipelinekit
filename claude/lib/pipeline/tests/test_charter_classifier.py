#!/usr/bin/env python3
"""Red-phase unit tests for claude/lib/pipeline/charter_classifier.py.

Contract sources:
  - docs/plan-v26.md § Task 1.1 (acceptance criteria + ten canonical cases)
  - docs/analysis-v25.md § 3 (algorithm), § 4 (public API), § 6 (skip-gate),
    § 7 (the ten canonical test cases)

This file must FAIL on base `main` because
`claude/lib/pipeline/charter_classifier.py` does not exist yet. Once the
Task 1.2 implementation lands, every assertion below MUST pass.

Run directly:
    python3 claude/lib/pipeline/tests/test_charter_classifier.py
Or via unittest from the repo root:
    python3 -m unittest claude.lib.pipeline.tests.test_charter_classifier

Stdlib only — pipelinekit avoids third-party deps.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Place the repo root on sys.path so `from claude.lib.pipeline import ...`
# resolves when running this file directly. From this file:
#   parents[0] = .../claude/lib/pipeline/tests
#   parents[1] = .../claude/lib/pipeline
#   parents[2] = .../claude/lib
#   parents[3] = .../claude
#   parents[4] = repo root (contains the `claude/` directory)
# The repo-root parent is the importable-package anchor. Mirrors the
# shim in test_charter_revalidate.py.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# This import is intentionally at module load time. On base `main` it must
# raise ImportError / ModuleNotFoundError, which is the red-phase signal.
from claude.lib.pipeline import charter_classifier  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers (analysis-v25 § 7 — `_charter()` and `_finding()` shape).
# ---------------------------------------------------------------------------


def _charter(
    non_goals: str = "",
    mvp_in: str = "",
    mvp_out: str = "",
) -> str:
    """Build a minimal charter text with Non-Goals + MVP Boundary sections.

    `non_goals` is dropped verbatim into the `## Non-Goals` body.
    `mvp_in` populates a `**In:**` block inside `## MVP Boundary`.
    `mvp_out` populates a `**Out (deferred):**` block inside `## MVP Boundary`.
    Pass empty strings to leave the corresponding section/sub-section empty.
    """
    mvp_body_parts: list[str] = []
    if mvp_in:
        mvp_body_parts.append("**In:**\n" + mvp_in)
    if mvp_out:
        mvp_body_parts.append("**Out (deferred):**\n" + mvp_out)
    mvp_body = "\n\n".join(mvp_body_parts)

    return textwrap.dedent(
        f"""\
        # Charter

        ## Non-Goals

        {non_goals}

        ## MVP Boundary

        {mvp_body}

        ## Next Section

        unused tail
        """
    )


def _finding(severity: str, text: str, **kw: str) -> dict:
    """Build a single finding dict with at minimum severity and text.

    Optional keys (`file`, `line`, `agent`, `task_id`) flow through `**kw`.
    """
    d: dict = {"severity": severity, "text": text}
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# Smoke import — asserts the public API surface exists and is callable.
# ---------------------------------------------------------------------------


class TestModuleSurface(unittest.TestCase):
    """Smoke imports for the three public names listed in plan-v26 Task 1.1.

    These assertions are intentionally minimal — Task 1.1 only requires that
    the names exist and are callable. Detailed behavior is covered by the
    ten cases below.
    """

    def test_classify_finding_is_callable(self):
        self.assertTrue(
            hasattr(charter_classifier, "classify_finding"),
            "charter_classifier must export classify_finding",
        )
        self.assertTrue(
            callable(charter_classifier.classify_finding),
            "classify_finding must be callable",
        )

    def test_classify_findings_is_callable(self):
        self.assertTrue(
            hasattr(charter_classifier, "classify_findings"),
            "charter_classifier must export classify_findings",
        )
        self.assertTrue(
            callable(charter_classifier.classify_findings),
            "classify_findings must be callable",
        )

    def test_classifier_should_skip_is_callable(self):
        self.assertTrue(
            hasattr(charter_classifier, "classifier_should_skip"),
            "charter_classifier must export classifier_should_skip",
        )
        self.assertTrue(
            callable(charter_classifier.classifier_should_skip),
            "classifier_should_skip must be callable",
        )


# ---------------------------------------------------------------------------
# Behavioral cases — the ten canonical scenarios from analysis-v25 § 7.
# ---------------------------------------------------------------------------


class TestCharterClassifier(unittest.TestCase):
    """Cases 1-10 per docs/analysis-v25.md § 7 / docs/plan-v26.md § Task 1.1."""

    # ---- Case 1 — In-scope match via MVP In bullets (rule 3a) -------------

    def test_in_scope_match_via_mvp_in_bullets(self):
        """`**In:**\n- auth flow improvements` short-circuits finding about auth."""
        charter_text = _charter(
            mvp_in="- auth flow improvements\n",
        )
        finding = _finding("non-blocking", "auth flow returns 500 on empty token")

        result = charter_classifier.classify_findings([finding], charter_text)

        self.assertEqual(len(result), 1, "classify_findings must preserve list length")
        self.assertIn(
            "scope_tag", result[0],
            "decorated finding must carry a scope_tag field",
        )
        self.assertEqual(
            result[0]["scope_tag"], "in_scope",
            "Case 1: MVP In match must short-circuit to 'in_scope' (rule 3a)",
        )

    # ---- Case 2 — Non-Goal + non-blocking -> out_of_scope (rule 3b) -------

    def test_out_of_scope_via_non_goal_with_non_blocking_severity(self):
        """Non-Goal `- no logging changes` flags non-blocking logging finding."""
        charter_text = _charter(non_goals="- no logging changes\n")
        finding = _finding("non-blocking", "logging adds latency")

        result = charter_classifier.classify_findings([finding], charter_text)

        self.assertEqual(
            result[0].get("scope_tag"), "out_of_scope",
            "Case 2: non-blocking Non-Goal match must tag 'out_of_scope' (rule 3b)",
        )

    # ---- Case 3 — Non-Goal + blocking -> scope_creep (rule 3b) ------------

    def test_scope_creep_via_non_goal_with_blocking_severity(self):
        """Non-Goal `- no logging changes` plus blocking severity -> scope_creep."""
        charter_text = _charter(non_goals="- no logging changes\n")
        finding = _finding("blocking", "logging leaks PII to stdout")

        result = charter_classifier.classify_findings([finding], charter_text)

        self.assertEqual(
            result[0].get("scope_tag"), "scope_creep",
            "Case 3: blocking Non-Goal match must tag 'scope_creep' (rule 3b)",
        )

    # ---- Case 4 — MVP Out (deferred) match -> out_of_scope (rule 3c) ------

    def test_out_of_scope_via_mvp_out_deferred_bullets(self):
        """`**Out (deferred):**\n- mobile app sync` tags blocking mobile finding."""
        charter_text = _charter(
            mvp_out="- mobile app sync\n",
        )
        finding = _finding("blocking", "mobile sync race")

        result = charter_classifier.classify_findings([finding], charter_text)

        self.assertEqual(
            result[0].get("scope_tag"), "out_of_scope",
            "Case 4: MVP Out (deferred) match is severity-agnostic — must "
            "tag 'out_of_scope' even for blocking severity (rule 3c)",
        )

    # ---- Case 5 — Default-allow for unmatched finding (rule 3d) -----------

    def test_default_allow_for_unmatched_finding(self):
        """Non-Goal `- no logging` does NOT flag an unrelated SQL-injection finding."""
        charter_text = _charter(non_goals="- no logging\n")
        finding = _finding("blocking", "sql injection in user input")

        result = charter_classifier.classify_findings([finding], charter_text)

        self.assertEqual(
            result[0].get("scope_tag"), "in_scope",
            "Case 5: unmatched finding must default to 'in_scope' (rule 3d). "
            "Default-allow prevents classifier-induced false positives.",
        )

    # ---- Case 6 — Severity 'nit' is still classified (rule 3b nit branch) -

    def test_severity_nit_is_still_classified(self):
        """`severity: nit` against Non-Goal still tags as out_of_scope."""
        charter_text = _charter(non_goals="- no logging changes\n")
        finding = _finding("nit", "logging variable named foo")

        result = charter_classifier.classify_findings([finding], charter_text)

        self.assertEqual(
            result[0].get("scope_tag"), "out_of_scope",
            "Case 6: nit severity is treated as non-blocking-equivalent for "
            "Non-Goal matches — must tag 'out_of_scope' (rule 3b nit branch)",
        )

    # ---- Case 7 — Empty findings list -------------------------------------

    def test_empty_findings_returns_empty_list(self):
        """`classify_findings([], 'any charter')` returns `[]` without raising."""
        result = charter_classifier.classify_findings([], "any charter text")

        self.assertEqual(
            result, [],
            "Case 7: empty findings input must return empty list, not None and not raise",
        )

    # ---- Case 8 — Missing charter returns findings unchanged --------------

    def test_missing_charter_returns_findings_unchanged(self):
        """`classify_findings([f], '')` returns input unchanged, no scope_tag added."""
        finding = _finding("blocking", "any text")

        result = charter_classifier.classify_findings([finding], "")

        # Length preserved.
        self.assertEqual(
            len(result), 1,
            "Case 8: empty charter must return the input list with the same length",
        )
        # No scope_tag decoration — caller is expected to detect skip via
        # classifier_should_skip() separately.
        self.assertNotIn(
            "scope_tag", result[0],
            "Case 8: empty charter must NOT add scope_tag — the function "
            "tolerates an empty charter without decorating. The caller uses "
            "classifier_should_skip() to detect the skip path.",
        )

    # ---- Case 9 — Skip condition: no progress.md --------------------------

    def test_skip_condition_no_progress_md(self):
        """progress.md path that does not exist returns (True, <log_line>)."""
        skip, log = charter_classifier.classifier_should_skip(
            progress_md_path="/nonexistent/progress.md",
        )

        self.assertTrue(
            skip,
            "Case 9: missing progress.md must return skip=True",
        )
        self.assertEqual(
            log,
            "CHARTER_ABSENT_CLASSIFIER_SKIPPED: progress.md not found",
            "Case 9: log_line must be exactly the canonical missing-progress.md "
            f"string; got {log!r}",
        )

    # ---- Case 10 — Skip condition: pointer literally (none) ---------------

    def test_skip_condition_pointer_is_none_literal(self):
        """A progress.md whose **Charter:** pointer literally equals `(none)` skips."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False,
        )
        try:
            tmp.write("**Charter:** (none)\n")
            tmp.close()
            # Register cleanup before any assertion fires so even an
            # assertion failure unlinks the temp file.
            self.addCleanup(os.unlink, tmp.name)

            skip, log = charter_classifier.classifier_should_skip(
                progress_md_path=tmp.name,
            )

            self.assertTrue(
                skip,
                "Case 10: '(none)' charter pointer must return skip=True",
            )
            self.assertEqual(
                log,
                "CHARTER_ABSENT_CLASSIFIER_SKIPPED: charter pointer is (none)",
                "Case 10: log_line must be exactly the canonical '(none)' "
                f"string; got {log!r}",
            )
        except Exception:
            # If NamedTemporaryFile.close() / write() succeeded but the
            # call under test raised before addCleanup ran, ensure cleanup.
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            raise


class TestClassifierShouldSkipCWDResolution(unittest.TestCase):
    """Review-v23 regression tests: relative pointer resolves against CWD, not
    progress.md's parent directory (B1 fix)."""

    def setUp(self):
        # Track all directories/files created so tearDown can clean up even
        # when an assertion fires mid-test.
        self._to_remove: list[str] = []
        self._original_cwd = os.getcwd()

    def tearDown(self):
        # Always restore the original CWD first so subsequent tests are not
        # affected.
        os.chdir(self._original_cwd)
        for path in reversed(self._to_remove):
            try:
                if os.path.isdir(path):
                    import shutil
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass

    def _make_tmp(self) -> str:
        tmp = tempfile.mkdtemp()
        self._to_remove.append(tmp)
        return tmp

    def test_skip_condition_relative_pointer_resolves_against_cwd(self):
        """B1 regression: `**Charter:** charter.md` with adjacent file; skip=False."""
        tmp = self._make_tmp()
        # Write progress.md with a CWD-relative pointer (no `docs/` prefix).
        progress = os.path.join(tmp, "progress.md")
        with open(progress, "w") as f:
            f.write("**Charter:** charter.md\n")
        # Place the charter at `<tmp>/charter.md` — i.e. accessible as
        # `charter.md` when CWD is `<tmp>`.
        charter = os.path.join(tmp, "charter.md")
        with open(charter, "w") as f:
            f.write("# Charter\n")

        os.chdir(tmp)
        skip, log = charter_classifier.classifier_should_skip(
            progress_md_path="progress.md",
        )

        self.assertFalse(
            skip,
            "B1: relative pointer 'charter.md' with CWD containing charter.md "
            f"must return skip=False; got skip={skip!r}, log={log!r}",
        )
        self.assertEqual(log, "", f"Expected empty log; got {log!r}")

    def test_skip_condition_docs_relative_pointer_resolves_against_cwd(self):
        """B1 regression: `**Charter:** docs/charter.md` resolves from CWD."""
        tmp = self._make_tmp()
        # progress.md lives at <tmp>/docs/progress.md (real pipelinekit layout).
        docs_dir = os.path.join(tmp, "docs")
        os.makedirs(docs_dir)
        progress = os.path.join(docs_dir, "progress.md")
        with open(progress, "w") as f:
            f.write("**Charter:** docs/charter.md\n")
        # charter.md lives at <tmp>/docs/charter.md, addressable as
        # 'docs/charter.md' when CWD is <tmp>.
        charter = os.path.join(docs_dir, "charter.md")
        with open(charter, "w") as f:
            f.write("# Charter\n")

        os.chdir(tmp)
        skip, log = charter_classifier.classifier_should_skip(
            progress_md_path="docs/progress.md",
        )

        self.assertFalse(
            skip,
            "B1: pointer 'docs/charter.md' with CWD containing docs/charter.md "
            f"must return skip=False; got skip={skip!r}, log={log!r}",
        )
        self.assertEqual(log, "", f"Expected empty log; got {log!r}")


class TestBulletLineRegexDRY(unittest.TestCase):
    """N1 regression: _BULLET_LINE_RE is imported from charter_revalidate, not
    duplicated. Verifies the DRY contract from plan-v26 Task 1.2 and review-v23
    N1."""

    def test_bullet_line_regex_matches_revalidate_source(self):
        """N1: _BULLET_LINE_RE imported from charter_revalidate (pattern equality)."""
        from claude.lib.pipeline.charter_revalidate import (
            _BULLET_LINE_RE as REV_RE,
        )
        from claude.lib.pipeline.charter_classifier import (
            _BULLET_LINE_RE as CLS_RE,
        )
        self.assertEqual(
            REV_RE.pattern,
            CLS_RE.pattern,
            "N1: _BULLET_LINE_RE in charter_classifier must have the same pattern "
            "as charter_revalidate._BULLET_LINE_RE. If they differ, the DRY fix was "
            "not applied — the local definition should be removed in favour of an "
            "explicit import.",
        )


if __name__ == "__main__":
    unittest.main()
