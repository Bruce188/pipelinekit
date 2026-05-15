#!/usr/bin/env python3
"""Denial tracking helper.

Mirrors Claude Code's utils/permissions/denialTracking.ts (NETMIND
Part 2 §1.4): records denial events and surfaces a retry-limit
advisory when the same tool/rule pair has been denied 3+ times in
the last 5 minutes.

Storage: ~/.claude/state/denial-log.jsonl (one JSON per line).
Rotation: entries older than 24h go to ~/.claude/state/denial-log.archive.jsonl.
PII-safe: only tool name and matched rule name — NO paths, NO
command content.

Modes:
  record <tool> <rule>     # called by a hook that is about to exit 2
  check <tool> <rule>      # returns exit 0 if retry-limit reached (caller
                           #   may then decide to allow), else exit 1
  rotate                   # move >24h entries to the archive file
  stats                    # dump recent counts (debug)
"""

from __future__ import annotations

import json
import os
import sys
import time

STATE_DIR = os.path.expanduser("~/.claude/state")
LOG_PATH = os.path.join(STATE_DIR, "denial-log.jsonl")
ARCHIVE_PATH = os.path.join(STATE_DIR, "denial-log.archive.jsonl")

RETRY_WINDOW_SECONDS = 5 * 60  # 5 minutes
RETRY_LIMIT = 3
ROTATE_AFTER_SECONDS = 24 * 60 * 60  # 24 hours


def _ensure_state_dir() -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except OSError:
        pass


def _read_log(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    entries: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return entries


def record(tool: str, rule: str) -> int:
    _ensure_state_dir()
    entry = {"tool": tool, "rule": rule, "ts": int(time.time())}
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        return 2
    return 0


def check(tool: str, rule: str) -> int:
    """Return 0 if this (tool, rule) pair has been denied RETRY_LIMIT+
    times in the past RETRY_WINDOW_SECONDS. Return 1 otherwise.

    Exit 0 means: caller should release the block, emit the advisory.
    Exit 1 means: normal block.
    """
    entries = _read_log(LOG_PATH)
    cutoff = int(time.time()) - RETRY_WINDOW_SECONDS
    count = 0
    for e in entries:
        if e.get("tool") == tool and e.get("rule") == rule and e.get("ts", 0) >= cutoff:
            count += 1
    if count >= RETRY_LIMIT:
        # Emit a system-reminder-shaped JSON on stdout. Hooks can
        # inject this via hookSpecificOutput when the format is
        # recognized. At minimum the caller sees a clear advisory
        # to stop the retry loop.
        advisory = (
            f"DENIAL_RETRY_LIMIT: operation ({tool}, {rule}) has been "
            f"blocked {count} times in the last {RETRY_WINDOW_SECONDS // 60} "
            f"minutes. Stopping silent deny — ask the user instead of "
            f"retrying."
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": advisory,
                    }
                }
            )
        )
        return 0
    return 1


def rotate() -> int:
    _ensure_state_dir()
    entries = _read_log(LOG_PATH)
    if not entries:
        return 0
    cutoff = int(time.time()) - ROTATE_AFTER_SECONDS
    keep: list[dict] = []
    move: list[dict] = []
    for e in entries:
        if e.get("ts", 0) >= cutoff:
            keep.append(e)
        else:
            move.append(e)
    if not move:
        return 0
    try:
        with open(ARCHIVE_PATH, "a") as f:
            for e in move:
                f.write(json.dumps(e) + "\n")
        with open(LOG_PATH, "w") as f:
            for e in keep:
                f.write(json.dumps(e) + "\n")
    except OSError:
        return 2
    print(f"rotated {len(move)} entries to {ARCHIVE_PATH}")
    return 0


def stats() -> int:
    entries = _read_log(LOG_PATH)
    if not entries:
        print("no entries")
        return 0
    cutoff = int(time.time()) - RETRY_WINDOW_SECONDS
    counts: dict[tuple[str, str], int] = {}
    for e in entries:
        if e.get("ts", 0) < cutoff:
            continue
        key = (e.get("tool", "?"), e.get("rule", "?"))
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        print("no recent entries (within 5 min window)")
        return 0
    for (tool, rule), n in sorted(counts.items(), key=lambda x: -x[1]):
        marker = " [LIMIT]" if n >= RETRY_LIMIT else ""
        print(f"{n:3d} {tool}:{rule}{marker}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: denial_tracker.py <record|check|rotate|stats> [args...]",
            file=sys.stderr,
        )
        return 2
    cmd = sys.argv[1]
    if cmd == "record" and len(sys.argv) >= 4:
        return record(sys.argv[2], sys.argv[3])
    if cmd == "check" and len(sys.argv) >= 4:
        return check(sys.argv[2], sys.argv[3])
    if cmd == "rotate":
        return rotate()
    if cmd == "stats":
        return stats()
    print("usage: denial_tracker.py <record|check|rotate|stats> [args...]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
