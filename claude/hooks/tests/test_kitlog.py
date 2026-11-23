"""kitlog.py: what an event holds, who can read it, and that logging never fails."""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
KITLOG = HOOKS / "kitlog.py"

_spec = importlib.util.spec_from_file_location("kitlog", KITLOG)
kitlog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kitlog)


@pytest.fixture
def state(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("PIPELINEKIT_STATE_DIR", str(d))
    monkeypatch.delenv("PIPELINEKIT_LOG", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    return d


def events(state):
    return [json.loads(ln) for ln in (state / "events.jsonl").read_text().splitlines()]


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_event_fields(state):
    data = {"session_id": "abc-123", "tool_use_id": "toolu_9", "cwd": "/work/repo"}
    assert kitlog.log("bash-guard", "block", "git.no-verify", "why", data, "git/git")
    (e,) = events(state)
    assert e["v"] == kitlog.VERSION
    assert (e["hook"], e["kind"], e["rule"]) == ("bash-guard", "block", "git.no-verify")
    assert (e["reason"], e["prog"]) == ("why", "git/git")
    assert e["session"] == "abc-123" and e["tool_use_id"] == "toolu_9"
    assert e["cwd"] == "/work/repo"
    assert kitlog.RULE.match(e["rule"])
    assert len(e["ts"]) == 20 and e["ts"].endswith("Z")
    assert "claude" not in e


def test_empty_fields_are_left_out(state):
    assert kitlog.log("pre-push", "block", "pre-push.protected-branch")
    (e,) = events(state)
    assert set(e) == {"ts", "v", "hook", "kind", "rule", "reason", "cwd"}


def test_claude_session_is_marked(state, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    kitlog.log("commit-msg", "block", "commit-msg.format", "x")
    assert events(state)[0]["claude"] is True


def test_only_the_owner_can_read_the_log(state):
    kitlog.log("bash-guard", "ask", "sql.destructive", "x")
    assert mode(state) == 0o700
    assert mode(state / "events.jsonl") == 0o600


def test_reason_is_one_clean_line_without_credentials(state):
    reason = "push to\n\x1b[31m https://user:s3cret@example.com/o/r.git " + "x" * 900
    kitlog.log("bash-guard", "block", "git.push-remote", reason)
    text = (state / "events.jsonl").read_text()
    assert text.count("\n") == 1
    assert "s3cret" not in text and "user:" not in text
    (e,) = events(state)
    assert "https://example.com/o/r.git" in e["reason"]
    assert len(e["reason"]) == 300
    assert not any(ord(ch) < 32 for ch in e["reason"])


@pytest.mark.parametrize("ch", ["x", "\u00e9", "\U0001f600"])
def test_a_line_never_exceeds_the_limit(state, ch):
    data = {"session_id": ch * 500, "tool_use_id": ch * 500, "cwd": "/" + ch * 5000}
    assert kitlog.log(
        "bash-guard", "block", "git.never-stage", ch * 5000, data, ch * 99
    )
    raw = (state / "events.jsonl").read_bytes()
    assert raw.endswith(b"\n") and len(raw) <= kitlog.MAX_LINE
    (e,) = events(state)
    assert e["rule"] == "git.never-stage" and e["reason"].startswith(ch)


def test_rotation_keeps_one_older_file(state, monkeypatch):
    monkeypatch.setattr(kitlog, "MAX_BYTES", 400)
    for i in range(30):
        assert kitlog.log("bash-guard", "block", "git.no-verify", f"event {i}")
    old, cur = state / "events.jsonl.1", state / "events.jsonl"
    assert old.exists() and cur.stat().st_size < 400 + kitlog.MAX_LINE
    assert sorted(p.name for p in state.iterdir()) == ["events.jsonl", "events.jsonl.1"]
    assert mode(old) == 0o600 and mode(cur) == 0o600
    last = json.loads(cur.read_text().splitlines()[-1])
    assert last["reason"] == "event 29"


def test_switched_off(state, monkeypatch):
    monkeypatch.setenv("PIPELINEKIT_LOG", "0")
    assert kitlog.log("bash-guard", "block", "git.no-verify", "x") is False
    assert not state.exists()


def test_a_log_that_cannot_be_written_is_ignored(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    monkeypatch.setenv("PIPELINEKIT_STATE_DIR", str(blocker / "state"))
    assert kitlog.log("bash-guard", "block", "git.no-verify", "x") is False


def test_a_symlinked_log_is_not_followed(state, tmp_path):
    state.mkdir()
    target = tmp_path / "elsewhere"
    target.write_text("")
    (state / "events.jsonl").symlink_to(target)
    assert kitlog.log("bash-guard", "block", "git.no-verify", "x") is False
    assert target.read_text() == ""


@pytest.mark.parametrize(
    "hook,kind,rule",
    [
        ("bash-guard", "nope", "git.no-verify"),
        ("bash guard", "block", "git.no-verify"),
        ("bash-guard", "block", "Git.NoVerify"),
        ("bash-guard", "block", "no-dot"),
        ("bash-guard", "block", "git.no verify"),
        ("", "block", "git.no-verify"),
    ],
)
def test_names_outside_the_format_are_refused(state, hook, kind, rule):
    assert kitlog.log(hook, kind, rule, "x") is False
    assert not state.exists()


def test_odd_arguments_do_not_raise(state):
    assert kitlog.log("bash-guard", "block", "git.no-verify", None, "not a dict", 5)
    assert kitlog.log("bash-guard", "block", "git.no-verify", b"\xff", {"cwd": 7})
    assert kitlog.log(None, None, None) is False
    assert len(events(state)) == 2


def test_default_location_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("PIPELINEKIT_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert kitlog.log_path() == str(tmp_path / "xdg" / "pipelinekit" / "events.jsonl")
    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    want = tmp_path / "home" / ".local" / "state" / "pipelinekit" / "events.jsonl"
    assert kitlog.log_path() == str(want)


def cli(state, *args):
    env = {"PATH": "/usr/bin:/bin", "PIPELINEKIT_STATE_DIR": str(state)}
    return subprocess.run(
        [sys.executable, str(KITLOG), *args], capture_output=True, text=True, env=env
    )


def test_cli_writes_one_event(state):
    p = cli(state, "pre-push", "block", "pre-push.protected-branch", "push", "refused")
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")
    (e,) = events(state)
    assert (e["hook"], e["kind"], e["rule"]) == (
        "pre-push",
        "block",
        "pre-push.protected-branch",
    )
    assert e["reason"] == "push refused"


@pytest.mark.parametrize(
    "args", [(), ("pre-push",), ("pre-push", "block"), ("a b", "nope", "x", "y")]
)
def test_cli_exits_zero_whatever_it_is_given(state, args):
    p = cli(state, *args)
    assert p.returncode == 0 and p.stderr == ""
    assert not state.exists()


def test_cli_exits_zero_when_the_log_cannot_be_written(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    p = cli(blocker / "state", "pre-push", "block", "pre-push.protected-branch")
    assert p.returncode == 0 and p.stderr == ""


@pytest.mark.parametrize(
    "url,kept",
    [
        ("https://h.example/o/r.git?access_token=SECRET", "https://h.example/o/r.git"),
        (
            "https://h.example/o/r.git?private_token=SECRET&x=1",
            "https://h.example/o/r.git",
        ),
        ("https://h.example/o/r.git#token=SECRET", "https://h.example/o/r.git"),
        ("u5:SECRET@h.example:o/r.git", "h.example:o/r.git"),
        ("//u11:SECRET@h.example/o/r.git", "//h.example/o/r.git"),
        ("https://u3:SEC@RET@h.example/o/r.git", "https://h.example/o/r.git"),
        ("https:/u12:SECRET@h.example/.env", "https:/h.example/.env"),
        ("https://SECRET@h.example/o/r.git", "https://h.example/o/r.git"),
        ("git@h.example:o/r.git", "git@h.example:o/r.git"),
        ("ssh://h.example:22/o/r.git", "ssh://h.example:22/o/r.git"),
        ("https://u1:SEC RET@h.example/o/r.git", "https://h.example/o/r.git"),
        ("https://u1:SEC'RET@h.example/o/r.git", "https://h.example/o/r.git"),
        ('https://u1:SEC"RET@h.example/o/r.git', "https://h.example/o/r.git"),
        ("https://SEC RET@h.example/o/r.git", "https://h.example/o/r.git"),
        ("ssh://u1:SEC\tRET@h.example:22/o/r.git", "ssh://h.example:22/o/r.git"),
        ("u5:SEC RET@h.example:o/r.git", "h.example:o/r.git"),
        ("https://h.example/o/r.git?SECRET", "https://h.example/o/r.git"),
        ("https://h.example/o/r.git#SECRET", "https://h.example/o/r.git"),
        ("https://h.example/o/r.git?SECRET#x", "https://h.example/o/r.git"),
        ("https://h.example?SECRET", "https://h.example"),
    ],
)
def test_no_form_of_a_remote_keeps_its_credentials(state, url, kept):
    reason = f"push to remote '{url}' is not allowed; only origin"
    kitlog.log("bash-guard", "block", "git.push-remote", reason)
    (e,) = events(state)
    assert e["reason"] == f"push to remote '{kept}' is not allowed; only origin"
    assert "SEC" not in (state / "events.jsonl").read_text()


def test_reason_has_no_character_that_changes_how_a_line_reads(state):
    odd = "\x9b\u202e\u2066\u200b\xad\u2028\u2029\ufeff\U000e0041\ud800"
    kitlog.log("bash-guard", "block", "git.push-remote", f"a{odd}b")
    (e,) = events(state)
    assert e["reason"] == "a b"


def test_a_named_pipe_at_the_log_path_is_left_alone(state):
    state.mkdir()
    pipe = state / "events.jsonl"
    os.mkfifo(pipe)
    env = {"PATH": "/usr/bin:/bin", "PIPELINEKIT_STATE_DIR": str(state)}
    args = [sys.executable, str(KITLOG), "pre-push", "block", "pre-push.x", "y"]
    p = subprocess.run(args, capture_output=True, text=True, env=env, timeout=30)
    assert p.returncode == 0 and p.stderr == ""
    reader = os.open(pipe, os.O_RDONLY | os.O_NONBLOCK)
    try:
        subprocess.run(args, env=env, timeout=30)
        assert os.read(reader, 100) == b""
    finally:
        os.close(reader)
