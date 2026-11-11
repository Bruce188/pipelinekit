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

PIPELINEKIT_SESSION_CHECK=0 switches it off. Stdlib only.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys

HOOK = "session-check"
TIMEOUT = 4  # seconds; settings.json gives the hook 5
REPAIR = "The kit's installer is the repair path and the user runs it."


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
