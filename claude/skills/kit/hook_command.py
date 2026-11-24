"""Which file a hook command in settings.json runs.

A command can start its script through an interpreter, as in
`python3 ~/.claude/hooks/session-check.py`. check.py and the installer both
need the script then: the installer to replace the kit's entries instead of
adding a second one, check.py to find a file that is missing and a kit hook
that is wired twice. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re

INTERPRETER = re.compile(r"python3?(\.\d+)?|bash|sh|env")
# What comes between an interpreter and the script: options, env's NAME=value.
BEFORE_SCRIPT = re.compile(r"-.*|[A-Za-z_][A-Za-z0-9_]*=.*")


def split(command: str) -> tuple[str, list[str]]:
    """(the file the command runs, the words after it), quotes around a word dropped."""
    words = [w.strip("'\"") for w in command.split()]
    if not words:
        return "", []
    if INTERPRETER.fullmatch(os.path.basename(words[0])):
        for i, w in enumerate(words[1:], 1):
            if INTERPRETER.fullmatch(os.path.basename(w)) or BEFORE_SCRIPT.fullmatch(w):
                continue
            return w, words[i + 1 :]
    return words[0], words[1:]


def program(command: str) -> str:
    """The file the command runs: its first word, or the script an interpreter gets."""
    return split(command)[0]


def expand(path: str) -> str:
    """The path with ~, $HOME and ${HOME} filled in."""
    home = os.path.expanduser("~")
    return os.path.expanduser(path).replace("${HOME}", home).replace("$HOME", home)


def wired_twice(
    hooks: object, hooks_dir: str, names: tuple[str, ...]
) -> list[tuple[str, str, int]]:
    """(event, hook, times) for each kit hook that runs more than once on one event.

    A kit hook is a file in hooks_dir with one of the names. Two entries count
    as the same when they give it the same arguments and condition, whatever
    starts it and whatever their matcher.
    """
    seen: dict[tuple[str, str, str], int] = {}
    where = os.path.normpath(hooks_dir)
    for event, groups in hooks.items() if isinstance(hooks, dict) else ():
        for g in groups if isinstance(groups, list) else ():
            entries = g.get("hooks") if isinstance(g, dict) else None
            for h in entries if isinstance(entries, list) else ():
                command = h.get("command") if isinstance(h, dict) else None
                if not isinstance(command, str):
                    continue
                script, rest = split(command)
                script = os.path.normpath(expand(script)) if script else ""
                name = os.path.basename(script)
                if os.path.dirname(script) != where or name not in names:
                    continue
                args = h.get("args") if isinstance(h.get("args"), list) else []
                how = json.dumps([rest, args, h.get("if")], default=str)
                key = (str(event), name, how)
                seen[key] = seen.get(key, 0) + 1
    return [(event, name, n) for (event, name, _), n in seen.items() if n > 1]
