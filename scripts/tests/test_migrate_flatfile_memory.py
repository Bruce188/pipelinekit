#!/usr/bin/env python3
"""Tests for scripts/migrate_flatfile_memory_to_agentmemory.py (F8 RED).

Discovered via `python3 -m unittest scripts/tests/test_migrate_flatfile_memory.py`.
Pure stdlib `unittest` — NO pytest, NO third-party imports.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migrate_flatfile_memory_to_agentmemory.py"
FIXTURE_ROOT = REPO_ROOT / "scripts" / "fixtures" / "memory-flatfile-sample"

FIXTURE_CONTENT = """\
---
name: feedback-subagent-first
description: "Multi-step / batched / autonomous / \\"5 at a time\\" work dispatches via Agent tool by default, not inline. Bundle parallel dispatches into a single message."
metadata:
  node_type: memory
  type: feedback
  last_seen: 2026-05-24
  confidence: 1
  originSessionId: c2fe837f-fixture-illustrative-only-no-pii
---

# Subagent-First

When work is multi-step, parallel-decomposable, or batched, dispatch via the [[Agent tool]] by default. Bundle multiple independent streams in a SINGLE assistant turn so they run concurrently. Inline is the EXCEPTION, reserved for one-shots under ~3 tool calls.

See also: [[agents-worktrees]] § Subagent Defaults.
"""

USER_FIXTURE_CONTENT = """\
---
name: user-profile
description: "User profile memory."
metadata:
  node_type: memory
  type: user
  last_seen: 2026-01-01
  confidence: 1
  originSessionId: c2fe837f-fixture-illustrative-only-no-pii
---

# User Profile

The user prefers terse responses.
"""

PROJECT_FIXTURE_CONTENT = """\
---
name: project-pipelinekit
description: "Project memory for pipelinekit."
metadata:
  node_type: memory
  type: project
  last_seen: 2026-01-01
  confidence: 1
  originSessionId: c2fe837f-fixture-illustrative-only-no-pii
---

# Project: pipelinekit

Main workflow toolkit project.
"""

REFERENCE_FIXTURE_CONTENT = """\
---
name: reference-agentmemory-api
description: "Reference memory for agentmemory API."
metadata:
  node_type: memory
  type: reference
  last_seen: 2026-01-01
  confidence: 1
  originSessionId: c2fe837f-fixture-illustrative-only-no-pii
---

# Agentmemory API Reference

See upstream README for tool signatures.
"""


def run_script(*args, env=None):
    """Run the migration script and return CompletedProcess."""
    cmd = ["python3", str(SCRIPT), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


class TestMigrationScript(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_fixture_dir(self, content=None):
        """Copy the fixture file into a temp dir and return the path."""
        d = pathlib.Path(self.tmpdir) / "mem-root"
        d.mkdir(parents=True, exist_ok=True)
        md_content = content if content is not None else FIXTURE_CONTENT
        (d / "feedback_subagent_first.md").write_text(md_content)
        return d

    def _make_fixture_with_content(self, content, filename="test_memory.md"):
        """Write a custom fixture file into a temp dir and return the dir path."""
        d = pathlib.Path(self.tmpdir) / "custom-root"
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text(content)
        return d

    # ── Test 1: dry-run default (no flags) ────────────────────────────────────
    def test_dry_run_default(self):
        d = self._make_fixture_dir()
        result = run_script("--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertRegex(combined, r"dry.run.*1 file", msg="Expected dry-run summary line")

    # ── Test 2: dry-run explicit flag ─────────────────────────────────────────
    def test_dry_run_explicit_flag(self):
        d = self._make_fixture_dir()
        result = run_script("--dry-run", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertRegex(combined, r"dry.run", msg="Expected dry-run prefix in output")

    # ── Test 3: apply flag writes log ─────────────────────────────────────────
    def test_apply_flag_writes_log(self):
        d = self._make_fixture_dir()
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        # Find the log file somewhere under d
        log_files = list(d.rglob(".migration.log"))
        self.assertTrue(len(log_files) >= 1, "Expected .migration.log to be written")
        log_text = log_files[0].read_text()
        self.assertRegex(log_text, r"(applied|apply-no-mcp-router)")

    # ── Test 4: apply emits memory_save payload on stdout ────────────────────
    def test_apply_emits_memory_save_payload_on_stdout(self):
        d = self._make_fixture_dir()
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = result.stdout.strip()
        self.assertTrue(stdout, "Expected stdout JSON line")
        # Parse the first non-empty line as JSON
        line = next((l for l in stdout.splitlines() if l.strip()), "")
        obj = json.loads(line)
        self.assertEqual(obj.get("_payload_kind"), "memory_save")
        required = {"tags", "category", "content", "ts"}
        self.assertTrue(required.issubset(obj.keys()), f"Missing keys: {required - obj.keys()}")

    # ── Test 5: dedup by content hash ─────────────────────────────────────────
    def test_dedup_by_content_hash(self):
        d = self._make_fixture_dir()
        # First apply
        result1 = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result1.returncode, 0, result1.stderr)
        # Second apply
        result2 = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result2.returncode, 0, result2.stderr)
        # Log should contain skipped-duplicate
        log_files = list(d.rglob(".migration.log"))
        self.assertTrue(len(log_files) >= 1)
        log_text = log_files[0].read_text()
        self.assertIn("skipped-duplicate", log_text)

    # ── Test 6: frontmatter parser extracts metadata.type ─────────────────────
    def test_frontmatter_parser_parses_metadata_type(self):
        d = self._make_fixture_dir()
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = result.stdout.strip()
        line = next((l for l in stdout.splitlines() if l.strip()), "")
        obj = json.loads(line)
        # The fixture has metadata.type: feedback — should be reflected in tags or category
        self.assertEqual(obj.get("category"), "feedback")

    # ── Test 7: taxonomy feedback → tags ─────────────────────────────────────
    def test_taxonomy_mapping_feedback_to_tags(self):
        d = self._make_fixture_dir()
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next((l for l in result.stdout.splitlines() if l.strip()), "")
        obj = json.loads(line)
        tags = obj.get("tags", [])
        self.assertIn("feedback", tags)
        self.assertIn("subagent-first", tags)

    # ── Test 8: taxonomy user → tags ─────────────────────────────────────────
    def test_taxonomy_mapping_user_to_tags(self):
        d = self._make_fixture_with_content(USER_FIXTURE_CONTENT, "user_profile.md")
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next((l for l in result.stdout.splitlines() if l.strip()), "")
        obj = json.loads(line)
        tags = obj.get("tags", [])
        self.assertIn("profile", tags)

    # ── Test 9: taxonomy project → tags ──────────────────────────────────────
    def test_taxonomy_mapping_project_to_tags(self):
        d = self._make_fixture_with_content(PROJECT_FIXTURE_CONTENT, "project_pipelinekit.md")
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next((l for l in result.stdout.splitlines() if l.strip()), "")
        obj = json.loads(line)
        tags = obj.get("tags", [])
        self.assertIn("project", tags)
        # Should also include a slug
        self.assertTrue(len(tags) >= 2, f"Expected slug in tags, got: {tags}")

    # ── Test 10: taxonomy reference → tags ────────────────────────────────────
    def test_taxonomy_mapping_reference_to_tags(self):
        d = self._make_fixture_with_content(REFERENCE_FIXTURE_CONTENT, "reference_agentmemory.md")
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next((l for l in result.stdout.splitlines() if l.strip()), "")
        obj = json.loads(line)
        tags = obj.get("tags", [])
        self.assertIn("reference", tags)

    # ── Test 11: body hash excludes frontmatter ───────────────────────────────
    def test_body_hash_excludes_frontmatter(self):
        # Write two fixtures with same body but different last_seen
        base_body = "\n# Body\n\nSame content here. [[link]] and [[other-link]].\n"
        content_a = "---\nname: test-a\nmetadata:\n  type: feedback\n  last_seen: 2026-01-01\n  confidence: 1\n---" + base_body
        content_b = "---\nname: test-b\nmetadata:\n  type: feedback\n  last_seen: 2026-06-01\n  confidence: 0.8\n---" + base_body

        d = pathlib.Path(self.tmpdir) / "hash-test"
        d.mkdir(parents=True, exist_ok=True)
        (d / "fixture_a.md").write_text(content_a)

        # Apply first fixture
        result1 = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result1.returncode, 0, result1.stderr)

        # Replace with fixture_b (same body, different frontmatter)
        (d / "fixture_a.md").write_text(content_b)

        # Apply again — should deduplicate because body is same
        result2 = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result2.returncode, 0, result2.stderr)

        log_files = list(d.rglob(".migration.log"))
        log_text = log_files[0].read_text() if log_files else ""
        self.assertIn("skipped-duplicate", log_text,
                      "Same body with different frontmatter should dedup")

    # ── Test 12: dry-run writes no log ────────────────────────────────────────
    def test_dry_run_writes_no_log(self):
        d = self._make_fixture_dir()
        result = run_script("--dry-run", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        log_files = list(d.rglob(".migration.log"))
        self.assertEqual(len(log_files), 0, "dry-run MUST NOT create .migration.log")

    # ── Test 13: both flags is usage error ────────────────────────────────────
    def test_both_flags_is_usage_error(self):
        d = self._make_fixture_dir()
        result = run_script("--dry-run", "--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 2, f"Expected exit 2, got {result.returncode}: {result.stderr}")

    # ── Test 14: unreadable memory root exits 2 ──────────────────────────────
    def test_unreadable_memory_root_exits_2(self):
        result = run_script("--memory-root", "/nonexistent/path/that/does/not/exist")
        self.assertEqual(result.returncode, 2, f"Expected exit 2, got {result.returncode}")

    # ── Test 15: log line shape ───────────────────────────────────────────────
    def test_log_line_shape(self):
        d = self._make_fixture_dir()
        result = run_script("--apply", "--memory-root", str(d))
        self.assertEqual(result.returncode, 0, result.stderr)
        log_files = list(d.rglob(".migration.log"))
        self.assertTrue(len(log_files) >= 1)
        log_text = log_files[0].read_text().strip()
        # Find first non-empty line
        line = next((l for l in log_text.splitlines() if l.strip()), "")
        fields = line.split("\t")
        self.assertEqual(len(fields), 4, f"Expected 4 tab-separated fields, got {len(fields)}: {line!r}")
        ts, sha, src, status = fields
        # ISO8601 UTC shape: 2026-05-26T12:00:00Z
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", f"Invalid timestamp: {ts}")
        # SHA256 hex
        self.assertRegex(sha, r"^[0-9a-f]{64}$", f"Invalid sha256: {sha}")
        # Status
        self.assertIn(status, ("applied", "apply-no-mcp-router", "skipped-duplicate"),
                      f"Unknown status: {status}")


if __name__ == "__main__":
    unittest.main()
