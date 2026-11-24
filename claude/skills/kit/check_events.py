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


def read_events(directory: str) -> list[dict]:
    """Every well-formed event in the log, older file first. Never raises."""
    events = []
    for name in ("events.jsonl.1", "events.jsonl"):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                raw = f.read(MAX_LOG_BYTES)
        except OSError:
            continue
        for line in raw.split(b"\n"):
            try:
                e = json.loads(line.decode("utf-8", "replace"))
            except (ValueError, RecursionError):
                continue
            if not isinstance(e, dict):
                continue
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
                events.append(e)
    return events


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
        c.add("activity", "info", f"the event log cannot be read: {clean(path)}")
    seen: set[tuple] = set()
    groups: dict[tuple[str, str, str], dict] = {}
    for e in read_events(directory):
        # An event from the future was written by a clock that was wrong.
        if e["when"] < since or e["when"] > now + 300:
            continue
        if c.session and e.get("session") != c.session:
            continue
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
    if not groups:
        if not off and not lost:
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
