"""Tests of check.py: activity, the session-start check, odd files, updates, sandbox."""

import importlib.util
import json
import os
import re
import subprocess
import time

import pytest
from check_fixtures import (
    REPO,
    check,
    check_py,
    edit_json,
    replace_script,
    snapshot,
)

# ---------------------------------------------------------------- activity


def state(kit):
    return kit["user"] / ".local" / "state" / "pipelinekit"


def ev(rule="git.no-verify", kind="block", hook="bash-guard", age_days=0.0, **more):
    ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_days * 86400)
    )
    e = {"ts": ts, "v": 1, "hook": hook, "kind": kind, "rule": rule}
    return {**e, "reason": "why it was refused", **more}


def write_events(kit, *events, name="events.jsonl"):
    state(kit).mkdir(parents=True, exist_ok=True)
    with open(state(kit) / name, "a") as f:
        for e in events:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")


def activity_rules(out):
    return re.findall(r"^  \[(?:info|warn)\] (\S+) \(\S+\): ", out, re.M)


def test_activity_of_a_fresh_install_is_empty(kit):
    rc, out = check(kit)
    assert rc == 0, out
    assert "Activity (last 7 days)\n  [info] no blocks, asks or hook errors" in out
    assert not state(kit).exists()


def test_activity_lists_what_the_hooks_refused(kit):
    write_events(
        kit,
        ev(tool_use_id="t1", age_days=2),
        ev(tool_use_id="t2", age_days=1),
        ev(tool_use_id="t3", reason="the newest reason"),
        ev("sql.destructive", "ask", age_days=3),
        ev("pre-push.allow-main", "override", "pre-push", age_days=4),
    )
    rc, out = check(kit)
    assert rc == 0, out
    assert "[info] git.no-verify (bash-guard): blocked 3 times, last 20" in out
    assert "UTC: the newest reason" in out
    assert "[info] sql.destructive (bash-guard): asked once, last 20" in out
    assert "[info] pre-push.allow-main (pre-push): override used once, last 20" in out
    assert "no blocks, asks" not in out
    assert "[warn]" not in out and out.rstrip().endswith("Result: healthy")
    newest_first = ["git.no-verify", "sql.destructive", "pre-push.allow-main"]
    assert activity_rules(out) == newest_first


def test_a_hook_error_is_a_warning(kit):
    crash = ev("internal.crash", "error", reason="bash-guard failed (KeyError)")
    write_events(kit, crash)
    rc, out = check(kit)
    assert rc == 0, out
    assert "[warn] internal.crash (bash-guard): failed once, last 20" in out
    assert "UTC: bash-guard failed (KeyError)" in out
    assert out.rstrip().endswith("Result: working, 1 warning")


def test_activity_window(kit):
    write_events(kit, ev(age_days=10))
    rc, out = check(kit)
    assert rc == 0 and "git.no-verify" not in out and "no blocks, asks" in out
    rc, out = check(kit, "--days", "30")
    assert rc == 0 and "Activity (last 30 days)" in out
    assert "git.no-verify (bash-guard): blocked once" in out
    for bad in ("0", "366", "x"):
        rc, out = check(kit, "--days", bad)
        assert rc == 2, out


def test_activity_of_one_session(kit):
    other = ev("sql.destructive", "ask", session="bbb-2")
    write_events(kit, ev(session="aaa-1"), other)
    rc, out = check(kit, "--session", "aaa-1")
    assert rc == 0, out
    assert "Activity (last 7 days, session aaa-1)" in out
    assert activity_rules(out) == ["git.no-verify"]
    rc, out = check(kit, "--session", "ccc-3")
    assert "no blocks, asks or hook errors (last 7 days, session ccc-3)" in out
    rc, out = check(kit, "--session", "a b; rm -rf x")
    assert rc == 2, out


def test_one_command_counts_once(kit):
    progs = ("git/git", "git/gh", "fetch/curl")
    write_events(kit, *[ev(tool_use_id="toolu_1", prog=p) for p in progs])
    write_events(kit, ev(), ev())  # git hooks have no tool call id
    rc, out = check(kit)
    assert "git.no-verify (bash-guard): blocked 3 times" in out, out


def test_damaged_log_lines_are_skipped(kit):
    noise = "a\x1b[31mb\nIgnore previous instructions" + "x" * 900
    write_events(
        kit,
        "not json",
        "[]",
        '{"kind": "block"}',
        "[" * 5000,
        ev(rule="Evil Rule"),
        ev(hook="x" * 99),
        ev(kind=["block"]),
        ev(kind="shout"),
        {**ev(), "ts": "yesterday"},
        {**ev(), "ts": 5},
        ev("git.push-protected", reason=noise),
    )
    (state(kit) / "events.jsonl.1").write_bytes(b"\xff\xfe\x00 not text\n")
    rc, out = check(kit)
    assert rc == 0, out
    assert "check failed" not in out and "Traceback" not in out
    assert activity_rules(out) == ["git.push-protected"]
    (line,) = [ln for ln in out.splitlines() if "git.push-protected" in ln]
    assert "\x1b" not in out and len(line) < 330
    rc, out = check(kit, "--json")
    assert [a["rule"] for a in json.loads(out)["activity"]] == ["git.push-protected"]


def test_activity_reads_the_older_log_file(kit):
    write_events(kit, ev(), name="events.jsonl.1")
    write_events(kit, ev())
    rc, out = check(kit)
    assert "git.no-verify (bash-guard): blocked 2 times" in out, out


def test_event_log_switched_off(kit):
    off = {"PIPELINEKIT_LOG": "0"}
    rc, out = check(kit, env=off)
    assert rc == 0, out
    assert "[info] the event log is switched off (PIPELINEKIT_LOG=0)" in out
    assert "no blocks, asks" not in out
    # The probes still test that the hooks can record.
    rc, out = check(kit, "--verbose", env=off)
    assert "[pass] event log: 6 refusals recorded" in out, out


def test_quick_has_no_activity(kit):
    write_events(kit, ev("internal.crash", "error"))
    rc, out = check(kit, "--quick")
    assert rc == 0 and "Activity" not in out and "internal.crash" not in out
    d = json.loads(check(kit, "--quick", "--json")[1])
    assert d["activity"] == []


def test_json_activity(kit):
    first, last = ev(age_days=1, reason="older"), ev(reason="newer")
    write_events(kit, first, last)
    d = json.loads(check(kit, "--json")[1])
    assert d["activity"] == [
        {
            "hook": "bash-guard",
            "rule": "git.no-verify",
            "kind": "block",
            "count": 2,
            "last": last["ts"],
            "reason": "newer",
        }
    ]
    assert d["healthy"] is True


def test_missing_log_helper(kit):
    (kit["home"] / "hooks" / "kitlog.py").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] hook helper missing: kitlog.py" in out
    assert "missing: hooks/kitlog.py" not in out and "event log:" not in out
    assert "gave" not in out  # the hooks themselves still decide


def test_log_helper_that_records_nothing(kit):
    body = "#!/usr/bin/env python3\ndef log(*a, **k):\n    return False\n"
    replace_script(kit, "hooks/kitlog.py", body)
    rc, out = check(kit)
    assert rc == 1
    hooks = (
        "bash-guard, block-bare-repo-markers, commit-msg, pre-commit, "
        "pre-merge-commit and 1 more"
    )
    assert f"[fail] event log: nothing recorded for {hooks}" in out


def test_event_log_formats_match_the_hooks(monkeypatch, tmp_path):
    path = REPO / "claude" / "hooks" / "kitlog.py"
    spec = importlib.util.spec_from_file_location("kitlog", path)
    kitlog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kitlog)
    cases = (
        {"PIPELINEKIT_STATE_DIR": str(tmp_path / "a")},
        {"XDG_STATE_HOME": str(tmp_path / "b")},
        {},
        {"PIPELINEKIT_STATE_DIR": "~/c", "XDG_STATE_HOME": "~/d"},
        {"PIPELINEKIT_STATE_DIR": "c", "XDG_STATE_HOME": "d"},
    )
    for case in cases:
        for k in ("PIPELINEKIT_STATE_DIR", "XDG_STATE_HOME"):
            monkeypatch.delenv(k, raising=False)
        for k, v in case.items():
            monkeypatch.setenv(k, v)
        assert check_py.state_dir() == kitlog.state_dir()
    assert check_py.EVENT_HOOK.pattern == kitlog.HOOK.pattern
    assert check_py.EVENT_RULE.pattern == kitlog.RULE.pattern
    assert tuple(check_py.EVENT_KINDS) == kitlog.KINDS


def test_a_failed_hook_is_shown_however_busy_the_log_is(kit):
    busy = [ev(f"git.rule-{n:02d}", age_days=n / 1000) for n in range(25)]
    write_events(kit, *busy, ev("internal.crash", "error", age_days=2))
    rc, out = check(kit)
    assert rc == 0, out
    assert "[warn] internal.crash (bash-guard): failed once" in out
    assert "[info] 5 more rules not shown (--json lists them all)" in out
    assert out.rstrip().endswith("Result: working, 1 warning")


def test_characters_the_report_cannot_show_do_not_end_it(kit):
    write_events(kit, ev(reason="a\x9b\u202e\u2028\u2029\ud800b"))
    rc, out = check(kit)
    assert rc == 0 and "UTC: a b" in out, out
    rocket = ev("commit-msg.emoji", hook="commit-msg", reason="emoji \U0001f680 x")
    write_events(kit, rocket)
    plain = {"LC_ALL": "POSIX", "LANG": "", "PYTHONUTF8": "0"}
    rc, out = check(kit, env=dict(plain, PYTHONCOERCECLOCALE="0"))
    assert rc == 0 and "check failed" not in out, out
    assert "commit-msg.emoji (commit-msg): blocked once" in out


def test_events_from_the_future_are_left_out(kit):
    write_events(kit, ev(age_days=-1), ev("sql.destructive", "ask"))
    rc, out = check(kit, "--days", "30")
    assert rc == 0 and activity_rules(out) == ["sql.destructive"], out


def test_a_log_that_cannot_be_read_is_named(kit):
    if os.geteuid() == 0:
        pytest.skip("root reads every file")
    write_events(kit, ev())
    (state(kit) / "events.jsonl").chmod(0)
    rc, out = check(kit)
    assert rc == 0, out
    assert "[info] the event log cannot be read: " in out
    assert "no blocks, asks" not in out


@pytest.mark.parametrize("how", ["closed directory", "directory", "pipe"])
def test_a_log_that_is_there_is_not_called_empty(kit, how):
    if os.geteuid() == 0:
        pytest.skip("root reads every file")
    write_events(kit, ev())
    log = state(kit) / "events.jsonl"
    if how == "closed directory":
        state(kit).chmod(0)
    else:
        log.unlink()
        log.mkdir() if how == "directory" else os.mkfifo(log)
    try:
        rc, out = check(kit)
    finally:
        state(kit).chmod(0o700)
    assert rc == 0, out
    assert "[info] the event log cannot be read: " in out
    assert "no blocks, asks" not in out


def test_a_session_id_as_long_as_the_hooks_store_it(kit):
    long = "a" * 80
    write_events(kit, ev(session=long))
    rc, out = check(kit, "--session", long)
    assert rc == 0 and activity_rules(out) == ["git.no-verify"], out
    rc, out = check(kit, "--session", long + "a")
    assert rc == 2, out


# ---------------------------------------------------------------- session start

START = '{"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"}'
WOLF = {
    "systemMessage": "Run /kit",
    "hookSpecificOutput": {"hookEventName": "SessionStart"},
}
CRY_WOLF = f"#!/bin/sh\necho '{json.dumps(WOLF)}'\n"


def session_check(kit, **env):
    """Run the installed session-start hook the way Claude Code does."""
    p = subprocess.run(
        [str(kit["home"] / "hooks" / "session-check.py")],
        input=START,
        capture_output=True,
        text=True,
        env=dict(kit["env"], **env),
        cwd=kit["root"],
    )
    assert p.returncode == 0 and p.stderr == "", p.stderr
    return p.stdout


def test_session_check_says_nothing_on_a_healthy_install(kit):
    before = snapshot(kit["user"])
    assert session_check(kit) == ""
    assert snapshot(kit["user"]) == before


def test_session_check_names_kit_when_a_hook_is_gone(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    out = session_check(kit)
    assert len(out.splitlines()) == 1, out
    said = json.loads(out)
    line = r"pipelinekit: \d+ problems? in this install\. Run /kit for the report\."
    assert re.fullmatch(line, said["systemMessage"]), said["systemMessage"]
    assert "bash-guard" not in out, "no text from the report in the line"
    assert said["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert session_check(kit, PIPELINEKIT_SESSION_CHECK="0") == ""


def test_session_check_keeps_quiet_about_warnings(kit):
    with open(kit["home"] / "hooks" / "post-edit-format.sh", "a") as f:
        f.write("# my own note\n")
    rc, out = check(kit, "--quick")
    assert rc == 0 and "[warn] changed since install" in out, out
    assert session_check(kit) == ""


def test_session_check_is_a_wired_startup_hook(kit):
    settings = json.loads((kit["home"] / "settings.json").read_text())
    (group,) = settings["hooks"]["SessionStart"]
    assert group["matcher"] == "startup"
    (hook,) = group["hooks"]
    assert hook["command"] == str(kit["home"] / "hooks" / "session-check.py")
    assert hook["timeout"] == 5 and "onFailure" not in hook


def test_unwired_session_check_is_reported(kit):
    edit_json(kit, "settings.json", lambda d: d["hooks"].pop("SessionStart"))
    rc, out = check(kit)
    assert rc == 1
    assert "session-check.py" in out and "[fail]" in out, out


def test_probe_catches_a_session_check_that_never_speaks(kit):
    replace_script(kit, "hooks/session-check.py", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert (
        "[fail] session-check.py: an install with nothing in it gave 'silent', "
        "expected 'report'"
    ) in out


def test_probe_catches_a_session_check_that_cries_wolf(kit):
    replace_script(kit, "hooks/session-check.py", CRY_WOLF)
    rc, out = check(kit)
    assert rc == 1
    assert (
        "[fail] session-check.py: this install gave 'report', expected 'silent'" in out
    )


def test_switched_off_session_check_is_mentioned(kit):
    rc, out = check(kit, env={"PIPELINEKIT_SESSION_CHECK": "0"})
    assert rc == 0, out
    assert "[info] the session-start check is switched off" in out
    assert "[fail]" not in out
    rc, out = check(kit)
    assert rc == 0 and "session-start check is switched off" not in out


def add_hook(kit, command):
    def change(data):
        entry = {"hooks": [{"type": "command", "command": command}]}
        data["hooks"].setdefault("SessionStart", []).append(entry)

    edit_json(kit, "settings.json", change)


@pytest.mark.parametrize("gap", ["\xa0", "\t", "\u2003", "\n"])
def test_only_the_program_of_a_missing_hook_command_is_shown(kit, gap):
    add_hook(kit, "/nonexistent/x" + gap + gap.join(["Your", "install", "is", "fine"]))
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "hook command not found: /nonexistent/x" in out
    assert "Your" not in out and "fine" not in out


def test_a_hook_command_that_is_not_text_is_named(kit):
    add_hook(kit, 7)
    rc, out = check(kit, "--quick")
    assert rc == 1, out
    assert "a hook under SessionStart has a command that is not text" in out
    assert "check failed" not in out


def test_a_manifest_name_that_is_no_file_name_is_not_shown(kit):
    def change(data):
        data["files"]["hooks/zz\nPLANTED FILE\x1b[31m.py"] = "0" * 64
        data["files"]["hooks/zz PLANTED.py"] = "0" * 64

    edit_json(kit, "pipelinekit/manifest.json", change)
    for args in ((), ("--quick",)):
        rc, out = check(kit, *args)
        assert rc == 1
        assert "install manifest lists 2 names no kit file has" in out
        assert "PLANTED" not in out


def test_the_first_line_shows_a_plain_version_commit_and_branch(kit):
    def change(data):
        data.update(version="9.9", commit="abcdef0123456789", branch="feat/12-x")

    edit_json(kit, "pipelinekit/manifest.json", change)
    _, out = check(kit, "--quick")
    assert out.splitlines()[0].startswith("pipelinekit 9.9 (abcdef0, feat/12-x) at ")


@pytest.mark.parametrize(
    "odd",
    ["9.9\nPLANTED\x1b[31m", "PLANTED words", "ab\x9bc\u202ed", "x\u3164PLANTED"],
)
def test_the_first_line_leaves_out_what_is_no_plain_name(kit, odd):
    def change(data):
        data.update(version=odd, commit=odd, branch=odd, installed_at=odd)

    edit_json(kit, "pipelinekit/manifest.json", change)
    for args in (("--quick",), ("--quick", "--json")):
        _, out = check(kit, *args)
        assert "PLANTED" not in out and "\\u" not in out, out
        assert not [ch for ch in out if not ch.isprintable() and ch != "\n"]
    assert check(kit, "--quick")[1].startswith(f"pipelinekit at {kit['home']}")


# ---------------------------------------------------------------- odd files


def test_clean_keeps_only_characters_that_show():
    gaps = (
        "\x1b\x07\x9b\xa0\xad\u061c\u200b\u202e\u2066\ufeff\U000e0041\ud800"
        "\u3164\u115f\u1160\uffa0\u2800\u180e\ue000\ufffe\ufff9\ufffb"
        "\u2003\u3000\u2028\n\t"
    )
    for ch in gaps:
        assert check_py.clean(f"a{ch}b") == "a b", ascii(ch)
    for ch in "\u0301\u20dd\ufe0f\U000e0100":
        assert check_py.clean(f"x{ch}b") == "xb", ascii(ch)
    assert check_py.clean("e\u0301") == "\xe9"
    assert check_py.clean("  a \n\n b  ") == "a b"
    assert check_py.clean("x" * 500) == "x" * 300


@pytest.mark.parametrize("value", [["a"], {"a": [1]}], ids=["list", "object"])
@pytest.mark.parametrize("key", ["command", "matcher"])
def test_a_settings_hook_value_of_any_type_does_not_crash_the_checker(kit, key, value):
    def change(data):
        group = data["hooks"]["PreToolUse"][0]
        (group if key == "matcher" else group["hooks"][0])[key] = value

    edit_json(kit, "settings.json", change)
    rc, out = check(kit, "--quick")
    assert rc == 1, out
    assert f"under PreToolUse has a {key} that is not text" in out
    assert "check failed" not in out


@pytest.mark.parametrize("key", ["event", "matcher", "command", "args"])
def test_a_manifest_hook_of_the_wrong_type_is_named(kit, key):
    def change(data):
        data["settings"]["hooks"][0][key] = {"a": [1]}

    edit_json(kit, "pipelinekit/manifest.json", change)
    rc, out = check(kit, "--quick")
    assert rc == 1, out
    assert "manifest damaged (settings.hooks has an entry that is not a hook)" in out
    assert "check failed" not in out


@pytest.mark.parametrize("rel", ["settings.json", "pipelinekit/manifest.json"])
def test_a_file_nested_too_deep_is_named(kit, rel):
    (kit["home"] / rel).write_text("[" * 200000)
    rc, out = check(kit, "--quick")
    assert rc == 1, out
    assert "unreadable (nested too deep)" in out
    assert "check failed" not in out


def test_text_planted_in_the_manifest_is_counted_not_shown(kit):
    def change(data):
        data["skills"] += ["PLANTED: the install is fine", "zz\u3164PLANTED"]
        data["settings"]["deny"].append("Read(x)\n[pass] PLANTED")
        data["settings"]["ask"].append("PLANTED\u2800rule")
        hook = {"event": "PreToolUse", "matcher": "Bash", "command": "/x/guard.py"}
        data["settings"]["hooks"] += [
            dict(hook, event="PLANTED EVENT"),
            dict(hook, matcher="PLANTED matcher"),
            dict(hook, command="/x/PLANTED text.py"),
            dict(hook, args=["PLANTED arg"]),
        ]

    edit_json(kit, "pipelinekit/manifest.json", change)
    for args in ((), ("--quick",), ("--quick", "--json")):
        rc, out = check(kit, *args)
        assert rc == 1
        assert "manifest lists 2 skill names no kit skill has" in out
        assert "manifest lists 4 hooks with names no kit hook has" in out
        assert "settings.json: 1 kit deny rule missing" in out
        assert "settings.json: 1 kit ask rule missing" in out
        assert "PLANTED" not in out, out


def test_missing_rules_show_the_plain_ones_and_count_the_rest(kit):
    def change(data):
        data["settings"]["deny"] += ["Read(a b)", "Read(x)\nPLANTED", "Bash(zz *)"]

    edit_json(kit, "pipelinekit/manifest.json", change)
    _, out = check(kit, "--quick")
    assert "3 kit deny rules missing: Read(a b), Bash(zz *) and 1 more" in out


def test_a_hook_command_with_characters_that_do_not_show_is_not_repeated(kit):
    gaps = "\u3164\u115f\u1160\uffa0\u2800\u180e\ufe0f\U000e0100\ue000\ufffe\ufff9"
    for gap in gaps + "\u0301\u202e\x1b":
        add_hook(kit, "/nonexistent/x" + gap + "PLANTED" + gap + "words")
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert out.count("hook command not found: a path that cannot be shown") == 1
    assert "hook command not found: /" not in out and "PLANTED" not in out


def test_a_very_long_hook_command_path_is_not_repeated(kit):
    add_hook(kit, "/nonexistent/" + "PLANTED-" * 40)
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "hook command not found: a path that cannot be shown" in out
    assert "PLANTED" not in out


@pytest.mark.parametrize("value", ["x", [], 5, None, True])
def test_a_hooks_block_of_the_wrong_type_is_named_once(kit, value):
    edit_json(kit, "settings.json", lambda d: d.update(hooks=value))
    for args in (("--verbose",), ("--quick", "--verbose")):
        rc, out = check(kit, *args)
        assert rc == 1, out
        assert out.count("[fail] settings.json: hooks is not an object") == 1
        assert "no longer wired" not in out and "hook commands resolve" not in out
        assert "check failed" not in out


def test_odd_shapes_inside_the_hooks_block_are_named(kit):
    def change(data):
        data["hooks"]["PreToolUse"] = "x"
        data["hooks"]["PostToolUse"] = ["x", {"hooks": "y"}, {"hooks": [5]}]
        data["hooks"]["PLANTED event\nname"] = 3

    edit_json(kit, "settings.json", change)
    rc, out = check(kit, "--quick", "--verbose")
    assert rc == 1, out
    for line in (
        "the hooks under PreToolUse are not a list",
        "a hook group under PostToolUse has no list of hooks",
        "a hook under PostToolUse is not an object",
        "the hooks under one event are not a list",
    ):
        assert f"[fail] settings.json: {line}" in out, line
    assert "hook commands resolve" not in out and "PLANTED" not in out
    assert "check failed" not in out


def test_every_name_the_kit_wires_is_one_the_report_shows():
    path = REPO / "claude" / "config" / "settings.template.json"
    template = json.loads(path.read_text())
    for kind in ("deny", "ask"):
        for rule in template["permissions"][kind]:
            assert check_py.PLAIN_RULE.fullmatch(rule), rule
    for event, groups in template["hooks"].items():
        assert check_py.PLAIN_EVENT.fullmatch(event), event
        for group in groups:
            assert check_py.PLAIN_MATCHER.fullmatch(group.get("matcher", "")), group
            for hook in group["hooks"]:
                name = os.path.basename(hook["command"])
                assert check_py.PLAIN_NAME.fullmatch(name), name
                for arg in hook.get("args", []):
                    assert check_py.PLAIN_NAME.fullmatch(arg), arg


# ---------------------------------------------------------------- updates

ON = {"PIPELINEKIT_UPDATE_CHECK": "1"}


def git(kit, cwd, *args):
    p = subprocess.run(
        [
            "git",
            "-C",
            str(cwd),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        capture_output=True,
        text=True,
        env=kit["env"],
    )
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.fixture
def tracked(kit, tmp_path):
    """The install says it came from a checkout whose origin is a local repo."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(kit, tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(kit, tmp_path, "init", "-q", "-b", "main", str(work))
    (work / "f0").write_text("0\n")
    git(kit, work, "add", "f0")
    git(kit, work, "commit", "-qm", "feat: start")
    git(kit, work, "remote", "add", "origin", str(origin))
    git(kit, work, "push", "-q", "origin", "main")
    head = git(kit, work, "rev-parse", "HEAD")
    edit_json(
        kit,
        "pipelinekit/manifest.json",
        lambda d: d.update(checkout=str(work), branch="main", commit=head),
    )
    return {"kit": kit, "work": work, "origin": origin, "head": head}


def commit_in(t, repo, subject="feat: more"):
    n = len(list(repo.iterdir()))
    (repo / f"f{n}").write_text("x\n")
    git(t["kit"], repo, "add", "-A")
    git(t["kit"], repo, "commit", "-qm", subject)
    return git(t["kit"], repo, "rev-parse", "HEAD")


def push_commit(t, subject="feat: more"):
    """Somebody else pushes to origin; the checkout does not know yet."""
    other = t["work"].parent / "other"
    if not other.exists():
        git(t["kit"], other.parent, "clone", "-q", str(t["origin"]), str(other))
    new = commit_in(t, other, subject)
    git(t["kit"], other, "push", "-q", "origin", "main")
    return new


def cache(kit):
    return state(kit) / "update.json"


def test_up_to_date(tracked):
    kit = tracked["kit"]
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0, out
    line = (
        f"[pass] up to date with origin/main ({tracked['head'][:7]}, checked just now)"
    )
    assert "Updates\n" in out and line in out
    assert out.rstrip().endswith("Result: healthy")
    saved = json.loads(cache(kit).read_text())
    assert saved["state"] == "ok" and saved["commit"] == tracked["head"]
    assert cache(kit).stat().st_mode & 0o777 == 0o600


def test_update_available_is_information_not_a_problem(tracked):
    kit = tracked["kit"]
    new = push_commit(tracked)
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert (
        f"[info] update available: origin/main is at {new[:7]}, "
        f"this install is from {tracked['head'][:7]} (checked just now)"
    ) in out
    assert "fix: /kit update in a session, or from a shell: python3 " in out
    assert "[warn]" not in out and out.rstrip().endswith("Result: healthy")
    rc, out = check(kit, "--json", env=ON)
    d = json.loads(out)
    assert rc == 0 and d["healthy"] is True
    assert d["update"]["state"] == "available"
    assert d["update"]["remote"] == new and d["update"]["installed"] == tracked["head"]


def test_update_counts_the_commits_it_can_see(tracked):
    kit = tracked["kit"]
    push_commit(tracked)
    new = push_commit(tracked)
    git(kit, tracked["work"], "fetch", "-q", "origin")
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert f"origin/main is at {new[:7]}, 2 commits ahead, this install" in out


def test_remote_is_asked_once_a_day(tracked):
    kit = tracked["kit"]
    check(kit, env=ON)
    new = push_commit(tracked)
    rc, out = check(kit, "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out
    saved = json.loads(cache(kit).read_text())
    saved["checked_at"] -= 5 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--verbose", env=ON)
    assert "up to date with origin/main" in out and "checked 5 hours ago" in out
    saved["checked_at"] -= 20 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, env=ON)
    assert f"update available: origin/main is at {new[:7]}" in out, out


@pytest.mark.parametrize(
    "junk", ["", "not json", "[]", '{"state": "ok"}', '{"checked_at": true}']
)
def test_broken_cache_is_ignored(tracked, junk):
    kit = tracked["kit"]
    cache(kit).parent.mkdir(parents=True, exist_ok=True)
    cache(kit).write_text(junk)
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0 and "[pass] up to date with origin/main" in out, out


def test_cache_of_another_checkout_is_not_used(tracked):
    kit = tracked["kit"]
    check(kit, env=ON)
    saved = json.loads(cache(kit).read_text())
    saved.update(checkout="/somewhere/else", commit="0" * 40)
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out


def test_unreachable_origin_is_not_a_problem(tracked):
    kit = tracked["kit"]
    git(
        kit, tracked["work"], "remote", "set-url", "origin", str(tracked["work"] / "no")
    )
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert "[info] not checked: origin did not answer" in out
    assert out.rstrip().endswith("Result: healthy")
    assert json.loads(cache(kit).read_text())["state"] == "unreachable"
    # An hour later it is asked again; an answer would be kept for a day.
    git(kit, tracked["work"], "remote", "set-url", "origin", str(tracked["origin"]))
    rc, out = check(kit, env=ON)
    assert "not checked: origin did not answer" in out
    saved = json.loads(cache(kit).read_text())
    saved["checked_at"] -= 2 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out


def test_branch_gone_from_origin(tracked):
    kit = tracked["kit"]
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(branch="old"))
    rc, out = check(kit, env=ON)
    assert rc == 0 and "[info] not checked: origin has no branch old" in out, out


@pytest.mark.parametrize(
    "change, said",
    [
        ({"checkout": "/no/such/checkout"}, "the checkout this install was made from"),
        ({"checkout": ""}, "the checkout this install was made from"),
        ({"commit": "abc"}, "the install manifest names no commit"),
        ({"branch": ""}, "the install was made from a checkout that was on no branch"),
        (
            {"branch": "--upload-pack=touch pwned"},
            "the install was made from a checkout that was on no branch",
        ),
    ],
)
def test_update_not_checked(tracked, change, said):
    kit = tracked["kit"]
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(change))
    rc, out = check(kit, env=ON, cwd=tracked["work"].parent)
    assert rc == 0, out
    assert f"[info] not checked: {said}" in out
    assert not cache(kit).exists()
    assert not (tracked["work"].parent / "pwned").exists()


def test_update_check_switched_off(tracked):
    kit = tracked["kit"]
    push_commit(tracked)
    rc, out = check(kit)
    assert rc == 0, out
    assert "[info] the update check is switched off (PIPELINEKIT_UPDATE_CHECK=0)" in out
    assert "update available" not in out and not cache(kit).exists()


def test_quick_has_no_update_check(tracked):
    kit = tracked["kit"]
    rc, out = check(kit, "--quick", "--verbose", env=ON)
    assert rc == 0 and "Updates" not in out and not cache(kit).exists(), out
    assert json.loads(check(kit, "--quick", "--json", env=ON)[1])["update"] == {}


def test_no_remote_uses_only_a_recent_answer(tracked):
    kit = tracked["kit"]
    rc, out = check(kit, "--no-remote", "--verbose", env=ON)
    assert rc == 0 and "Updates" not in out and not cache(kit).exists(), out
    check(kit, env=ON)
    rc, out = check(kit, "--no-remote", "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out


def test_checkout_ahead_of_the_install(tracked):
    kit = tracked["kit"]
    new = commit_in(tracked, tracked["work"])
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0, out
    assert (
        f"[info] the checkout is at {new[:7]}, this install was made from "
        f"{tracked['head'][:7]}: the installer brings the install in line"
    ) in out
    assert "fix: bash " in out and "scripts/install.sh" in out
    assert "[pass] up to date with origin/main" in out


def test_install_ahead_of_origin(tracked):
    kit = tracked["kit"]
    new = commit_in(tracked, tracked["work"])
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(commit=new))
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0, out
    assert f"[pass] ahead of origin/main: this install is from {new[:7]}" in out
    assert "update available" not in out


def test_remote_call_ends_with_its_children():
    start = time.time()
    rc, out = check_py.run_group(
        ["sh", "-c", "sleep 30 & sleep 30"], dict(os.environ), 1
    )
    assert (rc, out) == (None, "") and time.time() - start < 10
    assert check_py.run_group(["/no/such/program"], dict(os.environ), 1) == (None, "")
    assert check_py.run_group(["sh", "-c", "echo hi"], dict(os.environ), 5) == (
        0,
        "hi\n",
    )


def test_age_in_words():
    assert check_py.age(5) == "just now"
    assert check_py.age(600) == "10 minutes ago"
    assert check_py.age(3 * 3600) == "3 hours ago"


# ---------------------------------------------------------------- sandbox


@pytest.fixture
def with_gh(kit, tmp_path):
    """A gh on PATH, so the check does not depend on the machine's own."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\necho 'gh version 2.0.0 (test)'\n")
    (bin_dir / "gh").chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{kit['env']['PATH']}"}


def test_sandbox_denies_gh_its_login(kit, with_gh):
    edit_json(kit, "settings.json", lambda d: d.update(sandbox={"enabled": True}))
    rc, out = check(kit, env=with_gh)
    assert rc == 0, out
    assert "[warn] the Bash sandbox is on and applies the deny rule for the gh" in out
    assert 'fix: add "gh *" to sandbox.excludedCommands in settings.json' in out
    assert "Result: working, 1 warning" in out
    assert "sandbox" not in check(kit, "--quick", env=with_gh)[1]


@pytest.mark.parametrize("excluded", [["gh *"], ["docker", "gh"], ["gh:*"]])
def test_sandbox_with_gh_excluded(kit, with_gh, excluded):
    box = {"enabled": True, "excludedCommands": excluded}
    edit_json(kit, "settings.json", lambda d: d.update(sandbox=box))
    rc, out = check(kit, "--verbose", env=with_gh)
    assert rc == 0 and "[warn]" not in out, out
    assert "[pass] gh is excluded from the Bash sandbox" in out


@pytest.mark.parametrize(
    "box",
    [
        None,
        {},
        {"enabled": False},
        {"enabled": "yes"},
        "on",
        {"enabled": True, "excludedCommands": ["ghost"]},
    ],
)
def test_sandbox_off_or_gh_not_excluded(kit, with_gh, box):
    edit_json(kit, "settings.json", lambda d: d.update(sandbox=box))
    rc, out = check(kit, "--verbose", env=with_gh)
    assert rc == 0, out
    warned = isinstance(box, dict) and box.get("enabled") is True
    assert ("[warn] the Bash sandbox is on" in out) is warned
    assert "gh is excluded" not in out


def test_refused_read_is_told_from_a_closed_file(tmp_path, monkeypatch):
    login = tmp_path / "hosts.yml"
    assert check_py.read_refused(str(login)) is False  # no file
    login.write_text("x\n")
    assert check_py.read_refused(str(login)) is False  # readable
    login.chmod(0)
    assert check_py.read_refused(str(login)) is False  # closed by its owner
    login.chmod(0o600)

    def refuse(*_a, **_k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(check_py.os, "open", refuse)
    assert check_py.read_refused(str(login)) is True


def test_gh_login_file_follows_the_environment(monkeypatch):
    monkeypatch.setenv("GH_CONFIG_DIR", "/a/gh")
    assert check_py.gh_login_file() == "/a/gh/hosts.yml"
    monkeypatch.delenv("GH_CONFIG_DIR")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/b")
    assert check_py.gh_login_file() == "/b/gh/hosts.yml"


def test_the_repair_command_keeps_an_install_without_serena_that_way(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    _, out = check(kit, "--quick")
    assert out.rstrip().endswith(
        f"Next: run bash {REPO}/scripts/install.sh --no-serena, then /kit again."
    )
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(serena=True))
    _, out = check(kit, "--quick")
    assert out.rstrip().endswith(
        f"Next: run bash {REPO}/scripts/install.sh, then /kit again."
    )
