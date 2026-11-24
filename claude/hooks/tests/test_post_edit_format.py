"""post-edit-format.sh runs the project's prettier whichever time limit the
machine has: timeout, gtimeout (Homebrew coreutils on macOS) or none at all."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "post-edit-format.sh"

# The only commands the hook needs from PATH; bash comes from its shebang.
TOOLS = ("cat", "grep", "python3", "dirname")

STUB = """#!/bin/sh
echo "{name} $*" >> "$FORMAT_LOG"
{tail}
"""


def stub(path, name, tail=""):
    path.write_text(STUB.format(name=name, tail=tail))
    path.chmod(0o755)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "app"
    (root / "node_modules" / ".bin").mkdir(parents=True)
    (root / "package.json").write_text("{}\n")
    stub(root / "node_modules" / ".bin" / "prettier", "prettier")
    src = root / "src" / "index.ts"
    src.parent.mkdir()
    src.write_text("const a=1\n")
    return src


def run_hook(tmp_path, src, limits):
    """Run the hook with a PATH holding only TOOLS and the named stubs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found, f"{tool} not found on this machine"
        (bin_dir / tool).symlink_to(found)
    for name in limits:
        stub(bin_dir / name, name, 'shift\nexec "$@"')
    log = tmp_path / "format.log"
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(src)}}
    env = dict(os.environ, PATH=str(bin_dir), FORMAT_LOG=str(log))
    r = subprocess.run(
        [str(HOOK)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    return log.read_text().splitlines() if log.exists() else []


def test_runs_prettier_without_timeout_or_gtimeout(tmp_path, project):
    calls = run_hook(tmp_path, project, [])
    assert calls == [f"prettier --write -- {project}"]


def test_uses_gtimeout_when_there_is_no_timeout(tmp_path, project):
    calls = run_hook(tmp_path, project, ["gtimeout"])
    prettier = project.parents[1] / "node_modules" / ".bin" / "prettier"
    assert calls == [
        f"gtimeout 5 {prettier} --write -- {project}",
        f"prettier --write -- {project}",
    ]


def test_prefers_timeout(tmp_path, project):
    calls = run_hook(tmp_path, project, ["timeout", "gtimeout"])
    prettier = project.parents[1] / "node_modules" / ".bin" / "prettier"
    assert calls == [
        f"timeout 5 {prettier} --write -- {project}",
        f"prettier --write -- {project}",
    ]


def test_leaves_other_files_alone(tmp_path, project):
    other = project.with_suffix(".md")
    other.write_text("# x\n")
    assert run_hook(tmp_path, other, []) == []