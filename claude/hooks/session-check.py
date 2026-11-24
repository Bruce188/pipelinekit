#!/usr/bin/env python3
"""SessionStart hook: check the kit install, speak only when something is wrong.

Runs the self-check in quick mode (no probes, well under a second). A healthy
install, warnings included, prints nothing. Problems print one JSON object: a
line for the user and a short note for Claude, both naming /kit. Both carry
the number of problems and no text from the report, so nothing a file holds
can end up in them.

It never holds up a session: every path exits 0, a check that takes too long
is dropped without a word, together with every process it started (on Linux
also one that left its process group), and it reads a bounded amount of input
and of the check's output, waiting at most a second for its input to end. Its
own failures go to the event log as `session-check.timeout`,
`session-check.failed` and `session-check.stopped` (the hook was ended from
outside), where /kit shows them.

It runs only when a session starts: an input whose `source` is anything but
`startup` (a resume, /clear, a compaction) is left alone, wherever it is wired.
Exactly PIPELINEKIT_SESSION_CHECK=0 switches it off. Stdlib only.
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
PR_SET_CHILD_SUBREAPER = 36  # Linux prctl option
STOP_SIGNALS = ("SIGTERM", "SIGHUP", "SIGINT")
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


class Stopped(Exception):
    """The hook got a signal that ends it, for example at Claude Code's limit."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


def on_stop_signal(signum, frame):
    for name in STOP_SIGNALS:  # a second signal must not cut the cleanup short
        signal.signal(getattr(signal, name), signal.SIG_IGN)
    raise Stopped(signal.Signals(signum).name)


def adopt_orphans():
    """Become the parent of what the checker's processes leave behind (Linux).

    A process that left the checker's process group with setsid and then lost
    its parent would otherwise go to init, out of reach of descendants().
    """
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        one, zero = ctypes.c_ulong(1), ctypes.c_ulong(0)
        libc.prctl(ctypes.c_int(PR_SET_CHILD_SUBREAPER), one, zero, zero, zero)
    except (OSError, AttributeError, ImportError):
        pass


def descendants(root):
    """Pids of the live processes below root, from /proc; [] without /proc."""
    try:
        names = os.listdir("/proc")
    except OSError:
        return []
    children = {}
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as f:
                fields = f.read().rsplit(b")", 1)[1].split()
            state, parent = fields[0], int(fields[1])
        except (OSError, IndexError, ValueError):
            continue
        if state != b"Z":
            children.setdefault(parent, []).append(int(name))
    found, todo = [], [root]
    while todo:
        kids = children.get(todo.pop(), [])
        found += kids
        todo += kids
    return found


def reap():
    """Collect the exit status of every child that has ended."""
    with contextlib.suppress(ChildProcessError, OSError):
        while os.waitpid(-1, os.WNOHANG)[0]:
            pass


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
    """End the checker and all it started, also what left its process group.

    Takes at most about a second; a stop signal that comes meanwhile waits
    until the end, so it cannot cut this short.
    """
    stops = {getattr(signal, name) for name in STOP_SIGNALS}
    signal.pthread_sigmask(signal.SIG_BLOCK, stops)
    try:
        end = time.monotonic() + 1
        while True:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                with contextlib.suppress(OSError):
                    p.kill()
            left = descendants(os.getpid())
            for pid in left:
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                p.wait(timeout=max(end - time.monotonic(), 0.01))
            reap()
            if not left or time.monotonic() >= end:
                return
            time.sleep(0.01)  # let what was just killed end before looking again
    finally:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, stops)


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
        except BaseException:  # a timeout, too much output or a stop signal
            stop(p)
            raise
    return code, out.decode("utf-8", "replace")


def main():
    if os.environ.get("PIPELINEKIT_SESSION_CHECK") == "0":
        return
    for name in STOP_SIGNALS:
        signal.signal(getattr(signal, name), on_stop_signal)
    data = {}
    try:
        data = hook_input()
        source = data.get("source")
        if isinstance(source, str) and source != "startup":
            return  # a resume, /clear or a compaction: no session starts
        adopt_orphans()
        check(data)
    except Stopped as exc:
        record("session-check.stopped", f"ended from outside by {exc.name}", data)


def check(data):
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
        f"pipelinekit: the quick check found {found} in this install. "
        "Run /kit for the report.",
        f"The pipelinekit session-start check ran the kit's quick check, without "
        f"the live probes, and found {found} in the kit install, so some of its "
        f"guard hooks may not be working. /kit gives the full report, which can "
        f"list more. {REPAIR}",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a broken check must not get in the way of a session
        record("session-check.failed", f"hook crashed: {type(exc).__name__}")
    sys.exit(0)
