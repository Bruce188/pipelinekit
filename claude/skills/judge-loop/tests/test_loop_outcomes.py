"""Tests of loop.py: outcomes, ways out, fix order, settle, leftovers, skip."""

from __future__ import annotations

import json
import re

import pytest
from loop_fixtures import (
    FIX_BUILD,
    FIX_PLAN,
    NAME,
    brief_of,
    item,
    loop,
    nine,
    one_round,
    plan_stage,
    play,
    result,
    scored,
)

# Outcomes ---------------------------------------------------------------------


STALLS = [
    # kind, budget, scores, blocking, exit, outcome
    ("plan", 1, [9], False, 0, "budget"),
    ("build", 1, [9], False, 0, "budget"),
    ("plan", 2, [9, 9], False, 0, "budget"),
    ("build", 2, [9, 9], False, 0, "budget"),
    ("plan", 3, [9, 9, 9], False, 3, "ask"),
    ("plan", 3, [9, 9, 9], True, 3, "ask"),
    ("build", 3, [9, 9, 9], False, 0, "budget"),
    ("build", 3, [9, 9, 9], True, 3, "blocked"),
    ("build", 4, [9, 9, 9], False, 3, "stalled"),
    ("build", 4, [8, 9, 9, 9], False, 0, "budget"),
    ("plan", 4, [8, 9, 9, 9], False, 3, "ask"),
    ("build", 5, [8, 9, 9, 9], False, 3, "stalled"),
    ("build", 6, [9, 9, 9], False, 3, "stalled"),
    ("plan", 5, [9, 9, 9], False, 3, "ask"),
    ("plan", 6, [8, 9, 9, 9], False, 3, "ask"),
    ("build", 4, [9, 8, 8], False, 3, "stalled"),
    ("build", 4, [8, 8.5, 9, 9.5], False, 0, "budget"),
]


def stall_id(row):
    kind, budget, scores, blocking = row[:4]
    shown = "-".join(str(s) for s in scores)
    return f"{kind}-{budget}-{shown}{'-blocking' if blocking else ''}"


@pytest.mark.parametrize(
    "kind, budget, scores, blocking, code, outcome",
    STALLS,
    ids=[stall_id(s) for s in STALLS],
)
def test_the_stall_table(sb, kind, budget, scores, blocking, code, outcome):
    run = play(sb, kind, budget, scores, blocking)
    name = "p1" if kind == "plan" else None
    st = sb.state(kind, name)
    assert (run.code, st["outcome"]) == (code, outcome), run
    assert len(st["rounds"]) == len(scores)
    first = {
        "budget": "Budget used:",
        "ask": "STOP: ask the user, less than 0.2 gain in two rounds.",
        "stalled": "STOP: stalled, less than 0.2 gain in two rounds.",
        "blocked": "STOP: blocking items left after the last round.",
    }[outcome]
    assert run.last.startswith(first)
    if outcome in ("ask", "stalled") and not blocking:
        assert st["streak"] == 2
        shown = ", ".join(f"round {i} {s:.1f}" for i, s in enumerate(scores, 1))
        assert f"Averages: {shown}" in run.lines


@pytest.mark.parametrize("kind", ["build", "plan"])
def test_the_stall_rule_compares_with_the_round_before(sb, kind):
    # Against the best earlier average, 8.5 after 9 and 8 would stall in round 3.
    run = play(sb, kind, 6, [9, 8, 8.5, 9])
    st = sb.state(kind, "p1" if kind == "plan" else None)
    assert (run.code, st["outcome"], st["streak"]) == (1, "open", 0), run


def test_the_outcome_rows(sb):
    run = play(sb, "build", 5, [9])
    assert run.code == 1
    assert run.lines[0] == "Round 1 of 5: average 9.0; general 9 full"
    assert run.last == "Fix: 1 item (0 blocking). " + FIX_BUILD
    sb.change("app.py", 7)
    run = sb.judge({"general": result(10)})
    assert run.code == 0
    assert run.lines[0] == (
        "Round 2 of 5: average 10.0 (round before: 9.0); general 10 changes"
    )
    assert (
        run.last == "Done: 10 from every judge in 2 rounds. Next: the acceptance test."
    )


def test_a_ten_with_an_open_blocking_item_is_not_done(sb):
    sb.two_judges()
    sb.start_build()
    run = sb.judge({"general": 10, "tests": result(9, blocking=[item("B1")])})
    assert run.code == 1
    sb.change("app.py", 6)
    run = sb.judge({"general": 10, "tests": result(10)})
    assert run.code == 0
    assert sb.state()["outcome"] == "done"


def test_diagnosed_sets_the_streak_to_zero(sb):
    assert play(sb, "build", 6, [9, 9, 9]).code == 3
    assert sb.state()["streak"] == 2
    run = sb.run("diagnosed", "--note", "the judges disagree")
    assert run.code == 0
    assert run.last == "Open: the cause is recorded. " + FIX_BUILD
    st = sb.state()
    assert (st["outcome"], st["streak"], st["final"]) == ("open", 0, False)
    sb.change("app.py", 9)
    run = sb.judge({"general": scored(9)})
    assert run.code == 1
    assert sb.state()["streak"] == 1


def test_done_with_two_improvements_left(sb):
    sb.start_build()
    run = sb.judge({"general": result(10, improvements=[item("I1"), item("I2")])})
    assert run.code == 0
    assert run.last == (
        "Done: 10 from every judge in 1 round, 2 improvements left. Next: loop.py "
        "leftovers, file each as an issue, then the acceptance test."
    )


HANDOVER = (
    "check out a work branch, have kit-builder build docs/loops/p1/plan/plan.r{n}.md "
    "and commit, then loop.py start build --plan-loop p1."
)


def test_the_closing_lines_of_a_plan(sb):
    run = plan_stage(sb)
    assert run.last == "Done: 10 from every judge in 1 round. Next: " + HANDOVER.format(
        n=1
    )
    assert sb.run("start", "plan", "--name", "p2").code == 0
    sb.criteria("plan", "p2")
    (sb.loopdir("plan", "p2") / "plan.md").write_text("# Plan two\n")
    sb.set_state("plan", "p2", budget=1)
    which = ("--kind", "plan", "--name", "p2")
    run = sb.judge({"general": scored(9)}, "plan", "p2", which)
    assert run.code == 0
    assert run.last == (
        "Budget used: 1 round, average 9.0, 1 item left. Next: loop.py leftovers "
        "--kind plan --name p2, file each as an issue, "
        + HANDOVER.format(n=1).replace("p1", "p2")
    )
    assert sb.run("start", "plan", "--name", "p3").code == 0
    sb.criteria("plan", "p3")
    (sb.loopdir("plan", "p3") / "plan.md").write_text("# Plan three\n")
    which = ("--kind", "plan", "--name", "p3")
    assert sb.judge({"general": scored(9)}, "plan", "p3", which).code == 1
    run = sb.run("accept", "--note", "good enough", *which)
    assert run.code == 0
    assert run.last == (
        "Accepted: by the user in round 1 of 5 with 1 item left (0 blocking). Next: "
        "loop.py leftovers --kind plan --name p3, file each as an issue, "
        + HANDOVER.format(n=1).replace("p1", "p3")
    )


# Ways out ---------------------------------------------------------------------


ACCEPTED_LINE = (
    "Accepted: by the user in round 1 of 5 with 1 item left (0 blocking). "
    "Next: loop.py leftovers, file each as an issue, then the acceptance test."
)


@pytest.mark.parametrize("outcome", ["open", "stalled", "ask", "blocked"])
def test_accept_from_an_unfinished_state(sb, outcome):
    one_round(sb)
    sb.set_state(outcome=outcome)
    run = sb.run("accept", "--note", "the user is content")
    assert (run.code, run.last) == (0, ACCEPTED_LINE)
    assert sb.state()["outcome"] == "accepted"


def test_accept_without_a_counted_round(sb):
    sb.start_build()
    run = sb.run("accept", "--note", "x")
    assert (run.code, run.last) == (
        2,
        "Refused: nothing is judged yet, so there is nothing to accept. "
        "Next: judge a round, or loop.py abandon.",
    )
    assert sb.state()["outcome"] == "open"


def test_accept_after_a_missing_score(sb):
    one_round(sb)
    sb.change("app.py", 6)
    assert sb.run("brief").code == 0
    assert sb.run("round").code == 3
    run = sb.run("accept", "--note", "the user accepts")
    assert (run.code, run.last) == (0, ACCEPTED_LINE)
    st = sb.state()
    assert (st["outcome"], len(st["rounds"]), st["pending"]) == ("accepted", 1, {})


@pytest.mark.parametrize("outcome", ["open", "stalled", "ask", "blocked"])
def test_abandon_from_an_unfinished_state(sb, outcome):
    one_round(sb)
    sb.set_state(outcome=outcome)
    run = sb.run("abandon", "--note", "the user stops")
    assert (run.code, run.last) == (0, loop.ABANDONED)
    assert sb.run("skip", "--reason", "nothing to judge after all").code == 0
    assert sb.run("start", "build").code == 0


NOT_FITTING = [
    ("diagnosed", ("--note", "x"), "open", FIX_BUILD[6:]),
    ("resume", ("--note", "x"), "open", FIX_BUILD[6:]),
    ("resume", ("--note", "x"), "stalled", "read the judge items and find the cause"),
    ("diagnosed", ("--note", "x"), "ask", "explain what holds"),
    (
        "accept",
        ("--note", "x"),
        "done",
        "loop.py leftovers, file each as an issue, then",
    ),
    ("abandon", ("--note", "x"), "budget", "loop.py leftovers, file each"),
]


@pytest.mark.parametrize("command, args, outcome, fits", NOT_FITTING)
def test_a_command_that_does_not_fit_the_state(sb, command, args, outcome, fits):
    one_round(sb)
    sb.set_state(outcome=outcome)
    run = sb.run(command, *args, "--kind", "build", "--name", NAME)
    assert run.code == 2
    assert run.last.startswith(
        f"Refused: the loop is {outcome}; {command} does not apply. Next: {fits}"
    ), run


# Fix order --------------------------------------------------------------------


def line_of(x, role="general", mark=""):
    return (
        f"  [{role} {x}] problem {x} | evidence: evidence {x} | fix: fix {x} | "
        f"check: check {x}{mark}"
    )


RAISED_AGAIN = (
    " (raised again after being settled: fix it only if the judge gives new evidence, "
    "else ask the user)"
)


def items_block(run):
    """The lines under 'Items to fix, in this order:', without the last line."""
    i = run.lines.index("Items to fix, in this order:")
    return run.lines[i + 1 : -1]


def two_rounds(sb, kind):
    """Round 1 raises C1; questions.md changes; round 2 raises B1, C1 and N1."""
    which = ("plan", "p1") if kind == "plan" else ("build", None)
    if kind == "plan":
        sb.start_plan()
    else:
        sb.start_build()
    assert sb.judge({"general": nine("C1")}, *which).code == 1
    (sb.loopdir(*which) / "questions.md").write_text("Q: which way?\nA: this way.\n")
    if kind == "build":
        sb.change("app.py", 5, tag="r2")
    return sb.judge({"general": nine("C1", "N1", blocking=["B1"])}, *which)


@pytest.mark.parametrize("kind", ["build", "plan"])
def test_the_fix_order(sb, kind):
    run = two_rounds(sb, kind)
    assert run.code == 1
    assert items_block(run) == [
        "  New answers: questions.md changed since round 1; read it first",
        line_of("B1"),
        line_of("C1"),
        line_of("N1"),
    ]
    fix = FIX_PLAN if kind == "plan" else FIX_BUILD
    assert run.last == "Fix: 3 items (1 blocking). " + fix
    assert run.out.count("Next:") == 1


@pytest.mark.parametrize(
    "kind, outcome, command",
    [
        ("plan", "ask", "resume"),
        ("build", "blocked", "resume"),
        ("build", "stalled", "diagnosed"),
    ],
)
def test_the_fix_list_again_after_a_stop(sb, kind, outcome, command):
    which = ("plan", "p1") if kind == "plan" else ("build", None)
    flags = ("--kind", "plan", "--name", "p1") if kind == "plan" else ()
    two_rounds(sb, kind)
    sb.set_state(*which, outcome=outcome)
    assert sb.run("settle", "general", "N1", "--note", "leave it", *flags).code == 0
    run = sb.run(command, "--note", "the user said go on", *flags)
    assert run.code == 0, run
    assert items_block(run) == [line_of("B1"), line_of("C1")]
    fix = FIX_PLAN if kind == "plan" else FIX_BUILD
    head = (
        "Open: the cause is recorded. "
        if command == "diagnosed"
        else "Open: the user's answer is recorded, 3 rounds left. "
    )
    assert run.last == head + fix
    st = sb.state(*which)
    assert (st["outcome"], st["streak"]) == ("open", 0)


@pytest.mark.parametrize(
    "command, outcome", [("resume", "ask"), ("diagnosed", "stalled")]
)
def test_nothing_open_after_a_stop(sb, command, outcome):
    one_round(sb)
    sb.set_state(outcome=outcome)
    assert sb.run("settle", "general", "I1", "--note", "fine as it is").code == 0
    run = sb.run(command, "--note", "go on")
    assert run.code == 0
    assert "Items to fix, in this order:" not in run.out
    assert run.last.endswith(". Next: loop.py brief.")


def test_a_blocked_round_shows_its_blocking_item(sb):
    run = play(sb, "build", 1, [9], blocking=True)
    assert (run.code, run.last) == (3, loop.BLOCKED)
    assert run.lines[1] == (
        "r1: average 9.0 | general 9 full | items: 2 open, 0 closed, 2 new | "
        "judge tokens: not given | fix tokens: not given"
    )
    assert run.lines[2] == "Averages: round 1 9.0"
    assert run.lines[3] == "Judges below 10: general 9"
    assert items_block(run) == [line_of("B1"), line_of("I1")]


# Read modes -------------------------------------------------------------------


def ten_and_nine(sb, kind):
    """Round 1: general gives a 10 and tests a 9, so the loop stays open."""
    sb.two_judges()
    which = ("plan", "p1") if kind == "plan" else ("build", None)
    if kind == "plan":
        sb.start_plan()
    else:
        sb.start_build()
    assert sb.judge({"general": 10, "tests": nine("T1")}, *which).code == 1
    return which


def test_a_build_round_reads_the_changes(sb):
    which = ten_and_nine(sb, "build")
    sb.change("later.py", 2, tag="later")
    run = sb.run("brief")
    assert run.code == 0, run
    assert sb.state(*which)["pending"]["modes"] == {
        "general": "changes",
        "tests": "changes",
    }
    for role in ("general", "tests"):
        delta = sb.stored(role, ext="delta.diff").read_text()
        assert "later.py" in delta
        assert "app.py" not in delta
        prompt = "\n".join(brief_of(run, role, 2)[1])
        assert f"r2_{role}.delta.diff" in prompt
        assert loop.START_FROM_LAST in prompt


def test_an_unchanged_plan_skips_its_ten(sb):
    which = ten_and_nine(sb, "plan")
    run = sb.run("brief", "--kind", "plan", "--name", "p1")
    assert run.code == 0, run
    assert "general: skipped, 10 in round 1, the work is unchanged" in run.lines
    assert "----- brief general r2 -----" not in run.lines
    assert sb.state(*which)["pending"]["modes"] == {
        "general": "skipped",
        "tests": "changes",
    }


def test_a_changed_plan_gets_a_delta(sb):
    which = ten_and_nine(sb, "plan")
    (sb.loopdir(*which) / "plan.md").write_text("# Plan\n\nstep one\nstep two\n")
    run = sb.run("brief", "--kind", "plan", "--name", "p1")
    assert run.code == 0, run
    delta = sb.stored("general", *which, ext="delta.diff").read_text()
    assert delta.startswith("--- plan.r1.md\n+++ plan.md\n")
    assert "+step two\n" in delta


def test_a_ten_outside_the_changed_area_is_skipped(sb):
    which = ten_and_nine(sb, "build")
    (sb.loopdir(*which) / "map.md").write_text("code | app.py | tests\n")
    sb.change("app.py", 4, tag="r2")
    run = sb.run("brief")
    assert run.code == 0, run
    assert "general: skipped, 10 in round 1, nothing in its area changed" in run.lines
    assert sb.save("tests", 10).code == 0
    run = sb.run("round")
    assert run.code == 1, run
    assert run.lines[-1] == (
        "Final round: every judge is at 10, 1 of them on earlier work. "
        "Next: loop.py brief; those judges read everything once."
    )
    assert sb.state()["final"] is True
    run = sb.run("brief")
    assert run.code == 0, run
    assert sb.state()["pending"]["modes"] == {"general": "full", "tests": "skipped"}
    assert "tests: skipped, 10 in round 2, the work is unchanged" in run.lines
    assert sb.save("general", 10).code == 0
    run = sb.run("round")
    assert run.code == 0, run
    assert sb.state()["outcome"] == "done"


# settle -----------------------------------------------------------------------


def settled_md(sb, kind="build", name=None):
    return (sb.loopdir(kind, name) / "settled.md").read_text()


def state_bytes(sb):
    return (sb.loopdir() / "state.json").read_bytes()


def test_settle_an_open_item(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1", "I2")}).code == 1
    run = sb.run("settle", "general", "I1", "--note", "keep it as it is")
    assert run.code == 0
    assert items_block(run) == [line_of("I2")]
    assert run.last == "Settled: general I1 (1 settled, 0 blocking). " + FIX_BUILD
    assert settled_md(sb) == (
        "- [general I1] raised in round 1: problem I1 | note: keep it as it is\n"
    )
    item = sb.state()["items"]["general:I1"]["settled"]
    assert (item["round"], item["user_ok"]) == (1, False)
    run = sb.run("settle", "general", "I2", "--note", "also fine")
    assert (
        run.last == "Settled: general I2 (2 settled, 0 blocking). Next: loop.py brief."
    )
    assert len(settled_md(sb).splitlines()) == 2
    assert sb.run("accept", "--note", "content").code == 0
    run = sb.run("leftovers")
    assert run.last == "Open: nothing left. Next: nothing to file."


def test_settle_a_plan_item(sb):
    sb.start_plan()
    assert sb.judge({"general": nine("I1", "I2")}, "plan", "p1").code == 1
    run = sb.run("settle", "general", "I1", "--note", "fine")
    assert run.last == "Settled: general I1 (1 settled, 0 blocking). " + FIX_PLAN


def test_settle_refuses_an_unknown_or_closed_id(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1")}).code == 1
    sb.change("app.py", 6)
    assert sb.judge({"general": nine("I2")}).code == 1
    before = state_bytes(sb)
    for item_id in ("I9", "I1"):
        run = sb.run("settle", "general", item_id, "--note", "x")
        assert (run.code, run.last) == (
            2,
            f"Refused: general {item_id} is not an open item. Next: loop.py status.",
        )
    assert state_bytes(sb) == before


def test_settle_a_blocking_item_needs_the_users_yes(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1", blocking=["B1"])}).code == 1
    before = state_bytes(sb)
    run = sb.run("settle", "general", "B1", "--note", "x")
    assert (run.code, run.last) == (
        3,
        "STOP: ask the user before settling a blocking item. "
        "Next: with their yes, the same command with --user-ok.",
    )
    assert state_bytes(sb) == before
    run = sb.run("settle", "general", "B1", "--note", "the user agrees", "--user-ok")
    assert run.code == 0
    assert run.last == "Settled: general B1 (1 settled, 1 blocking). " + FIX_BUILD
    assert sb.state()["items"]["general:B1"]["settled"]["user_ok"] is True


def test_a_settled_item_raised_again(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1", "I2")}).code == 1
    assert sb.run("settle", "general", "I1", "--note", "leave it").code == 0
    sb.change("app.py", 6)
    run = sb.judge({"general": nine("I1")})
    assert run.code == 1
    assert items_block(run) == [line_of("I1", mark=RAISED_AGAIN)]
    assert run.out.count("Next:") == 1
    assert run.last == "Fix: 1 item (0 blocking). " + FIX_BUILD
    assert sb.state()["items"]["general:I1"]["settled"]["raised_again"] == 2
    sb.change("app.py", 7)
    assert sb.run("brief").code == 0
    assert (
        settled_md(sb)
        .rstrip("\n")
        .endswith("| note: leave it | raised again in round 2")
    )
    run = sb.run("settle", "general", "I1", "--note", "still leave it")
    assert run.code == 0
    assert run.last.startswith("Settled: general I1 (1 settled, 0 blocking). Next: ")


def test_every_ten_with_a_settled_item_is_done(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1")}).code == 1
    assert sb.run("settle", "general", "I1", "--note", "fine").code == 0
    sb.change("app.py", 6)
    run = sb.judge({"general": 10})
    done = (
        "Done: 10 from every judge in 2 rounds, 1 settled (0 blocking). "
        "Next: the acceptance test."
    )
    assert (run.code, run.last) == (0, done)
    run = sb.run("status")
    assert (run.code, run.last) == (0, done)
    assert json.loads(sb.run("status", "--json").out)["settled"] == ["general:I1"]


# leftovers --------------------------------------------------------------------


def accepted_with_items(sb, b=("B1",), i=("I1",), problem=None):
    sb.start_build()
    blocking = [item(x) for x in b]
    improvements = [item(x) for x in i]
    if problem:
        for entry in blocking + improvements:
            entry.update(problem=problem, evidence=problem, fix=problem)
    data = json.dumps(
        {
            "overall": 9,
            "dimensions": {"fit": 9},
            "blocking": blocking,
            "improvements": improvements,
        }
    ).encode()
    assert sb.judge({"general": data}).code == 1
    assert sb.run("accept", "--note", "content").code == 0


def test_leftovers_lists_blocking_first(sb):
    accepted_with_items(sb)
    run = sb.run("leftovers")
    assert run.code == 0
    assert run.lines == [
        "Items left, blocking first:",
        line_of("B1"),
        line_of("I1"),
        "Open: 2 items left (1 blocking). Next: loop.py leftovers --dir, then file "
        "each body file as an issue.",
    ]


def test_leftovers_after_done(sb):
    sb.start_build()
    assert sb.judge({"general": result(10, improvements=["I1", "I2"])}).code == 0
    run = sb.run("leftovers")
    assert run.lines[1:] == [
        line_of("I1"),
        line_of("I2"),
        "Open: 2 items left (0 blocking). Next: loop.py leftovers --dir, then file "
        "each body file as an issue.",
    ]


def test_leftovers_with_nothing_left(sb):
    sb.start_build()
    assert sb.judge({"general": 10}).code == 0
    run = sb.run("leftovers")
    assert (run.code, run.lines) == (0, ["Open: nothing left. Next: nothing to file."])


def test_leftovers_on_an_unfinished_loop(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1", blocking=["B1"])}).code == 1
    run = sb.run("leftovers")
    assert (run.code, run.last) == (
        0,
        "Open: 2 items open (1 blocking), the loop is not finished. "
        "Next: loop.py status.",
    )


NASTY = "@someone ![x](http://example.invalid/p.png) ``` <img src=x>"


def test_leftovers_writes_body_files(sb):
    accepted_with_items(sb, problem=NASTY)
    run = sb.run("leftovers", "--dir")
    rel = sb.loopdir().relative_to(sb.root).as_posix()
    assert run.lines == [
        f"[general B1] {rel}/leftovers/general-B1.md",
        f"[general I1] {rel}/leftovers/general-I1.md",
        f"all items in one file: {rel}/leftovers/all.md",
        "Open: 2 items left (1 blocking). Next: file each as an issue.",
    ]
    folder = sb.loopdir() / "leftovers"
    for x in ("B1", "I1"):
        lines = (folder / f"general-{x}.md").read_text().splitlines()
        assert lines[0] == (
            "Raised by the general judge in round 1 of the judge loop; the text below "
            "is the judge's, unverified."
        )
        rest = [line for line in lines[1:] if line.strip()]
        assert rest and all(line.startswith("    ") for line in rest)
        assert any("@someone" in line for line in rest)
    lines = (folder / "all.md").read_text().splitlines()
    assert lines[0] == (
        "Raised by the judges of the judge loop; the text below is theirs, unverified."
    )
    assert lines[-2:] == ["- [ ] general B1", "- [ ] general I1"]
    rest = [line for line in lines[1:-2] if line.strip()]
    assert rest and all(line.startswith("    ") for line in rest)
    assert "    [general B1]" in rest


# skip -------------------------------------------------------------------------


def skipped(sha, files, lines):
    return (
        f"Skipped: {loop.short(sha)} ({files}, {lines}) is recorded as not judged. "
        "Next: the acceptance test."
    )


def ten_lines(n):
    return "".join(f"line {i}\n" for i in range(n))


SKIP_SIZES = [
    # name, {path: text}, exit
    ("one file of ten lines", {"app.py": ten_lines(10)}, 0),
    ("one file of eleven lines", {"app.py": ten_lines(11)}, 3),
    ("two files", {"a.py": "a\n", "b.py": "b\n"}, 3),
    (
        "three documentation files",
        {"a.md": ten_lines(40), "b.rst": "b\n", "c/d.adoc": "d\n"},
        0,
    ),
    ("an mdx file", {"site/page.mdx": ten_lines(30)}, 0),
    ("requirements.txt", {"requirements.txt": ten_lines(11)}, 3),
    ("an off line in CLAUDE.md", {"CLAUDE.md": "Judge loop: off\n"}, 3),
    ("claude.md", {"claude.md": "x\n"}, 3),
    ("SKILL.md", {"skills/x/SKILL.md": "x\n"}, 3),
    ("agents", {"agents/x.md": "x\n"}, 3),
    (".claude", {".claude/x.md": "x\n"}, 3),
    ("hooks readme", {"claude/hooks/README.md": "x\n"}, 3),
    ("deploy guide", {"docs/deploy/guide.md": "x\n"}, 3),
    ("install.sh", {"scripts/install.sh": "x\n"}, 3),
    (".mcp.json", {".mcp.json": "{}\n"}, 3),
]


@pytest.mark.parametrize(
    "files, code", [r[1:] for r in SKIP_SIZES], ids=[r[0] for r in SKIP_SIZES]
)
def test_the_skip_table(sb, files, code):
    for rel, text in files.items():
        sb.write(rel, text)
    head = sb.commit()
    run = sb.run("skip", "--reason", "small fix")
    assert run.code == code, run
    if code == 3:
        assert re.fullmatch(
            r"STOP: this change is \d+ files? and \d+ lines?(, .+)?\. "
            r"Next: ask the user before skipping the judge; "
            r"with their yes, the same command with --user-ok\.",
            run.last,
        ), run
        assert not (sb.loopdir() / "state.json").exists()
        run = sb.run("skip", "--reason", "small fix", "--user-ok")
        assert run.code == 0, run
    st = sb.state()
    assert (st["outcome"], st["commit"]) == ("skip", head)
    lines = sum(len(text.splitlines()) for text in files.values())
    assert st["skip"] == {
        "reason": "small fix",
        "files": len(files),
        "lines": lines,
        "user_ok": code == 3,
    }


def test_skip_names_the_cause(sb):
    sb.write("CLAUDE.md", "Judge loop: off\n")
    sb.commit()
    run = sb.run("skip", "--reason", "x")
    assert run.last.startswith(
        "STOP: this change is 1 file and 1 line, sensitive path CLAUDE.md."
    )


def test_skip_of_an_empty_diff(sb):
    run = sb.run("skip", "--reason", "nothing changed")
    assert (run.code, run.last) == (0, skipped(sb.head(), "0 files", "0 lines"))


def test_skip_stores_the_base(sb):
    sb.git("push", "-q", "origin", "main:develop")
    sb.git("fetch", "-q", "origin")
    sb.change("app.py", 2)
    run = sb.run("skip", "--reason", "x", "--base", "develop")
    assert run.code == 0, run
    st = sb.state()
    assert (st["base"], st["base_ref"], st["base_source"]) == (
        "develop",
        "refs/remotes/origin/develop",
        "--base",
    )


def test_skip_on_a_dirty_tree(sb):
    sb.change("app.py", 2)
    sb.write("app.py", "changed\n")
    run = sb.run("skip", "--reason", "x")
    assert (run.code, run.last) == (2, loop.DIRTY)


def test_skip_on_an_unfinished_loop(sb):
    one_round(sb)
    run = sb.run("skip", "--reason", "x")
    assert (run.code, run.last) == (
        2,
        "Refused: a judge loop is open on this branch. "
        "Next: finish it, or loop.py accept or abandon.",
    )


def test_skip_after_done(sb):
    sb.start_build()
    assert sb.judge({"general": 10}).code == 0
    run = sb.run("skip", "--reason", "x")
    assert (run.code, run.last) == (
        2,
        "Refused: this branch is already judged (done). Next: the acceptance test.",
    )
    sb.change("more.py", 1)
    assert sb.run("skip", "--reason", "x").code == 2
    sb.git("reset", "-q", "--hard", "HEAD~2")
    sb.change("app.py", 2, tag="other")
    run = sb.run("skip", "--reason", "rewritten")
    assert run.code == 0, run
    assert run.lines[0] == f"Earlier loop moved to docs/loops/{NAME}/build.1"
    assert run.last == skipped(sb.head(), "1 file", "2 lines")
    assert (
        json.loads((sb.loopdir().parent / "build.1" / "state.json").read_text())[
            "outcome"
        ]
        == "done"
    )


def test_skip_replaces_a_skip(sb):
    sb.change("app.py", 2)
    assert sb.run("skip", "--reason", "first").code == 0
    sb.change("app.py", 3)
    run = sb.run("skip", "--reason", "second")
    assert (run.code, run.last) == (0, skipped(sb.head(), "1 file", "3 lines"))
    assert sb.state()["skip"]["reason"] == "second"
    assert not (sb.loopdir().parent / "build.1").exists()


def test_skip_after_abandoned(sb):
    one_round(sb)
    assert sb.run("abandon", "--note", "stop").code == 0
    run = sb.run("skip", "--reason", "x")
    assert run.code == 0, run
    assert run.lines[0] == f"Earlier loop moved to docs/loops/{NAME}/build.1"
