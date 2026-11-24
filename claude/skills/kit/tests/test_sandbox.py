"""The Environment line about the Bash sandbox and gh's login file.

check_sandbox.py; the install comes from test_check.py.
"""

import importlib.util
import os

import pytest
import test_check as base
from test_check import KIT, check, edit_json

_spec = importlib.util.spec_from_file_location(
    "check_sandbox", KIT / "check_sandbox.py"
)
sandbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox)

# The install of test_check.py, made once for this module too.
installed = base.installed
kit = base.kit


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
    assert "[warn] the Bash sandbox is on and applies a deny rule for the gh" in out
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
    assert sandbox.read_refused(str(login)) is False  # no file
    login.write_text("x\n")
    assert sandbox.read_refused(str(login)) is False  # readable
    login.chmod(0)
    assert sandbox.read_refused(str(login)) is False  # closed by its owner
    login.chmod(0o600)

    def refuse(*_a, **_k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(sandbox.os, "open", refuse)
    assert sandbox.read_refused(str(login)) is True


def test_gh_login_file_follows_the_environment(monkeypatch):
    monkeypatch.setenv("GH_CONFIG_DIR", "/a/gh")
    assert sandbox.gh_login_file() == "/a/gh/hosts.yml"
    monkeypatch.delenv("GH_CONFIG_DIR")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/b")
    assert sandbox.gh_login_file() == "/b/gh/hosts.yml"
    assert sandbox.gh_login_file({"GH_CONFIG_DIR": "/c"}) == "/c/hosts.yml"


LOGIN = "/h/.config/gh/hosts.yml"


@pytest.mark.parametrize(
    "rule",
    [
        "Read(~/.config/gh/hosts.yml)",
        "Read(~/.config/gh/**)",
        "Read(~/.config/**)",
        "Read(~/.config/gh)",
        "Read(~/.config/gh/)",
        "Read(~/.config/gh/*.yml)",
        "Read(~/**/hosts.yml)",
        "Read(//h/.config/gh/hosts.yml)",
        "Read(//h/**)",
        "Read(**/hosts.yml)",
        "Read(hosts.yml)",
        "Read(**/gh/**)",
        "Read",
        "Read(/../.config/gh/hosts.yml)",
    ],
)
def test_deny_rules_that_cover_the_login_file(rule):
    assert sandbox.denies_read(rule, LOGIN, "/h", "/h/.claude") is True


@pytest.mark.parametrize(
    "rule",
    [
        "Edit(~/.config/gh/hosts.yml)",
        "Bash(cat ~/.config/gh/hosts.yml)",
        "Read(~/.config/git/**)",
        "Read(~/.config/gh/config.yml)",
        "Read(~/.config/gh/hosts.yml.bak)",
        "Read(~/.config/g/hosts.yml)",
        "Read(.config/gh/hosts.yml)",
        "Read(/.config/gh/hosts.yml)",
        "Read()",
        "Read(//other/**)",
        42,
        None,
    ],
)
def test_deny_rules_that_leave_the_login_file_alone(rule):
    assert sandbox.denies_read(rule, LOGIN, "/h", "/h/.claude") is False


def deny_only(kit, rule, **box):
    def change(d):
        d["permissions"]["deny"] = [rule]
        d["sandbox"] = dict({"enabled": True}, **box)

    edit_json(kit, "settings.json", change)


@pytest.mark.parametrize("rule", ["Read(~/.config/gh/**)", "Read(~/.config/**)"])
def test_a_broader_deny_rule_is_seen(kit, with_gh, rule):
    deny_only(kit, rule)
    rc, out = check(kit, env=with_gh)
    assert "[warn] the Bash sandbox is on and applies a deny rule for the gh" in out


def test_one_excluded_gh_command_does_not_switch_the_warning_off(kit, with_gh):
    box = {"enabled": True, "excludedCommands": ["gh pr list"]}
    edit_json(kit, "settings.json", lambda d: d.update(sandbox=box))
    rc, out = check(kit, "--verbose", env=with_gh)
    assert "[warn] the Bash sandbox is on" in out, out
    assert "sandbox.excludedCommands takes out only some gh commands" in out
    assert "gh is excluded" not in out


@pytest.mark.parametrize("where", ["environment", "settings"])
def test_a_token_in_the_environment_needs_no_login_file(kit, with_gh, where):
    edit_json(kit, "settings.json", lambda d: d.update(sandbox={"enabled": True}))
    env = dict(with_gh)
    if where == "settings":
        edit_json(
            kit, "settings.json", lambda d: d.setdefault("env", {}).update(GH_TOKEN="x")
        )
    else:
        env["GH_TOKEN"] = "x"
    rc, out = check(kit, env=env)
    assert rc == 0 and "[warn]" not in out, out
    assert (
        "[info] gh cannot read its login file (hosts.yml) in the Bash sandbox, "
        "and takes its token from GH_TOKEN instead"
    ) in out


def test_a_login_file_elsewhere_is_not_covered_by_the_kit_rule(kit, with_gh, tmp_path):
    edit_json(kit, "settings.json", lambda d: d.update(sandbox={"enabled": True}))
    env = dict(with_gh, GH_CONFIG_DIR=str(tmp_path / "gh"))
    rc, out = check(kit, "--verbose", env=env)
    assert rc == 0 and "[warn]" not in out and "sandbox" not in out, out
    rule = f"Read(/{tmp_path}/gh/**)"
    deny_only(kit, rule)
    assert "[warn] the Bash sandbox is on" in check(kit, env=env)[1]
