"""block-bare-repo-markers.py and the settings template."""

import json
import os
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


def test_block_is_logged_with_its_rule(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "HEAD").write_text("ref: refs/heads/main\n")
    env = dict(os.environ, PIPELINEKIT_STATE_DIR=str(tmp_path / "state"))
    payload = json.dumps(
        {"session_id": "s-2", "tool_input": {"file_path": "config"}, "cwd": str(repo)}
    )
    p = subprocess.run(
        [str(BARE)], input=payload, capture_output=True, text=True, env=env
    )
    assert p.returncode == 2
    assert p.stderr.startswith("BLOCKED: ")
    assert p.stderr.rstrip().endswith("[bare-repo.marker]")
    lines = (tmp_path / "state" / "events.jsonl").read_text().splitlines()
    (e,) = [json.loads(ln) for ln in lines]
    assert (e["hook"], e["kind"], e["rule"]) == (
        "block-bare-repo-markers",
        "block",
        "bare-repo.marker",
    )
    assert e["session"] == "s-2" and e["cwd"] == str(repo)
    payload = json.dumps({"tool_input": {"file_path": "notes.txt"}, "cwd": str(repo)})
    p = subprocess.run(
        [str(BARE)], input=payload, capture_output=True, text=True, env=env
    )
    assert p.returncode == 0
    assert (tmp_path / "state" / "events.jsonl").read_text().splitlines() == lines


@pytest.mark.parametrize("payload", ["not json", "[]", '{"tool_input": "x"}', "{}"])
def test_odd_input_never_ends_in_a_traceback(tmp_path, payload):
    env = dict(os.environ, PIPELINEKIT_STATE_DIR=str(tmp_path / "state"))
    p = subprocess.run(
        [str(BARE)], input=payload, capture_output=True, text=True, env=env
    )
    assert p.returncode in (0, 2) and "Traceback" not in p.stderr
    if payload in ("not json", "[]"):
        assert p.returncode == 2 and "[input.invalid]" in p.stderr


def test_input_nested_too_deep_is_refused(tmp_path):
    env = dict(os.environ, PIPELINEKIT_STATE_DIR=str(tmp_path / "state"))
    p = subprocess.run(
        [str(BARE)], input="[" * 200000, capture_output=True, text=True, env=env
    )
    assert p.returncode == 2 and "Traceback" not in p.stderr
    assert p.stderr.rstrip().endswith("[input.invalid]")
