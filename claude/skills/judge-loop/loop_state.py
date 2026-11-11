"""Git, repository files, the state file and which loop is meant."""

# ruff: noqa: F403, F405
from __future__ import annotations

import contextlib
import datetime
import json
import math
import os
import re
import stat
import subprocess
from pathlib import Path

from loop_text import *

# Git and files ----------------------------------------------------------------


def git_said(text, rc):
    """Why a git command failed: its error line, without the hints around it."""
    lines = [line.strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line and not line.startswith("hint:")]
    errors = [line for line in lines if line.startswith(("fatal:", "error:"))]
    return " ".join((errors or lines or [""])[0].split())[:LIMIT] or f"exit {rc}"


class Git:
    """Every git call of the helper, run with the repository root as cwd."""

    def __init__(self, root):
        self.root = root

    def run(self, *args, ok=(0,)):
        proc = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, check=False
        )
        if ok is not None and proc.returncode not in ok:
            err = proc.stderr.decode("utf-8", "replace")
            raise GitFailed(args[0], proc.returncode, git_said(err, proc.returncode))
        return proc

    def out(self, *args, ok=(0,)):
        return os.fsdecode(self.run(*args, ok=ok).stdout).strip()

    def code(self, *args):
        return self.run(*args, ok=None).returncode


class Ctx:
    """The checkout a command runs in."""

    def __init__(self):
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                check=False,
            )
        except OSError:
            raise Exit(2, NOT_A_REPO) from None
        top = os.fsdecode(proc.stdout).strip()
        if proc.returncode or not top:
            raise Exit(2, NOT_A_REPO)
        self.root = Path(os.path.realpath(top))
        self.git = Git(self.root)
        self.branch = self.git.out("branch", "--show-current")
        remote = ""
        if self.branch:
            remote = self.git.out("config", f"branch.{self.branch}.remote", ok=(0, 1))
        self.remote = remote if REMOTE_NAME.fullmatch(remote) else "origin"
        self.has_remote = bool(self.git.out("remote"))

    def head(self):
        return self.git.out("rev-parse", "--verify", "HEAD", ok=(0, 128))

    def resolve(self, ref):
        if not ref:
            return ""
        sha = self.git.out(
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{ref}^{{commit}}",
            ok=(0, 1, 128),
        )
        return sha if SHA.fullmatch(sha) else ""

    def merge_base(self, sha):
        out = self.git.out("merge-base", sha, "HEAD", ok=(0, 1))
        return out if SHA.fullmatch(out) else ""

    def dirty(self):
        out = self.git.run("status", "--porcelain", "-z", "--untracked-files=no").stdout
        return bool(out)

    def is_ancestor(self, older, newer):
        return self.git.code("merge-base", "--is-ancestor", older, newer) == 0


DIRTY = (
    "Refused: tracked files have uncommitted changes. "
    "Next: commit, then the same command."
)


def link_error(rel, folder):
    return Exit(
        2,
        f"Error: {show_path(rel)} is tracked by git or reached through a link. "
        f"Next: move the folder {show_path(folder)} away, then loop.py start again.",
    )


def check_contained(root, rel, folder=None):
    """No part of `rel` below the root is a link; the real path is the literal one."""
    parts = Path(rel).parts
    here = root
    for i, part in enumerate(parts):
        here = here / part
        try:
            st = os.lstat(here)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(st.st_mode) or (
            i < len(parts) - 1 and not stat.S_ISDIR(st.st_mode)
        ):
            raise link_error(rel, folder or "/".join(parts[: i + 1]))
    if os.path.realpath(root / rel) != str(root / rel):
        raise link_error(rel, folder or rel)
    return root / rel


def read_plain(path, limit):
    """The bytes of a regular file of at most `limit` bytes; None when missing.

    A link, a file of another type or a larger file gives False.
    """
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    except OSError as err:
        if os.path.islink(path):
            return False
        raise err
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return False
        data = fh.read(limit + 1)
    return data if len(data) <= limit else False


def write_atomic(path, data: bytes):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def ensure_ignored(ctx):
    """docs/loops/ is ignored, by the checkout's own rules or the exclude file."""
    if ctx.git.code("check-ignore", "-q", "docs/loops/x") == 0:
        return
    path = Path(ctx.git.out("rev-parse", "--git-path", "info/exclude"))
    if not path.is_absolute():
        path = ctx.root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_bytes() if path.exists() else b""
    lead = b"\n" if old and not old.endswith(b"\n") else b""
    with open(path, "ab") as fh:
        fh.write(lead + b"docs/loops/\n")


def user_home():
    home = os.environ.get("CLAUDE_HOME")
    if home:
        return Path(home), "$CLAUDE_HOME/CLAUDE.md"
    return Path(os.path.expanduser("~")) / ".claude", "~/.claude/CLAUDE.md"


def agents_dir():
    """The installed agent files: <skill dir>/../../agents."""
    return Path(os.path.abspath(__file__)).parent.parent.parent / "agents"


def skill_dir():
    return Path(os.path.abspath(__file__)).parent


def utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


# State ------------------------------------------------------------------------

STATE_TYPES = {
    "schema": int,
    "kind": str,
    "name": str,
    "branch": str,
    "base": str,
    "base_ref": str,
    "base_sha": str,
    "base_source": str,
    "panel": list,
    "panel_reason": str,
    "panel_forced": str,
    "budget": int,
    "switches": list,
    "agents": str,
    "plan_loop": dict,
    "pending": dict,
    "rounds": list,
    "items": dict,
    "last_full": dict,
    "streak": int,
    "notes": list,
    "outcome": str,
    "commit": str,
    "skip": dict,
}
HEX64 = re.compile(r"[0-9a-f]{64}")


def is_type(value, kind):
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def is_number(value):
    return (is_type(value, int) or isinstance(value, float)) and math.isfinite(value)


def sha_or_empty(value, empty_ok=True):
    return (empty_ok and value == "") or bool(SHA.fullmatch(value))


def good_branch(git, name):
    if not name or name.startswith("-"):
        return False
    proc = git.run("check-ref-format", "--branch", name, ok=None)
    return proc.returncode == 0 and os.fsdecode(proc.stdout).strip() == name


def state_ok(st, kind, name, git):
    """True when a loaded state holds every field with a fitting value."""
    if any(not is_type(st.get(k), t) for k, t in STATE_TYPES.items()):
        return False
    build = st["kind"] == "build"
    checks = [
        st["kind"] == kind and st["name"] == name and NAME.fullmatch(name),
        st["outcome"] in OUTCOMES,
        st["panel"] and all(r in ROLES for r in st["panel"]),
        len(set(st["panel"])) == len(st["panel"]),
        st["panel_forced"] in ("", "single", "full"),
        st["agents"] in ("kit", "fallback"),
        st["budget"] >= 1 and st["streak"] >= 0,
        sha_or_empty(st["commit"]) and sha_or_empty(st["base_sha"], not build),
        not build or st["branch"],
    ]
    if not all(checks):
        return False
    if (st["base"] or build) and not good_branch(git, st["base"]):
        return False
    ref = st["base_ref"]
    if ref and ref != f"refs/heads/{st['base']}":
        if not (ref.startswith("refs/remotes/") and ref.endswith(f"/{st['base']}")):
            return False
        if git.code("check-ref-format", ref) != 0:
            return False
    plan_loop = st["plan_loop"]
    if plan_loop and not (
        is_type(plan_loop.get("name"), str)
        and NAME.fullmatch(plan_loop["name"])
        and is_type(plan_loop.get("sha256"), str)
        and HEX64.fullmatch(plan_loop["sha256"])
    ):
        return False
    pending = st["pending"]
    if pending:
        if not is_type(pending.get("round"), int):
            return False
        if build and not (
            is_type(pending.get("commit"), str)
            and SHA.fullmatch(pending["commit"])
            and is_type(pending.get("base_sha"), str)
            and SHA.fullmatch(pending["base_sha"])
        ):
            return False
        if not build and not (
            is_type(pending.get("sha256"), str) and HEX64.fullmatch(pending["sha256"])
        ):
            return False
    for i, rnd in enumerate(st["rounds"], 1):
        if not isinstance(rnd, dict) or rnd.get("n") != i:
            return False
        for key in ("commit", "base_sha", "plan_sha256", "questions_sha256"):
            if not is_type(rnd.get(key), str):
                return False
        if build and not (
            SHA.fullmatch(rnd["commit"]) and SHA.fullmatch(rnd["base_sha"])
        ):
            return False
        if not build and (rnd["commit"] or not HEX64.fullmatch(rnd["plan_sha256"])):
            return False
        scores, results = rnd.get("scores"), rnd.get("results")
        if not (isinstance(scores, dict) and isinstance(results, dict)):
            return False
        if not all(r in ROLES and is_number(v) for r, v in scores.items()):
            return False
        if not all(is_type(v, str) for v in results.values()):
            return False
        if not (is_number(rnd.get("average")) and is_type(rnd.get("blocking"), int)):
            return False
        if not (isinstance(rnd.get("changes_only"), list)):
            return False
    for key, item in st["items"].items():
        role, _, item_id = key.partition(":")
        if (
            role not in ROLES
            or not ITEM_ID.fullmatch(item_id)
            or not isinstance(item, dict)
        ):
            return False
        if item.get("kind") not in ("blocking", "improvement"):
            return False
        if not all(is_type(item.get(k), str) for k in ("problem", "evidence", "fix")):
            return False
        if not all(is_type(item.get(k), int) for k in ("first", "last")):
            return False
        settled = item.get("settled")
        if not is_type(item.get("open"), bool) or not isinstance(settled, dict):
            return False
        if settled and not (
            is_type(settled.get("round"), int)
            and is_type(settled.get("user_ok"), bool)
            and is_type(settled.get("note"), str)
            and is_type(settled.get("raised_again"), int)
        ):
            return False
    if not all(r in ROLES and is_type(v, int) for r, v in st["last_full"].items()):
        return False
    if not all(isinstance(note, dict) for note in st["notes"]):
        return False
    return all(isinstance(entry, dict) for entry in st["switches"])


class Loop:
    """One loop folder, docs/loops/<name>/<kind>, and its state."""

    def __init__(self, ctx, kind, name):
        self.ctx, self.kind, self.name = ctx, kind, name
        self.rel = f"docs/loops/{name}/{kind}"
        self.st = None

    def path(self, sub=""):
        rel = f"{self.rel}/{sub}" if sub else self.rel
        return check_contained(self.ctx.root, rel, self.rel)

    def mkdir(self, sub=""):
        rel = f"{self.rel}/{sub}" if sub else self.rel
        here = self.ctx.root
        for part in Path(rel).parts:
            here = here / part
            check_contained(
                self.ctx.root, os.path.relpath(here, self.ctx.root), self.rel
            )
            if not os.path.lexists(here):
                os.mkdir(here)
        return self.path(sub)

    def read(self, sub, limit=MAX_TEXT_FILE):
        data = read_plain(self.path(sub), limit)
        if data is False:
            raise link_error(f"{self.rel}/{sub}", self.rel)
        return data

    def text(self, sub):
        data = self.read(sub)
        return data.decode("utf-8", "replace") if data else ""

    def write(self, sub, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        parent = os.path.dirname(sub)
        self.mkdir(parent)
        write_atomic(self.path(sub), data)

    def exists(self, sub=""):
        return os.path.lexists(self.path(sub))

    def has_files(self):
        folder = self.path()
        return folder.is_dir() and any(os.scandir(folder))

    def load(self):
        rel = f"{self.rel}/state.json"
        tracked = self.ctx.git.run("ls-files", "-z", "--", rel).stdout
        if tracked:
            raise link_error(rel, self.rel)
        unreadable = Exit(
            2,
            f"Error: {show_path(rel)} is not a readable loop state. "
            f"Next: move the folder {show_path(self.rel)} away, then loop.py start "
            "again.",
        )
        data = read_plain(self.path("state.json"), MAX_STATE)
        if not data:
            raise unreadable
        try:
            st = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise unreadable from None
        if not isinstance(st, dict):
            raise unreadable
        if is_type(st.get("schema"), int) and st["schema"] != SCHEMA:
            raise Exit(
                2,
                f"Error: {show_path(rel)} was written by another version of the kit. "
                "Next: run the installer.",
            )
        if not state_ok(st, self.kind, self.name, self.ctx.git):
            raise unreadable
        self.st = st
        return st

    def save(self):
        ensure_ignored(self.ctx)
        self.write("state.json", json.dumps(self.st, indent=1, sort_keys=True) + "\n")

    def mtime(self):
        return os.lstat(self.path("state.json")).st_mtime_ns


def scan(ctx, load=True):
    """Every loop folder of the checkout: docs/loops/<name>/<kind> with a state."""
    folder = check_contained(ctx.root, "docs/loops", "docs/loops")
    if not folder.is_dir():
        return []
    found = []
    for entry in sorted(os.scandir(folder), key=lambda e: e.name):
        if entry.is_symlink():
            raise link_error(f"docs/loops/{entry.name}", f"docs/loops/{entry.name}")
        if not entry.is_dir() or not NAME.fullmatch(entry.name):
            continue
        for kind in KINDS:
            loop = Loop(ctx, kind, entry.name)
            if os.path.lexists(loop.path("state.json")):
                found.append(loop)
    if load:
        for loop in found:
            loop.load()
    return found


QUALIFY = []
NO_OPEN = (
    "Refused: no loop is open here. Next: loop.py start plan or loop.py start build."
)
NO_LOOP = "Open: no loop here. Next: loop.py start plan or loop.py start build."
NO_SUCH = "Refused: no such loop here. Next: loop.py status."


def pick(ctx, args, command):
    """The loop a command means."""
    found = scan(ctx)
    if len(found) > 1:
        QUALIFY.append(True)
    kind, name = getattr(args, "kind", None), getattr(args, "name", None)
    if kind or name:
        found = [
            lp
            for lp in found
            if (not kind or lp.kind == kind) and (not name or lp.name == name)
        ]
        if not found:
            raise Exit(2, NO_SUCH)
        if len(found) == 1:
            return chosen(found[0])
    if ctx.branch and any(
        lp.kind == "build" and lp.st["branch"] == ctx.branch for lp in found
    ):
        found = [
            lp for lp in found if lp.kind == "plan" or lp.st["branch"] == ctx.branch
        ]
    unfinished = [lp for lp in found if lp.st["outcome"] in UNFINISHED]
    if len(unfinished) == 1:
        return chosen(unfinished[0])
    if len(unfinished) > 1:
        names = ", ".join(f"{lp.kind} {lp.name}" for lp in unfinished)
        raise Exit(
            2,
            f"Refused: more than one loop is open ({names}). "
            "Next: the same command with --kind and --name.",
        )
    if command in ("status", "leftovers"):
        if not found:
            raise Exit(0, NO_LOOP)
        return chosen(max(found, key=lambda lp: lp.mtime()))
    raise Exit(2, NO_OPEN)


def chosen(loop):
    if QUALIFY:
        QUALIFY.append((loop.kind, loop.name))
    return loop


QUALIFIED = re.compile(
    r"(loop\.py (?:brief|save|round|status|diagnosed|resume|accept|abandon|settle"
    r"|leftovers))"
    r"(?![\w-])"
)


def qualify(line):
    """With more than one loop folder, every Next: command names its loop."""
    if len(QUALIFY) < 2 or " Next: " not in line:
        return line
    kind, name = QUALIFY[-1]
    head, tail = line.split(" Next: ", 1)
    tail = QUALIFIED.sub(lambda m: f"{m.group(1)} --kind {kind} --name {name}", tail)
    return f"{head} Next: {tail}"


def check_branch(loop):
    st = loop.st
    if loop.kind == "build" and loop.ctx.branch != st["branch"]:
        mine = show_branch(st["branch"])
        other = show_branch(loop.ctx.branch) if loop.ctx.branch else "no branch"
        raise Exit(
            2,
            f"Refused: this loop is for {mine}, {other} is checked out. "
            f"Next: check out {mine}, or loop.py start build here.",
        )
