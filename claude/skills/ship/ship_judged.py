"""The judged gate of ship.py: the build was judged before the acceptance test.

It reads the judge loop's record, docs/loops/<slug of the branch>/build/state.json,
and never imports or runs loop.py. The switch-line rule and the cleaning rule
below are copies of the judge loop's (loop_start.py and loop_text.py); a test runs
the loop's switch_cases.json against this copy.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import unicodedata
from pathlib import Path

from ship_base import *

JUDGE_SCHEMA = 1
ROLES = (
    "general",
    "correctness",
    "security",
    "tests",
    "operations",
    "user-experience",
    "scope",
)
UNFINISHED = ("open", "stalled", "ask", "blocked")
FINISHED = ("done", "budget", "accepted", "abandoned", "skip")
OUTCOMES = UNFINISHED + FINISHED
MAX_SWITCH_ROUNDS = 20
MAX_STATE = 5 * 1024 * 1024
MAX_TEXT_FILE = 1024 * 1024
LIMIT = 300
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
COMMIT = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
PLAIN_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+@-]{0,79}")
BLANK = frozenset("\u115f\u1160\u3164\uffa0\u2800")
STATE_TYPES = {
    "kind": str,
    "branch": str,
    "base": str,
    "outcome": str,
    "commit": str,
    "budget": int,
    "panel": list,
    "panel_forced": str,
    "switches": list,
    "agents": str,
    "rounds": list,
    "items": dict,
    "skip": dict,
}

# ---------------------------------------------------------------- text


def clean(text, limit=LIMIT):
    """One line of characters that show (the rule of clean() in loop_text.py)."""
    out = []
    for ch in unicodedata.normalize("NFC", str(text)[: limit * 8]):
        kind = unicodedata.category(ch)
        if kind[0] in "CZ" or ch in BLANK:
            out.append(" ")
        elif kind not in ("Mn", "Me"):
            out.append(ch)
    return " ".join("".join(out).split())[:limit]


def show_branch(name):
    return name if PLAIN_BRANCH.fullmatch(name or "") else "another branch"


# ---------------------------------------------------------------- switch lines

SWITCH = re.compile(r"(judge loop|judge rounds|judges):[ \t]*(.*?)[ \t]*", re.I | re.A)
KEYS = {"judge loop": "Judge loop", "judge rounds": "Judge rounds", "judges": "Judges"}
FENCE = re.compile(r"( {0,3})(`{3,}|~{3,})(.*)")
LIST_ITEM = re.compile(r"( {0,3})([-*+]|\d{1,9}\.)( +)(.*)")
HTML_OPEN = re.compile(r" {0,3}<([A-Za-z][A-Za-z0-9-]*)(\s[^>]*)?>")
RAW_TAGS = frozenset(("pre", "script", "style", "textarea"))
BLOCK_OPEN = re.compile(r" {0,3}</?([A-Za-z][A-Za-z0-9]*)(?=[ \t>]|/>|$)")
BLOCK_NAMES = (
    "address article aside base basefont blockquote body caption center col "
    "colgroup dd details dialog dir div dl dt fieldset figcaption figure footer "
    "form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li "
    "link main menu menuitem nav noframes ol optgroup option p param search "
    "section summary table tbody td tfoot th thead title tr track ul"
)
BLOCK_TAGS = frozenset(BLOCK_NAMES.split())


def switch_value(key, value):
    """The value of a switch line and the names it dropped; None: not valid."""
    if key == "Judge loop":
        return ("off" if value.lower() == "off" else None), []
    if key == "Judge rounds":
        if re.fullmatch(r"\d{1,2}", value) and 1 <= int(value) <= MAX_SWITCH_ROUNDS:
            return int(value), []
        return None, []
    kept, dropped = [], []
    for name in value.split(","):
        name = name.strip().lower()
        if name not in ROLES:
            dropped.append(name)
        elif name not in kept:
            kept.append(name)
    return (kept or None), dropped


def parse_switches(text):
    """Every switch line of a Markdown text: (key, value, line number, dropped)."""
    found = []
    fence = comment = None
    tag = None
    list_col = None
    for number, line in enumerate(text.split("\n"), 1):
        line = line.removesuffix("\r")
        if fence:
            m = FENCE.fullmatch(line)
            closes = m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence)
            if closes and not m.group(3).strip():
                fence = None
            continue
        if comment:
            if "-->" in line:
                comment = None
            continue
        if tag:
            ends = f"</{tag}" in line.lower() if tag in RAW_TAGS else not line.strip()
            if ends:
                tag = None
            continue
        if not line.strip():
            continue
        m = FENCE.fullmatch(line)
        if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
            fence = m.group(2)
            continue
        if "<!--" in line:
            if "-->" not in line.split("<!--", 1)[1]:
                comment = True
            continue
        m = BLOCK_OPEN.match(line)
        if m and m.group(1).lower() in BLOCK_TAGS:
            tag = m.group(1).lower()
            continue
        m = HTML_OPEN.match(line)
        if m and (m.group(1).lower() in RAW_TAGS or not line[m.end() :].strip()):
            name = m.group(1).lower()
            if name not in RAW_TAGS or f"</{name}" not in line.lower():
                tag = name
            continue
        indent = len(line) - len(line.lstrip(" "))
        if list_col is not None and indent >= list_col:
            continue
        if line.startswith("\t") or indent >= 4:
            list_col = None
            continue
        content = line
        m = LIST_ITEM.fullmatch(line)
        if m:
            spaces = len(m.group(3)) if len(m.group(3)) <= 4 else 1
            list_col = len(m.group(1)) + len(m.group(2)) + spaces
            if spaces < len(m.group(3)):
                continue  # five spaces or more: code inside the item
            content = m.group(4)
        else:
            list_col = None
            content = line.lstrip(" ")
        if any(
            unicodedata.category(ch)[0] == "C"
            or ch in BLANK
            or (unicodedata.category(ch)[0] == "Z" and ch != " ")
            for ch in content.replace("\t", " ")
        ):
            continue
        m = SWITCH.fullmatch(content)
        if not m:
            continue
        key = KEYS[m.group(1).lower()]
        value, dropped = switch_value(key, m.group(2))
        found.append((key, value, number, dropped))
    return found


def first_switches(text):
    """The first valid line per key of one text, as {key: value}."""
    out = {}
    for key, value, _, _ in parse_switches(text):
        if value is not None and key not in out:
            out[key] = value
    return out


# ---------------------------------------------------------------- files


def read_plain(path, limit):
    """The bytes of a regular file of at most `limit` bytes; None when missing.

    A link, a folder, a file of another type or a larger file gives False. The
    file is opened without waiting, so a named pipe cannot hold the gate up.
    """
    if not hasattr(os, "O_NOFOLLOW") and os.path.islink(path):
        return False
    try:
        flags = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, os.O_RDONLY | flags)
    except FileNotFoundError:
        return None
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return False
        data = os.read(fd, limit + 1)
    except OSError:
        return False
    finally:
        os.close(fd)
    return data if len(data) <= limit else False


READ_FIX = "make it a readable regular file or remove it"


def cannot_read(name, why):
    return f"cannot read {name} ({why})"


def read_policy(path, limit=MAX_TEXT_FILE):
    """(text, why) of a CLAUDE.md: text None and why '' when there is none.

    Both the policy gate and the judged gate read a CLAUDE.md through this. A
    link is followed, as Claude Code follows it. The file is opened without
    waiting, so a named pipe or a device at the end of the path cannot hold the
    gate up; anything but a regular file of at most `limit` bytes, or a link to
    nothing, gives the reason in `why`.
    """
    flags = getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0)
    try:
        fd = os.open(path, os.O_RDONLY | flags)
    except FileNotFoundError:
        return None, "a link to a missing file" if os.path.islink(path) else ""
    except IsADirectoryError:
        return None, "a folder, not a file"
    except OSError as exc:
        return None, (exc.strerror or type(exc).__name__).lower()
    try:
        mode = os.fstat(fd).st_mode
        if stat.S_ISDIR(mode):
            return None, "a folder, not a file"
        if stat.S_ISFIFO(mode):
            return None, "a named pipe, not a regular file"
        if not stat.S_ISREG(mode):
            return None, "not a regular file"
        chunks, size = [], 0
        while size <= limit:
            chunk = os.read(fd, limit + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    except OSError as exc:
        return None, (exc.strerror or type(exc).__name__).lower()
    finally:
        os.close(fd)
    if size > limit:
        return None, f"larger than {limit // (1024 * 1024)} MB"
    return b"".join(chunks).decode("utf-8", "replace"), ""


def user_file():
    """The user-level CLAUDE.md and the name it is shown by."""
    home = os.environ.get("CLAUDE_HOME")
    if home:
        return Path(home) / "CLAUDE.md", "$CLAUDE_HOME/CLAUDE.md"
    return Path(
        os.path.expanduser("~")
    ) / ".claude" / "CLAUDE.md", "~/.claude/CLAUDE.md"


def base_blob(repo, spec):
    """The bytes of a file on the base branch as git keeps them; None without one.

    Read raw: the output of try_git is stripped, which would move line numbers
    and turn an indented code line into a switch line.
    """
    try:
        done = subprocess.run(
            ["git", "cat-file", "blob", spec],
            cwd=repo.root,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def off_line(repo, base):
    """(where `Judge loop: off` stands, why the user-level file cannot be read).

    Each is '' when there is nothing to say.

    The project's files count on the base branch as the remote has it, never in
    the checkout, so a branch cannot switch the judge off for its own pull
    request; without a base only the user-level file is read.
    """
    sources = []
    if base:
        ref = f"refs/remotes/{repo.remote}/{base}"
        for rel in ("CLAUDE.md", ".claude/CLAUDE.md"):
            data = base_blob(repo, f"{ref}:{rel}")
            if data is not None and len(data) <= MAX_TEXT_FILE:
                text = data.decode("utf-8", "replace")
                sources.append((rel, text, f" on {show_branch(base)}"))
    path, shown = user_file()
    text, why = read_policy(path)
    if text:
        sources.append((shown, text, ""))
    for rel, text, on in sources:
        for key, value, number, _ in parse_switches(text):
            if key == "Judge loop" and value == "off":
                return f"{rel}:{number}{on}", ""
    return "", cannot_read(shown, why) if why else ""


# ---------------------------------------------------------------- the record


class Unreadable(Exception):
    """The record is there but is not one this gate can read."""


def items_ok(items):
    for item in items.values():
        if not isinstance(item, dict):
            return False
        settled = item.get("settled")
        if not (
            isinstance(item.get("open"), bool)
            and isinstance(item.get("kind"), str)
            and isinstance(settled, dict)
        ):
            return False
        if settled and not is_int(settled.get("raised_again")):
            return False
    return True


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def skip_ok(st):
    skip = st["skip"]
    if st["outcome"] != "skip":
        return True
    return (
        isinstance(skip.get("reason"), str)
        and all(is_int(skip.get(k)) and skip[k] >= 0 for k in ("files", "lines"))
        and isinstance(skip.get("user_ok"), bool)
    )


def load_state(data):
    """The record as a dict; Unreadable when it is not one; None: another schema."""
    try:
        st = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise Unreadable from exc
    if not isinstance(st, dict) or not is_int(st.get("schema")):
        raise Unreadable
    if st["schema"] != JUDGE_SCHEMA:
        return None
    for key, kind in STATE_TYPES.items():
        value = st.get(key)
        if not (is_int(value) if kind is int else isinstance(value, kind)):
            raise Unreadable
    if st["kind"] not in ("plan", "build"):
        raise Unreadable
    if not (items_ok(st["items"]) and skip_ok(st)):
        raise Unreadable
    if not all(isinstance(entry, dict) for entry in st["switches"]):
        raise Unreadable
    return st


def open_counts(st):
    items = [
        it
        for it in st["items"].values()
        if it["open"] and (not it["settled"] or it["settled"]["raised_again"])
    ]
    return len(items), sum(1 for it in items if it["kind"] == "blocking")


def settled_counts(st):
    settled = [
        it
        for it in st["items"].values()
        if it["settled"] and not it["settled"]["raised_again"]
    ]
    return len(settled), sum(1 for it in settled if it["kind"] == "blocking")


def linked(root, name):
    """True when a level of the record's path, the record included, is a link."""
    path = root
    for part in ("docs", "loops", name, "build", "state.json"):
        path = path / part
        try:
            if stat.S_ISLNK(os.lstat(path).st_mode):
                return True
        except OSError:
            return False
    return False


# ---------------------------------------------------------------- the gate


def judged(state, detail, stop=False):
    return gate("judged", state, detail, stop=stop)


def size_since(repo, span):
    """('3 files, 140 lines since', ''), or ('', why git failed).

    The size of the commits in `span`: the branch's own, without those merged in
    from the base. A file counts once; its lines are added up over the commits.
    """
    rc, out, err = repo.try_git(
        "log",
        "--numstat",
        "--format=",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        *span,
    )
    if rc:
        return "", clean(git_said(err or out, rc))
    files, lines = set(), 0
    for row in out.splitlines():
        parts = row.split("\t", 2)
        if len(parts) < 3:
            continue
        files.add(parts[2])
        lines += sum(int(n) for n in parts[:2] if n.isdigit())
    return f"{count(len(files), 'file')}, {count(lines, 'line')} since", ""


def pass_reason(st, sha, before):
    outcome = st["outcome"]
    at = (
        f"{short(sha)} ({count(before, 'commit')} before the head)"
        if before
        else short(sha)
    )
    if outcome == "done":
        judges, rounds = len(st["panel"]), len(st["rounds"])
        return (
            f"done, 10 from {count(judges, 'judge')} in {count(rounds, 'round')} "
            f"on {at}"
        )
    if outcome == "budget":
        left, _ = open_counts(st)
        return f"budget used, {count(left, 'item')} left, on {at}"
    if outcome == "accepted":
        left, blocking = open_counts(st)
        return (
            f"accepted by the user in round {len(st['rounds'])} of {st['budget']} "
            f"with {count(left, 'item')} left ({blocking} blocking), on {at}"
        )
    skip = st["skip"]
    asked = ", user asked" if skip["user_ok"] else ""
    return (
        f"skipped on {at} ({count(skip['files'], 'file')}, "
        f"{count(skip['lines'], 'line')}{asked}): {clean(skip['reason'])}"
    )


def additions(st):
    out = []
    n, blocking = settled_counts(st)
    if n:
        out.append(f"{n} settled ({blocking} blocking)")
    if st["panel_forced"] in ("single", "full"):
        out.append(f"panel forced: --panel {st['panel_forced']}")
    for entry in st["switches"]:
        value = entry.get("value")
        if entry.get("key") == "Judge rounds" and is_int(value):
            out.append(f"Judge rounds: {value}")
            break
    if st["agents"] == "fallback":
        out.append("agents: fallback")
    return out


def base_mismatch(st, base):
    """The reason when the record was made against another base, or ''."""
    if not base or st["base"] == base or st["outcome"] not in OUTCOMES:
        return ""
    was, now = show_branch(clean(st["base"])), show_branch(base)
    if st["outcome"] == "skip":
        return (
            f"skipped against {was}, the pull request goes to {now}: loop.py skip "
            f"again with --base {now}"
        )
    head = f"judged against {was}, the pull request goes to {now}"
    if st["outcome"] in UNFINISHED:
        return (
            f"{head}: /judge-loop (loop.py abandon, then loop.py start build "
            f"--base {now})"
        )
    return f"{head}: /judge-loop (loop.py start build --base {now})"


def judged_gate(repo, head, base):
    """The build loop of the branch ended on this commit or one before it, or a
    skip record stands on the head; the judge loop is off; or why not."""
    where, unread = off_line(repo, base)
    if where:
        return judged("pass", f"off ({clean(where)})")
    if unread:
        # It may hold `Judge loop: off`: only the user can tell.
        return judged("fail", f"{unread}: {READ_FIX}", stop=True)
    name = slug(repo.branch)
    if not NAME.fullmatch(name):
        return judged(
            "fail", "the branch name cannot name a judge record: rename the branch"
        )
    folder = f"docs/loops/{name}/build"
    record = f"{folder}/state.json"
    move = f"move the folder {folder} away and judge again"
    if linked(repo.root, name):
        return judged(
            "fail",
            f"the judge record is reached through a link ({record}): "
            f"replace the link with a plain folder, then {move}",
        )
    rc, out, err = repo.try_git("ls-files", "-z", "--", ":(icase)docs/loops")
    if rc:
        return judged(
            "fail",
            "git ls-files could not say whether files under docs/loops are tracked: "
            f"{clean(git_said(err or out, rc))}",
        )
    if out:
        return judged(
            "fail",
            "files under docs/loops are tracked by git; the judge record must be a "
            "local file: git rm -r --cached docs/loops, then judge again",
        )
    data = read_plain(repo.root / record, MAX_STATE)
    if data is None:
        return judged(
            "fail",
            f"no judge record ({record}, in this checkout): run "
            "/judge-loop (loop.py start build), or loop.py skip --reason for a "
            "change with nothing to judge",
        )
    unreadable = f"not a readable judge record ({record}): {move}"
    try:
        if data is False:
            raise Unreadable
        st = load_state(data)
    except Unreadable:
        return judged("fail", unreadable)
    if st is None:
        return judged(
            "fail",
            f"the judge record {record} was written by another version of the kit: "
            "run the installer",
        )
    if st["kind"] != "build":
        return judged("fail", f"the record {record} is for a plan loop: {move}")
    if st["branch"] != repo.branch:
        return judged(
            "fail",
            f"the record {record} is for {show_branch(clean(st['branch']))}: {move}",
        )
    why = base_mismatch(st, base)
    if why:
        return judged("fail", why)
    return outcome_gate(repo, st, head, base, unreadable)


def outcome_gate(repo, st, head, base, unreadable):
    outcome, rounds = st["outcome"], len(st["rounds"])
    if outcome in ("open", "stalled"):
        n = rounds + 1 if outcome == "open" else rounds
        return judged(
            "fail",
            f"judge loop not finished (round {n} of {st['budget']}): loop.py status",
        )
    if outcome in ("ask", "blocked"):
        return judged(
            "fail", "the judge loop is waiting for the user: loop.py status", stop=True
        )
    if outcome == "abandoned":
        return judged("fail", "abandoned: /judge-loop (loop.py start build)")
    if outcome not in OUTCOMES or not COMMIT.fullmatch(st["commit"]):
        return judged("fail", unreadable)
    if outcome in ("done", "budget") and open_counts(st)[1]:
        return judged("fail", unreadable)  # the loop ends as blocked then
    sha = st["commit"]
    if outcome == "skip":
        if sha != head:
            return judged(
                "fail",
                "new commits since the skip: judge them with /judge-loop (loop.py "
                "start build), or skip again if there is still nothing to judge",
            )
        return judged("pass", pass_reason(st, sha, 0))
    gone = (
        f"the judged commit {short(sha)} is no longer on this branch (rebased or "
        "amended): judge again"
    )
    if sha != head:
        rc, _, err = repo.try_git("merge-base", "--is-ancestor", sha, head)
        if rc == 1:
            return judged("fail", gone)
        if rc:
            return judged("fail", f"{gone} ({clean(git_said(err, rc))})")
    if base:
        ref = f"refs/remotes/{repo.remote}/{base}"
        rc, _, err = repo.try_git("merge-base", "--is-ancestor", sha, ref)
        if rc == 0:
            return judged(
                "fail",
                f"the judged commit {short(sha)} is already on {show_branch(base)}: "
                "judge the branch's own commits with /judge-loop (loop.py start "
                "build)",
            )
        if rc != 1:
            return judged(
                "fail",
                f"git merge-base could not place {short(sha)} against "
                f"{show_branch(base)}: {clean(git_said(err, rc))}",
            )
    before, extra = 0, additions(st)
    if sha != head:
        span = [f"{sha}..{head}"]
        if base:
            span.append(f"^refs/remotes/{repo.remote}/{base}")
        rc, out, err = repo.try_git("rev-list", "--count", *span)
        if rc:
            size, why = "", clean(git_said(err or out, rc))
        elif not out.isdigit():
            size, why = "", "git rev-list gave no count"
        else:
            size, why = size_since(repo, span)
        if why:
            return judged(
                "fail", f"git could not measure the commits since {short(sha)}: {why}"
            )
        before = int(out)
        extra.append(size)
    reason = "; ".join([pass_reason(st, sha, before), *extra])
    return judged("pass", reason)
