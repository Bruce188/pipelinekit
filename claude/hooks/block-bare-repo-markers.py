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

Exit 0 = allow, exit 2 + stderr = block.
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


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        print(
            "BLOCKED: block-bare-repo-markers got invalid hook input", file=sys.stderr
        )
        return 2
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return 0
    reason = check(path, data.get("cwd") or os.getcwd())
    if reason:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
