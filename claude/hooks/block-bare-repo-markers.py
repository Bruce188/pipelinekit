#!/usr/bin/env python3
"""PreToolUse hook for Write and Edit tools.

Blocks creation of files named HEAD, objects, refs, hooks, or config at
the working-directory root or in shallow subdirectories, because git
treats any directory containing that marker set as a bare repository.
Combined with core.fsmonitor, any subsequent git command in that cwd
executes arbitrary shell code — a documented sandbox-escape pattern
(NETMIND Part 2 §2.3).

Reads the tool_input JSON from stdin. Exits 0 to allow, 2 to block.
"""

from __future__ import annotations

import json
import os
import sys

BARE_REPO_MARKERS = frozenset({"HEAD", "objects", "refs", "hooks", "config"})

# Depth at which we still care. Git detects bare repos from the top level,
# so a file at cwd or one level deep is dangerous. Deeper paths are not
# interpreted as bare-repo markers by git's discovery logic.
MAX_DEPTH = 2


def is_inside_real_git_dir(path: str) -> bool:
    """Return True if `path` is inside a real .git/ directory.

    A real .git/ directory is one whose nearest .git ancestor contains
    either a config file or HEAD file — meaning git itself treats it as
    the metadata directory.
    """
    parts = path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == ".git":
            # Walk upward from the original path to the parent of .git,
            # then check that .git/config or .git/HEAD exists on disk.
            git_dir = "/".join(parts[: i + 1])
            if os.path.isfile(os.path.join(git_dir, "config")) or os.path.isfile(
                os.path.join(git_dir, "HEAD")
            ):
                return True
    return False


def is_bare_repo_marker(path: str) -> tuple[bool, str]:
    """Return (blocked, reason)."""
    # Normalize. Reject writes to cwd-rooted or depth-1 files with marker names.
    norm = os.path.normpath(path).replace("\\", "/")
    parts = [p for p in norm.split("/") if p and p != "."]

    if not parts:
        return (False, "")

    basename = parts[-1]

    if basename not in BARE_REPO_MARKERS:
        return (False, "")

    # Legitimate .git/ paths are allowed.
    if is_inside_real_git_dir(norm):
        return (False, "")

    # Absolute paths: check depth from cwd.
    if os.path.isabs(norm):
        try:
            rel = os.path.relpath(norm, os.getcwd())
        except ValueError:
            rel = norm
        rel_parts = [p for p in rel.replace("\\", "/").split("/") if p and p != "."]
        depth = len([p for p in rel_parts if p != ".."])
    else:
        depth = len(parts)

    if depth > MAX_DEPTH:
        # Deep paths not interpreted as bare-repo markers by git discovery.
        return (False, "")

    return (
        True,
        f"'{norm}' matches bare-repo marker '{basename}'. Git would "
        f"treat the parent directory as a bare repository, and with "
        f"core.fsmonitor this executes arbitrary shell. "
        f"See NETMIND Part 2 §2.3. Refused.",
    )


def session_scan() -> int:
    """Scan cwd for existing bare-repo markers and warn only if a
    directory contains 2+ markers outside a real .git/.

    Single marker files (.azure/config, mydata/HEAD) are almost always
    legitimate — a real bare-repo attack places multiple markers in the
    same dir. Intended for SessionStart hook. Returns 0 always.
    """
    cwd = os.getcwd()
    suspicious_dirs: dict[str, list[str]] = {}

    def scan_dir(d: str) -> None:
        try:
            entries = os.listdir(d)
        except OSError:
            return
        markers_here: list[str] = []
        for name in entries:
            full = os.path.join(d, name)
            if name in BARE_REPO_MARKERS and os.path.isfile(full):
                markers_here.append(name)
        if len(markers_here) >= 2:
            rel = os.path.relpath(d, cwd) or "."
            if not is_inside_real_git_dir(rel):
                suspicious_dirs[rel] = markers_here

    # Scan cwd root only — depth-0. The PreToolUse hook catches new writes
    # at depth-1 actively; this session scan is a safety net for pre-existing
    # state and at depth-1 it produces too many false positives from
    # legitimate config dirs (.azure, .aws, etc.).
    scan_dir(cwd)

    if suspicious_dirs:
        print(
            "WARNING: directories with multiple bare-repo markers detected:",
            file=sys.stderr,
        )
        for d, markers in suspicious_dirs.items():
            print(f"  {d}: {', '.join(markers)}", file=sys.stderr)
        print(
            "These may cause git to treat the directory as a bare repository. "
            "Review before running any git command in that directory.",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--session-scan":
        return session_scan()

    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # malformed input — don't block

    tool_input = data.get("tool_input", {})
    # Write tool uses file_path, Edit tool uses file_path.
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return 0

    blocked, reason = is_bare_repo_marker(path)
    if blocked:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
