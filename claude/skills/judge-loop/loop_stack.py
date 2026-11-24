"""Stacks: issues that touch the same files are built as pull requests, each on
the branch of the one below, and judged together in one loop."""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from loop_modes import *

# The cap of one stack (STACK_MAX_PRS pull requests and these lines), so that
# a judge's input stays bounded. Past it the stack splits: the part above is
# based on the top branch of the part below.
STACK_MAX_LINES = 2500
# A stack loop runs at most this many rounds, whatever Judge rounds says.
STACK_BUDGET = 5
MAX_STACK_FILE = 256 * KB
MAX_PATHS = 200
TYPES = (
    "feat",
    "fix",
    "refactor",
    "docs",
    "test",
    "chore",
    "perf",
    "style",
    "build",
    "ci",
    "revert",
)
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,49}")
STACK_BRANCH = re.compile(r"[a-z]+/([1-9][0-9]{0,8})-[A-Za-z0-9._-]+")
ISSUES_FORM = (
    'a JSON list of {"issue": N, "type": "feat", "slug": "short-name", '
    '"files": [paths], "after": [issue numbers], "lines": N}'
)
STACK_FORM = (
    'a JSON object {"base": "<branch>", "prs": [{"pr": N, "issue": N, '
    '"branch": "<type>/<issue>-<slug>"}, ...]}, bottom first'
)
STACK_READ = (
    "This loop judges a stack of pull requests, each on the branch of the one "
    "below. Read {rel}/stack.md first: it lists each pull request, its issue, its "
    "branch and its hunks file; for a pull request judged before, that file holds "
    "only its own changes since then. A full brief reads the whole change all "
    "the same: {rel}/hunks.patch holds it, against the base of the stack."
)
STACK_ITEMS = (
    'Every item names the pull request it belongs to: "pr", one of {prs}. '
    "Its fix goes on that pull request's branch."
)
FIX_RULE = (
    "Every item names its pull request. Its fix is committed on that pull "
    "request's branch and merged up through the branches above it, bottom first; "
    "never rebased or force pushed."
)


def refuse(why, fix):
    return Exit(2, f"Refused: {why}. Next: {fix}.")


def positive(value):
    return is_type(value, int) and 0 < value < 10**9


def read_json(path, what, form):
    """The JSON of a file the session wrote."""
    fix = f"write {what} as {form}, then the same command"
    try:
        data = read_plain(Path(path), MAX_STACK_FILE)
    except OSError:
        data = None
    if not data:
        raise refuse(
            f"{shown_value(path)} is not a readable file of at most "
            f"{size_text(MAX_STACK_FILE)}",
            fix,
        )
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise refuse(f"{shown_value(path)} is not JSON", fix) from None


# Forming stacks -----------------------------------------------------------------


def plain_path(value):
    return value[2:] if value.startswith("./") else value


def read_issues(data):
    """The issues of an issues file, checked."""
    fix = f"write the issues file as {ISSUES_FORM}, then loop.py stacks again"
    if isinstance(data, dict):
        data = data.get("issues")
    if not isinstance(data, list) or not data:
        raise refuse("the issues file holds no list of issues", fix)
    issues, seen = [], set()
    for i, entry in enumerate(data, 1):
        where = f"issues[{i}]"
        if not isinstance(entry, dict):
            raise refuse(f"{where} is not an object", fix)
        number = entry.get("issue")
        if not positive(number):
            raise refuse(f"{where}.issue is not an issue number", fix)
        if number in seen:
            raise refuse(f"issue #{number} is listed twice", fix)
        seen.add(number)
        kind = entry.get("type", "feat")
        if kind not in TYPES:
            raise refuse(f"{where}.type is not one of {', '.join(TYPES)}", fix)
        name = entry.get("slug")
        if not (isinstance(name, str) and SLUG.fullmatch(name)):
            raise refuse(f"{where}.slug is not lower-case letters, digits and -", fix)
        files = entry.get("files", [])
        if not (
            isinstance(files, list)
            and len(files) <= MAX_PATHS
            and all(isinstance(f, str) and f.strip("./") for f in files)
        ):
            raise refuse(f"{where}.files is not a list of paths", fix)
        after = entry.get("after", [])
        if not (isinstance(after, list) and all(positive(a) for a in after)):
            raise refuse(f"{where}.after is not a list of issue numbers", fix)
        lines = entry.get("lines", 0)
        if not (is_type(lines, int) and lines >= 0):
            raise refuse(f"{where}.lines is not a number of lines", fix)
        issues.append(
            {
                "issue": number,
                "type": kind,
                "slug": name,
                "files": [plain_path(f) for f in files],
                "after": after,
                "lines": lines,
            }
        )
    for it in issues:
        for other in it["after"]:
            if other not in seen or other == it["issue"]:
                raise refuse(
                    f"issue #{it['issue']} comes after #{other}, which is not "
                    "another issue of the list",
                    fix,
                )
    return issues


def overlap(paths, others):
    """True when two lists of paths share a file; a path ending in / is a folder."""
    for p in paths:
        for q in others:
            if p == q or (p.endswith("/") and q.startswith(p)):
                return True
            if q.endswith("/") and p.startswith(q):
                return True
    return False


def groups(issues):
    """The issues that touch the same files or wait on each other, together;
    in the order of their first issue."""
    parent = list(range(len(issues)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    index = {it["issue"]: i for i, it in enumerate(issues)}
    for i, it in enumerate(issues):
        for j in range(i):
            if overlap(it["files"], issues[j]["files"]):
                parent[find(i)] = find(j)
        for other in it["after"]:
            parent[find(i)] = find(index[other])
    out = {}
    for i, it in enumerate(issues):
        out.setdefault(find(i), []).append(it)
    return list(out.values())


def ordered(group):
    """Each issue after the issues it waits on; otherwise in the given order."""
    out, done, rest = [], set(), list(group)
    while rest:
        ready = next((it for it in rest if set(it["after"]) <= done), None)
        if ready is None:
            names = ", ".join(f"#{it['issue']}" for it in rest)
            raise refuse(
                f"issues {names} wait on each other",
                "drop one of their after links, then loop.py stacks again",
            )
        out.append(ready)
        done.add(ready["issue"])
        rest.remove(ready)
    return out


def branch_of(it):
    return f"{it['type']}/{it['issue']}-{it['slug']}"


def split(issues):
    """The parts of one ordered stack, each under the cap."""
    parts, part, lines = [], [], 0
    for it in issues:
        full = len(part) >= STACK_MAX_PRS or lines + it["lines"] > STACK_MAX_LINES
        if part and full:
            parts.append(part)
            part, lines = [], 0
        part.append(it)
        lines += it["lines"]
    parts.append(part)
    return parts


def form_stacks(issues, base, stacked=True):
    """[{"base", "issues", "lines", "part"}]: one stack per group of issues that
    touch the same files, split at the cap. Without stacks: one per issue."""
    if not stacked:
        return [
            {"base": base, "issues": [it], "lines": it["lines"], "part": 0}
            for it in ordered(issues)
        ]
    stacks = []
    for group in groups(issues):
        below = base
        for k, part in enumerate(split(ordered(group))):
            lines = sum(it["lines"] for it in part)
            stacks.append({"base": below, "issues": part, "lines": lines, "part": k})
            below = branch_of(part[-1])
    return stacks


def cmd_stacks(args):
    ctx = Ctx()
    issues = read_issues(read_json(args.issues, "the issues file", ISSUES_FORM))
    base, _ = find_base(ctx, args.base)
    if not base:
        raise refuse("no base branch found", "the same command with --base <branch>")
    switches, _ = read_switches(ctx, base)
    off = switches.get("Stacks")
    stacks = form_stacks(issues, base, stacked=not off)
    if off:
        say(
            f"Stacks: off, by {off['where']}: one loop per pull request, each on "
            f"{show_branch(base)}"
        )
    total = len(stacks)
    for i, stack in enumerate(stacks, 1):
        part = ", the part above the stack before it" if stack["part"] else ""
        say(
            f"Stack {i} of {total}: base {show_branch(stack['base'])}, "
            f"{count(len(stack['issues']), 'pull request')}, about "
            f"{count(stack['lines'], 'changed line')}{part}"
        )
        below = stack["base"]
        for k, it in enumerate(stack["issues"], 1):
            over = ""
            if it["lines"] > STACK_MAX_LINES:
                over = f" (over the cap of {STACK_MAX_LINES} lines alone: split it)"
            say(f"  {k}. #{it['issue']} {branch_of(it)} on {show_branch(below)}{over}")
            below = branch_of(it)
    say(
        f"Cap: {STACK_MAX_PRS} pull requests and {STACK_MAX_LINES} changed lines "
        "per stack"
    )
    planned = f"Planned: {count(total, 'stack')} for {count(len(issues), 'issue')}."
    if off:
        raise Exit(
            0,
            f"{planned} Next: build each issue on its own branch with a draft pull "
            "request, then loop.py start build on that branch.",
        )
    raise Exit(
        0,
        f"{planned} Next: build each stack bottom-up, one draft pull request per "
        "issue against the branch below it; once a stack is built, loop.py start "
        "build --stack <stack file> on its top branch.",
    )


def configure_stacks(sub):
    sub.add_argument(
        "--issues", required=True, help=f"the issues to plan: {ISSUES_FORM}"
    )
    sub.add_argument("--base", help="the branch the stacks are based on")


COMMANDS["stacks"] = (configure_stacks, cmd_stacks)


# A stack loop ---------------------------------------------------------------


def load_stack(path):
    """The stack file of `start build --stack`, checked."""
    data = read_json(path, "the stack file", STACK_FORM)
    fix = f"write the stack file as {STACK_FORM}, then the same command"
    if not isinstance(data, dict) or not isinstance(data.get("prs"), list):
        raise refuse("the stack file holds no list of pull requests", fix)
    if not data["prs"]:
        raise refuse("the stack file holds no list of pull requests", fix)
    base = data.get("base")
    if not (isinstance(base, str) and PLAIN_BRANCH.fullmatch(base)):
        raise refuse("the stack file names no base branch", fix)
    prs, seen = [], set()
    for i, entry in enumerate(data["prs"], 1):
        where = f"prs[{i}]"
        if not isinstance(entry, dict):
            raise refuse(f"{where} is not an object", fix)
        pr, issue, branch = entry.get("pr"), entry.get("issue"), entry.get("branch")
        if not positive(pr):
            raise refuse(f"{where}.pr is not a pull request number", fix)
        if not positive(issue):
            raise refuse(f"{where}.issue is not an issue number", fix)
        m = STACK_BRANCH.fullmatch(branch) if isinstance(branch, str) else None
        if not (m and PLAIN_BRANCH.fullmatch(branch) and int(m.group(1)) == issue):
            raise refuse(f"{where}.branch is not <type>/{issue}-<slug>", fix)
        for key in (("pr", pr), ("issue", issue), ("branch", branch)):
            if key in seen:
                raise refuse(f"{where}.{key[0]} is listed twice", fix)
            seen.add(key)
        prs.append({"pr": pr, "issue": issue, "branch": branch})
    if len(prs) > STACK_MAX_PRS:
        raise refuse(
            f"the stack holds {count(len(prs), 'pull request')}, over the cap of "
            f"{STACK_MAX_PRS}",
            "split it (loop.py stacks shows where), then start a loop for each part",
        )
    return {"base": base, "prs": prs}


def chain_heads(ctx, stack, then):
    """{pr: head} of every branch of the stack; each must hold the one below."""
    heads, below = {}, None
    for entry in stack["prs"]:
        branch = show_branch(entry["branch"])
        sha = ctx.resolve(f"refs/heads/{entry['branch']}")
        if not sha:
            raise refuse(
                f"no branch {branch} here (#{entry['pr']})",
                f"check out each branch of the stack once, then {then}",
            )
        if below and not ctx.is_ancestor(below[1], sha):
            lower = show_branch(below[0])
            raise refuse(
                f"{branch} does not hold {lower}, the branch below it",
                f"merge {lower} into {branch} (never rebase), then {then}",
            )
        heads[str(entry["pr"])] = sha
        below = (entry["branch"], sha)
    return heads


def check_stack(ctx, stack, size):
    """The checks of `start build --stack` after the usual ones."""
    top = stack["prs"][-1]["branch"]
    if ctx.branch != top:
        raise refuse(
            f"the top of the stack is {show_branch(top)}, the checkout is on "
            f"{show_branch(ctx.branch)}",
            f"git switch {show_branch(top)}, then the same command",
        )
    chain_heads(ctx, stack, "the same command")
    if size.lines > STACK_MAX_LINES:
        raise refuse(
            f"the stack changes {count(size.lines, 'line')}, over the cap of "
            f"{STACK_MAX_LINES}",
            "split it (loop.py stacks shows where), then start a loop for each part",
        )


def stack_list(stack):
    names = ", ".join(f"#{e['pr']} {e['branch']}" for e in stack["prs"])
    return f"{names}, bottom first, on {show_branch(stack['base'])}"


def stack_prs(st):
    """The pull request numbers of a stack loop; () for any other loop."""
    stack = st.get("stack")
    return tuple(entry["pr"] for entry in stack["prs"]) if stack else ()


def stack_heads(loop):
    return chain_heads(loop.ctx, loop.st["stack"], "loop.py brief")


def check_criteria(loop):
    """criteria.md holds the criteria of each issue, under its number."""
    text = loop_file(loop, "criteria.md")
    missing = [
        f"#{entry['issue']}"
        for entry in loop.st["stack"]["prs"]
        if not re.search(rf"#{entry['issue']}(?![0-9])", text)
    ]
    if missing:
        raise refuse(
            f"criteria.md names no criteria for {', '.join(missing)}",
            f"add a section per issue to {loop.rel}/criteria.md (## #N, then its "
            "criteria), then loop.py brief",
        )


def own_changes(ctx, old, head, below, base, m):
    """The commits of one pull request since round m, without what came up from
    the branches below it or straight from the base of the stack."""
    body = ctx.git.capped(
        "log",
        "-p",
        "--no-merges",
        *DIFF_FLAGS,
        "--format=commit %H%n%n    %s%n",
        f"{old}..{head}",
        f"^{below}",
        f"^{base}",
        "--",
        limit=MAX_DIFF,
    )
    first = (
        f"# Its own commits since round {m}; merges from below and from the base "
        "left out.\n"
    )
    if not body.strip():
        return (
            f"# No commit of its own since round {m}, only merges from below or "
            "from the base.\n"
        ).encode()
    out = first.encode() + body[:MAX_DIFF]
    if len(body) > MAX_DIFF:
        out += f"----- the log is cut here at {size_text(MAX_DIFF)} -----\n".encode()
    return out


def item_status(item):
    settled = item["settled"]
    if settled and not settled["raised_again"]:
        return f"settled by the user: {field_text(settled['note'])}"
    return "open" if item["open"] else f"closed in round {item['last'] + 1}"


def write_stack(loop, n, work):
    """stack.md, the map of the stack, and stack/pr<N>.patch per pull request."""
    st, ctx = loop.st, loop.ctx
    stack, heads = st["stack"], work["heads"]
    last = st["rounds"][-1] if st["rounds"] else None
    judged = last.get("heads", {}) if last else {}
    full = f"{loop.rel}/judge/r{n}.diff"
    below_sha, below_name = work["base_sha"], stack["base"]
    rows, before = [], []
    for k, entry in enumerate(stack["prs"], 1):
        key = str(entry["pr"])
        head, old = heads[key], judged.get(key, "")
        rel = f"stack/pr{entry['pr']}.patch"
        if old == head:
            since = f"unchanged since round {last['n']}"
            data = f"# #{entry['pr']} is {since}: nothing new to read.\n".encode()
        elif old and ctx.is_ancestor(old, head):
            since = f"changes since round {last['n']}"
            data = own_changes(ctx, old, head, below_sha, work["base_sha"], last["n"])
        else:
            since = f"rewritten since round {last['n']}" if old else "new"
            start = ctx.git.out("merge-base", below_sha, head, ok=(0, 1))
            data = hunks_text(ctx, start or below_sha, head, full)
        loop.write(rel, data)
        rows.append(
            f"| {k} | #{entry['pr']} | #{entry['issue']} | {entry['branch']} | "
            f"{show_branch(below_name)} | {loop.rel}/{rel} | {since} |"
        )
        if old:
            before.append((entry["pr"], since))
        below_sha, below_name = head, entry["branch"]
    prs = ", ".join(f"#{e['pr']}" for e in stack["prs"])
    lines = [
        f"# A stack of {count(len(stack['prs']), 'pull request')} on "
        f"{show_branch(stack['base'])}",
        "",
        "Bottom first; each pull request is based on the branch of the one above "
        "it in this table, and they merge in this order.",
        "",
        "| # | Pull request | Issue | Branch | Based on | Hunks | Since the last "
        "round |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"Criteria: {loop.rel}/criteria.md, one section per issue.",
        f"Items: {STACK_ITEMS.format(prs=prs)}",
        f"Fixes: {FIX_RULE}",
    ]
    if before:
        lines += ["", "## Judged before", ""]
        for pr, since in before:
            lines.append(f"### #{pr}, {since}")
            mine = [(key, it) for key, it in st["items"].items() if it.get("pr") == pr]
            for key, it in mine:
                role, _, item_id = key.partition(":")
                lines.append(
                    f"- [{role} {item_id}] {item_status(it)}: "
                    f"{field_text(it['problem'])} | fix: {field_text(it['fix'])}"
                )
            if not mine:
                lines.append("- no items")
            lines.append("")
    loop.write("stack.md", "\n".join(lines).rstrip("\n") + "\n")


def stack_prompt(loop):
    """The lines a judge of a stack loop reads before the usual ones."""
    prs = ", ".join(f"#{pr}" for pr in stack_prs(loop.st))
    return [STACK_READ.format(rel=loop.rel), STACK_ITEMS.format(prs=prs)]


# Waiting for the judges ----------------------------------------------------------


def waiting_line(st):
    waiting = st.get("waiting")
    if not waiting:
        return ""
    return f"Waiting since {clean(waiting['since'])}: {clean(waiting['note'])}"


def cmd_wait(args):
    ctx = Ctx()
    loop = pick(ctx, args, "wait")
    st = loop.st
    if st["outcome"] != "open":
        raise state_exit(loop)
    note = clean(args.note or "") or "the judge model is at its limit"
    st["waiting"] = {
        "since": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "note": note,
    }
    loop.save()
    what = "stack" if st.get("stack") else f"{loop.kind} loop"
    raise Exit(
        0,
        f"Waiting: the {what} {loop.name} waits for its judges ({note}). Next: build "
        "other stacks; loop.py brief once the judges can run again.",
    )


def configure_wait(sub):
    sub.add_argument("--note", help="why the judges cannot run now")
    sub.add_argument("--kind", choices=KINDS, help="plan or build")
    sub.add_argument("--name", help="the loop's name, see loop.py status")


COMMANDS["wait"] = (configure_wait, cmd_wait)
