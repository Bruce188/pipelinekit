"""check.py: a healthy install passes and each way it can break is reported."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
CHECK = KIT / "check.py"
REPO = KIT.parents[2]

_spec = importlib.util.spec_from_file_location("kit_check", CHECK)
check_py = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_py)


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """One real install into a throwaway HOME, kept as a template."""
    root = tmp_path_factory.mktemp("kit")
    user = root / "home"
    user.mkdir()
    env = dict(
        os.environ,
        HOME=str(user),
        CLAUDE_HOME=str(user / ".claude"),
        USER_NAME="Test User",
        USER_EMAIL="test@example.com",
        GIT_CONFIG_GLOBAL=str(user / ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        XDG_CONFIG_HOME=str(user / ".config"),
        PIPELINEKIT_GIT_HOOKS="1",
    )
    # The event log then sits below the throwaway HOME, as on a real machine.
    for k in (
        "ALLOW_MAIN_PUSH",
        "PIPELINEKIT_ALLOW_SECRET",
        "PIPELINEKIT_STATE_DIR",
        "PIPELINEKIT_LOG",
        "XDG_STATE_HOME",
    ):
        env.pop(k, None)
    p = subprocess.run(
        ["bash", str(REPO / "scripts" / "install.sh"), "--no-serena"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    shutil.copytree(user, root / "template", symlinks=True)
    return {"root": root, "user": user, "home": user / ".claude", "env": env}


@pytest.fixture
def kit(installed):
    """A fresh copy of the install at the same path (settings hold that path)."""
    shutil.rmtree(installed["user"])
    shutil.copytree(installed["root"] / "template", installed["user"], symlinks=True)
    return installed


def check(kit, *args, cwd=None, env=None):
    p = subprocess.run(
        [sys.executable, str(CHECK), *args],
        capture_output=True,
        text=True,
        env=dict(kit["env"], **(env or {})),
        cwd=cwd or kit["root"],
    )
    return p.returncode, p.stdout + p.stderr


def replace_script(kit, rel, body):
    path = kit["home"] / rel
    path.write_text(body)
    path.chmod(0o755)


def edit_json(kit, rel, change):
    path = kit["home"] / rel
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2))


def snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------- healthy


def test_healthy_install(kit):
    rc, out = check(kit)
    assert rc == 0, out
    assert out.startswith("pipelinekit ")
    assert "[fail]" not in out and "[warn]" not in out
    assert "Live probe" in out
    assert out.rstrip().endswith("Result: healthy")


def test_verbose_lists_every_probe(kit):
    rc, out = check(kit, "--verbose")
    assert rc == 0, out
    for line in (
        "[pass] bash-guard.py: 5 probes as expected",
        "[pass] block-bare-repo-markers.py: 2 probes as expected",
        "[pass] post-edit-format.sh: 1 probe as expected",
        "[pass] commit-msg: 2 probes as expected",
        "[pass] pre-commit: 1 probe as expected",
        "[pass] pre-push: 2 probes as expected",
        "[pass] event log: 4 refusals recorded",
        "[pass] hook helper: kitlog.py",
        "[pass] git: global core.hooksPath set",
        "[pass] settings.json: 11 kit hook entries wired",
    ):
        assert line in out, out


def test_quick_skips_the_probes(kit):
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "(quick check)" in out and "Live probe" not in out


def test_check_changes_nothing(kit):
    before = snapshot(kit["user"])
    check(kit)
    check(kit, "--quick")
    assert snapshot(kit["user"]) == before


# ---------------------------------------------------------------- files


def test_missing_hook_is_reported_once(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] hook missing: bash-guard.py" in out
    assert "settings.json: hook command not found" in out
    assert "missing: hooks/bash-guard.py" not in out
    assert "bash-guard.py does not start" not in out
    assert "Repair: bash " in out


def test_hook_not_executable(kit):
    (kit["home"] / "hooks" / "block-bare-repo-markers.py").chmod(0o644)
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] hook not executable: block-bare-repo-markers.py" in out


@pytest.mark.parametrize("mode", [(), ("--quick",)])
def test_crlf_hook(kit, mode):
    guard = kit["home"] / "hooks" / "bash-guard.py"
    guard.write_bytes(guard.read_bytes().replace(b"\n", b"\r\n"))
    rc, out = check(kit, *mode)
    assert rc == 1
    assert "hook has CRLF line endings and cannot start: bash-guard.py" in out


def test_missing_git_hook(kit):
    (kit["home"] / "git-hooks" / "pre-push").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] git hook missing: pre-push" in out


def test_removed_skill_is_one_line(kit):
    shutil.rmtree(kit["home"] / "skills" / "mobile")
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] skill missing: mobile" in out
    assert out.count("mobile") == 1, out


def test_removed_skill_file(kit):
    (kit["home"] / "skills" / "kit" / "check.py").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] missing: skills/kit/check.py" in out


def test_edited_skill_file_is_only_a_warning(kit):
    with open(kit["home"] / "skills" / "deploy" / "SKILL.md", "a") as f:
        f.write("\nmy own note\n")
    rc, out = check(kit)
    assert rc == 0, out
    assert "[warn] changed since install: skills/deploy/SKILL.md" in out
    assert "Result: working, 1 warning" in out


def test_missing_manifest(kit):
    (kit["home"] / "pipelinekit" / "manifest.json").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] install manifest not found: run the installer once" in out


def test_damaged_manifest_does_not_crash_the_checker(kit):
    (kit["home"] / "pipelinekit" / "manifest.json").write_text(
        '{"files": [], "commit": 5, "hooks_path": 7, "skills": 3,'
        ' "settings": "x", "checkout": 1}'
    )
    rc, out = check(kit)
    assert rc == 1, out
    assert "install manifest lists no files" in out
    assert "check failed" not in out


# ---------------------------------------------------------------- probes


def test_guard_that_allows_everything(kit):
    replace_script(kit, "hooks/bash-guard.py", "#!/usr/bin/env python3\n")
    rc, out = check(kit)
    assert rc == 1
    assert "bash-guard.py: commit --no-verify gave 'allow', expected 'block'" in out
    assert "DROP TABLE through psql gave 'allow', expected 'ask'" in out
    assert "[warn] changed since install: hooks/bash-guard.py" in out
    # Without the probes the same install only shows a changed file.
    rc, out = check(kit, "--quick")
    assert rc == 0, out


def test_guard_that_blocks_everything(kit):
    replace_script(
        kit, "hooks/bash-guard.py", "#!/usr/bin/env python3\nraise SystemExit(2)\n"
    )
    rc, out = check(kit)
    assert rc == 1
    assert "a harmless git command gave 'block', expected 'allow'" in out


def test_guard_that_crashes(kit):
    replace_script(
        kit, "hooks/bash-guard.py", "#!/usr/bin/env python3\nraise RuntimeError\n"
    )
    rc, out = check(kit)
    assert rc == 1
    assert "a harmless git command gave 'exit 1', expected 'allow'" in out


def test_bare_repo_hook_that_allows_everything(kit):
    replace_script(kit, "hooks/block-bare-repo-markers.py", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert "HEAD next to refs/ gave 'allow', expected 'block'" in out


def test_commit_msg_that_accepts_everything(kit):
    replace_script(kit, "git-hooks/commit-msg", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert (
        "commit-msg: a non-conventional message gave 'accept', expected 'reject'" in out
    )


def test_pre_push_that_accepts_main(kit):
    replace_script(kit, "git-hooks/pre-push", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert "pre-push: push to main gave 'accept', expected 'reject'" in out


# ---------------------------------------------------------------- settings


def test_hook_entry_removed_from_settings(kit):
    def drop(d):
        for g in d["hooks"]["PreToolUse"]:
            g["hooks"] = [
                h
                for h in g["hooks"]
                if not h["command"].endswith("block-bare-repo-markers.py")
                and h.get("args") != ["fetch", "curl"]
            ]

    edit_json(kit, "settings.json", drop)
    rc, out = check(kit, "--quick")
    assert rc == 1
    wired = "kit hook no longer wired: PreToolUse"
    assert f"{wired} Edit|Write -> block-bare-repo-markers.py" in out
    assert f"{wired} Bash -> bash-guard.py fetch curl" in out


def test_deny_rule_removed(kit):
    rule = "Read(.env.*)"
    edit_json(kit, "settings.json", lambda d: d["permissions"]["deny"].remove(rule))
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert f"[fail] settings.json: 1 kit deny rule missing: {rule}" in out


def test_ask_rule_removed_is_a_warning(kit):
    edit_json(kit, "settings.json", lambda d: d["permissions"]["ask"].pop())
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "[warn] settings.json: 1 kit ask rule missing" in out


def test_attribution_switched_back_on(kit):
    edit_json(kit, "settings.json", lambda d: d.pop("attribution"))
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "[fail] settings.json: attribution not disabled" in out


def test_invalid_settings_json(kit):
    (kit["home"] / "settings.json").write_text("{not json")
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] settings.json: unreadable" in out


def test_missing_settings_json(kit):
    (kit["home"] / "settings.json").unlink()
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "[fail] settings.json: missing" in out


# ---------------------------------------------------------------- git


def git_config(kit, *args, cwd=None):
    subprocess.run(
        ["git", "config", *args], check=True, env=kit["env"], cwd=cwd or kit["root"]
    )


def test_hooks_path_changed_since_install(kit):
    git_config(kit, "--global", "core.hooksPath", "/elsewhere")
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "pointed at the kit when it was installed, now '/elsewhere'" in out
    assert f"fix: git config --global core.hooksPath {kit['home']}/git-hooks" in out


def test_hooks_path_never_enabled_is_not_a_problem(kit):
    git_config(kit, "--global", "--unset", "core.hooksPath")
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(hooks_path=""))
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "[info] global core.hooksPath is 'unset' (kit git hooks inactive)" in out


def test_repository_with_its_own_hooks_path(kit, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=kit["env"])
    git_config(kit, "core.hooksPath", ".husky", cwd=tmp_path)
    rc, out = check(kit, cwd=tmp_path)
    assert rc == 0, out
    assert "[warn] this repository sets its own core.hooksPath (.husky)" in out


# ---------------------------------------------------------------- output


def test_json_report(kit):
    rc, out = check(kit, "--json")
    assert rc == 0, out
    d = json.loads(out)
    assert set(d) == {
        "schema",
        "home",
        "mode",
        "kit",
        "healthy",
        "counts",
        "repair",
        "results",
        "activity",
    }
    assert d["healthy"] is True and d["mode"] == "full"
    assert d["counts"]["fail"] == 0 and d["counts"]["pass"] > 20
    assert d["kit"]["checkout"] == str(REPO)
    assert re.fullmatch(r"[0-9a-f]{40}", d["kit"]["commit"])
    assert all({"section", "level", "msg"} <= set(r) for r in d["results"])
    assert {r["section"] for r in d["results"]} == {
        "install",
        "drift",
        "probe",
        "environment",
        "activity",
    }


def test_json_report_of_a_broken_install(kit):
    (kit["home"] / "hooks" / "post-edit-format.sh").unlink()
    rc, out = check(kit, "--json", "--quick")
    d = json.loads(out)
    assert rc == 1 and d["healthy"] is False and d["mode"] == "quick"
    assert d["counts"]["fail"] >= 1
    assert not any(r["section"] == "probe" for r in d["results"])


def test_exit_zero_still_reports_the_problem(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    rc, out = check(kit, "--exit-zero")
    assert rc == 0
    assert "[fail] hook missing: bash-guard.py" in out


def test_messages_are_one_printable_line():
    assert check_py.clean("a\x1b[31mb\nc\td") == "a [31mb c d"
    assert len(check_py.clean("x" * 999)) == 300


def test_remote_url_loses_its_credentials():
    strip = check_py.without_credentials
    assert (
        strip("https://user:token@example.com/o/r.git") == "https://example.com/o/r.git"
    )
    assert strip("https://example.com/o/r.git") == "https://example.com/o/r.git"
    assert strip("git@example.com:o/r.git") == "git@example.com:o/r.git"


# ---------------------------------------------------------------- manifest


def test_manifest_describes_the_install(kit):
    m = json.loads((kit["home"] / "pipelinekit" / "manifest.json").read_text())
    assert m["schema"] == check_py.SCHEMA
    assert m["checkout"] == str(REPO)
    assert m["hooks_path"] == f"{kit['home']}/git-hooks"
    assert m["skills"] == sorted(check_py.KIT_SKILLS)
    files = m["files"]
    for rel in (
        "hooks/bash-guard.py",
        "git-hooks/pre-push",
        "skills/kit/check.py",
        "skills/kit/SKILL.md",
        "config/never-stage.txt",
        "CLAUDE.md",
    ):
        assert rel in files
    assert all(files.values()), "a file was listed but not installed"
    assert not any(
        "__pycache__" in rel or "/tests/" in rel
        for rel in files
        if rel.startswith("hooks/")
    )
    assert len(m["settings"]["hooks"]) == 11
    assert "Read(.env)" in m["settings"]["deny"]


def test_skill_list_matches_the_repo_and_the_installer():
    in_repo = sorted(
        p.name for p in (REPO / "claude" / "skills").iterdir() if p.is_dir()
    )
    assert list(check_py.KIT_SKILLS) == in_repo
    text = (REPO / "scripts" / "install.sh").read_text()
    listed = re.search(r"^KIT_SKILLS=\(([^)]*)\)", text, re.M).group(1).split()
    assert sorted(listed) == in_repo


def test_hook_lists_match_the_repo():
    hooks = sorted(
        p.name
        for p in (REPO / "claude" / "hooks").iterdir()
        if p.is_file() and p.suffix in (".py", ".sh")
    )
    assert sorted(check_py.HOOKS + check_py.HELPERS) == hooks
    git_hooks = sorted(p.name for p in (REPO / "claude" / "git-hooks").iterdir())
    assert sorted(check_py.GIT_HOOKS) == git_hooks


def test_environment_covers_what_the_ship_skill_needs(kit):
    rc, out = check(kit, "--verbose")
    assert rc == 0, out
    assert re.search(r"\[pass\] gh: \S|\[info\] gh not installed", out)
    assert re.search(r"\[pass\] playwright: \S|\[info\] playwright not installed", out)
    rc, out = check(kit, "--verbose", "--quick")
    assert rc == 0 and "playwright" not in out


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
    assert "[pass] event log: 4 refusals recorded" in out, out


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
    hooks = "bash-guard, block-bare-repo-markers, commit-msg, pre-push"
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
