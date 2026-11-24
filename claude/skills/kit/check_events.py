"""The hooks' event log as check.py reads it: where it is, what it holds, and
the Activity section of the report."""

# ruff: noqa: F403, F405
from __future__ import annotations

import calendar
import json
import os
import time
from typing import TYPE_CHECKING

from check_base import *

if TYPE_CHECKING:
    from check_core import Check

# kitlog.py rotates the log at LOG_ROTATE_BYTES and writes lines of at most
# LOG_MAX_LINE bytes; a test keeps both equal to the ones there.
LOG_ROTATE_BYTES = 1_000_000
LOG_MAX_LINE = 2048

# ---------------------------------------------------------------- event log


def env_dir(name: str) -> str:
    """A directory named in the environment: a leading ~ is expanded, and a
    path that is still relative is not used (it would depend on where a hook
    runs)."""
    value = os.path.expanduser(os.environ.get(name) or "")
    return value if os.path.isabs(value) else ""


def state_dir() -> str:
    """Where the hooks keep their event log (the same rule as kitlog.py)."""
    explicit = env_dir("PIPELINEKIT_STATE_DIR")
    if explicit:
        return explicit
    base = env_dir("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "pipelinekit")


def event_time(ts: object) -> int | None:
    if not isinstance(ts, str):
        return None
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def parse_event(line: bytes) -> dict | None:
    """One well-formed event with its time as "when", or None."""
    try:
        e = json.loads(line.decode("utf-8", "replace"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(e, dict):
        return None
    kind, hook, rule = e.get("kind"), e.get("hook"), e.get("rule")
    when = event_time(e.get("ts"))
    if (
        isinstance(kind, str)
        and kind in EVENT_KINDS
        and isinstance(hook, str)
        and EVENT_HOOK.match(hook)
        and isinstance(rule, str)
        and EVENT_RULE.match(rule)
        and when is not None
    ):
        e["when"] = when
        return e
    return None


class EventLog:
    """What read_log found in the log files."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.skipped = 0  # lines that are no event this check can read
        self.cut: list[str] = []  # files of which only the newest part was read
        self.sizes: dict[str, int] = {}


def read_log(directory: str) -> EventLog:
    """Every well-formed event in the log, older file first. Of a file larger
    than MAX_LOG_BYTES only its newest part is read. Never raises."""
    log = EventLog()
    for name in ("events.jsonl.1", "events.jsonl"):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                size = os.fstat(f.fileno()).st_size
                start = max(0, size - MAX_LOG_BYTES)
                f.seek(max(0, start - 1))
                raw = f.read(MAX_LOG_BYTES + 1)
        except OSError:
            continue
        log.sizes[name] = size
        if start:
            # Begin after the first newline: the line before it is cut.
            log.cut.append(name)
            raw = raw[raw.find(b"\n") + 1 :] if b"\n" in raw else b""
        for line in raw.split(b"\n"):
            if not line.strip():
                continue
            e = parse_event(line)
            if e is None:
                log.skipped += 1
            else:
                log.events.append(e)
    return log


def read_events(directory: str) -> list[dict]:
    return read_log(directory).events


# ---------------------------------------------------------------- activity


def check_activity(c: Check) -> None:
    """What the hooks blocked, asked about, let through or failed on."""
    off = os.environ.get("PIPELINEKIT_LOG") == "0"
    if off:
        c.add("activity", "info", "the event log is switched off (PIPELINEKIT_LOG=0)")
    now = time.time()
    since = now - c.days * 86400
    directory = state_dir()
    logs = [os.path.join(directory, n) for n in ("events.jsonl.1", "events.jsonl")]
    # A log that is there and cannot be read is named, not taken for empty.
    lost = [
        p
        for p in logs
        if os.path.lexists(p) and not (os.path.isfile(p) and os.access(p, os.R_OK))
    ]
    if os.path.lexists(directory) and not (
        os.path.isdir(directory) and os.access(directory, os.R_OK | os.X_OK)
    ):
        lost = [directory]
    for path in lost:
        c.add("activity", "warn", f"the event log cannot be read: {clean(path)}")
    log = read_log(directory)
    if log.sizes.get("events.jsonl", 0) > LOG_ROTATE_BYTES + LOG_MAX_LINE:
        c.add(
            "activity",
            "warn",
            "the event log was not rotated at 1 MB: events.jsonl cannot be moved "
            f"to events.jsonl.1 in {clean(directory)}; from 4 MB on, new events "
            "are dropped",
            "make the directory writable and move whatever is at events.jsonl.1 "
            "out of the way",
        )
    for name in log.cut:
        c.add("activity", "info", f"{name}: only its newest 4 MB were read")
    if log.skipped:
        c.add(
            "activity",
            "info",
            f"{plural(log.skipped, 'line')} of the event log skipped: "
            "not an event this check can read (damaged, or from a newer kit)",
        )
    seen: set[tuple] = set()
    groups: dict[tuple[str, str, str], dict] = {}
    future = 0
    for e in log.events:
        if e["when"] < since:
            continue
        if c.session and e.get("session") != c.session:
            continue
        if e["when"] > now + 300:
            future += 1  # written while a clock was wrong
        key = (e["hook"], e["rule"], e["kind"])
        call = e.get("tool_use_id")
        if isinstance(call, str) and call:
            # One command can trip the same rule once per program in it.
            if (call, *key) in seen:
                continue
            seen.add((call, *key))
        g = groups.setdefault(key, {"count": 0, "last": -1, "reason": ""})
        g["count"] += 1
        if e["when"] >= g["last"]:
            g["last"] = e["when"]
            g["reason"] = clean(e.get("reason") or "", 200)
    if future:
        c.add(
            "activity",
            "info",
            f"{plural(future, 'event')} {'is' if future == 1 else 'are'} dated "
            "after now: a clock was wrong when the hook wrote "
            + ("it" if future == 1 else "them"),
        )
    if not groups:
        if not off and not lost and not log.skipped:
            c.add("activity", "info", f"no blocks, asks or hook errors ({c.window})")
        return
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1]["last"], kv[0]))
    hidden: list[str] = []
    extra = 0
    for n, ((hook, rule, kind), g) in enumerate(ordered):
        when = time.gmtime(g["last"])
        c.activity.append(
            {
                "hook": hook,
                "rule": rule,
                "kind": kind,
                "count": g["count"],
                "last": time.strftime("%Y-%m-%dT%H:%M:%SZ", when),
                "reason": g["reason"],
            }
        )
        if n >= ACTIVITY_LINES:
            # A failed hook is not dropped for newer blocks.
            if kind != "error" or extra >= ACTIVITY_LINES:
                hidden.append(kind)
                continue
            extra += 1
        times = "once" if g["count"] == 1 else f"{g['count']} times"
        msg = (
            f"{rule} ({hook}): {EVENT_KINDS[kind]} {times}, "
            f"last {time.strftime('%Y-%m-%d %H:%M UTC', when)}"
        )
        if g["reason"]:
            msg += f": {g['reason']}"
        c.add("activity", "warn" if kind == "error" else "info", msg)
    if hidden:
        failed = hidden.count("error")
        c.add(
            "activity",
            "warn" if failed else "info",
            f"{plural(len(hidden), 'more rule')} not shown"
            + (f", {failed} of them failed" if failed else "")
            + " (--json lists them all)",
        )
