#!/usr/bin/env python3
"""Event log for the kit's hooks: one JSON line per block, ask, override or error.

  kitlog.log(hook, kind, rule, reason="", data=None, prog="") -> bool
  kitlog.py HOOK KIND RULE [REASON]        (shell hooks; always exits 0)

The log is $PIPELINEKIT_STATE_DIR/events.jsonl, by default
~/.local/state/pipelinekit ($XDG_STATE_HOME is honoured). Only its owner can
read it: a log or a directory made before with a wider mode is made private (a
directory that holds other files, or a shared one, keeps its mode). Every event
is a single write, and at 1 MB it moves to events.jsonl.1. A log that cannot be
moved (a read-only directory, something else at events.jsonl.1) still takes
events until it holds 4 MB.
PIPELINEKIT_LOG=0 switches it off.

The command text is never logged: an event holds the rule id, the hook's
reason and where it happened. A log that cannot be written is ignored, because
logging must not change what a hook decides. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import time

VERSION = 1
KINDS = ("block", "ask", "override", "error")
HOOK = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
RULE = re.compile(r"^[a-z-]{1,30}\.[a-z0-9-]{1,40}$")
MAX_BYTES = 1_000_000  # rotate at this size; one older file is kept
MAX_UNROTATED = 4_000_000  # a log that cannot be rotated grows to this size
MAX_LINE = 2048
# Characters that can change how a line reads: controls (C0 and C1), the soft
# hyphen, line and paragraph separators, direction marks, zero-width and tag
# characters, and halves of a surrogate pair.
CONTROL = re.compile(
    r"[\x00-\x1f\x7f-\x9f\xad\u061c\u200b-\u200f\u2028-\u202e\u2060-\u206f"
    r"\ufeff\ud800-\udfff\U000e0000-\U000e007f]+"
)
# A password can hold a space or a quote, so only a slash ends it.
USER_PASSWORD = re.compile(r"[^\s/@:'\"]+:[^/]{0,400}@")  # user:password@host
URL_USER = re.compile(r"//[^/]{0,400}@")  # //token@host
URL_QUERY = re.compile(r"(?<=[^\s'\"])[?#][^\s'\"]*")  # ?token=... and #token
# What the kit keeps in its state directory; only such a directory is made private.
OWN_FILES = {"events.jsonl", "events.jsonl.1", "update.json", "update.json.tmp"}


def state_dir() -> str:
    explicit = os.environ.get("PIPELINEKIT_STATE_DIR")
    if explicit:
        return explicit
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "pipelinekit")


def log_path() -> str:
    return os.path.join(state_dir(), "events.jsonl")


def tidy(text: object, limit: int) -> str:
    """One printable line."""
    return CONTROL.sub(" ", "" if text is None else str(text)).strip()[:limit]


def without_credentials(text: str) -> str:
    """Without what a URL or remote can carry as a secret: user:password@,
    a user in front of the host, a query string and a fragment."""
    text = URL_USER.sub("//", USER_PASSWORD.sub("", text))
    return URL_QUERY.sub("", text)


def event(
    hook: str,
    kind: str,
    rule: str,
    reason: str = "",
    data: dict | None = None,
    prog: str = "",
) -> dict:
    data = data if isinstance(data, dict) else {}
    out: dict = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "v": VERSION,
        "hook": hook,
        "kind": kind,
        "rule": rule,
        "reason": without_credentials(tidy(reason, 4000))[:300],
    }
    optional = {
        "prog": tidy(prog, 40),
        "session": tidy(data.get("session_id") or "", 80),
        "tool_use_id": tidy(data.get("tool_use_id") or "", 80),
        "cwd": tidy(data.get("cwd") or os.getcwd(), 400),
    }
    out.update({k: v for k, v in optional.items() if v})
    if os.environ.get("CLAUDECODE") == "1":
        out["claude"] = True  # the hook ran inside a Claude Code session
    return out


def encode(e: dict) -> bytes:
    """One JSON line of at most MAX_LINE bytes: the long fields give way first."""
    reason = e["reason"]
    last = {"cwd": "", "session": "", "tool_use_id": "", "prog": ""}
    steps = (
        {},
        {"cwd": e.get("cwd", "")[:120], "reason": reason[:80]},
        {**last, "reason": reason[:40]},
    )
    line = b""
    for change in steps:
        cur = {k: v for k, v in {**e, **change}.items() if v != "" or k == "reason"}
        line = (json.dumps(cur, separators=(",", ":")) + "\n").encode("ascii")
        if len(line) <= MAX_LINE:
            break
    return line


def private_dir(directory: str) -> None:
    """Create the state directory, or close one made before with a wider mode."""
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        st = os.stat(directory)
        if (
            st.st_mode & 0o077
            and st.st_uid == os.geteuid()
            and not st.st_mode & stat.S_ISVTX  # a shared directory such as /tmp
            and set(os.listdir(directory)) <= OWN_FILES
        ):
            os.chmod(directory, 0o700)
    except OSError:
        pass  # the log itself is still private


def append(line: bytes) -> None:
    path = log_path()
    private_dir(os.path.dirname(path))
    try:
        size = os.stat(path).st_size
    except FileNotFoundError:
        size = 0
    if size >= MAX_BYTES:
        try:
            os.replace(path, path + ".1")
        except OSError:
            # Events still count for more than a tidy log; /kit says it is
            # not rotated.
            if size >= MAX_UNROTATED:
                raise
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    # A named pipe at the path must not make a hook wait for a reader.
    fd = os.open(path, flags | getattr(os, "O_NONBLOCK", 0), 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("the log is not a regular file")
        if st.st_uid != os.geteuid():
            raise OSError("the log belongs to another user")
        if st.st_mode & 0o077:
            os.fchmod(fd, 0o600)  # a log made before with a wider mode
        os.write(fd, line)
    finally:
        os.close(fd)


def log(
    hook: str,
    kind: str,
    rule: str,
    reason: str = "",
    data: dict | None = None,
    prog: str = "",
) -> bool:
    """Append one event. True when it was written. Never raises."""
    try:
        if os.environ.get("PIPELINEKIT_LOG") == "0":
            return False
        if kind not in KINDS or not HOOK.match(hook) or not RULE.match(rule):
            return False
        append(encode(event(hook, kind, rule, reason, data, prog)))
        return True
    except Exception:
        return False


def main(argv: list[str]) -> int:
    if len(argv) >= 3:
        log(argv[0], argv[1], argv[2], " ".join(argv[3:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
