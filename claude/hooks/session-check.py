#!/usr/bin/env python3
"""SessionStart hook: check the kit install, speak only when something is wrong.

Runs the self-check in quick mode (no probes, well under a second). A healthy
install, warnings included, prints nothing. Problems print one JSON object: a
line for the user and a short note for Claude, both naming /kit. Both carry
the number of problems and no text from the report, so nothing a file holds
can end up in them.

It never holds up a session: every path exits 0 and a check that takes too
long is dropped without a word. Its own failures go to the event log as
`session-check.timeout` and `session-check.failed`, where /kit shows them.

In a project whose last /garden run (docs/garden/last.json) is more than 30
days old it adds one line naming /garden and the number of days, at most once
in 7 days per project. That line holds a number and fixed words only. A
project never audited, a last.json that cannot be read, the line
`Garden reminder: off` in the project's CLAUDE.md and PIPELINEKIT_GARDEN=0
give no line.

PIPELINEKIT_SESSION_CHECK=0 switches it all off. Stdlib only.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

HOOK = "session-check"
TIMEOUT = 4  # seconds; settings.json gives the hook 5
REPAIR = "The kit's installer is the repair path and the user runs it."
GARDEN_DAYS = 30  # a last run older than this gets the reminder
GARDEN_EVERY = 7 * 86400  # at most one reminder per project in this time
GARDEN_MAX_BYTES = 256 * 1024
# The switch, after a line's leading space, quote, list, heading and code marks.
# Checked line by line: one pattern over the whole file backtracks on long
# runs of blank space and could hold the hook past its time limit.
GARDEN_OFF = re.compile(r"garden\s+reminder\s*:\s*off\b", re.IGNORECASE)
LINE_MARKS = " \t\r\f\v>*#-`"
# Text that does not count for the switch: code fences and HTML comments.
NOT_PROSE = re.compile(
    r"<!--.*?(?:-->|\Z)|^ {0,3}(`{3,}|~{3,}).*?(?:^ {0,3}\1|\Z)", re.S | re.M
)


def record(rule, reason, data=None):
    try:
        sys.dont_write_bytecode = True  # leave no __pycache__ beside the hooks
        import kitlog

        kitlog.log(HOOK, "error", rule, reason, data)
    except Exception:
        pass


def hook_input():
    """What Claude Code sent on stdin, or {} when that is not a JSON object."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        data = json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


class Out:
    """What the hook says: one JSON object, however many lines it holds."""

    def __init__(self):
        self.messages, self.contexts = [], []

    def say(self, message, context):
        self.messages.append(message)
        self.contexts.append(context)

    def flush(self):
        if not self.messages:
            return
        out = {
            "systemMessage": "\n".join(self.messages),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": " ".join(self.contexts),
            },
        }
        print(json.dumps(out))


def could_not_run(out, reason, advice, data):
    record("session-check.failed", reason, data)
    out.say(
        f"pipelinekit: the session-start check could not run ({reason}). {advice}",
        "The pipelinekit session-start check could not run, so the state of "
        f"the kit's guard hooks is unknown. {REPAIR}",
    )


def project_root(start):
    """The top of the git checkout holding `start`, else `start` itself."""
    path = os.path.abspath(start)
    here = path
    for _ in range(64):
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return path


def small_text(path):
    """The text of a small file, or None."""
    try:
        if os.path.getsize(path) > GARDEN_MAX_BYTES:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def last_garden_run(root):
    """The date of the last recorded /garden run, or None; any fault is None."""
    text = small_text(os.path.join(root, "docs", "garden", "last.json"))
    if text is None:
        return None
    try:
        date = json.loads(text)["date"]
        when = datetime.fromisoformat(date.replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def reminded_recently(root, now):
    """True when this project had the reminder within GARDEN_EVERY; else note it now.

    The note sits in the kit's state folder, keyed by a hash of the project's
    path. When it cannot be kept, no reminder is given, so it never repeats.
    """
    try:
        sys.dont_write_bytecode = True
        import kitlog

        folder = kitlog.state_dir()
    except Exception:
        return True
    path = os.path.join(folder, "garden-reminders.json")
    key = hashlib.sha256(os.path.realpath(root).encode()).hexdigest()[:24]
    seen = {}
    text = small_text(path)
    if text is not None:
        try:
            seen = json.loads(text)
        except (ValueError, RecursionError):
            seen = {}
        if not isinstance(seen, dict):
            seen = {}
    last = seen.get(key)
    if isinstance(last, (int, float)) and 0 <= now - last < GARDEN_EVERY:
        return True
    seen = {
        k: v
        for k, v in seen.items()
        if isinstance(v, (int, float)) and now - v < GARDEN_EVERY
    }
    seen[key] = int(now)
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(seen, f)
        os.replace(tmp, path)
    except OSError:
        return True
    return False


def switched_off(text: str) -> bool:
    return any(GARDEN_OFF.match(line.lstrip(LINE_MARKS)) for line in text.splitlines())


def garden_reminder(out, data):
    """One line when the project's last /garden run is old; silent on any fault."""
    if os.environ.get("PIPELINEKIT_GARDEN") == "0":
        return
    cwd = data.get("cwd")
    root = project_root(cwd if isinstance(cwd, str) and cwd else os.getcwd())
    when = last_garden_run(root)
    if when is None:
        return
    days = int((datetime.now(timezone.utc) - when).total_seconds() // 86400)
    if days <= GARDEN_DAYS:
        return
    for name in ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md")):
        text = small_text(os.path.join(root, name))
        if text and switched_off(NOT_PROSE.sub("", text)):
            return
    if reminded_recently(root, time.time()):
        return
    out.say(
        f"pipelinekit: the last /garden run in this project was {days} days ago.",
        f"The last /garden audit of this project was {days} days ago. Mention it "
        "once if it fits the user's task; run /garden only when the user asks.",
    )


def run_checker(checker, env):
    """The checker's exit code and output. On a timeout it and all it started end."""
    p = subprocess.Popen(
        [sys.executable, checker, "--quick", "--json"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        env=env,
        start_new_session=True,  # its own process group, so a child can go too
    )
    try:
        out, _ = p.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
            p.communicate(timeout=1)
        raise
    return p.returncode, out


def main():
    if os.environ.get("PIPELINEKIT_SESSION_CHECK") == "0":
        return
    data = hook_input()
    out = Out()
    try:
        kit_check(out, data)
    finally:
        # The reminder never gets in the way, and never says why it is quiet.
        with contextlib.suppress(Exception):
            garden_reminder(out, data)
        out.flush()


def kit_check(out, data):
    home = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checker = os.path.join(home, "skills", "kit", "check.py")
    if not os.path.isfile(checker):
        could_not_run(
            out,
            "skills/kit/check.py is missing",
            "Run the kit's installer again.",
            data,
        )
        return
    env = dict(os.environ)
    if not env.get("CLAUDE_HOME") and os.path.isfile(
        os.path.join(home, "settings.json")
    ):
        env["CLAUDE_HOME"] = home  # check the install this hook sits in
    try:
        code, report = run_checker(checker, env)
    except subprocess.TimeoutExpired:
        record("session-check.timeout", f"no result within {TIMEOUT} seconds", data)
        return
    except OSError as exc:
        reason = f"check.py did not start: {exc.strerror or type(exc).__name__}"
        could_not_run(out, reason, "Run the kit's installer again.", data)
        return
    try:
        results = json.loads(report)["results"]
        fails = [r for r in results if r["level"] == "fail"]
    except (ValueError, KeyError, TypeError, RecursionError):
        reason = f"check.py gave no report, exit {code}"
        could_not_run(out, reason, "Run /kit to see why.", data)
        return
    if not fails:
        return
    found = "1 problem" if len(fails) == 1 else f"{len(fails)} problems"
    out.say(
        f"pipelinekit: {found} in this install. Run /kit for the report.",
        f"The pipelinekit session-start check found {found} in the kit install, "
        f"so some of its guard hooks may not be working. /kit gives the report. "
        f"{REPAIR}",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a broken check must not get in the way of a session
        record("session-check.failed", f"hook crashed: {type(exc).__name__}")
    sys.exit(0)
