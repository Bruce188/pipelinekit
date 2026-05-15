#!/usr/bin/env python3
"""Match engine for block-stage-sensitive.sh.

Usage: python3 _never_stage_match.py COMMAND CONFIG_PATH
Exits 1 if any token in the git add command matches a pattern in CONFIG_PATH.
Exits 0 if no match (allow through).
Exits 2 on error (config missing — treated as default-deny by the caller).
"""
from __future__ import annotations
import fnmatch
import re
import sys


def load_patterns(config_path: str) -> list[str]:
    with open(config_path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def tokenize(command: str) -> list[str]:
    """Extract path tokens from a git add command."""
    m = re.search(r"git\s+add\s+(.*)", command)
    if not m:
        return []
    remainder = m.group(1)
    # Trim at first shell operator so downstream commands do not bleed in.
    remainder = re.split(r"\s*(?:&&|\|\||;|\|(?!\|)|\n)", remainder)[0]
    # Strip flags
    remainder = re.sub(r"\s+-[A-Za-z]+", "", remainder)
    remainder = re.sub(r"\s+--[a-z-]+", "", remainder)
    tokens = []
    for tok in re.split(r"\s+", remainder.strip()):
        tok = tok.strip('"').strip("'")
        if tok:
            tokens.append(tok)
    return tokens


def matches(token: str, pattern: str) -> bool:
    """Return True if token matches the fnmatch-style pattern.

    Pattern semantics:
    - Ending /  : directory segment match — any component of the path equals the segment.
    - Contains * or ? with a / prefix path (e.g. docs/review*): fnmatch against the
      full token and against progressively-shorter suffix sub-paths (e.g. docs/review*
      matches token docs/review-v5.md via the sub-path check).
    - Contains * or ? with NO / in the pattern (e.g. *.pyc, credentials*): fnmatch
      against the full token AND against the basename component only.
    - Plain (no wildcards, no trailing /): exact boundary-aware match. .env blocks
      .env at a path boundary but NOT .env.example, .envrc, environment.py.
    """
    norm_tok = token.replace("\\", "/")

    # Directory patterns (ending /)
    if pattern.endswith("/"):
        seg = pattern.rstrip("/")
        parts = norm_tok.split("/")
        return seg in parts

    # Wildcard patterns
    if "*" in pattern or "?" in pattern:
        # Full token match
        if fnmatch.fnmatchcase(norm_tok, pattern):
            return True
        parts = norm_tok.split("/")
        # Try progressively-shorter suffix sub-paths (handles docs/review* etc.)
        for i in range(len(parts)):
            sub = "/".join(parts[i:])
            if fnmatch.fnmatchcase(sub, pattern):
                return True
        # For patterns WITHOUT a directory component (e.g. *.pyc, credentials*),
        # also check the basename. Patterns WITH a directory component (e.g.
        # .claude/*, docs/review*) must NOT match arbitrary basenames.
        if "/" not in pattern:
            return fnmatch.fnmatchcase(parts[-1], pattern)
        return False

    # Plain pattern: boundary-aware match
    # .env blocks token == .env, or ends with /.env, or starts with .env/, or contains /.env/
    norm_pat = pattern
    if norm_tok == norm_pat:
        return True
    if norm_tok.endswith("/" + norm_pat):
        return True
    if norm_tok.startswith(norm_pat + "/"):
        return True
    if ("/" + norm_pat + "/") in norm_tok:
        return True
    return False


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: _never_stage_match.py COMMAND CONFIG_PATH", file=sys.stderr)
        return 2

    command = sys.argv[1]
    config_path = sys.argv[2]

    try:
        patterns = load_patterns(config_path)
    except OSError as e:
        print(f"ERROR: cannot read config: {e}", file=sys.stderr)
        return 2

    tokens = tokenize(command)
    if not tokens:
        return 0

    for token in tokens:
        for pattern in patterns:
            if matches(token, pattern):
                return 1  # match found — block

    return 0  # no match — allow


if __name__ == "__main__":
    raise SystemExit(main())
