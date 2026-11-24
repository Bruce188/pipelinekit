"""What the garden scan parts share: the project, its files, safe names.

The scan reads files and asks git and gh. It runs nothing from the project.
Everything it reports is a file name that passed `shown`, a count, a duration
or a date, so no text from a file reaches the report.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
from pathlib import Path

MAX_FILES = 50000
MAX_READ = 512 * 1024
# Folders that hold installed packages, build output or caches, never the
# project's own work.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".nox",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "obj",
        "bin",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        "vendor",
        "site-packages",
        ".gradle",
        ".idea",
    }
)
# A name the report may repeat: plain letters, digits and a few signs.
SAFE_REL = re.compile(r"[A-Za-z0-9_.@+=,-]+(?:/[A-Za-z0-9_.@+=,-]+)*")
SAFE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
SAFE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+@-]{0,79}")
MAX_SHOWN = 160
GARDEN_DIR = "docs/garden"


def shown(rel):
    """`rel` when the report may repeat it, else None."""
    if (
        isinstance(rel, str)
        and len(rel) <= MAX_SHOWN
        and SAFE_REL.fullmatch(rel)
        and ".." not in rel.split("/")
    ):
        return rel
    return None


def git_run(cwd, *args, timeout=20):
    """(exit code, stdout, stderr) of a read-only git command.

    127 when git is missing, 124 when it gave no answer in time. Messages are
    asked for in English so that "not a git repository" can be told apart.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    try:
        p = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return 124, "", ""
    except OSError:
        return 127, "", ""
    return p.returncode, p.stdout, p.stderr


def git(cwd, *args, timeout=20):
    """(exit code, stdout) of a read-only git command; 127 when git is missing."""
    rc, out, _err = git_run(cwd, *args, timeout=timeout)
    return rc, out


class Project:
    """The project in a directory: its root, whether it is a git checkout, its files."""

    def __init__(self, cwd):
        self.cwd = Path(cwd).resolve()
        rc, out, err = git_run(self.cwd, "rev-parse", "--show-toplevel")
        self.in_git = rc == 0 and bool(out.strip())
        self.root = Path(out.strip()).resolve() if self.in_git else self.cwd
        # Why git could not be asked, when it is not simply "not a repository".
        self.git_problem = None
        if rc == 127:
            self.git_problem = "git is not installed"
        elif rc == 124:
            self.git_problem = "git gave no answer within 20 seconds"
        elif not self.in_git and "not a git repository" not in err.lower():
            self.git_problem = f"git rev-parse failed with exit {rc}"
        self._files = None
        self.truncated = False
        # True when the project's own folder could not be listed: then no
        # count from the file list means anything.
        self.files_unavailable = False

    @property
    def garden(self):
        return self.root / GARDEN_DIR

    def files(self):
        """The project's own files, relative, with `/`; caches and packages left out."""
        if self._files is None:
            names = self._git_files() if self.in_git else None
            if names is None:
                names = self._walk()
            kept = []
            for name in names:
                parts = name.split("/")
                if any(p in SKIP_DIRS for p in parts[:-1]):
                    continue
                if name.startswith(GARDEN_DIR + "/"):
                    continue
                kept.append(name)
                if len(kept) >= MAX_FILES:
                    self.truncated = True
                    break
            self._files = sorted(set(kept))
        return self._files

    def _git_files(self):
        rc, out = git(
            self.root,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            timeout=30,
        )
        if rc:
            return None
        return [n for n in out.split("\0") if n]

    def _walk(self):
        names = []
        root = os.fspath(self.root)

        def failed(err):
            if err.filename == root:
                self.files_unavailable = True

        for top, dirs, files in os.walk(self.root, onerror=failed):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            rel = os.path.relpath(top, self.root).replace(os.sep, "/")
            for f in sorted(files):
                names.append(f if rel == "." else f"{rel}/{f}")
                if len(names) >= MAX_FILES:
                    self.truncated = True
                    return names
        return names

    def inside(self, path):
        """True when `path`, with its links followed, stays in the project."""
        try:
            return path.resolve().is_relative_to(self.root)
        except (OSError, RuntimeError):
            return False

    def has(self, rel):
        path = self.root / rel
        return path.is_file() and self.inside(path)

    def read(self, rel, limit=MAX_READ):
        """The text of a file of the project, or None when it is missing, too big
        or a link that leads out of the project."""
        path = self.root / rel
        try:
            if not path.is_file() or not self.inside(path):
                return None
            if path.stat().st_size > limit:
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None


def garden_problem(project):
    """Why docs/garden/ cannot be written safely, or None.

    A link on the way would send the files out of the project.
    """
    path = project.root
    for part in GARDEN_DIR.split("/"):
        path = path / part
        rel = path.relative_to(project.root).as_posix()
        if path.is_symlink():
            return f"{rel} is a link; remove it"
        if path.exists() and not path.is_dir():
            return f"{rel} is a file, not a folder; move it"
    return None


def write_new(path, text):
    """Write `path` through a fresh temporary file; no link is followed.

    Raises OSError and leaves no temporary file behind when it fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.unlink(missing_ok=True)
        with open(tmp, "x", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def duration(seconds):
    """`4.2 s`, `42 s`, `4 min 12 s` or `1 h 3 min`."""
    s = int(round(seconds))
    if seconds < 10:
        return f"{seconds:.1f} s"
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60} s"
    return f"{s // 3600} h {s % 3600 // 60} min"
