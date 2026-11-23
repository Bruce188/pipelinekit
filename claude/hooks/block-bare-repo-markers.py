#!/usr/bin/env python3
"""PreToolUse hook for Write and Edit: refuse to assemble a bare git repo.

Git treats a directory holding HEAD plus objects/ and refs/ as a bare
repository, and runs its `config` (core.fsmonitor and friends) on the next
git command there. A file planted at the working-directory root, or one level
down, is the known sandbox-escape pattern.

Blocks a write only when, after the write, a directory at depth 0 or 1 below
cwd would hold HEAD together with config, objects or refs. A lone `config`
(src/config, app/config) or a lone HEAD is allowed. Paths inside a real .git
directory are allowed.

Exit 0 = allow, exit 2 + stderr = block. A block is written to the kit's event
log (kitlog.py) under the rule id `bare-repo.marker`.
"""

from __future__ import annotations

import json
import os
import sys

MARKERS = ("HEAD", "config", "objects", "refs")


def check(path: str, cwd: str) -> str | None:
    target = os.path.normpath(os.path.join(cwd, path))
    rel = os.path.relpath(target, cwd)
    parts = rel.split(os.sep)
    if parts[0] == ".." or ".git" in parts:
        return None
    # The directory that would become the bare repo, and the marker written into it.
    for depth in (0, 1):
        if len(parts) > depth and parts[depth] in MARKERS:
            repo_dir = os.path.join(cwd, *parts[:depth])
            present = {m for m in MARKERS if os.path.exists(os.path.join(repo_dir, m))}
            present.add(parts[depth])
            if "HEAD" in present and len(present) >= 2:
                where = os.path.relpath(repo_dir, cwd)
                return (
                    f"writing {rel} leaves '{where}' with {sorted(present)}: "
                    "git would treat it as a bare repository and run its config"
                )
    return None


def record(kind: str, rule: str, reason: str, data: object = None) -> None:
    """One line in the kit's event log. A missing or failing log changes nothing."""
    try:
        sys.dont_write_bytecode = True  # leave no __pycache__ beside the hooks
        import kitlog

        kitlog.log("block-bare-repo-markers", kind, rule, reason, data)
    except Exception:
        pass


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (ValueError, RecursionError):
        data = None
    if not isinstance(data, dict):
        record("error", "input.invalid", "invalid hook input")
        print(
            "BLOCKED: block-bare-repo-markers got invalid hook input [input.invalid]",
            file=sys.stderr,
        )
        return 2
    tool_input = data.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return 0
    try:
        reason = check(str(path), str(data.get("cwd") or os.getcwd()))
    except Exception as exc:  # a bug here refuses the write, it does not crash
        name = type(exc).__name__
        record(
            "error", "internal.crash", f"block-bare-repo-markers failed ({name})", data
        )
        print(
            f"BLOCKED: block-bare-repo-markers failed ({name}); the write was not"
            " checked [internal.crash]",
            file=sys.stderr,
        )
        return 2
    if reason:
        record("block", "bare-repo.marker", reason, data)
        print(f"BLOCKED: {reason} [bare-repo.marker]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
