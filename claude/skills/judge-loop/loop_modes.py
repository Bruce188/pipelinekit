"""Judge modes, areas, the change log and the scorecard."""

# ruff: noqa: F403, F405
from __future__ import annotations

import difflib
import json
import os
import re

from loop_results import *

ROW = re.compile(
    r"- r([0-9]{1,4}) \[([a-z-]+) ([A-Z][A-Za-z0-9_-]{0,19})\] "
    r"(fixed|answered|owner): \S.*"
)
NOT_PLAIN = (
    "Refused: {path} is not a plain file of at most 200 kB. "
    "Next: shorten it, then loop.py brief."
)
WAIT_NOTE = (
    "note: {items} {verb} for the user. Ask in one batch and record the answers "
    "(questions.md, loop.py settle) before the judges run."
)


def work_id(pending):
    return pending.get("commit") or pending.get("sha256", "")


def read_meta(loop, n, role):
    data = loop.read(f"judge/r{n}_{role}.meta", MAX_TEXT_FILE)
    if not data:
        return None
    try:
        meta = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {}
    return meta if isinstance(meta, dict) else {}


def briefed_roles(st):
    """The roles of the pending round that read: every role not skipped."""
    modes = st["pending"].get("modes", {})
    return [role for role in st["panel"] if modes.get(role) != "skipped"]


def saved_roles(loop):
    """The roles whose result for the pending round is saved."""
    st = loop.st
    pending = st["pending"]
    if not pending:
        return []
    n, briefed = pending["round"], work_id(pending)
    out = []
    for role in briefed_roles(st):
        meta = read_meta(loop, n, role)
        ok = meta and meta.get("round") == n and meta.get("briefed") == briefed
        if ok and os.path.lexists(loop.path(f"judge/r{n}_{role}.json")):
            out.append(role)
    return out


# Modes ------------------------------------------------------------------------


def last_counted(st, role):
    """The latest round in which the role read (full or changes); 0 if none."""
    for rnd in reversed(st["rounds"]):
        if role in rnd["scores"] and rnd.get("modes", {}).get(role) != "skipped":
            return rnd["n"]
    return 0


def same_work(kind, rnd, work):
    """True when a counted round judged this work."""
    if kind == "plan":
        return rnd["plan_sha256"] == work.get("sha256")
    return rnd["commit"] == work.get("commit") and rnd["base_sha"] == work.get(
        "base_sha"
    )


def loop_file(loop, sub):
    """The text of map.md or changes.md, '' without the file."""
    data = read_plain(loop.path(sub), MAX_AREA_FILE)
    if data is False:
        raise Exit(2, NOT_PLAIN.format(path=show_path(f"{loop.rel}/{sub}")))
    return data.decode("utf-8", "replace") if data else ""


def area_path(entry):
    """(path, folder) of one path of an area line, or None."""
    folder = entry.endswith("/")
    path = entry[:-1] if folder else entry
    if not path or len(path) > MAX_AREA_PATH or not SAFE_REL.fullmatch(path):
        return None
    if any(part in (".", "..") for part in path.split("/")):
        return None
    return path, folder


def read_areas(loop):
    """[(paths, roles)] of map.md; None without the file."""
    if not os.path.lexists(loop.path("map.md")):
        return None
    areas = []
    for number, line in enumerate(loop_file(loop, "map.md").split("\n"), 1):
        line = line.removesuffix("\r")
        if not line.strip() or line.lstrip().startswith("#") or line.count("|") != 2:
            continue
        name, paths, roles = (part.strip() for part in line.split("|"))
        paths = [area_path(p.strip()) for p in paths.split(",")]
        roles = [r.strip() for r in roles.split(",")]
        if (
            not name
            or None in paths
            or not all(r in ROLES or r == "all" for r in roles)
        ):
            raise Exit(
                2,
                f"Refused: map.md line {number} is not an area line. "
                "Next: write it as name | paths | roles, then loop.py brief.",
            )
        areas.append((paths, set(ROLES) if "all" in roles else set(roles)))
    return areas


def roles_of(path, areas):
    """The roles a changed file belongs to."""
    if areas is None:
        return set(ROLES)
    found, covered = set(), False
    for paths, roles in areas:
        if any(
            path == p or (folder and path.startswith(p + "/")) for p, folder in paths
        ):
            covered = True
            found |= roles
    return found if covered else set(ROLES)


def changed_names(ctx, commit):
    out = ctx.git.run("diff", "--name-only", "-z", "--no-renames", commit, "HEAD")
    return [os.fsdecode(name) for name in out.stdout.split(b"\0") if name]


def decide_modes(loop, n, moved, work, areas):
    """{role: mode} of a new round, and the work of every skipped role's round."""
    st = loop.st
    if n == 1 or moved:
        return {role: "full" for role in st["panel"]}
    last = n >= st["budget"]
    changed = {}
    modes = {}
    for role in st["panel"]:
        m = last_counted(st, role)
        if not m:
            modes[role] = "full"
            continue
        rnd = st["rounds"][m - 1]
        if rnd["scores"][role] == 10 and same_work(loop.kind, rnd, work):
            modes[role] = "skipped"
        elif st.get("final"):
            modes[role] = "full"
        elif rnd["scores"][role] == 10 and loop.kind == "build" and not last:
            if rnd["commit"] not in changed:
                changed[rnd["commit"]] = changed_names(loop.ctx, rnd["commit"])
            hit = any(role in roles_of(p, areas) for p in changed[rnd["commit"]])
            modes[role] = "changes" if hit else "skipped"
        else:
            modes[role] = "changes"
    if all(mode == "skipped" for mode in modes.values()):
        raise Exit(
            2,
            "Refused: no judge has anything to read. "
            "Next: tell the user; loop.py abandon, then loop.py start again.",
        )
    return modes


def skip_line(loop, role, work):
    m = last_counted(loop.st, role)
    rnd = loop.st["rounds"][m - 1]
    why = (
        "the work is unchanged"
        if same_work(loop.kind, rnd, work)
        else "nothing in its area changed"
    )
    return f"{role}: skipped, 10 in round {m}, {why}"


# The change log ----------------------------------------------------------------


def change_rows(loop):
    """[(round, role, id, kind)] of the rows of changes.md that have the form."""
    rows = []
    for line in loop_file(loop, "changes.md").split("\n"):
        hit = ROW.fullmatch(line.removesuffix("\r"))
        if hit and hit.group(2) in ROLES:
            rows.append((int(hit.group(1)), hit.group(2), hit.group(3), hit.group(4)))
    return rows


def counting_rows(st, rows, role):
    """The rows that count for a role: marked with its last counted round or later."""
    m = last_counted(st, role)
    return [r for r in rows if r[1] == role and m and r[0] >= m]


def print_notes(st, rows):
    """The notes before the first brief of a round: missing rows, waiting items."""
    waiting = set()
    for key, item in st["items"].items():
        if not effective_open(item):
            continue
        role, _, item_id = key.partition(":")
        mine = [r for r in counting_rows(st, rows, role) if r[2] == item_id]
        if not mine:
            say(f"note: no changes.md row for [{role} {item_id}]")
        if any(r[3] == "owner" for r in mine):
            waiting.add(key)
    if waiting:
        k = len(waiting)
        say(
            WAIT_NOTE.format(items=count(k, "item"), verb="waits" if k == 1 else "wait")
        )


# Diffs ------------------------------------------------------------------------


def cut_diff(body):
    if len(body) > MAX_DIFF:
        return body[:MAX_DIFF] + b"\n----- the diff is cut here at 2 MB -----\n"
    return body


def diff_text(ctx, base, head):
    """The changed files, then the diff of base..head, cut at 2 MB."""
    rows, _ = changed_rows(ctx, base, head, sep="..")
    out = ["Changed files (added deleted path):"]
    for path, added, deleted in rows:
        shown = clean(path, 4096)
        mark = " (name cleaned)" if shown != path else ""
        counts = f"{added} {deleted}" if added is not None else "- -"
        out.append(f"{counts} {shown}{mark}")
    out.append("")
    body = ctx.git.capped("diff", *DIFF_FLAGS, base, head, limit=MAX_DIFF)
    return "\n".join(out).encode() + b"\n" + cut_diff(body)


def write_delta(loop, role, n):
    """The delta of a changes judge: since the work of its last counted round."""
    st = loop.st
    m = last_counted(st, role)
    if loop.kind == "build":
        data = diff_text(loop.ctx, st["rounds"][m - 1]["commit"], "HEAD")
    else:
        old = loop.text(f"plan.r{m}.md").splitlines(keepends=True)
        new = loop.text("plan.md").splitlines(keepends=True)
        data = cut_diff(
            "".join(difflib.unified_diff(old, new, f"plan.r{m}.md", "plan.md")).encode(
                "utf-8"
            )
        )
    loop.write(f"judge/r{n}_{role}.delta.diff", data)


# Tokens and the scorecard -----------------------------------------------------


def whole(value, flag):
    """A token number of the command line, or None without the flag."""
    if value is None:
        return None
    if re.fullmatch(r"[0-9]{1,10}", value) and int(value) <= MAX_TOKENS:
        return int(value)
    raise Exit(
        2,
        f"Refused: {flag} takes a whole number from 0 to 1000000000. "
        "Next: the same command with the number, or without the flag.",
    )


def doubled(rnd):
    """The sum of a round's scores times 2: a whole number, as steps are 0.5."""
    return round(sum(rnd["scores"].values()) * 2)


def low_gain(now, before, panel_size):
    """True when the average rose by less than 0.2 (a fall counts)."""
    return (now - before) * 5 < 2 * panel_size


def gain_text(now, before, panel_size):
    diff = now - before
    hundredths = abs(diff) * 50 // panel_size
    sign = "-" if diff < 0 else "+"
    return f"{sign}{hundredths // 100}.{hundredths % 100:02d}"


def tokens_text(rnd):
    modes = rnd.get("modes", {})
    read = [r for r in rnd["scores"] if modes.get(r) != "skipped"]
    have = [rnd.get("tokens", {})[r] for r in read if r in rnd.get("tokens", {})]
    if not have:
        return "not given"
    if len(have) < len(read):
        return f"{sum(have)} ({len(have)} of {len(read)} judges)"
    return str(sum(have))


def scorecard_line(st, rnd):
    head = f"r{rnd['n']}: average {average_text(rnd['average'])}"
    if rnd["n"] > 1:
        before = st["rounds"][rnd["n"] - 2]
        gain = gain_text(doubled(rnd), doubled(before), len(rnd["scores"]))
        head += f" (gain {gain})"
    modes = rnd.get("modes", {})
    judges = ", ".join(
        f"{role} {score_text(score)} {modes.get(role, 'full')}"
        for role, score in rnd["scores"].items()
    )
    counts = rnd.get("items", {"open": 0, "closed": 0, "new": 0})
    fix = rnd.get("fix_tokens")
    return (
        f"{head} | {judges} | items: {counts['open']} open, {counts['closed']} "
        f"closed, {counts['new']} new | judge tokens: {tokens_text(rnd)} | "
        f"fix tokens: {'not given' if fix is None else fix}"
    )


def write_scorecard(loop):
    lines = [scorecard_line(loop.st, rnd) for rnd in loop.st["rounds"]]
    loop.write("scorecard.md", "\n".join(lines) + "\n")


def pending_line(st):
    pending = st["pending"]
    modes = pending.get("modes", {})
    roles = ", ".join(f"{role} {modes.get(role, 'full')}" for role in st["panel"])
    return f"Pending round {pending['round']}: {roles}"
