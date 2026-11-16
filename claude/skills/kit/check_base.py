"""Constants, small helpers and the install manifest of check.py."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import unicodedata

SCHEMA = 1
HOOKS = (
    "bash-guard.py",
    "block-bare-repo-markers.py",
    "post-edit-format.sh",
    "session-check.py",
)
# Imported or called by the hooks; not wired into settings.json themselves.
# Each with what goes missing without it.
HELPERS = ("kitlog.py", "filesize.py")
HELPER_LOSS = {
    "kitlog.py": "the hooks still decide, but nothing is recorded",
    "filesize.py": "pre-commit lets commits through without the file size limit",
}
GIT_HOOKS = ("commit-msg", "pre-commit", "pre-push")
# Used when there is no manifest; a test keeps it equal to claude/skills/.
KIT_SKILLS = (
    "deploy",
    "docs-writer",
    "dotnet-conventions",
    "exchange-api-keys",
    "frontend-design",
    "judge-loop",
    "kit",
    "mobile",
    "ship",
)
# A test keeps it equal to claude/agents/ and to the installer's list.
KIT_AGENTS = ("kit-planner.md", "kit-builder.md", "kit-judge.md")
# The judge reads and never writes or runs anything.
JUDGE_TOOLS = ("Read", "Grep", "Glob")
PLACEHOLDERS = ("${USER_NAME}", "${USER_EMAIL}", "${CLAUDE_HOME}")
SECTIONS = (
    ("install", "Install"),
    ("drift", "Changes since install"),
    ("probe", "Live probe"),
    ("environment", "Environment"),
    ("update", "Updates"),
    ("activity", "Activity"),
)
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
# Letters and symbols that draw as nothing: the fillers and the braille blank.
BLANK = frozenset("\u115f\u1160\u3164\uffa0\u2800")
# What the report repeats from settings.json or the manifest has to read as a
# name. Anything else is counted, not quoted.
PLAIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,39}")
PLAIN_EVENT = re.compile(r"[A-Za-z]{1,40}")
PLAIN_MATCHER = re.compile(r"[A-Za-z0-9_.*|-]{0,60}")
PLAIN_RULE = re.compile(r"[A-Za-z0-9_]{1,40}(\([!-~]([ -~]{0,78}[!-~])?\))?")
PLAIN_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,39}")
PLAIN_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+@-]{0,79}")
PLAIN_COMMIT = re.compile(r"[0-9a-f]{7,64}")
PLAIN_TIME = re.compile(r"[0-9TZ:.+-]{1,32}")
MAX_PATH_SHOWN = 120
SAFE_REL = re.compile(r"[A-Za-z0-9._@+-]+(/[A-Za-z0-9._@+-]+)*")
WSL_NOTE = (
    "WSL: in Claude Code Desktop pick the WSL environment; "
    "a Local (Windows) session cannot run these hooks"
)
# The kit ships frontend-design; the same skill enabled as a plugin loads twice.
DESIGN_SKILL = "frontend-design"
DESIGN_PLUGIN_NOTE = (
    "frontend-design is also enabled as a plugin, so sessions that load plugins "
    "get two copies (harmless). To keep one, disable the plugin: /plugin in a "
    "terminal session, or its enabledPlugins entry in ~/.claude/settings.json."
)
# An enabledPlugins key for it: the name, "@" and a marketplace name.
DESIGN_PLUGIN_KEY = re.compile(re.escape(DESIGN_SKILL) + r"@[A-Za-z0-9._-]+")
# The hooks' event log. claude/hooks/kitlog.py writes it; a test keeps the
# kinds and the two patterns equal to the ones there.
EVENT_KINDS = {
    "block": "blocked",
    "ask": "asked",
    "override": "override used",
    "error": "failed",
}
EVENT_HOOK = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
EVENT_RULE = re.compile(r"^[a-z-]{1,30}\.[a-z0-9-]{1,40}$")
SESSION = re.compile(r"[A-Za-z0-9_-]{1,80}")
MAX_LOG_BYTES = 4_000_000  # read at most this much of a log file
ACTIVITY_LINES = 20
# The update check: how long an answer of the remote is reused, in seconds.
UPDATE_TTL = {"ok": 24 * 3600, "gone": 24 * 3600, "unreachable": 3600}
UPDATE_TIMEOUT = 5  # seconds the remote gets to answer
BRANCH = re.compile(r"(?!-)[A-Za-z0-9._/+-]{1,200}")
COMMIT = re.compile(r"[0-9a-f]{40,64}")


def clean(text: object, limit: int = 300) -> str:
    """One line of characters that show. People and a model read the report.

    Controls, format and direction marks, private-use and unassigned code
    points, every kind of space and the blank letters become one plain space.
    Marks that stack on a letter are dropped once composing has used them.
    """
    out = []
    for ch in unicodedata.normalize("NFC", str(text)[: limit * 8]):
        kind = unicodedata.category(ch)
        if kind[0] in "CZ" or ch in BLANK:
            out.append(" ")
        elif kind not in ("Mn", "Me"):
            out.append(ch)
    return " ".join("".join(out).split())[:limit]


def plain(value: object, pattern: re.Pattern) -> str:
    """The value when it reads as the name the pattern describes, else ""."""
    return value if isinstance(value, str) and pattern.fullmatch(value) else ""


def names(items: list[str], limit: int = 5) -> str:
    more = len(items) - limit
    return ", ".join(str(i) for i in items[:limit]) + (
        f" and {more} more" if more > 0 else ""
    )


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def run(
    argv: list[str],
    *,
    stdin: str = "",
    env: dict | None = None,
    cwd: str | None = None,
    timeout: int = 10,
) -> tuple[int | None, str, str]:
    """(exit code, stdout, stderr). Exit code None: the program did not start."""
    try:
        p = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "", str(exc)
    return p.returncode, p.stdout, p.stderr


def run_group(argv: list[str], env: dict, timeout: int) -> tuple[int | None, str]:
    """(exit code, stdout) of a program that may start others, as git does.

    It gets no terminal to ask on, and a timeout ends its children too.
    Exit code None: it did not start or did not finish in time.
    """
    try:
        p = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            env=env,
            start_new_session=True,
        )
    except OSError:
        return None, ""
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None, ""
    return p.returncode, out


def git_value(*args: str) -> str:
    rc, out, _ = run(["git", *args], timeout=5)
    return out.strip() if rc == 0 else ""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str) -> tuple[dict | None, str]:
    """(object, "") or (None, why)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, "missing"
    except RecursionError:
        return None, "unreadable (nested too deep)"
    except (OSError, ValueError) as exc:
        return None, f"unreadable ({exc})"
    if not isinstance(data, dict):
        return None, "not a JSON object"
    return data, ""


def manifest_problem(m: dict) -> str:
    """What in an install manifest has the wrong type, or ""."""

    def texts(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)

    keys = ("version", "commit", "branch", "origin", "checkout", "installed_at")
    for key in (*keys, "hooks_path"):
        if not isinstance(m.get(key, ""), str):
            return f"{key} is not text"
    if not texts(m.get("skills", [])):
        return "skills is not a list of names"
    files = m.get("files", {})
    if not isinstance(files, dict) or not texts(list(files.values())):
        return "files is not a table of names and hashes"
    settings = m.get("settings", {})
    if not isinstance(settings, dict):
        return "settings is not an object"
    for kind in ("deny", "ask"):
        if not texts(settings.get(kind, [])):
            return f"settings.{kind} is not a list of rules"
    hooks = settings.get("hooks", [])
    if not isinstance(hooks, list):
        return "settings.hooks is not a list"
    for e in hooks:
        if not (
            isinstance(e, dict)
            and all(isinstance(e.get(k, ""), str) for k in ("event", "matcher"))
            and isinstance(e.get("command", ""), str)
            and texts(e.get("args", []))
        ):
            return "settings.hooks has an entry that is not a hook"
    return ""


def wiring(event: object, matcher: object, command: object, args: object) -> str:
    """One hook entry as text that compares, whatever types a file holds."""
    return json.dumps([event, matcher, command, args], sort_keys=True, default=str)


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def without_credentials(url: str) -> str:
    """A remote URL can carry a token; keep scheme, host and path."""
    return re.sub(r"://[^/@]*@", "://", url)


def same_path(a: str, b: str) -> bool:
    return bool(a) and os.path.expanduser(a).rstrip("/") == b.rstrip("/")


# ---------------------------------------------------------------- manifest


def skill_dirs(repo: str) -> list[str]:
    """The folders below claude/skills that hold a SKILL.md, sorted."""
    skills = os.path.join(repo, "claude", "skills")
    return sorted(
        d
        for d in os.listdir(skills)
        if os.path.isfile(os.path.join(skills, d, "SKILL.md"))
    )


def kit_files(repo: str) -> list[str]:
    """Every file the installer copies, as a path below CLAUDE_HOME."""
    src = os.path.join(repo, "claude")
    out = []
    for n in sorted(os.listdir(os.path.join(src, "hooks"))):
        if n.endswith((".py", ".sh")) and os.path.isfile(os.path.join(src, "hooks", n)):
            out.append(f"hooks/{n}")
    out += [
        f"git-hooks/{n}" for n in sorted(os.listdir(os.path.join(src, "git-hooks")))
    ]
    for skill in skill_dirs(repo):
        for root, dirs, files in os.walk(os.path.join(src, "skills", skill)):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for n in sorted(files):
                if not n.endswith(".pyc"):
                    out.append(os.path.relpath(os.path.join(root, n), src))
    out += [f"agents/{n}" for n in KIT_AGENTS]
    out.append("config/never-stage.txt")
    return out


def kit_settings(repo: str, home: str) -> dict:
    """The settings.json entries the kit owns, as the installer renders them."""
    path = os.path.join(repo, "claude", "config", "settings.template.json")
    with open(path, encoding="utf-8") as f:
        tmpl = json.loads(f.read().replace("${CLAUDE_HOME}", home))
    hooks = [
        {
            "event": event,
            "matcher": g.get("matcher", ""),
            "command": h.get("command", ""),
            "args": h.get("args", []),
        }
        for event, groups in tmpl.get("hooks", {}).items()
        for g in groups
        for h in g.get("hooks", [])
    ]
    perms = tmpl.get("permissions", {})
    return {"hooks": hooks, "deny": perms.get("deny", []), "ask": perms.get("ask", [])}


def write_manifest(repo: str, home: str) -> str:
    repo = os.path.abspath(repo)

    def g(*args: str) -> str:
        return git_value("-C", repo, *args)

    try:
        with open(os.path.join(repo, "VERSION"), encoding="utf-8") as f:
            version = f.read().strip()
    except OSError:
        version = ""
    files = {}
    for rel in [*kit_files(repo), "CLAUDE.md"]:
        full = os.path.join(home, rel)
        files[rel] = sha256(full) if os.path.isfile(full) else ""
    manifest = {
        "schema": SCHEMA,
        "version": version,
        "commit": g("rev-parse", "HEAD"),
        "branch": g("branch", "--show-current"),
        "origin": without_credentials(g("remote", "get-url", "origin")),
        "checkout": repo,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hooks_path": git_value("config", "--global", "--get", "core.hooksPath"),
        # False: installed with --no-serena; an update keeps it that way.
        "serena": os.environ.get("CLAUDE_INSTALL_SKIP_SERENA") != "1",
        "skills": skill_dirs(repo),
        "files": files,
        "settings": kit_settings(repo, home),
    }
    target = os.path.join(home, "pipelinekit", "manifest.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target + ".tmp", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    os.replace(target + ".tmp", target)
    return target
