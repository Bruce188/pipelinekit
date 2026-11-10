"""block-bare-repo-markers.py and the settings template."""

import json
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
KIT = HOOKS.parent
BARE = HOOKS / "block-bare-repo-markers.py"
TEMPLATE = KIT / "config" / "settings.template.json"


def bare(cwd, path, tool="Write"):
    payload = json.dumps(
        {"tool_name": tool, "tool_input": {"file_path": str(path)}, "cwd": str(cwd)}
    )
    p = subprocess.run([str(BARE)], input=payload, capture_output=True, text=True)
    assert p.returncode in (0, 2), p.stderr
    return "block" if p.returncode == 2 else "allow"


@pytest.mark.parametrize(
    "existing,path,want",
    [
        ([], "config", "allow"),  # lone config at the root
        ([], "src/config", "allow"),
        ([], "app/config", "allow"),
        ([], "HEAD", "allow"),  # a lone HEAD is not a repo
        (["HEAD"], "config", "block"),
        (["HEAD"], "objects/ab/cd", "block"),
        (["config"], "HEAD", "block"),
        (["sub/HEAD"], "sub/config", "block"),
        (["sub/HEAD"], "sub/refs/heads/x", "block"),
        (["a/b/HEAD"], "a/b/config", "allow"),  # deeper than one level
        (["HEAD"], "src/config", "allow"),
        ([".git/HEAD"], ".git/config", "allow"),
        ([], "/elsewhere/HEAD", "allow"),
    ],
)
def test_bare_repo(tmp_path, existing, path, want):
    for f in existing:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("ref: refs/heads/main\n")
    target = path if path.startswith("/") else tmp_path / path
    assert bare(tmp_path, target) == want
    assert bare(tmp_path, target, tool="Edit") == want


def test_bare_repo_relative_path(tmp_path):
    (tmp_path / "HEAD").write_text("x")
    assert bare(tmp_path, "config") == "block"


def test_template_shape():
    d = json.loads(TEMPLATE.read_text())
    # CLAUDE_CODE_SUBPROCESS_ENV_SCRUB forces the default permission mode.
    assert "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB" not in d.get("env", {})
    text = TEMPLATE.read_text()
    for leak in ("/home/", "/Users/"):
        assert leak not in text
    deny = d["permissions"]["deny"]
    assert not any(r.startswith("Write(") for r in deny + d["permissions"]["ask"])
    # A `!` carve-out only applies to rules listed before it in the same file.
    for i, rule in enumerate(deny):
        if "(!" in rule:
            tool, pat = rule.split("(!", 1)
            assert any(r.startswith(tool + "(") and "(!" not in r for r in deny[:i]), (
                rule
            )
    for r in (
        "Read(.env)",
        "Edit(.env)",
        "Read(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Read(~/.kube/config)",
        "Read(~/.config/gh/hosts.yml)",
        "Read(**/credentials*)",
        "Read(!.env.example)",
    ):
        assert r in deny, r
    for event in d["hooks"].values():
        for group in event:
            for h in group["hooks"]:
                script = h["command"].replace("${CLAUDE_HOME}/hooks/", "")
                assert (HOOKS / script).is_file(), script
                assert "timeout" in h
    pre = [h for g in d["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert all(h.get("onFailure") == "block" for h in pre)
    assert all(h.get("if") for h in pre if h["command"].endswith("bash-guard.py"))
    handlers = [json.dumps(h, sort_keys=True) for h in pre]
    assert len(handlers) == len(set(handlers))
