"""hook_command.py: which file a hook command in settings.json runs."""

import importlib.util
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("hook_command", KIT / "hook_command.py")
hook_command = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook_command)

KIT_HOOKS = ("bash-guard.py", "session-check.py")


@pytest.mark.parametrize(
    "command, script",
    [
        ("/h/hooks/x.py", "/h/hooks/x.py"),
        ("/h/hooks/x.py git git", "/h/hooks/x.py"),
        ("python3 /h/hooks/x.py", "/h/hooks/x.py"),
        ("/usr/bin/python3.12 -u /h/hooks/x.py", "/h/hooks/x.py"),
        ("/usr/bin/env python3 /h/hooks/x.py", "/h/hooks/x.py"),
        ("env FOO=1 bash /h/hooks/x.sh arg", "/h/hooks/x.sh"),
        ("'/h/hooks/x.py'", "/h/hooks/x.py"),
        ("/nonexistent/x\xa0Your\u2003install", "/nonexistent/x"),
        ("echo my-hook", "echo"),
        ("python3", "python3"),
        ("", ""),
    ],
)
def test_the_script_a_command_runs(command, script):
    assert hook_command.program(command) == script


def group(command, **extra):
    return {"matcher": "startup", "hooks": [{"command": command, **extra}]}


def test_a_kit_hook_started_two_ways_is_wired_twice():
    hooks = {
        "SessionStart": [
            group("/h/hooks/session-check.py", args=[]),
            group("python3 /h/hooks/session-check.py"),
        ],
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {"command": "/h/hooks/bash-guard.py", "args": ["git", "git"]},
                    {"command": "/h/hooks/bash-guard.py", "args": ["sql", "psql"]},
                ],
            }
        ],
    }
    assert hook_command.wired_twice(hooks, "/h/hooks", KIT_HOOKS) == [
        ("SessionStart", "session-check.py", 2)
    ]


@pytest.mark.parametrize(
    "second",
    [
        "/elsewhere/session-check.py",  # not the kit's file
        "/h/hooks/my-check.py",  # not a kit hook
        "/h/hooks/session-check.py --other",  # other arguments
    ],
)
def test_what_is_not_wired_twice(second):
    hooks = {"SessionStart": [group("/h/hooks/session-check.py"), group(second)]}
    assert hook_command.wired_twice(hooks, "/h/hooks", KIT_HOOKS) == []


@pytest.mark.parametrize(
    "hooks", [None, [], {"SessionStart": "x"}, {"SessionStart": [{"hooks": 7}, 5]}]
)
def test_a_hooks_block_of_the_wrong_shape_has_nothing_wired_twice(hooks):
    assert hook_command.wired_twice(hooks, "/h/hooks", KIT_HOOKS) == []
