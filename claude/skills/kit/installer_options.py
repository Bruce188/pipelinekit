"""The installer options that repeat the choices an install was made with.

Part of the self-check (check.py), whose `Repair:` and `fix:` lines name the
installer with them, and of update.py, which runs the installer with them: a
repair shown by the check is the same command an update runs. Without a
terminal the installer does not ask about the git hooks, so the command says
`--git-hooks` or `--no-git-hooks` as the install manifest records it.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable


def kit_hooks(path: str, home: str) -> bool:
    """Is `path`, as core.hooksPath holds it, the kit's git-hooks folder?"""
    want = os.path.join(home, "git-hooks").rstrip("/")
    return bool(path) and os.path.expanduser(path).rstrip("/") == want


def options(manifest: dict, home: str, hooks_now: Callable[[], str]) -> list[str]:
    """--git-hooks or --no-git-hooks, then --no-serena when serena was left out.

    The global core.hooksPath the manifest recorded at install time decides
    the first; `hooks_now` (what git says now) only when the manifest has no
    record of it. A manifest without the serena field goes by whether serena
    is installed.
    """
    recorded = manifest.get("hooks_path")
    hooks = recorded if isinstance(recorded, str) else hooks_now()
    args = ["--git-hooks" if kit_hooks(hooks, home) else "--no-git-hooks"]
    serena = manifest.get("serena")
    if serena is False or (serena is None and not shutil.which("serena")):
        args.append("--no-serena")
    return args
