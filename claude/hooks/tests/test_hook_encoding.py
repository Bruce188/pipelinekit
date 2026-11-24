"""The hooks speak UTF-8 to Claude Code and log their refusals, whatever the
locale, PYTHONUTF8 and PYTHONIOENCODING say."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_session_check import START, checker

HOOKS = Path(__file__).resolve().parents[1]
GUARD = HOOKS / "bash-guard.py"
BARE = HOOKS / "block-bare-repo-markers.py"
COMMIT_MSG = HOOKS.parent / "git-hooks" / "commit-msg"

ODD = {
    "PYTHONIOENCODING=utf-16": {"PYTHONIOENCODING": "utf-16"},
    "PYTHONIOENCODING=latin-1": {"PYTHONIOENCODING": "latin-1"},
    "LC_ALL=C PYTHONUTF8=0": {"LC_ALL": "C", "PYTHONUTF8": "0"},
}


@pytest.fixture
def env(tmp_path):
    e = dict(
        os.environ,
        PIPELINEKIT_STATE_DIR=str(tmp_path / "state"),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )
    for k in ("PIPELINEKIT_LOG", "PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL"):
        e.pop(k, None)
    return e


def events(env):
    log = Path(env["PIPELINEKIT_STATE_DIR"]) / "events.jsonl"
    lines = log.read_text().splitlines() if log.exists() else []
    return [json.loads(ln) for ln in lines]


def commit_msg(tmp_path, env, message, **more):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    msg = tmp_path / "msg.txt"
    msg.write_bytes(message.encode("utf-8"))
    return subprocess.run(
        [str(COMMIT_MSG), str(msg)],
        cwd=repo,
        env=dict(env, **more),
        capture_output=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    "locale",
    [{}, {"LC_ALL": "C"}, {"PYTHONUTF8": "0"}, {"LC_ALL": "C", "PYTHONUTF8": "0"}],
    ids=["default", "LC_ALL=C", "PYTHONUTF8=0", "LC_ALL=C PYTHONUTF8=0"],
)
def test_an_emoji_refusal_is_logged_in_any_locale(tmp_path, env, locale):
    p = commit_msg(tmp_path, env, "feat: emoji \U0001f680\n", **locale)
    assert p.returncode == 1 and b"[commit-msg.emoji]" in p.stderr, p.stderr
    (e,) = events(env)
    assert (e["hook"], e["kind"]) == ("commit-msg", "block")
    assert e["rule"] == "commit-msg.emoji"


def test_the_emoji_refusal_names_the_rule_not_the_emoji(tmp_path, env):
    p = commit_msg(tmp_path, env, "feat: sparkle \u2728 and rocket \U0001f680\n")
    assert p.returncode == 1
    (e,) = events(env)
    assert e["reason"] == "emoji are not allowed"
    raw = (Path(env["PIPELINEKIT_STATE_DIR"]) / "events.jsonl").read_text()
    assert "2728" not in raw and "ud83d" not in raw.lower() and "1f680" not in raw


def run_hook(path, payload, env, odd):
    return subprocess.run(
        [sys.executable, str(path)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        env=dict(env, **odd),
        capture_output=True,
        timeout=60,
    )


def bash(command, cwd):
    return {
        "session_id": "s1",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


@pytest.mark.parametrize("odd", ODD.values(), ids=ODD.keys())
def test_bash_guard_speaks_utf8(tmp_path, env, odd):
    harmless = run_hook(GUARD, bash("git status -- caf\u00e9", tmp_path), env, odd)
    assert (harmless.returncode, harmless.stdout, harmless.stderr) == (0, b"", b"")
    ask = run_hook(GUARD, bash('psql -c "DROP TABLE t"', tmp_path), env, odd)
    assert ask.returncode == 0, ask.stderr
    said = json.loads(ask.stdout.decode("utf-8"))
    assert said["hookSpecificOutput"]["permissionDecision"] == "ask"
    block = run_hook(GUARD, bash("git commit --no-verify -m x", tmp_path), env, odd)
    assert block.returncode == 2
    assert block.stderr.decode("utf-8").startswith("BLOCKED: "), block.stderr
    assert [e["rule"] for e in events(env)] == ["sql.destructive", "git.no-verify"]


@pytest.mark.parametrize("odd", ODD.values(), ids=ODD.keys())
def test_block_bare_repo_markers_speaks_utf8(tmp_path, env, odd):
    def write(rel):
        payload = {
            "session_id": "s1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / rel), "content": "x"},
            "cwd": str(tmp_path),
        }
        return run_hook(BARE, payload, env, odd)

    harmless = write("caf\u00e9/notes.txt")
    assert (harmless.returncode, harmless.stdout, harmless.stderr) == (0, b"", b"")
    (tmp_path / "HEAD").write_text("ref: refs/heads/main\n")
    block = write("config")
    assert block.returncode == 2
    assert block.stderr.decode("utf-8").startswith("BLOCKED: "), block.stderr


@pytest.mark.parametrize("odd", ODD.values(), ids=ODD.keys())
def test_session_check_speaks_utf8(tmp_path, env, odd):
    home = tmp_path / "claude"
    (home / "hooks").mkdir(parents=True)
    (home / "skills" / "kit").mkdir(parents=True)
    for name in ("session-check.py", "kitlog.py"):
        shutil.copy(HOOKS / name, home / "hooks" / name)
    (home / "skills" / "kit" / "check.py").write_text(checker(("fail", "x")))
    env.pop("PIPELINEKIT_SESSION_CHECK", None)
    env.pop("CLAUDE_HOME", None)
    p = subprocess.run(
        [sys.executable, str(home / "hooks" / "session-check.py")],
        input=START.encode("utf-8"),
        env=dict(env, **odd),
        capture_output=True,
        timeout=60,
    )
    assert p.returncode == 0 and p.stderr == b"", p.stderr
    said = json.loads(p.stdout.decode("utf-8"))
    assert said["systemMessage"] == (
        "pipelinekit: 1 problem in this install. Run /kit for the report."
    )
