#!/usr/bin/env python3
"""Red-phase unit tests for claude/lib/pipeline/charter_extractor.py.

Contract source: docs/plan-v27.md § Task 1.1 (acceptance criteria) and
docs/analysis-v26.md § 7 (field-mapping table).

This file must FAIL on base `main` because
`claude/lib/pipeline/charter_extractor.py` does not exist yet. Once the
Task 1.2 implementation lands, every assertion below MUST pass.

Run directly:
    python3 claude/lib/pipeline/tests/test_charter_extractor.py
Or via unittest from the repo root:
    python3 -m unittest claude.lib.pipeline.tests.test_charter_extractor

Stdlib only — pipelinekit avoids third-party deps.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Place the repo root on sys.path so `from claude.lib.pipeline import ...`
# resolves when running this file directly. From this file:
#   parents[0] = .../claude/lib/pipeline/tests
#   parents[1] = .../claude/lib/pipeline
#   parents[2] = .../claude/lib
#   parents[3] = .../claude
#   parents[4] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# This import is intentionally at module load time. On base `main` it must
# raise ImportError / ModuleNotFoundError, which is the red-phase signal.
from claude.lib.pipeline import charter_extractor  # noqa: E402


class TestModuleSurface(unittest.TestCase):
    """Smoke-import test: verify the four public callables exist."""

    def test_extract_draft_charter_callable(self):
        self.assertTrue(callable(charter_extractor.extract_draft_charter))

    def test_discover_artifact_paths_callable(self):
        self.assertTrue(callable(charter_extractor.discover_artifact_paths))

    def test_should_auto_extract_callable(self):
        self.assertTrue(callable(charter_extractor.should_auto_extract))

    def test_render_charter_markdown_callable(self):
        self.assertTrue(callable(charter_extractor.render_charter_markdown))


class TestExtractDraftCharter(unittest.TestCase):
    """Behavioral tests for extract_draft_charter field-mapping logic."""

    def _load_fixture(self, name: str) -> str:
        fixture_path = Path(__file__).parent / "fixtures" / name
        return fixture_path.read_text(encoding="utf-8")

    def test_extract_goal_from_numbered_objective_header(self):
        """analysis_full.md has '## 1. Objective'; goal should be first paragraph."""
        analysis_text = self._load_fixture("analysis_full.md")
        draft = charter_extractor.extract_draft_charter(analysis_text=analysis_text)
        self.assertIn("auto-extract", draft["goal"].lower())
        # The first paragraph should not include section headers
        self.assertNotIn("##", draft["goal"])
        # Must be non-empty
        self.assertTrue(draft["goal"].strip())

    def test_extract_goal_from_unnumbered_objective_header(self):
        """analysis_minimal.md has '## Objective' (no numeric prefix)."""
        analysis_text = self._load_fixture("analysis_minimal.md")
        draft = charter_extractor.extract_draft_charter(analysis_text=analysis_text)
        self.assertIn("auto-extract", draft["goal"].lower())
        self.assertTrue(draft["goal"].strip())

    def test_extract_non_goals_and_constraints_from_avoid_preserve_bullets(self):
        """analysis_full.md Constraints section has **AVOID:** and **PRESERVE:** bullets."""
        analysis_text = self._load_fixture("analysis_full.md")
        draft = charter_extractor.extract_draft_charter(analysis_text=analysis_text)
        # non_goals comes from AVOID bullets
        self.assertIsInstance(draft["non_goals"], list)
        self.assertTrue(len(draft["non_goals"]) >= 1)
        # First AVOID bullet mentions overwriting
        combined_non_goals = " ".join(draft["non_goals"]).lower()
        self.assertIn("overwriting", combined_non_goals)
        # constraints comes from PRESERVE bullets
        self.assertIsInstance(draft["constraints"], list)
        self.assertTrue(len(draft["constraints"]) >= 1)
        combined_constraints = " ".join(draft["constraints"]).lower()
        self.assertIn("skip-condition", combined_constraints)

    def test_extract_users_from_prp_when_present(self):
        """PRP ## Users section should be extracted when prp_text is provided."""
        analysis_text = self._load_fixture("analysis_minimal.md")
        prp_text = self._load_fixture("prp_sample.md")
        draft = charter_extractor.extract_draft_charter(
            analysis_text=analysis_text, prp_text=prp_text
        )
        self.assertIn("solo developer", draft["users"].lower())

    def test_extract_mvp_boundary_from_plan_in_out_bullets(self):
        """plan_full.md has ## MVP Boundary with **In:** and **Out (deferred):** sub-lists."""
        analysis_text = self._load_fixture("analysis_full.md")
        plan_text = self._load_fixture("plan_full.md")
        draft = charter_extractor.extract_draft_charter(
            analysis_text=analysis_text, plan_text=plan_text
        )
        self.assertIn("**In:**", draft["mvp_boundary"])
        self.assertIn("**Out (deferred):**", draft["mvp_boundary"])

    def test_extract_prior_art_from_analysis_section(self):
        """analysis_full.md has ## Prior Art section."""
        analysis_text = self._load_fixture("analysis_full.md")
        draft = charter_extractor.extract_draft_charter(analysis_text=analysis_text)
        self.assertIn("charter_revalidate", draft["prior_art"])

    def test_unmapped_sections_render_as_empty(self):
        """analysis_minimal.md has no Constraints or Prior Art — should yield empty."""
        analysis_text = self._load_fixture("analysis_minimal.md")
        draft = charter_extractor.extract_draft_charter(analysis_text=analysis_text)
        self.assertEqual(draft["non_goals"], [])
        self.assertEqual(draft["constraints"], [])
        self.assertEqual(draft["prior_art"], "")

    def test_should_auto_extract_returns_true_when_analysis_and_plan_present_and_no_charter(self):
        """should_auto_extract returns (True, '') when analysis+plan exist but no charter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            os.makedirs(docs_dir)
            # Create analysis and plan files
            open(os.path.join(docs_dir, "analysis-v3.md"), "w").close()
            open(os.path.join(docs_dir, "plan-v3.md"), "w").close()
            # No charter.md
            result = charter_extractor.should_auto_extract(docs_dir=docs_dir)
            self.assertEqual(result, (True, ""))

    def test_should_auto_extract_returns_false_when_charter_exists(self):
        """should_auto_extract returns (False, reason) when docs/charter.md exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            os.makedirs(docs_dir)
            open(os.path.join(docs_dir, "analysis-v3.md"), "w").close()
            open(os.path.join(docs_dir, "plan-v3.md"), "w").close()
            open(os.path.join(docs_dir, "charter.md"), "w").close()
            result = charter_extractor.should_auto_extract(docs_dir=docs_dir)
            self.assertFalse(result[0])
            self.assertIn("CHARTER_AUTO_EXTRACT_SKIPPED", result[1])
            self.assertIn("already exists", result[1])

    def test_should_auto_extract_returns_false_when_no_prior_artifacts(self):
        """should_auto_extract returns (False, reason) when no analysis or plan exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            os.makedirs(docs_dir)
            # Empty docs dir — no analysis, no plan, no charter
            result = charter_extractor.should_auto_extract(docs_dir=docs_dir)
            self.assertFalse(result[0])
            self.assertIn("CHARTER_AUTO_EXTRACT_SKIPPED", result[1])
            self.assertIn("no prior analysis or plan", result[1])


class TestRenderCharterMarkdown(unittest.TestCase):
    """Behavioral tests for render_charter_markdown output structure."""

    def _empty_draft(self):
        return {
            "goal": "",
            "users": "",
            "problem": "",
            "success": "",
            "non_goals": [],
            "constraints": [],
            "mvp_boundary": "",
            "prior_art": "",
            "open_questions": "",
        }

    def test_render_includes_all_nine_sections_and_decision_log(self):
        """Empty draft must still have all 9 section headers + Decision Log."""
        draft = self._empty_draft()
        output = charter_extractor.render_charter_markdown(draft)
        expected_headers = [
            "## Goal",
            "## Users",
            "## Problem",
            "## Success",
            "## Non-Goals",
            "## Constraints",
            "## MVP Boundary",
            "## Prior Art",
            "## Open Questions",
            "## Decision Log",
        ]
        for header in expected_headers:
            self.assertIn(header, output, f"Missing section header: {header}")

    def test_render_frontmatter_status_is_draft(self):
        """Frontmatter must contain 'status: draft'."""
        draft = self._empty_draft()
        output = charter_extractor.render_charter_markdown(draft)
        self.assertIn("status: draft", output)

    def test_render_empty_fields_render_blank_body(self):
        """For each empty field, the line after the section header must be blank (not placeholder text)."""
        draft = self._empty_draft()
        output = charter_extractor.render_charter_markdown(draft)
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("## ") and line != "## Decision Log":
                # Check the next non-blank-causing line: it should be blank or another ##
                # Per plan-v27: empty fields render the header followed by ONE blank line.
                # The next non-empty-if-skipped content should be another ## header, not placeholder
                remaining = lines[i + 1:]
                # The next non-empty line should be another ## header (or end of file)
                for next_line in remaining:
                    if next_line.strip():
                        self.assertTrue(
                            next_line.startswith("## ") or "|" in next_line,
                            f"After empty section '{line}', unexpected content: '{next_line}'"
                        )
                        break

    def test_render_today_default_is_today_iso(self):
        """Passing today='2026-05-18' must put that date in the created: frontmatter field."""
        draft = self._empty_draft()
        output = charter_extractor.render_charter_markdown(draft, today="2026-05-18")
        self.assertIn("created: 2026-05-18", output)


class TestShouldAutoExtractOrSemantics(unittest.TestCase):
    """Verify OR semantics: should_auto_extract returns True with only analysis present."""

    def test_should_auto_extract_returns_true_with_only_analysis(self):
        """should_auto_extract returns (True, '') when only analysis exists (no plan), no charter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            os.makedirs(docs_dir)
            open(os.path.join(docs_dir, "analysis-v1.md"), "w").close()
            # No plan, no charter
            result = charter_extractor.should_auto_extract(docs_dir=docs_dir)
            self.assertEqual(result, (True, ""),
                             "OR semantics: analysis alone (no plan) should trigger auto-extract")


class TestH1Truncation(unittest.TestCase):
    """Verify H1 truncation is word-aware (textwrap.shorten)."""

    def test_h1_truncation_is_word_aware(self):
        """A goal longer than 80 chars must truncate with '...' or '…' (textwrap.shorten), not mid-word."""
        # This goal is > 80 chars and the 80-char hard-cut lands mid-word: "...artifacts w"
        long_goal = "Enable /pipeline to auto-extract a draft charter from prior workflow artifacts when analysis and plan exist"
        self.assertGreater(len(long_goal), 80)
        draft = {
            "goal": long_goal,
            "users": "", "problem": "", "success": "",
            "non_goals": [], "constraints": [],
            "mvp_boundary": "", "prior_art": "", "open_questions": "",
        }
        output = charter_extractor.render_charter_markdown(draft)
        # Find the H1 line
        h1_line = next(line for line in output.splitlines() if line.startswith("# Charter"))
        title = h1_line[len("# Charter — "):]
        self.assertLessEqual(len(title), 80)
        # textwrap.shorten places the placeholder ('…' or '...') at the end;
        # a raw [:80] slice produces a title ending mid-word without any placeholder.
        # Assert the title ends with '…' or '[...]' (not a raw alphabetic mid-word cut).
        self.assertTrue(
            title.endswith("…") or title.endswith("...") or not title[-1:].isalpha(),
            f"H1 truncation cut mid-word without ellipsis: '{title}'"
        )


if __name__ == "__main__":
    unittest.main()
