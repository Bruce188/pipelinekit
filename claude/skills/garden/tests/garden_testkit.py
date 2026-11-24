"""Shared pieces for the garden tests: a throwaway project, a fake gh, a narrow PATH."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

GARDEN = Path(__file__).resolve().parents[1]
HELPER = GARDEN / "garden.py"
REPO = GARDEN.parents[2]
SECTIONS = ("## Friction", "## Checks", "## Pruning", "## Guidance")
# JSON nested deeper than Python's recursion limit: json.loads raises
# RecursionError on it, not ValueError. Small enough to be read (512 kB).
DEEP_JSON = '{"a": ' * 20000 + "1" + "}" * 20000

FAKE_GH = r"""#!/usr/bin/env python3
import json
import os
import sys

d = os.environ["FAKE_GH"]
args = sys.argv[1:]
with open(os.path.join(d, "calls.jsonl"), "a") as f:
    f.write(json.dumps(args) + "\n")
with open(os.path.join(d, "state.json")) as f:
    state = json.load(f)
if args[:2] == ["repo", "view"]:
    if "default" not in state:
        sys.exit(1)
    print(state["default"])
elif args[:2] == ["run", "list"]:
    if state.get("runs_exit"):
        sys.exit(state["runs_exit"])
    raw = state.get("runs_raw")
    print(raw if raw is not None else json.dumps(state.get("runs", [])))
else:
    sys.exit("fake gh: unexpected call " + " ".join(args))
"""

# The sample project of criterion 15: no lint configuration, a test that
# asserts nothing and a skipped test.
SAMPLE = {
    "pyproject.toml": (
        '[project]\nname = "sample"\nversion = "0.1.0"\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    ),
    "src/sample/__init__.py": "def add(a, b):\n    return a + b\n",
    "tests/test_add.py": (
        "import pytest\n"
        "from sample import add\n"
        "\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
        "\n"
        "\n"
        "def test_add_runs():\n"
        "    add(2, 2)\n"
        "\n"
        "\n"
        '@pytest.mark.skip(reason="flaky")\n'
        "def test_add_negative():\n"
        "    assert add(-1, -1) == -2\n"
    ),
    "README.md": "# sample\n",
}
SAMPLE_NO_ASSERT = "tests/test_add.py:9"
SAMPLE_SKIP = "tests/test_add.py:13"


def seed_sample(root: Path) -> None:
    for rel, text in SAMPLE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class Sandbox:
    """A project folder and an environment whose PATH holds only git and python3."""

    def __init__(self, tmp: Path, git: bool = True):
        self.tmp = tmp
        self.root = tmp / "project"
        self.bin = tmp / "bin"
        self.fake = tmp / "fake"
        for d in (self.root, self.bin, self.fake, tmp / "home"):
            d.mkdir(parents=True, exist_ok=True)
        for name, target in (("git", shutil.which("git")), ("python3", sys.executable)):
            (self.bin / name).symlink_to(target)
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(tmp / "home"),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "FAKE_GH": str(self.fake),
        }
        if git:
            self.git("init", "-q", "-b", "main")

    def write(self, rel: str, text: str | bytes = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text)
        return path

    def git(self, *args: str) -> str:
        p = subprocess.run(
            ["git", *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return p.stdout

    def commit_all(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "chore: start")

    def tool(self, name: str, script: str = "#!/bin/sh\nexit 0\n") -> Path:
        path = self.bin / name
        path.write_text(script)
        path.chmod(0o755)
        return path

    def gh(self, **state) -> None:
        self.tool("gh", FAKE_GH)
        (self.fake / "state.json").write_text(json.dumps(state))

    def gh_calls(self) -> list:
        log = self.fake / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def garden(self, *args: str, cwd: Path | None = None, timeout: float = 60):
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            cwd=cwd or self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def scan(self) -> str:
        p = self.garden("scan")
        assert p.returncode == 0, p.stderr
        assert p.stderr == "", p.stderr
        return p.stdout

    def scan_json(self) -> dict:
        p = self.garden("scan", "--json")
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)

    def scan_id(self) -> str:
        return self.scan_json()["scan"]

    def record(self, *picked: str):
        """record with the ids picked from a scan run just before it."""
        return self.garden("record", "--scan", self.scan_id(), "--picked", *picked)

    def snapshot(self) -> dict:
        """Every file below the project but .git, with a hash of its bytes."""
        out = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for name in filenames:
                path = Path(dirpath) / name
                rel = str(path.relative_to(self.root))
                out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return out

    def status(self) -> str:
        return self.git("status", "--porcelain", "--untracked-files=all")


def section(text: str, heading: str) -> str:
    """The lines of one section of the scan, without its heading."""
    body = text.split(heading + "\n", 1)[1]
    return body.split("\n## ", 1)[0].split("\nFindings, ranked", 1)[0]


def findings(text: str) -> list:
    """[(id, size, area, title)] from the ranked list of the scan."""
    out = []
    for line in text.split("Findings, ranked", 1)[1].splitlines():
        if line.startswith("- G"):
            fid, size, rest = line[2:].split(" ", 2)
            area, title = rest.split(": ", 1)
            out.append((fid, size.strip("[]"), area, title))
    return out
