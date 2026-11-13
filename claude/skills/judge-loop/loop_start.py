"""Switch lines, the base, the size, the panel, the agents and start."""

# ruff: noqa: F403, F405
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import unicodedata
from pathlib import Path

import loop_state
from loop_state import *

# Switch lines -----------------------------------------------------------------

SWITCH = re.compile(r"(judge loop|judge rounds|judges):[ \t]*(.*?)[ \t]*", re.I | re.A)
KEYS = {"judge loop": "Judge loop", "judge rounds": "Judge rounds", "judges": "Judges"}
FENCE = re.compile(r"( {0,3})(`{3,}|~{3,})(.*)")
LIST_ITEM = re.compile(r"( {0,3})([-*+]|\d{1,9}\.)( +)(.*)")
HTML_OPEN = re.compile(r" {0,3}<([A-Za-z][A-Za-z0-9-]*)(\s[^>]*)?>")
VOID_TAGS = frozenset(
    ("br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed")
    + ("source", "wbr")
)
# Raw HTML that runs to its closing tag; any other tag ends at a blank line.
RAW_TAGS = frozenset(("pre", "script", "style", "textarea"))


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
            if f"</{tag}" in line.lower() or (tag not in RAW_TAGS and not line.strip()):
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
        m = HTML_OPEN.match(line)
        if m and (m.group(1).lower() in RAW_TAGS or not line[m.end() :].strip()):
            name = m.group(1).lower()
            opens = name not in VOID_TAGS and not line.rstrip().endswith("/>")
            if opens and f"</{name}" not in line.lower():
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


def project_ref(ctx, base):
    """The ref the project's switch lines are read from, or ''."""
    if not base:
        return ""
    remote = f"refs/remotes/{ctx.remote}/{base}"
    if ctx.resolve(remote):
        return remote
    if not ctx.has_remote and ctx.resolve(f"refs/heads/{base}"):
        return f"refs/heads/{base}"
    return ""


def read_switches(ctx, base):
    """The switch lines that count, and the lines that say what was not used."""
    used, said = {}, []
    ref = project_ref(ctx, base)
    if base and not ref and ctx.has_remote:
        said.append(
            f"no refs/remotes/{ctx.remote}/{show_branch(base)}: "
            "no switch line of the project counts"
        )
    sources = []
    for rel in ("CLAUDE.md", ".claude/CLAUDE.md"):
        text = ""
        if ref:
            proc = ctx.git.run("cat-file", "blob", f"{ref}:{rel}", ok=(0, 128))
            if proc.returncode == 0 and len(proc.stdout) <= MAX_TEXT_FILE:
                text = proc.stdout.decode("utf-8", "replace")
        sources.append((rel, text, f" on {show_branch(base)}" if ref else ""))
        local = read_plain(ctx.root / rel, MAX_TEXT_FILE)
        if local:
            on_base = {
                (key, repr(value)) for key, value, _, _ in parse_switches(text) if value
            }
            for key, value, number, _ in parse_switches(
                local.decode("utf-8", "replace")
            ):
                if value is not None and (key, repr(value)) not in on_base:
                    where = show_branch(base) if base else "the base branch"
                    said.append(
                        f"line {number} of {rel} is not on {where} yet: not used"
                    )
    home, shown = user_home()
    try:
        data = read_plain(home / "CLAUDE.md", MAX_TEXT_FILE)
    except IsADirectoryError:
        data = None
        said.append(f"{shown} is a folder where a file was expected: not used")
    if data is False:
        said.append(f"{shown} is a link or over 1 MB: not used")
    sources.append((shown, data.decode("utf-8", "replace") if data else "", ""))
    for rel, text, on in sources:
        for key, value, number, dropped in parse_switches(text):
            where = f"{rel}:{number}{on}"
            for name in dropped:
                said.append(
                    f"{where}: {show_name(name, 'a name')} is not a role: dropped"
                )
            if value is None:
                said.append(f"switch line {where} ({key}) is not valid: not used")
            elif key in used:
                said.append(
                    f"switch line {where} ({key}): an earlier line wins, not used"
                )
            else:
                used[key] = {
                    "key": key,
                    "value": value,
                    "file": rel,
                    "line": number,
                    "where": where,
                }
    return used, said


def switch_text(entry):
    value = entry["value"]
    if isinstance(value, list):
        value = ", ".join(value)
    return f"{entry['key']}: {value}"


# Base -------------------------------------------------------------------------


def plain_base(ctx, value):
    """A --base value as a bare branch name, or None when it is not one."""
    if not value or value.startswith("-"):
        return None
    for prefix in ("refs/heads/", f"refs/remotes/{ctx.remote}/", f"{ctx.remote}/"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if not value or value.startswith("-"):
        return None
    proc = ctx.git.run("check-ref-format", "--branch", value, ok=None)
    if proc.returncode or os.fsdecode(proc.stdout).strip() != value:
        return None
    return value


def gh_base(ctx):
    """The base branch of the pull request; None, with a note when gh misbehaved."""
    gh = shutil.which("gh")
    if not gh or not ctx.branch:
        return None
    try:
        proc = subprocess.run(
            [gh, "pr", "view", "--json", "baseRefName"],
            cwd=ctx.root,
            capture_output=True,
            timeout=GH_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return gh_note(f"gave no answer in {GH_TIMEOUT} seconds")
    except (OSError, subprocess.SubprocessError):
        return gh_note("did not run")
    if proc.returncode:
        return None  # no pull request for this branch
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        return gh_note("gave no JSON")
    name = data.get("baseRefName") if isinstance(data, dict) else None
    base = plain_base(ctx, name) if isinstance(name, str) else None
    return base or gh_note("gave no base branch")


def gh_note(why):
    say(f"note: gh pr view {why}, so the pull request does not set the base")
    return None


def find_base(ctx, given):
    """(base, source); base '' when nothing was found. Raises on a bad --base."""
    if given is not None:
        base = plain_base(ctx, given)
        if base is None:
            raise Exit(
                2,
                f"Refused: {shown_value(given)} is not a branch name. Next: --base "
                "<branch>.",
            )
        return base, "--base"
    base = gh_base(ctx)
    if base:
        return base, "the pull request"
    head = f"refs/remotes/{ctx.remote}/HEAD"
    target = ctx.git.out("symbolic-ref", "-q", head, ok=(0, 1, 128))
    prefix = f"refs/remotes/{ctx.remote}/"
    if target.startswith(prefix):
        base = plain_base(ctx, target[len(prefix) :])
        if base:
            return base, head
    for name in ("main", "master"):
        if ctx.resolve(f"refs/remotes/{ctx.remote}/{name}") or ctx.resolve(
            f"refs/heads/{name}"
        ):
            return name, f"the default name {name}"
    return "", ""


def base_ref_of(ctx, base):
    if not base:
        return ""
    for ref in (f"refs/remotes/{ctx.remote}/{base}", f"refs/heads/{base}"):
        if ctx.resolve(ref):
            return ref
    return ""


# Measure and panel ------------------------------------------------------------

# Measuring keeps git's binary rule (a binary or -diff file has no line count);
# the diff the judges read is shown as text all the same.
MEASURE_FLAGS = ("--no-renames", "--no-ext-diff", "--no-textconv")
DIFF_FLAGS = (*MEASURE_FLAGS, "--text")


def is_sensitive(path):
    low = path.lower()
    if low.startswith(".github/workflows/"):
        return True
    parts = low.split("/")
    if parts[-1] in STEERING_FILES or any(p in STEERING_FOLDERS for p in parts[:-1]):
        return True
    words = [word for part in parts for word in re.split(r"[._-]", part)]
    return any(word in SENSITIVE_WORDS for word in words)


def is_doc(path):
    return path.lower().endswith(DOC_EXTENSIONS) and not is_sensitive(path)


def changed_rows(ctx, left, right="HEAD", sep="..."):
    """[(path, added or None, deleted or None)] and the submodule pointers."""
    spec = f"{left}{sep}{right}"
    out = ctx.git.run("diff", "--numstat", "-z", *MEASURE_FLAGS, spec).stdout
    rows = []
    for record in out.split(b"\0"):
        if not record:
            continue
        added, deleted, path = record.split(b"\t", 2)
        path = os.fsdecode(path)
        if added == b"-" or deleted == b"-":
            rows.append((path, None, None))
        else:
            rows.append((path, int(added), int(deleted)))
    raw = ctx.git.run("diff", "--raw", "-z", *DIFF_FLAGS, spec).stdout.split(b"\0")
    subs = []
    for i in range(0, len(raw) - 1, 2):
        fields = raw[i].lstrip(b":").split(b" ")
        if len(fields) >= 2 and b"160000" in fields[:2]:
            subs.append(os.fsdecode(raw[i + 1]))
    return rows, subs


class Size:
    """The measured size of a diff against the merge base."""

    def __init__(self, rows, subs):
        self.files = len(rows)
        self.lines = sum((a or 0) + (d or 0) for _, a, d in rows)
        self.cause = ""
        self.full = True
        if subs:
            self.cause = f"{show_path(subs[0])} is a submodule pointer"
        elif any(a is None for _, a, _ in rows):
            path = next(p for p, a, _ in rows if a is None)
            self.cause = f"{show_path(path)} has no line count"
        elif any(is_sensitive(p) for p, _, _ in rows):
            path = next(p for p, _, _ in rows if is_sensitive(p))
            self.cause = f"sensitive path {show_path(path)}"
        if self.cause:
            self.reason = f"auto: {self.cause}"
            self.exempt = False
            return
        self.exempt = (
            self.files == 0
            or (self.files == 1 and self.lines <= EXEMPT_LINES)
            or all(is_doc(p) for p, _, _ in rows)
        )
        if self.exempt:
            self.full = False
            self.reason = (
                "auto: within the exempt size (loop.py skip --reason would also do)"
            )
        elif self.lines > FULL_LINES:
            self.reason = f"auto: {count(self.lines, 'changed line')}"
        elif self.files > FULL_FILES:
            self.reason = f"auto: {count(self.files, 'file')}"
        else:
            self.full = False
            lines = count(self.lines, "changed line")
            self.reason = f"auto: {lines} in {count(self.files, 'file')}"


def choose_panel(kind, forced, switches, size):
    if forced == "single":
        return ["general"], "--panel single"
    if forced == "full":
        return list(FULL_PANEL), "--panel full"
    if "Judges" in switches:
        return list(switches["Judges"]["value"]), "Judges line"
    if kind == "plan":
        return ["general"], "auto: plan"
    return (list(FULL_PANEL) if size.full else ["general"]), size.reason


# Agents -----------------------------------------------------------------------


NOT_ONE_LINE = tuple("|>&!*{[")


def frontmatter_name(data):
    """A kit agent name of any name line of the front matter, else ''.

    None when the top-level name cannot be read on one line, so it cannot be
    checked: an empty value, a block, anchor, tag or flow value, a quoted key,
    an escape inside double quotes, or front matter that is one flow mapping.
    """
    text = data.decode("utf-8", "replace").lstrip("\ufeff").replace("\r", "")
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return ""
    unreadable = False
    for number, line in enumerate(lines[1:]):
        if line.strip() == "---":
            break
        if number == 0 and line.lstrip().startswith("{"):
            return None
        key, sep, value = line.partition(":")
        bare = key.strip().strip("\"'")
        if not sep or bare.lower() != "name":
            continue
        top = not line[:1].isspace()
        value = re.sub(r"\s#.*$", "", value).strip()
        name = value.strip("\"'").strip().lower()
        if name in AGENT_NAMES:
            return name
        if top and (
            key.strip() != bare
            or not value
            or value.startswith(NOT_ONE_LINE)
            or (value.startswith('"') and "\\" in value)
        ):
            unreadable = True
    return None if unreadable else ""


def project_agent(root):
    """None, or (name, path) of a project agent with a kit name, or ('', path)."""
    here = root
    for part in (".claude", "agents"):
        here = here / part
        try:
            st = os.lstat(here)
        except FileNotFoundError:
            return None
        rel = os.path.relpath(here, root)
        if stat.S_ISLNK(st.st_mode):
            return "", rel
        if not stat.S_ISDIR(st.st_mode):
            return None
    for top, dirs, files in os.walk(here, followlinks=False):
        for entry in sorted(dirs) + sorted(files):
            path = Path(top) / entry
            rel = os.path.relpath(path, root)
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                return "", rel
            if entry in files and entry.lower().endswith(".md"):
                if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_AGENT_FILE:
                    return "", rel
                stem = entry[:-3].lower()
                if stem in AGENT_NAMES:
                    return stem, rel
                data = read_plain(path, MAX_AGENT_FILE)
                if data is False:
                    return "", rel
                name = frontmatter_name(data or b"")
                if name is None:
                    return "", rel
                if name in AGENT_NAMES:
                    return name, rel
    return None


def check_agents(ctx, agents, command, panel=()):
    folder = loop_state.agents_dir()
    for name in AGENT_NAMES:
        if not (folder / f"{name}.md").is_file():
            raise Exit(
                2, f"Refused: agents/{name}.md is not installed. Next: run /kit."
            )
    for role in panel:
        if not (skill_dir() / "roles" / f"{role}.md").is_file():
            raise Exit(2, f"Refused: roles/{role}.md is not installed. Next: run /kit.")
    if agents != "kit":
        return
    hit = project_agent(ctx.root)
    if hit is None:
        return
    name, rel = hit
    if not name:
        raise Exit(
            3,
            f"STOP: {show_path(rel)} cannot be checked for an agent name (a link, or "
            "over "
            "64 kB). Next: ask the user: make it a plain file or folder, or the same "
            "command with --agents fallback.",
        )
    again = "start ..." if command == "start" else command
    raise Exit(
        3,
        f"STOP: this project has its own agent named {name} ({show_path(rel)}). "
        f"Next: ask the user: rename it, or loop.py {again} --agents fallback.",
    )


# start ------------------------------------------------------------------------


def bad_name(value, tail):
    return Exit(
        2,
        f"Refused: {shown_value(value)} cannot name a judge record (letters, digits, "
        f"'.', '_', '-'; at most 80). Next: {tail}.",
    )


def no_history(
    branch, base, tail="the same command with --base and the right base branch"
):
    return Exit(
        2,
        f"Refused: {show_branch(branch) if branch else 'HEAD'} and {show_branch(base)} "
        f"share no history. Next: {tail}.",
    )


def prepare(args):
    """The checks `start` and `skip` share, in their fixed order."""
    kind = getattr(args, "loop_kind", "build")
    if kind == "build" and getattr(args, "name", None) is not None:
        raise Exit(
            2,
            "Refused: a build loop is named after its branch. "
            "Next: loop.py start build without --name.",
        )
    if kind == "plan" and getattr(args, "plan_loop", None) is not None:
        raise Exit(
            2,
            "Refused: --plan-loop is for start build. Next: loop.py start plan without "
            "it.",
        )
    ctx = Ctx()
    if not ctx.branch and (kind == "build" or args.name is None):
        raise Exit(
            2, "Refused: no branch is checked out. Next: check out the work branch."
        )
    base, source = find_base(ctx, args.base)
    base_ref = base_ref_of(ctx, base)
    switches, said = read_switches(ctx, base)
    if "Judge loop" in switches:
        entry = switches["Judge loop"]
        raise Exit(
            0,
            f"Off: judge loop switched off by {entry['where']}. Next: work without it.",
        )
    if kind == "build" and not base_ref and source == "--base":
        raise Exit(
            2,
            f"Refused: no base branch {show_branch(base)} found. "
            "Next: the same command with --base <branch>.",
        )
    if kind == "build" and not base_ref:
        raise Exit(
            2,
            "Refused: no base branch found. Next: the same command with --base "
            "<branch>.",
        )
    if kind == "build" and ctx.branch == base:
        raise Exit(
            2,
            f"Refused: {show_branch(base)} is the base branch. "
            "Next: git switch -c <work branch>, then the same command.",
        )
    if kind == "build" or args.name is None:
        name = slug(ctx.branch)
        if not NAME.fullmatch(name):
            raise Exit(
                2,
                "Refused: the branch name cannot name a judge record. Next: rename the "
                "branch.",
            )
    else:
        name = args.name
        if not NAME.fullmatch(name):
            raise bad_name(name, "the same command with another --name")
    plan_loop = getattr(args, "plan_loop", None)
    if plan_loop is not None and not NAME.fullmatch(plan_loop):
        raise bad_name(
            plan_loop,
            "the same command with the name of the plan loop, see loop.py status",
        )
    base_sha = ctx.resolve(base_ref)
    size = None
    if kind == "build":
        if ctx.dirty():
            raise Exit(2, DIRTY)
        merge = ctx.merge_base(base_sha) if base_sha else ""
        if not merge:
            raise no_history(ctx.branch, base)
        base_sha = merge
        size = Size(*changed_rows(ctx, merge))
    return ctx, kind, name, base, base_ref, base_sha, source, switches, said, size


def move_aside(loop):
    """A finished loop's folder becomes <kind>.1, <kind>.2, ..."""
    parent = loop.path().parent
    i = 1
    while os.path.lexists(parent / f"{loop.kind}.{i}"):
        i += 1
    os.rename(loop.path(), parent / f"{loop.kind}.{i}")
    return f"docs/loops/{loop.name}/{loop.kind}.{i}"


def existing(loop):
    """None, or the loaded state of a loop folder; a folder of files is refused."""
    folder = loop.path()
    if os.path.lexists(loop.path("state.json")):
        return loop.load()
    if folder.is_dir() and any(os.scandir(folder)):
        rel = show_path(loop.rel)
        raise Exit(
            2,
            f"Error: {rel} holds files but no loop state. "
            f"Next: move the folder {rel} away, then loop.py start again.",
        )
    return None


def judged_plan(ctx, name):
    """The judged plan of a plan loop: (bytes, criteria bytes, sha256)."""
    plan = Loop(ctx, "plan", name)
    if not os.path.lexists(plan.path("state.json")):
        raise Exit(
            2,
            f"Refused: plan loop {name} has no judged plan (no plan loop {name} in "
            "this "
            f"checkout). Next: copy the folder docs/loops/{name}/plan/ from the "
            "checkout "
            "that holds it, or start without --plan-loop.",
        )
    st = plan.load()
    why = ""
    data = None
    if st["outcome"] not in ("done", "budget", "accepted") or not st["rounds"]:
        why = f"that loop is {outcome_words(st['outcome'])}"
    else:
        n = st["rounds"][-1]["n"]
        data = plan.read(f"plan.r{n}.md")
        if not data or sha256(data) != st["rounds"][-1]["plan_sha256"]:
            why = f"plan.r{n}.md is not the plan that was judged"
    if why:
        raise Exit(
            2,
            f"Refused: plan loop {name} has no judged plan ({why}). "
            "Next: finish that loop, or start without --plan-loop.",
        )
    return data, plan.read("criteria.md") or b"", sha256(data)


def new_state(**fields):
    st = {
        "schema": SCHEMA,
        "branch": "",
        "base": "",
        "base_ref": "",
        "base_sha": "",
        "base_source": "",
        "panel": [],
        "panel_reason": "",
        "panel_forced": "",
        "budget": DEFAULT_BUDGET,
        "switches": [],
        "agents": "kit",
        "plan_loop": {},
        "pending": {},
        "rounds": [],
        "items": {},
        "streak": 0,
        "final": False,
        "notes": [],
        "outcome": "open",
        "commit": "",
        "skip": {},
    }
    st.update(fields)
    return st


def cmd_start(args):
    ctx, kind, name, base, base_ref, base_sha, source, switches, said, size = prepare(
        args
    )
    if kind == "build" and size.files == 0:
        raise Exit(
            2,
            "Refused: nothing is built yet. Next: build and commit first; loop.py skip "
            "is "
            "only for a head with nothing to judge.",
        )
    loop = Loop(ctx, kind, name)
    others = [lp for lp in scan(ctx, load=False) if (lp.kind, lp.name) != (kind, name)]
    left_out([lp for lp in others if lenient(lp) is None], args)
    old = existing(loop)
    if old and old["outcome"] in UNFINISHED:
        raise Exit(
            2,
            f"Refused: this loop is not finished ({outcome_words(old['outcome'])}, "
            f"round {current_round(old)} of {old['budget']}). "
            "Next: loop.py status; loop.py accept or abandon ends it.",
        )
    plan = None
    if args.plan_loop is not None:
        plan = judged_plan(ctx, args.plan_loop)
    check_agents(ctx, args.agents, "start")
    forced = "" if args.panel == "auto" else args.panel
    panel, reason = choose_panel(kind, forced, switches, size)
    check_agents(ctx, args.agents, "start", panel)
    budget = (
        switches["Judge rounds"]["value"]
        if "Judge rounds" in switches
        else DEFAULT_BUDGET
    )
    moved = move_aside(loop) if old else ""
    loop.st = new_state(
        kind=kind,
        name=name,
        branch=ctx.branch,
        base=base,
        base_ref=base_ref,
        base_sha=base_sha,
        base_source=source,
        panel=panel,
        panel_reason=reason,
        panel_forced=forced,
        budget=budget,
        switches=list(switches.values()),
        agents=args.agents,
        plan_loop={"name": args.plan_loop, "sha256": plan[2]} if plan else {},
    )
    loop.mkdir()
    if plan:
        try:
            loop.write("plan.md", plan[0])
            loop.write("criteria.md", plan[1])
        except OSError:
            for sub in ("plan.md", "criteria.md"):
                with contextlib.suppress(OSError):
                    os.unlink(loop.path(sub))
            raise
    loop.save()
    if others:
        QUALIFY.extend([True, (kind, name)])
    say(f"Repository: {clean(ctx.root)}")
    if moved:
        say(f"Earlier loop moved to {show_path(moved)}")
    say(f"Loop: {kind} {name} in {loop.rel}/")
    if base_ref:
        say(
            f"Base: {show_branch(base)}, read from {show_path(base_ref)} "
            f"({clean(source)})"
        )
    else:
        say("no base branch found: only the user-level switch lines count")
    if kind == "build":
        say(
            f"Measured: {count(size.files, 'file')}, "
            f"{count(size.lines, 'changed line')}"
        )
    say(f"Panel: {', '.join(panel)} ({clean(reason)})")
    for role in panel:
        say(
            f"{role}: result kept in {loop.rel}/judge/r1_{role}.json "
            "(written by loop.py save; the answer file is named in the brief)"
        )
    say(f"Budget: {count(budget, 'round')}")
    for entry in switches.values():
        say(f"switch used: {clean(switch_text(entry))} ({entry['where']})")
    for line in said:
        say(clean(line))
    say(f"Agents: {args.agents}")
    if args.agents == "fallback":
        say(FALLBACK_SENTENCE)
    j = len(panel)
    say(
        f"Expected cost: {count(j, 'judge run')} per round, at most "
        f"{count(budget, 'round')} ({count(j * budget, 'judge run')}), one fix pass "
        "between rounds"
    )
    head = (
        f"Started: {kind} loop {name}, {count(j, 'judge')}, at most "
        f"{count(budget, 'round')}."
    )
    if plan:
        say(
            f"plan.md and criteria.md copied from plan loop {args.plan_loop}; "
            f"add to {loop.rel}/criteria.md before the first brief if needed"
        )
        raise Exit(0, f"{head} Next: loop.py brief.")
    say(f"Criteria: write the acceptance criteria to {loop.rel}/criteria.md")
    if kind == "plan":
        raise Exit(
            0,
            f"{head} Next: write criteria.md, have kit-planner write plan.md, "
            "then loop.py brief.",
        )
    raise Exit(0, f"{head} Next: write criteria.md, then loop.py brief.")


def configure_start(sub):
    sub.add_argument("loop_kind", choices=KINDS, metavar="plan|build")
    sub.add_argument("--name", help="the loop's name (default: from the branch)")
    sub.add_argument(
        "--panel",
        choices=("auto", "single", "full"),
        default="auto",
        help="auto by the size of the change, one judge, or all six",
    )
    sub.add_argument("--base", help="the branch the work is compared with")
    sub.add_argument(
        "--plan-loop", dest="plan_loop", help="the plan loop this build follows"
    )
    sub.add_argument("--agents", choices=("kit", "fallback"), default="kit")


COMMANDS["start"] = (configure_start, cmd_start)


def current_round(st):
    n = len(st["rounds"])
    return n + 1 if st["outcome"] == "open" else n
