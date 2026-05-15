#!/usr/bin/env python3
"""Shared path validation helper for .claude/hooks/*.

is_sensitive_path(path: str) -> tuple[bool, str]
returns (blocked, reason). A False return means the path passes all
defenses; True means one or more rules blocked it.

Defense categories (mirrors Claude Code's utils/permissions/pathValidation.ts):
    1. Shell expansion rejection  ($VAR, ${VAR}, $(cmd), backticks, %VAR%, ~user)
    2. Case normalization         (Docs/Plan.md matches docs/plan.md)
    3. os.path.normpath()         (docs/../docs/plan.md expands before matching)
    4. Glob rejection             (* ** ? [ ] reject in write ops)
    5. UNC path rejection         (backslash-backslash host share form)

Performance budget: under 10ms per call. Pure stdlib, no third-party imports.
"""

from __future__ import annotations

import os
import re

# --- Sensitive pattern catalogue -------------------------------------------
# Lowercased patterns. Glob patterns from block-stage-sensitive.sh translated
# into simple startswith / contains rules that apply AFTER normalization.

# Files with EXACT basename match (post-normalize).
# Map each sensitive basename to a short rationale. Presence in this mapping
# is the authoritative block list — see SENSITIVE_BASENAMES below.
DANGEROUS_FILE_REASONS: dict[str, str] = {
    ".env": "contains secrets — staging refused",
    ".env.local": "contains secrets — staging refused",
    ".env.production": "contains secrets — staging refused",
    ".env.development": "contains secrets — staging refused",
    ".gitconfig": "can set core.hooksPath to attacker directory — staging refused",
    ".gitmodules": "can pull attacker-controlled submodule — staging refused",
    ".bashrc": "executes on every bash shell start — staging refused",
    ".bash_profile": "executes on every login bash shell — staging refused",
    ".zshrc": "executes on every zsh shell start — staging refused",
    ".zprofile": "executes on every login zsh shell — staging refused",
    ".profile": "executes on every POSIX shell login — staging refused",
    ".ripgreprc": "executes when any rg invocation starts — staging refused",
    ".mcp.json": "configures MCP servers run by Claude Code — staging refused",
    ".claude.json": "configures Claude Code behavior — staging refused",
}

SENSITIVE_BASENAMES = frozenset(DANGEROUS_FILE_REASONS.keys())

# Substring anywhere in the path (post-normalize, case-insensitive).
SENSITIVE_SUBSTRINGS = (
    "credentials",
    "/.credentials.json",
)

# Path prefixes that are blocked (post-normalize, case-insensitive).
SENSITIVE_PREFIXES = (
    ".claude/projects/",
    ".claude/sessions/",
    ".claude/todos/",
    ".claude/paste-cache/",
    ".claude/shell-snapshots/",
    ".claude/statsig/",
    ".claude/debug/",
    ".claude/logs/",
    ".claude/memory/",
    ".claude/file-history/",
    ".claude/backups/",
    ".claude/cache/",
    "docs/progress.md",
    "docs/plan",
    "docs/prompts",
    "docs/analysis",
    "docs/prp",
    "docs/review",
    "docs/pipeline-state.md",
    "docs/.last-verify.json",
    "docs/context-dump.md",
    ".vscode/",
    ".idea/",
)

# Paths that are explicitly exempt even when they match above rules.
EXEMPT_PATHS = frozenset({
    ".claude/claude.md",  # project CLAUDE.md is committed
})

# Exempt prefix match — anything under .claude/skills/<name>/ that ends in SKILL.md
# and tracked agent/hook/rule files are allowed by the consuming shell hook,
# not by _pathguard. _pathguard only concerns itself with outright-dangerous paths.

# --- Defense regexes -------------------------------------------------------

SHELL_EXPANSION_RE = re.compile(
    r"\$[A-Za-z_{(]"          # $VAR, ${VAR}, $(cmd)
    r"|\$\{[^}]*\}"           # ${...}
    r"|\$\([^)]*\)"           # $(...)
    r"|`[^`]*`"               # backticks
    r"|%[A-Za-z_][A-Za-z0-9_]*%"  # %VAR% (Windows)
    r"|(^|[^=])~[A-Za-z0-9._-]+"  # ~user (home expansion of other users)
)

GLOB_RE = re.compile(r"[*?\[\]]")

UNC_RE = re.compile(r"^\\\\[^\\]+\\")


def is_sensitive_path(path: str) -> tuple[bool, str]:
    """Return (blocked, reason). False => path passes all defenses."""
    if not path:
        return (False, "")

    # 1. Shell expansion rejection (applied to raw input)
    if SHELL_EXPANSION_RE.search(path):
        return (True, f"shell expansion in path '{path}' — refused")

    # 4. Glob rejection (applied to raw input)
    if GLOB_RE.search(path):
        return (True, f"glob pattern in path '{path}' — refused in write ops")

    # 5. UNC path rejection (applied to raw input)
    if UNC_RE.match(path):
        return (True, f"UNC path '{path}' — refused (NTLM credential leak risk)")

    # 3. Normalize (collapses .. and duplicate slashes)
    normalized = os.path.normpath(path).replace("\\", "/")

    # 2. Case fold for comparison
    lowered = normalized.lower()
    basename = os.path.basename(lowered)

    # Exemption check
    if lowered in EXEMPT_PATHS:
        return (False, "")

    # Exact basename match — emit the specific rationale
    if basename in DANGEROUS_FILE_REASONS:
        reason = f"{basename}: {DANGEROUS_FILE_REASONS[basename]}"
        return (True, reason)

    # Substring match
    for s in SENSITIVE_SUBSTRINGS:
        if s in lowered:
            return (True, f"sensitive substring '{s}' in '{normalized}' — refused")

    # Prefix match
    for p in SENSITIVE_PREFIXES:
        if lowered.startswith(p):
            # Opt-in exemption: projects can allow tracked .vscode/settings.json
            # by setting HOOK_ALLOW_VSCODE_SETTINGS=1 in their environment.
            if p == ".vscode/" and lowered == ".vscode/settings.json":
                if os.environ.get("HOOK_ALLOW_VSCODE_SETTINGS") == "1":
                    return (False, "")
            return (True, f"sensitive prefix '{p}' in '{normalized}' — refused")

    # Normalization changed the path AND it still looks harmless?
    # Normalized paths that differ from input but don't match any rule are
    # allowed. Normalized paths that differ AND match a sensitive rule are
    # already caught above — that's the whole point of normalizing first.

    return (False, "")


def _main() -> int:
    """CLI:
    _pathguard.py <path>            -- check a single path
    _pathguard.py --stdin           -- read one path per line; exit 1 if ANY blocks

    Exit codes: 0 allow, 1 block, 2 usage error.
    """
    import sys

    if len(sys.argv) < 2:
        print("usage: _pathguard.py <path> | --stdin", file=sys.stderr)
        return 2

    if sys.argv[1] == "--stdin":
        any_blocked = False
        for raw in sys.stdin:
            p = raw.strip()
            if not p:
                continue
            blocked, reason = is_sensitive_path(p)
            if blocked:
                print(f"BLOCKED: {reason}", file=sys.stderr)
                any_blocked = True
        return 1 if any_blocked else 0

    blocked, reason = is_sensitive_path(sys.argv[1])
    if blocked:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
