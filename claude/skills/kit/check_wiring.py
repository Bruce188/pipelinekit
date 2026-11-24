"""How settings.json wires the kit, and the paths the report shows.

Part of the self-check (check.py). A path the report repeats from
settings.json, the git config or the install manifest is shown only when it
reads as a plain path: no shell quoting, no punctuation, nothing that draws
as something else. The program a hook command runs is read the way a shell
reads it, so quotes and what follows a `;` or `&&` are not part of it.

Two settings switch kit hooks off without removing them: a SessionStart entry
of session-check.py whose type or timeout is no longer the one the installer
wrote, and `disableAllHooks`. Both are a `[warn]`. Stdlib only.
"""

from __future__ import annotations

import os
import re
import shlex

import hook_command

# A test keeps these equal to the entry in settings.template.json.
SESSION_EVENT = "SessionStart"
SESSION_HOOK = "session-check.py"
SESSION_TYPE = "command"
SESSION_TIMEOUT = 5
MAX_PATH = 120
_PART = r"[A-Za-z0-9._@+=,~-]+"
# Parts of letters, digits and ._@+=,~- joined by / or one space.
PLAIN_PATH = re.compile(rf"/?{_PART}(?:(?:/| ){_PART})*/?|/")
PLAIN_TYPE = re.compile(r"[A-Za-z]{1,20}")
# What a shell takes as the end of one command.
OPERATOR = re.compile(r"[();<>|&]+")


def shown_path(value: object) -> str:
    """The value when it reads as a plain path, else ""."""
    if not isinstance(value, str) or len(value) > MAX_PATH:
        return ""
    return value if PLAIN_PATH.fullmatch(value) else ""


def words(command: str) -> list[str]:
    """The words of the command's first part, quotes removed, as a shell splits them.

    Any kind of space separates words, as hook_command reads them. A command
    a shell cannot split (an open quote) is split at spaces.
    """
    text = "".join(" " if ch.isspace() else ch for ch in command)
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        found = list(lexer)
    except ValueError:
        return [w.strip("'\"") for w in text.split()]
    for i, w in enumerate(found):
        if OPERATOR.fullmatch(w):
            return found[:i]
    return found


def program(command: str) -> str:
    """The file the command runs: its first word, or the script an interpreter gets."""
    found = words(command)
    if not found:
        return ""
    if hook_command.INTERPRETER.fullmatch(os.path.basename(found[0])):
        for w in found[1:]:
            name = os.path.basename(w)
            if hook_command.INTERPRETER.fullmatch(name):
                continue
            if hook_command.BEFORE_SCRIPT.fullmatch(w):
                continue
            return w
    return found[0]


def session_entries(settings: dict, hooks_dir: str) -> list[dict]:
    """The SessionStart hook entries that run the kit's session-check.py."""
    hooks = settings.get("hooks")
    groups = hooks.get(SESSION_EVENT) if isinstance(hooks, dict) else None
    where = os.path.normpath(hooks_dir)
    found = []
    for g in groups if isinstance(groups, list) else ():
        entries = g.get("hooks") if isinstance(g, dict) else None
        for h in entries if isinstance(entries, list) else ():
            command = h.get("command") if isinstance(h, dict) else None
            if not isinstance(command, str):
                continue
            script = os.path.normpath(hook_command.expand(program(command) or "."))
            if script == os.path.join(where, SESSION_HOOK):
                found.append(h)
    return found


def entry_problems(h: dict) -> list[str]:
    """What in one session-check.py entry differs from what the kit wrote."""
    out = []
    kind = h.get("type")
    if kind is None:
        out.append(f"has no type, where the kit sets {SESSION_TYPE}")
    elif kind != SESSION_TYPE:
        shown = kind if isinstance(kind, str) and PLAIN_TYPE.fullmatch(kind) else ""
        out.append(
            (f"has the type {shown}" if shown else "has another type")
            + f", where the kit sets {SESSION_TYPE}"
        )
    limit = h.get("timeout")
    if "timeout" not in h:
        out.append(f"has no timeout, where the kit sets {SESSION_TIMEOUT} seconds")
    elif limit != SESSION_TIMEOUT or isinstance(limit, bool):
        number = (
            isinstance(limit, (int, float))
            and not isinstance(limit, bool)
            and 0 <= limit < 1e6
        )
        shown = f"{limit:g} seconds" if number else "a timeout that is not a number"
        out.append(
            f"has a timeout of {shown}, where the kit sets {SESSION_TIMEOUT} seconds"
        )
    return out


def check(c, repair_fix: str) -> None:
    """Warn about settings that keep kit hooks from running as installed."""
    settings = c.settings if isinstance(c.settings, dict) else {}
    if settings.get("disableAllHooks") is True:
        c.add(
            "install",
            "warn",
            "settings.json: disableAllHooks is set, so Claude Code runs no hook: "
            "not the kit's guards and not the session-start check",
            fix="remove disableAllHooks from settings.json; the installer leaves it",
        )
    for h in session_entries(settings, c.path("hooks")):
        for why in entry_problems(h):
            c.add(
                "install",
                "warn",
                f"settings.json: the kit's {SESSION_EVENT} entry for "
                f"{SESSION_HOOK} {why}",
                fix=repair_fix,
            )
