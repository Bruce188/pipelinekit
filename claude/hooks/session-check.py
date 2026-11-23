#!/usr/bin/env python3
"""SessionStart hook: check the kit install, speak only when something is wrong.

Runs the self-check in quick mode (no probes, well under a second). A healthy
install, warnings included, prints nothing. Problems print one JSON object: a
line for the user and a short note for Claude, both naming /kit. Both carry
the number of problems and no text from the report, so nothing a file holds
can end up in them.

It never holds up a session: every path exits 0, a check that takes too long
is dropped without a word, and it reads a bounded amount of input and of the
check's output, waiting at most a second for its input to end. Its own failures go to the event log as
`session-check.timeout` and `session-check.failed`, where /kit shows them.

PIPELINEKIT_SESSION_CHECK=0 switches it off. Stdlib only.
"""

from __future__ import annotations

import contextlib
import json
import os
import select
import signal
import subprocess
import sys
import time

HOOK = "session-check"
TIMEOUT = 4  # seconds; settings.json gives the hook 5
INPUT_WAIT = 1  # seconds for Claude Code's input to end; it is sent at once
MAX_INPUT = 1_000_000  # bytes; the input is a few hundred
MAX_OUTPUT = 1_000_000  # bytes; check.py --quick --json prints a few thousand
REPAIR = "The kit's installer is the repair path and the user runs it."


def record(rule, reason, data=None):
    try:
        sys.dont_write_bytecode = True  # leave no __pycache__ beside the hooks
        import kitlog

        kitlog.log(HOOK, "error", rule, reason, data)
    except Exception:
        pass


class TooMuchOutput(Exception):
    """The checker printed more than MAX_OUTPUT bytes."""


def read_bounded(fd, deadline, limit):
    """What fd gives until it ends, the deadline passes or more than limit came.

    (data, why): why is "" at the end, "time" or "size" when it stopped early.
    """
    data = bytearray()
    while len(data) <= limit:
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([fd], [], [], left)[0]:
            return bytes(data), "time"
        chunk = os.read(fd, 65536)
        if not chunk:
            return bytes(data), ""
        data += chunk
    return bytes(data), "size"


def hook_input():
    """What Claude Code sent on stdin, or {} when that is not a JSON object.

    An input that never ends is read for INPUT_WAIT seconds: what came by then
    still counts when it is a whole JSON object.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        deadline = time.monotonic() + INPUT_WAIT
        raw, _ = read_bounded(sys.stdin.fileno(), deadline, MAX_INPUT)
        data = json.loads(raw.decode("utf-8", "replace") or "{}")
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def say(message, context):
    out = {
        "systemMessage": message,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        },
    }
    print(json.dumps(out))


def could_not_run(reason, advice, data):
    record("session-check.failed", reason, data)
    say(
        f"pipelinekit: the session-start check could not run ({reason}). {advice}",
        "The pipelinekit session-start check could not run, so the state of "
        f"the kit's guard hooks is unknown. {REPAIR}",
    )


def stop(p):
    """End the checker and all it started."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        p.kill()
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        p.wait(timeout=1)


def run_checker(checker, env):
    """The checker's exit code and output, of which at most MAX_OUTPUT is read.

    A timeout or more output than that ends it and all it started, and raises
    subprocess.TimeoutExpired or TooMuchOutput.
    """
    deadline = time.monotonic() + TIMEOUT
    p = subprocess.Popen(
        [sys.executable, checker, "--quick", "--json"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,  # its own process group, so a child can go too
    )
    with p.stdout:
        try:
            out, why = read_bounded(p.stdout.fileno(), deadline, MAX_OUTPUT)
            if why == "size":
                raise TooMuchOutput
            if why == "time":
                raise subprocess.TimeoutExpired(p.args, TIMEOUT)
            # Its output ended; give it what is left of the time to exit.
            code = p.wait(timeout=max(deadline - time.monotonic(), 0.1))
        except (subprocess.TimeoutExpired, TooMuchOutput):
            stop(p)
            raise
    return code, out.decode("utf-8", "replace")


def main():
    if os.environ.get("PIPELINEKIT_SESSION_CHECK") == "0":
        return
    data = hook_input()
    home = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checker = os.path.join(home, "skills", "kit", "check.py")
    if not os.path.isfile(checker):
        could_not_run(
            "skills/kit/check.py is missing", "Run the kit's installer again.", data
        )
        return
    env = dict(os.environ)
    if not env.get("CLAUDE_HOME") and os.path.isfile(
        os.path.join(home, "settings.json")
    ):
        env["CLAUDE_HOME"] = home  # check the install this hook sits in
    try:
        code, out = run_checker(checker, env)
    except subprocess.TimeoutExpired:
        record("session-check.timeout", f"no result within {TIMEOUT} seconds", data)
        return
    except TooMuchOutput:
        reason = f"check.py printed more than {MAX_OUTPUT // 1_000_000} MB"
        could_not_run(reason, "Run /kit to see why.", data)
        return
    except OSError as exc:
        reason = f"check.py did not start: {exc.strerror or type(exc).__name__}"
        could_not_run(reason, "Run the kit's installer again.", data)
        return
    try:
        results = json.loads(out)["results"]
        fails = [r for r in results if r["level"] == "fail"]
    except (ValueError, KeyError, TypeError, RecursionError):
        reason = f"check.py gave no report, exit {code}"
        could_not_run(reason, "Run /kit to see why.", data)
        return
    if not fails:
        return
    found = "1 problem" if len(fails) == 1 else f"{len(fails)} problems"
    say(
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
