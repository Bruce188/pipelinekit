"""Which files of an install may be started as programs.

check.py records them in the install manifest when the kit is installed and
reports a file that has lost its executable bit since. Stdlib only.
"""

from __future__ import annotations

import os
import stat


def runnable(path: str) -> bool:
    """True if path is a regular file with an executable bit set."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and bool(mode & 0o111)


def executable(home: str, rels: list[str]) -> list[str]:
    """The paths of rels, relative to home, that are runnable, in their order."""
    return [rel for rel in rels if runnable(os.path.join(home, rel))]
