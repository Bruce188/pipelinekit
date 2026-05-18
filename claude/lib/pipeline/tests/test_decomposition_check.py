#!/usr/bin/env python3
"""Red-phase unit tests for claude/lib/pipeline/decomposition_check.py.

Contract sources:
  - docs/plan-v46.md § Task 1.2 (11 test cases)
  - docs/prompts-v46.md § Task 1.2 + Task 1.3

This file must FAIL on base before decomposition_check.py exists.
Once Task 1.3 implementation lands, all 11 assertions MUST pass.

Run directly:
    python3 claude/lib/pipeline/tests/test_decomposition_check.py
Or via unittest from the repo root:
    python3 -m unittest claude.lib.pipeline.tests.test_decomposition_check

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
# shim in test_charter_classifier.py lines 36-42.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# This import is intentionally at module load time. On base before
# decomposition_check.py exists it must raise ImportError /
# ModuleNotFoundError — that is the red-phase signal.
from claude.lib.pipeline.decomposition_check import (  # noqa: E402
    audit_plan,
    format_ac_line,
    render_compliance_section,
    should_block,
)


class TestAuditAllPass(unittest.TestCase):
    """test_audit_all_pass — plan with every task having **Tests:** non-empty;
    phase 2 marked parallel-safe; charter absent (defaults flexible)."""

    def setUp(self):
        content = textwrap.dedent("""\
            # Plan

            ## Phase 1
            ### Task 1.1: thing one
            **Testable:** yes
            **Tests:** test_decomposition_check.py::TestAuditAllPass
            **Files:** a.py

            ## Phase 2 — parallel-safe — zero file overlap
            ### Task 2.1: thing two
            **Testable:** no
            **Files:** b.py

            ### Task 2.2: thing three
            **Testable:** no
            **Files:** c.py
        """)
        self._plan = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._plan.write(content)
        self._plan.close()

    def tearDown(self):
        os.unlink(self._plan.name)

    def test_audit_all_pass(self):
        result = audit_plan(self._plan.name)
        self.assertTrue(result["tdd_pairing"], result)
        self.assertTrue(result["parallel_marked"], result)
        self.assertTrue(result["slice_strategy"], result)


class TestAuditTddPairingFail(unittest.TestCase):
    """test_audit_tdd_pairing_fail_when_missing_tests_field — Testable: yes
    task whose **Tests:** field is N/A."""

    def setUp(self):
        content = textwrap.dedent("""\
            # Plan

            ## Phase 1
            ### Task 1.1: thing one
            **Testable:** yes
            **Tests:** N/A
            **Files:** a.py
        """)
        self._plan = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._plan.write(content)
        self._plan.close()

    def tearDown(self):
        os.unlink(self._plan.name)

    def test_audit_tdd_pairing_fail_when_missing_tests_field(self):
        result = audit_plan(self._plan.name)
        self.assertFalse(result["tdd_pairing"], result)


class TestAuditParallelMarkedFail(unittest.TestCase):
    """test_audit_parallel_marked_fail_when_shared_files_unmarked — phase 2
    with non-overlapping files but no parallel-safe marker."""

    def setUp(self):
        content = textwrap.dedent("""\
            # Plan

            ## Phase 2
            ### Task 2.1: thing two
            **Testable:** no
            **Files:** b.py

            ### Task 2.2: thing three
            **Testable:** no
            **Files:** c.py
        """)
        self._plan = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._plan.write(content)
        self._plan.close()

    def tearDown(self):
        os.unlink(self._plan.name)

    def test_audit_parallel_marked_fail_when_shared_files_unmarked(self):
        result = audit_plan(self._plan.name)
        self.assertFalse(result["parallel_marked"], result)


class TestAuditSliceStrategyFailVertical(unittest.TestCase):
    """test_audit_slice_strategy_fail_when_charter_vertical_without_touches —
    charter vertical; plan tasks lack **Touches:** lines."""

    def setUp(self):
        plan_content = textwrap.dedent("""\
            # Plan

            ## Phase 1
            ### Task 1.1: thing one
            **Testable:** no
            **Files:** a.py
        """)
        self._plan = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._plan.write(plan_content)
        self._plan.close()

        charter_content = textwrap.dedent("""\
            # Charter

            ## Slice Strategy
            vertical
        """)
        self._charter = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._charter.write(charter_content)
        self._charter.close()

    def tearDown(self):
        os.unlink(self._plan.name)
        os.unlink(self._charter.name)

    def test_audit_slice_strategy_fail_when_charter_vertical_without_touches(self):
        result = audit_plan(self._plan.name, charter_path=self._charter.name)
        self.assertFalse(result["slice_strategy"], result)


class TestAuditSliceStrategyPassFlexible(unittest.TestCase):
    """test_audit_slice_strategy_pass_when_charter_flexible_default — charter
    flexible; auto-PASS regardless of Touches:."""

    def setUp(self):
        plan_content = textwrap.dedent("""\
            # Plan

            ## Phase 1
            ### Task 1.1: thing one
            **Testable:** no
            **Files:** a.py
        """)
        self._plan = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._plan.write(plan_content)
        self._plan.close()

        charter_content = textwrap.dedent("""\
            # Charter

            ## Slice Strategy
            flexible
        """)
        self._charter = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._charter.write(charter_content)
        self._charter.close()

    def tearDown(self):
        os.unlink(self._plan.name)
        os.unlink(self._charter.name)

    def test_audit_slice_strategy_pass_when_charter_flexible_default(self):
        result = audit_plan(self._plan.name, charter_path=self._charter.name)
        self.assertTrue(result["slice_strategy"], result)


class TestAuditSliceStrategyPassCharterAbsent(unittest.TestCase):
    """test_audit_slice_strategy_pass_when_charter_absent — charter_path=None
    defaults to flexible → auto-PASS."""

    def setUp(self):
        plan_content = textwrap.dedent("""\
            # Plan

            ## Phase 1
            ### Task 1.1: thing one
            **Testable:** no
            **Files:** a.py
        """)
        self._plan = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        self._plan.write(plan_content)
        self._plan.close()

    def tearDown(self):
        os.unlink(self._plan.name)

    def test_audit_slice_strategy_pass_when_charter_absent(self):
        result = audit_plan(self._plan.name, charter_path=None)
        self.assertTrue(result["slice_strategy"], result)


class TestFormatAcLineAllPass(unittest.TestCase):
    """test_format_ac_line_all_pass."""

    def test_format_ac_line_all_pass(self):
        line = format_ac_line(
            {"tdd_pairing": True, "parallel_marked": True, "slice_strategy": True, "details": []}
        )
        self.assertEqual(
            line,
            "AC-DECOMP: TDD-pairing PASS | parallel-marked PASS | slice-strategy PASS",
        )


class TestFormatAcLineMixed(unittest.TestCase):
    """test_format_ac_line_mixed."""

    def test_format_ac_line_mixed(self):
        line = format_ac_line(
            {"tdd_pairing": True, "parallel_marked": False, "slice_strategy": True, "details": []}
        )
        self.assertEqual(
            line,
            "AC-DECOMP: TDD-pairing PASS | parallel-marked FAIL | slice-strategy PASS",
        )


class TestRenderComplianceSectionContainsMatrixTable(unittest.TestCase):
    """test_render_compliance_section_contains_matrix_table."""

    def test_render_compliance_section_contains_matrix_table(self):
        audit_result = {
            "tdd_pairing": True,
            "parallel_marked": False,
            "slice_strategy": True,
            "details": ["Phase 2 unmarked"],
        }
        section = render_compliance_section(audit_result)
        self.assertTrue(
            section.startswith("## Decomposition Compliance"),
            f"Expected section to start with '## Decomposition Compliance', got:\n{section[:80]}",
        )
        self.assertIn("| Axis |", section)
        self.assertIn("TDD pairing", section)
        self.assertIn("parallel-marked", section)
        self.assertIn("slice-strategy", section)
        self.assertIn("claude/skills/tdd/SKILL.md", section)


class TestShouldBlockDefaultFalse(unittest.TestCase):
    """test_should_block_default_false."""

    def test_should_block_default_false(self):
        self.assertFalse(should_block(env={}))


class TestShouldBlockTrueWhenEnvSet(unittest.TestCase):
    """test_should_block_true_when_env_set."""

    def test_should_block_true_when_env_set(self):
        self.assertTrue(
            should_block(env={"DECOMPOSITION_COMPLIANCE_BLOCKING": "true"})
        )


if __name__ == "__main__":
    unittest.main()
