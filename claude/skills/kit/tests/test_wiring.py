"""Paths the report shows once and plainly, and the kit's SessionStart entry.

check_wiring.py; the install comes from test_check.py.
"""

import importlib.util
import json
import subprocess
import sys

import pytest
import test_check as base
from test_check import KIT, REPO, add_hook, check, edit_json, git_config

sys.path.insert(0, str(KIT))
_spec = importlib.util.spec_from_file_location("check_wiring", KIT / "check_wiring.py")
wiring = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wiring)

# The install of test_check.py, made once for this module too.
installed = base.installed
kit = base.kit

TEMPLATE = REPO / "claude" / "config" / "settings.template.json"
SESSION = "[warn] settings.json: the kit's SessionStart entry for session-check.py"


# ---------------------------------------------------------------- the module


@pytest.mark.parametrize(
    "value",
    ["/home/u/.claude/git-hooks", ".husky", "/a b/c", "~/x", "/", "/x"],
)
def test_a_plain_path_is_shown(value):
    assert wiring.shown_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "/else'where",
        '"/x"',
        "/x;",
        "/x$(id)",
        "/x\n[pass] fine",
        "/a  b",
        "/x\u202e",
        "/" + "a" * 200,
        "",
        None,
        5,
    ],
)
def test_a_path_with_punctuation_is_not_shown(value):
    assert wiring.shown_path(value) == ""


@pytest.mark.parametrize(
    "command, program",
    [
        ('"/a b/h.py" --x', "/a b/h.py"),
        ("/x/hook.py; echo hi", "/x/hook.py"),
        ("/x/hook.py&&true", "/x/hook.py"),
        ("/x/hook.py|cat", "/x/hook.py"),
        ("python3 -u '/x/h.py' arg", "/x/h.py"),
        ("env A=1 bash /x/h.sh", "/x/h.sh"),
        ('"/x/h.py', "/x/h.py"),
        ("/x/h.py\xa0Your\xa0install", "/x/h.py"),
        ("", ""),
        ("; /x/h.py", ""),
    ],
)
def test_the_program_is_read_as_a_shell_reads_it(command, program):
    assert wiring.program(command) == program


def test_the_kit_values_are_the_template_entry():
    template = json.loads(TEMPLATE.read_text())
    entries = [
        h
        for g in template["hooks"][wiring.SESSION_EVENT]
        for h in g["hooks"]
        if h["command"].endswith("/" + wiring.SESSION_HOOK)
    ]
    assert len(entries) == 1
    assert entries[0]["type"] == wiring.SESSION_TYPE
    assert entries[0]["timeout"] == wiring.SESSION_TIMEOUT


@pytest.mark.parametrize(
    "entry, problems",
    [
        ({"type": "command", "timeout": 5}, []),
        ({"type": "command", "timeout": 5.0}, []),
        ({"type": "prompt", "timeout": 5}, ["has the type prompt"]),
        ({"type": "x;y", "timeout": 5}, ["has another type"]),
        ({"timeout": 5}, ["has no type"]),
        ({"type": "command", "timeout": 60}, ["has a timeout of 60 seconds"]),
        ({"type": "command"}, ["has no timeout"]),
        ({"type": "command", "timeout": "5"}, ["a timeout that is not a number"]),
        ({"type": "command", "timeout": True}, ["a timeout that is not a number"]),
        ({"type": "agent"}, ["has the type agent", "has no timeout"]),
    ],
)
def test_entry_problems(entry, problems):
    found = wiring.entry_problems(entry)
    assert len(found) == len(problems), found
    for line, want in zip(found, problems, strict=True):
        assert want in line, line


# ---------------------------------------------------------------- the entry


def change_session_entry(kit, change):
    def edit(data):
        for g in data["hooks"]["SessionStart"]:
            for h in g["hooks"]:
                if h["command"].endswith("/session-check.py"):
                    change(h)

    edit_json(kit, "settings.json", edit)


def test_session_entry_with_another_type_is_a_warning(kit):
    change_session_entry(kit, lambda h: h.update(type="prompt"))
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert f"{SESSION} has the type prompt, where the kit sets command" in out
    assert "fix: run the repair command at the end of the report" in out
    assert "Result: working, 1 warning" in out
    assert out.rstrip().splitlines()[-1].startswith("Repair: bash "), out


@pytest.mark.parametrize(
    "change, said",
    [
        (lambda h: h.update(timeout=60), "has a timeout of 60 seconds"),
        (lambda h: h.pop("timeout"), "has no timeout"),
        (lambda h: h.update(timeout="5"), "has a timeout of a timeout that"),
    ],
)
def test_session_entry_with_another_timeout_is_a_warning(kit, change, said):
    change_session_entry(kit, change)
    rc, out = check(kit)
    assert rc == 0, out
    assert f"{SESSION} {said}" in out
    assert "where the kit sets 5 seconds" in out
    assert "Result: working, 1 warning" in out


def test_disable_all_hooks_is_a_warning(kit):
    edit_json(kit, "settings.json", lambda d: d.update(disableAllHooks=True))
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "[warn] settings.json: disableAllHooks is set, so Claude Code runs" in out
    assert "fix: remove disableAllHooks from settings.json" in out
    assert "Result: working, 1 warning" in out
    edit_json(kit, "settings.json", lambda d: d.update(disableAllHooks=False))
    rc, out = check(kit, "--quick")
    assert rc == 0 and "Result: healthy" in out, out


def test_healthy_install_has_no_repair_line(kit):
    rc, out = check(kit, "--quick")
    assert rc == 0 and "Repair:" not in out, out


# ---------------------------------------------------------------- paths


@pytest.mark.parametrize(
    "command, shown",
    [
        ('"/nonexistent/x.py";', "/nonexistent/x.py"),
        ("/nonexistent/x.py&&true", "/nonexistent/x.py"),
        ("'/nonexistent/my hook.py' --x", "/nonexistent/my hook.py"),
        ("/nonexistent/$(id).py", "a path that cannot be shown"),
    ],
)
def test_a_missing_hook_path_is_shown_plainly(kit, command, shown):
    add_hook(kit, command)
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    line = next(x for x in out.splitlines() if "runs a file that is not there" in x)
    assert line.endswith(f"not there: {shown}"), line
    assert '"' not in line and "'" not in line, line


def test_a_changed_hooks_path_is_named_once(kit):
    git_config(kit, "--global", "core.hooksPath", "/elsewhere")
    rc, out = check(kit, "--quick")
    assert rc == 1, out
    line = next(x for x in out.splitlines() if "[fail] git:" in x)
    assert "is now /elsewhere, so commit-msg" in line, line
    assert line.count("elsewhere") == 1 and "'/" not in line, line


def test_a_hooks_path_with_a_quote_is_not_shown(kit):
    git_config(kit, "--global", "core.hooksPath", "/qq'zz")
    _, out = check(kit, "--quick")
    assert "is now set to a path that cannot be shown" in out, out
    assert "qq" not in out, out


def test_a_repository_hooks_path_with_a_quote_is_not_shown(kit, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=kit["env"])
    git_config(kit, "core.hooksPath", '.qq"zz', cwd=tmp_path)
    rc, out = check(kit, cwd=tmp_path)
    assert "[warn] this repository sets its own core.hooksPath: the kit" in out
    assert "qq" not in out, out


def test_the_checkout_is_named_once(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    add_hook(kit, f"python3 {kit['home'] / 'hooks' / 'session-check.py'}")
    change_session_entry(kit, lambda h: h.update(timeout=60))
    rc, out = check(kit, "--quick")
    assert rc == 1, out
    assert out.count(str(REPO)) == 1, out
    rc, out = check(kit, "--quick", "--json")
    d = json.loads(out)
    assert "checkout" not in d["kit"]
    assert json.dumps(d).count(str(REPO)) == 1, out
    assert d["repair"].startswith(f"bash {REPO}/scripts/install.sh")
