#!/usr/bin/env python3
"""
RED-phase unit tests for build_catalog_data.py and the two catalog-grid snippets.

These tests MUST fail before Task 1.2 is implemented (no build script, no snippets).
All 5 tests turn GREEN after Task 1.2 completes.
"""
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
BUILD_SCRIPT = REPO_ROOT / "claude" / "skills" / "docs-writer" / "build_catalog_data.py"
SNIPPETS_DIR = REPO_ROOT / "claude" / "skills" / "docs-writer" / "snippets"
SKILL_SNIPPET = SNIPPETS_DIR / "skill-catalog-grid.html"
AGENT_SNIPPET = SNIPPETS_DIR / "agent-catalog-grid.html"


def _parse_frontmatter(path: pathlib.Path) -> dict | None:
    """Minimal frontmatter parser — used to count live agents without PyYAML dependency."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None
    result: dict = {}
    for line in lines[1:end]:
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def _live_skill_count() -> int:
    """Count SKILL.md files under claude/skills/*/SKILL.md."""
    return len(glob.glob(str(REPO_ROOT / "claude" / "skills" / "*" / "SKILL.md")))


def _live_agent_count() -> int:
    """Count agent .md files that carry a 'name:' frontmatter key."""
    count = 0
    for p in pathlib.Path(REPO_ROOT / "claude" / "agents").glob("*.md"):
        fm = _parse_frontmatter(p)
        if fm and "name" in fm:
            count += 1
    return count


class TestBuildCatalogData(unittest.TestCase):

    def test_script_exists_and_executable(self):
        """Build script exists at expected path and has executable bit set."""
        self.assertTrue(
            BUILD_SCRIPT.exists(),
            f"build_catalog_data.py not found at {BUILD_SCRIPT}",
        )
        self.assertTrue(
            os.access(BUILD_SCRIPT, os.X_OK),
            f"build_catalog_data.py is not executable: {BUILD_SCRIPT}",
        )

    def test_idempotent_double_run_byte_identical(self):
        """Running build_catalog_data.py twice produces byte-identical snippet files."""
        # First run
        result1 = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            capture_output=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(result1.returncode, 0, f"First run failed: {result1.stderr.decode()}")

        content1_skill = SKILL_SNIPPET.read_bytes()
        content1_agent = AGENT_SNIPPET.read_bytes()

        # Second run
        result2 = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            capture_output=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(result2.returncode, 0, f"Second run failed: {result2.stderr.decode()}")

        content2_skill = SKILL_SNIPPET.read_bytes()
        content2_agent = AGENT_SNIPPET.read_bytes()

        self.assertEqual(
            content1_skill,
            content2_skill,
            "skill-catalog-grid.html differs between run 1 and run 2 (not idempotent)",
        )
        self.assertEqual(
            content1_agent,
            content2_agent,
            "agent-catalog-grid.html differs between run 1 and run 2 (not idempotent)",
        )

    def test_skill_snippet_lists_at_least_n_skill_cards(self):
        """Skill snippet contains at least N data-skill-card entries (N = live count)."""
        n_skills = _live_skill_count()
        self.assertGreater(n_skills, 0, "No SKILL.md files found — repo structure issue")
        content = SKILL_SNIPPET.read_text(encoding="utf-8")
        count = len(re.findall(r'data-skill-card', content))
        self.assertGreaterEqual(
            count,
            n_skills,
            f"skill-catalog-grid.html has {count} data-skill-card entries, expected >= {n_skills}",
        )

    def test_agent_snippet_lists_at_least_n_agent_cards(self):
        """Agent snippet contains at least N data-agent-card entries (N = live count)."""
        n_agents = _live_agent_count()
        self.assertGreater(n_agents, 0, "No agent .md files with frontmatter found — repo structure issue")
        content = AGENT_SNIPPET.read_text(encoding="utf-8")
        count = len(re.findall(r'data-agent-card', content))
        self.assertGreaterEqual(
            count,
            n_agents,
            f"agent-catalog-grid.html has {count} data-agent-card entries, expected >= {n_agents}",
        )

    def test_json_island_parses(self):
        """Both snippets contain a valid JSON island (script[type='application/json'])."""
        for snippet, label in [(SKILL_SNIPPET, "skill"), (AGENT_SNIPPET, "agent")]:
            content = snippet.read_text(encoding="utf-8")
            match = re.search(
                r'<script\s+type="application/json"[^>]*>(.*?)</script>',
                content,
                re.DOTALL,
            )
            self.assertIsNotNone(
                match,
                f"{label} snippet is missing a <script type='application/json'> island",
            )
            assert match is not None  # narrow for type checker after assertIsNotNone
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                self.fail(f"{label} snippet JSON island is invalid JSON: {exc}")
            self.assertIsInstance(
                parsed,
                (dict, list),
                f"{label} snippet JSON island should be a dict or list",
            )


if __name__ == "__main__":
    unittest.main()
