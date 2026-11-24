"""The Bash sandbox and gh's login file: the Environment line about the two.

Part of the self-check (check.py). The kit denies reads of gh's login file
(hosts.yml). With the Bash sandbox on, Claude Code applies that rule to the
commands it runs, gh included, so gh cannot read its own login there. A deny
rule of the user's own that covers the file, such as `Read(~/.config/**)`,
does the same.
"""

from __future__ import annotations

import os
import re
import shutil

# gh takes its token from one of these before it reads the login file.
TOKEN_VARS = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
)
# A sandbox.excludedCommands entry that takes every gh command out of it.
ALL_OF_GH = re.compile(r"gh(?:\s*\*|:\*)?|\*")
FIX = (
    'add "gh *" to sandbox.excludedCommands in settings.json, '
    "or run gh outside the sandbox"
)


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def session_env(settings: dict) -> dict:
    """The environment of a session: this one, with the settings' env on top."""
    env = dict(os.environ)
    for key, value in as_dict(settings.get("env")).items():
        if isinstance(key, str) and isinstance(value, str):
            env[key] = value
    return env


def gh_login_file(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    base = env.get("GH_CONFIG_DIR") or os.path.join(
        env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
        "gh",
    )
    return os.path.join(base, "hosts.yml")


def read_refused(path: str) -> bool:
    """The file is ours and readable by its mode, and opening it is refused.

    That is what a sandbox around this process does. Nothing is read from it.
    """
    try:
        st = os.stat(path)
        if st.st_uid != os.getuid() or not st.st_mode & 0o400:
            return False
        os.close(os.open(path, os.O_RDONLY))
    except PermissionError:
        return True
    except OSError:
        return False
    return False


def glob_regex(pattern: str) -> str:
    """A gitignore-style glob as a regex: * and ? stay within one folder."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return "".join(out)


def denies_read(rule: object, path: str, home: str, settings_dir: str) -> bool:
    """Does this permissions.deny entry keep `path` from being read?

    The paths of Claude Code's rules: `~/` the home folder, `//` the root, `/`
    the folder of the settings file. A pattern without a slash, or one that
    starts with `**/`, matches at any depth. A rule on a folder covers what is
    in it. A pattern relative to the project folder is never decided here.
    """
    m = re.fullmatch(r"\s*Read(?:\((.*)\))?\s*", str(rule), re.S)
    if not m:
        return False
    pattern = "**" if m.group(1) is None else m.group(1).strip()
    if not pattern:
        return False
    if pattern.startswith("~/"):
        rx = glob_regex(os.path.normpath(home + "/" + pattern[2:]))
    elif pattern.startswith("//"):
        rx = glob_regex(os.path.normpath(pattern[1:]))
    elif pattern.startswith("/"):
        rx = glob_regex(os.path.normpath(settings_dir + pattern))
    elif pattern.startswith("**/") or "/" not in pattern.rstrip("/"):
        rx = "(?:.*/)?" + glob_regex(pattern.removeprefix("**/"))
    else:
        return False
    rx = rx.rstrip("/") if len(rx) > 1 else rx
    names = {path, os.path.realpath(path)}
    for name in names:
        while True:
            if re.fullmatch(rx, name, re.S):
                return True
            parent = os.path.dirname(name)
            if parent == name:
                break
            name = parent
    return False


def check(c) -> None:
    """One Environment line when the sandbox keeps gh from its login file."""
    if not shutil.which("gh"):
        return
    settings = as_dict(c.settings)
    box = as_dict(settings.get("sandbox"))
    env = session_env(settings)
    login = gh_login_file(env)
    home = os.path.expanduser("~")
    rules = as_list(as_dict(settings.get("permissions")).get("deny"))
    declared = box.get("enabled") is True and any(
        denies_read(r, login, home, c.home) for r in rules
    )
    refused = read_refused(login)
    if not (declared or refused):
        return
    excluded = [str(x).strip() for x in as_list(box.get("excludedCommands"))]
    token = next((k for k in TOKEN_VARS if env.get(k)), "")
    if any(ALL_OF_GH.fullmatch(x) for x in excluded):
        c.add(
            "environment",
            "pass",
            "gh is excluded from the Bash sandbox, which denies its login file",
        )
    elif token:
        c.add(
            "environment",
            "info",
            "gh cannot read its login file (hosts.yml) in the Bash sandbox, and "
            f"takes its token from {token} instead",
        )
    elif declared:
        some = any(re.match(r"gh\s+\S", x) for x in excluded)
        c.add(
            "environment",
            "warn",
            "the Bash sandbox is on and applies a deny rule for the gh login "
            "file (hosts.yml) to gh itself: gh fails in sandboxed commands, and "
            "so does git over https when it asks gh for the token"
            + (
                "; sandbox.excludedCommands takes out only some gh commands"
                if some
                else ""
            ),
            FIX,
        )
    else:
        c.add(
            "environment",
            "info",
            "this session cannot open the gh login file (hosts.yml), as inside "
            "a Bash sandbox: gh works here only when it is excluded from it",
            FIX,
        )
