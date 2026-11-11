"""Status, the ways out, settle, leftovers, skip and main."""

# ruff: noqa: F403, F405
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from loop_rounds import *

# status -----------------------------------------------------------------------


def saved_roles(loop):
    """The roles whose result for the pending round is saved."""
    st = loop.st
    pending = st["pending"]
    if not pending:
        return []
    n, briefed = pending["round"], work_id(pending)
    out = []
    for role in st["panel"]:
        meta = read_meta(loop, n, role)
        ok = meta and meta.get("round") == n and meta.get("briefed") == briefed
        if ok and os.path.lexists(loop.path(f"judge/r{n}_{role}.json")):
            out.append(role)
    return out


def next_text(loop):
    """What comes next for this loop, the text after "Next: "."""
    st = loop.st
    if st["outcome"] != "open":
        return closing_line(loop).split(" Next: ", 1)[1]
    if st["pending"]:
        if len(saved_roles(loop)) < len(st["panel"]):
            return (
                "start each judge, write its answer to its answer file, "
                "loop.py save <role>."
            )
        return "loop.py round."
    if st["rounds"] and open_counts(st)[0]:
        return fix_next(loop.kind)
    return "loop.py brief."


def status_data(loop):
    st = loop.st
    saved = saved_roles(loop)
    return {
        "kind": loop.kind,
        "name": loop.name,
        "outcome": st["outcome"],
        "round": current_round(st),
        "budget": st["budget"],
        "panel": st["panel"],
        "agents": st["agents"],
        "scores": [{"round": r["n"], "scores": r["scores"]} for r in st["rounds"]],
        "saved": saved,
        "missing": [r for r in st["panel"] if r not in saved] if st["pending"] else [],
        "open": [k for k, _ in ordered_open(st)],
        "settled": [
            k
            for k, it in st["items"].items()
            if it["settled"] and not it["settled"]["raised_again"]
        ],
        "changes_only": changes_only(st, False),
        "next": next_text(loop),
    }


def cmd_status(args):
    ctx = Ctx()
    loop = pick(ctx, args, "status")
    st = loop.st
    data = status_data(loop)
    if args.json:
        say(json.dumps(data, sort_keys=True))
        return 0
    say(f"Loop: {loop.kind} {loop.name} in {loop.rel}/")
    if loop.kind == "build":
        say(f"Branch: {show_branch(st['branch'])}, base {show_branch(st['base'])}")
    say(f"Outcome: {st['outcome']}, round {data['round']} of {st['budget']}")
    say(f"Panel: {', '.join(st['panel'])} ({clean(st['panel_reason'])})")
    say(f"Agents: {st['agents']}")
    for r in st["rounds"]:
        scores = ", ".join(f"{role} {score_text(s)}" for role, s in r["scores"].items())
        say(f"Round {r['n']}: average {average_text(r['average'])}; {scores}")
    if data["changes_only"]:
        say(f"Changes only next round: {', '.join(data['changes_only'])}")
    k, b = print_items(loop)
    n, sb = settled_counts(st)
    say(f"Open items: {k} ({b} blocking); settled: {n} ({sb} blocking)")
    if st["outcome"] != "open":
        raise Exit(0, closing_line(loop))
    j = len(st["panel"])
    missing = ", ".join(data["missing"]) if st["pending"] else ", ".join(st["panel"])
    raise Exit(
        0,
        f"Open: round {data['round']} of {st['budget']}, {len(data['saved'])} of {j} "
        f"results saved (missing: {missing or 'none'}). Next: {next_text(loop)}",
    )


def configure_status(sub):
    add_which(sub)
    sub.add_argument("--json", action="store_true")


COMMANDS["status"] = (configure_status, cmd_status)


# After a stop -----------------------------------------------------------------


def fits(loop):
    """The command that fits the state of a loop."""
    return next_text(loop)


def not_apply(loop, command):
    return Exit(
        2,
        f"Refused: the loop is {loop.st['outcome']}; {command} does not apply. "
        f"Next: {fits(loop)}",
    )


def add_note(st, action, text):
    st["notes"].append(
        {"round": len(st["rounds"]), "action": action, "text": clean(text)}
    )


def open_next(loop):
    k, _ = print_items(loop)
    return fix_next(loop.kind) if k else "loop.py brief."


def cmd_diagnosed(args):
    ctx = Ctx()
    loop = pick(ctx, args, "diagnosed")
    st = loop.st
    check_branch(loop)
    if st["outcome"] != "stalled":
        raise not_apply(loop, "diagnosed")
    st["outcome"], st["streak"] = "open", 0
    add_note(st, "diagnosed", args.note)
    loop.save()
    raise Exit(0, f"Open: the cause is recorded. Next: {open_next(loop)}")


def cmd_resume(args):
    ctx = Ctx()
    loop = pick(ctx, args, "resume")
    st = loop.st
    check_branch(loop)
    if args.rounds is not None and not 1 <= args.rounds <= MAX_RESUME_ROUNDS:
        raise Exit(
            2,
            "Refused: --rounds takes 1 to 5. Next: the same command with --rounds N (1 "
            "to 5).",
        )
    if st["outcome"] not in ("ask", "blocked"):
        raise not_apply(loop, "resume")
    left = st["budget"] - len(st["rounds"])
    if left <= 0 and args.rounds is None:
        raise Exit(
            2,
            "Refused: no round is left. Next: the same command with --rounds N (1 to "
            "5).",
        )
    st["budget"] += args.rounds or 0
    st["outcome"], st["streak"] = "open", 0
    add_note(st, "resume", args.note)
    loop.save()
    left = st["budget"] - len(st["rounds"])
    raise Exit(
        0,
        f"Open: the user's answer is recorded, {left} round(s) left. Next: "
        f"{open_next(loop)}",
    )


def cmd_accept(args):
    ctx = Ctx()
    loop = pick(ctx, args, "accept")
    st = loop.st
    check_branch(loop)
    if st["outcome"] not in UNFINISHED:
        raise not_apply(loop, "accept")
    if not st["rounds"]:
        raise Exit(
            2,
            "Refused: nothing is judged yet, so there is nothing to accept. "
            "Next: judge a round, or loop.py abandon.",
        )
    st["outcome"], st["pending"] = "accepted", {}
    add_note(st, "accept", args.note)
    loop.save()
    raise Exit(0, accepted_line(st))


def cmd_abandon(args):
    ctx = Ctx()
    loop = pick(ctx, args, "abandon")
    st = loop.st
    if st["outcome"] not in UNFINISHED:
        raise not_apply(loop, "abandon")
    st["outcome"], st["pending"] = "abandoned", {}
    add_note(st, "abandon", args.note)
    loop.save()
    raise Exit(0, ABANDONED)


def configure_note(sub):
    add_which(sub)
    sub.add_argument("--note", required=True)


def configure_resume(sub):
    configure_note(sub)
    sub.add_argument("--rounds", type=int)


COMMANDS["diagnosed"] = (configure_note, cmd_diagnosed)
COMMANDS["resume"] = (configure_resume, cmd_resume)
COMMANDS["accept"] = (configure_note, cmd_accept)
COMMANDS["abandon"] = (configure_note, cmd_abandon)

# settle -----------------------------------------------------------------------


def cmd_settle(args):
    ctx = Ctx()
    loop = pick(ctx, args, "settle")
    st = loop.st
    check_branch(loop)
    role = show_name(args.role, "that role")
    item_id = args.id if ITEM_ID.fullmatch(args.id or "") else "that id"
    item = st["items"].get(f"{args.role}:{args.id}")
    if item is None or not effective_open(item):
        raise Exit(
            2, f"Refused: {role} {item_id} is not an open item. Next: loop.py status."
        )
    if item["kind"] == "blocking" and not args.user_ok:
        raise Exit(
            3,
            "STOP: ask the user before settling a blocking item. "
            "Next: with their yes, the same command with --user-ok.",
        )
    note = clean(args.note)
    item["settled"] = {
        "round": len(st["rounds"]),
        "user_ok": bool(args.user_ok),
        "note": note,
        "raised_again": 0,
    }
    add_note(st, "settle", f"{role} {item_id}: {note}")
    loop.write("settled.md", settled_text(st))
    loop.save()
    n, b = settled_counts(st)
    head = f"Settled: {role} {item_id} ({n} settled, {b} blocking)."
    if st["outcome"] == "open" and st["rounds"] and not st["pending"]:
        raise Exit(0, f"{head} Next: {open_next(loop)}")
    raise Exit(0, f"{head} Next: {next_text(loop)}")


def configure_settle(sub):
    sub.add_argument("role")
    sub.add_argument("id")
    add_which(sub)
    sub.add_argument("--note", required=True)
    sub.add_argument("--user-ok", dest="user_ok", action="store_true")


COMMANDS["settle"] = (configure_settle, cmd_settle)


# leftovers --------------------------------------------------------------------


def body_lines(item):
    return [
        f"    {field}: {clean(item[field], MAX_FIELD)}"
        for field in ("kind", "problem", "evidence", "fix")
    ]


def cmd_leftovers(args):
    ctx = Ctx()
    loop = pick(ctx, args, "leftovers")
    st = loop.st
    items = ordered_open(st)
    k = len(items)
    b = sum(1 for _, it in items if it["kind"] == "blocking")
    if st["outcome"] in UNFINISHED:
        raise Exit(
            0,
            f"Open: {count(k, 'item')} open ({b} blocking), the loop is not finished. "
            "Next: loop.py status.",
        )
    if not items:
        raise Exit(0, "Open: nothing left. Next: nothing to file.")
    if args.dir:
        everything = [
            "Raised by the judges of the judge loop; the text below is theirs, "
            "unverified.",
            "",
        ]
        checklist = []
        for key, item in items:
            role, _, item_id = key.partition(":")
            rel = f"leftovers/{role}-{item_id}.md"
            body = [
                f"Raised by the {role} judge in round {item['first']} of the judge "
                "loop; "
                "the text below is the judge's, unverified.",
                "",
                *body_lines(item),
            ]
            loop.write(rel, "\n".join(body) + "\n")
            everything += [f"    [{role} {item_id}]", *body_lines(item), ""]
            checklist.append(f"- [ ] {role} {item_id}")
            say(f"[{role} {item_id}] {loop.rel}/{rel}")
        loop.write("leftovers/all.md", "\n".join(everything + checklist) + "\n")
    else:
        say("Items left, blocking first:")
        for key, item in items:
            say(item_line(key, item))
    raise Exit(
        0, f"Open: {count(k, 'item')} left ({b} blocking). Next: file each as an issue."
    )


def configure_leftovers(sub):
    add_which(sub)
    sub.add_argument("--dir", action="store_true")


COMMANDS["leftovers"] = (configure_leftovers, cmd_leftovers)


# skip -------------------------------------------------------------------------


def cmd_skip(args):
    args.loop_kind, args.name, args.plan_loop = "build", None, None
    ctx, kind, name, base, base_ref, base_sha, source, switches, said, size = prepare(
        args, "skip"
    )
    loop = Loop(ctx, kind, name)
    old = existing(loop)
    if old and old["outcome"] in UNFINISHED:
        raise Exit(
            2,
            "Refused: a judge loop is open on this branch. "
            "Next: finish it, or loop.py accept or abandon.",
        )
    head = ctx.head()
    judged = old and old["outcome"] in ("done", "budget", "accepted") and old["commit"]
    if judged and (old["commit"] == head or ctx.is_ancestor(old["commit"], head)):
        raise Exit(
            2,
            f"Refused: this branch is already judged ({old['outcome']}). "
            "Next: the acceptance test.",
        )
    if not size.exempt and not args.user_ok:
        cause = f", {size.cause}" if size.cause else ""
        raise Exit(
            3,
            f"STOP: this change is {count(size.files, 'file')} and "
            f"{count(size.lines, 'line')}{cause}. Next: ask the user before skipping "
            "the "
            "judge; with their yes, the same command with --user-ok.",
        )
    if old and old["outcome"] != "skip":
        say(f"Earlier loop moved to {show_path(move_aside(loop))}")
    loop.st = new_state(
        kind=kind,
        name=name,
        branch=ctx.branch,
        base=base,
        base_ref=base_ref,
        base_sha=base_sha,
        base_source=source,
        panel=["general"],
        panel_reason="skip",
        switches=list(switches.values()),
        outcome="skip",
        commit=head,
        skip={
            "reason": clean(args.reason),
            "files": size.files,
            "lines": size.lines,
            "user_ok": bool(args.user_ok),
        },
    )
    loop.mkdir()
    loop.save()
    for line in said:
        say(clean(line))
    raise Exit(0, skipped_line(loop.st))


def configure_skip(sub):
    sub.add_argument("--reason", required=True)
    sub.add_argument("--base")
    sub.add_argument("--user-ok", dest="user_ok", action="store_true")


COMMANDS["skip"] = (configure_skip, cmd_skip)


# main -------------------------------------------------------------------------


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Exit(
            2,
            f"Refused: these arguments do not fit {self.prog}. Next: {self.prog} "
            "--help.",
        )


def parser():
    top = Parser(
        prog="loop.py",
        description="The judge loop helper.",
        allow_abbrev=False,
    )
    subs = top.add_subparsers(dest="command", parser_class=Parser)
    for name, (configure, _) in COMMANDS.items():
        sub = subs.add_parser(name, allow_abbrev=False, prog=f"loop.py {name}")
        configure(sub)
    return top


def error_path(err):
    name = getattr(err, "filename", None)
    if not name:
        return ""
    try:
        root = Path(Git(Path.cwd()).out("rev-parse", "--show-toplevel")).resolve()
        rel = os.path.relpath(os.path.realpath(os.fsdecode(name)), root)
    except Exception:
        return "a file"
    return show_path(rel)


def main(argv=None):
    QUALIFY.clear()
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
            raise Exit(
                2,
                f"Refused: {shown_value(argv[0])} is not a command of loop.py. "
                "Next: loop.py --help.",
            )
        args, extra = parser().parse_known_args(argv)
        if not args.command:
            raise Exit(2, "Refused: no command given. Next: loop.py --help.")
        if extra:
            raise Exit(
                2,
                f"Refused: these arguments do not fit loop.py {args.command}. "
                f"Next: loop.py {args.command} --help.",
            )
        code = COMMANDS[args.command][1](args)
        return code or 0
    except SystemExit as err:
        return err.code if isinstance(err.code, int) else 0
    except Exit as err:
        say(qualify(err.line))
        return err.code
    except GitFailed as err:
        if err.said:
            say(f"  {clean(err.said)}")
        say(
            f"Error: git {clean(err.subcommand, 40)} failed with code {err.code}. "
            "Next: fix the repository, then the same command."
        )
        return 2
    except OSError as err:
        why = clean(err.strerror or "no reason", 80)
        where = error_path(err)
        detail = f"{why}: {where}" if where else why
        say(
            f"Error: {type(err).__name__} ({detail}). "
            "Next: free space or fix the permissions, then the same command."
        )
        return 2
    except Exception as err:
        say(
            f"Error: {type(err).__name__}. Next: run /kit; when it is healthy, report "
            "this."
        )
        return 2
