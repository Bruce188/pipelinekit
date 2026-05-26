"""Test-runner auto-detection helper for the implement-plan inner loop.

Pure stdlib. The helper inspects the project root for a small set of
well-known marker files and returns the canonical shell command string the
implement-plan Step 2e.5 inner loop should invoke.

Probe order (first match wins, per `feat/implement-test-loop` spec):

    1. ``pyproject.toml`` OR ``setup.py``                 -> ``"pytest"``
    2. ``package.json`` w/ non-empty ``scripts.test``     -> ``"npm test"``
    3. ``go.mod``                                         -> ``"go test ./..."``
    4. ``Makefile`` containing a ``^test:`` target        -> ``"make test"``
    5. (no marker matched)                                -> ``None``

Safety contract: this module NEVER calls ``eval``, ``exec``,
``subprocess``, ``os.system``, or any shell. It only reads file presence
and the contents of ``package.json`` / ``Makefile`` via ``pathlib`` +
``json`` + ``re``. The returned string is one of four hard-coded literals
or ``None``; the caller is responsible for passing it to a subprocess
runner with arguments split (no ``shell=True``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

__all__ = ["detect_test_runner"]

_MAKEFILE_TEST_TARGET = re.compile(r"^test\s*:", re.MULTILINE)


def detect_test_runner(project_root: str) -> Optional[str]:
    """Probe ``project_root`` for a known test-runner marker.

    Returns the canonical shell command string for the first match in the
    documented probe order, or ``None`` if no marker matched.

    Args:
        project_root: Filesystem path to the project root. Accepted as a
            ``str`` (the helper internally wraps it in ``pathlib.Path``).

    Returns:
        One of ``"pytest"``, ``"npm test"``, ``"go test ./..."``,
        ``"make test"``, or ``None``.

    Never raises on missing / unreadable / malformed marker files —
    ``json.JSONDecodeError`` and ``OSError`` are caught and treated as
    "not detected" so the caller can continue past a quirky file.
    """
    root = Path(project_root)

    # 1. pytest
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "pytest"

    # 2. npm test (requires non-empty scripts.test)
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict):
            scripts = data.get("scripts")
            if isinstance(scripts, dict):
                test_cmd = scripts.get("test", "")
                if isinstance(test_cmd, str) and test_cmd.strip():
                    return "npm test"

    # 3. go test
    if (root / "go.mod").exists():
        return "go test ./..."

    # 4. make test
    makefile = root / "Makefile"
    if makefile.exists():
        try:
            contents = makefile.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            contents = ""
        if _MAKEFILE_TEST_TARGET.search(contents):
            return "make test"

    return None
