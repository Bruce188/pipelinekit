"""The commands that act on a judged loop: the branch check, diagnosed, resume,
accept, abandon and settle, and what brief and round say while the user decides."""

import json

import pytest
from loop_fixtures import FIX_BUILD, NAME, loop, nine, one_round, plan_stage, play

WHICH = ("--kind", "build", "--name", NAME)
OTHER = "feat/9-other"


def elsewhere(other):
    return (
        f"Refused: this loop is for feat/1-x, {other} is checked out. "
        "Next: check out feat/1-x, or loop.py start build here."
    )


def judged_and_briefed(sb):
    """Round 1 judged with item I1 open, round 2 briefed and answered."""
    one_round(sb)
    sb.change("app.py", 5, tag="r1")
    assert sb.run("brief").code == 0
    sb.answer("general", nine("I1"))


def snapshot(folder):
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.is_file()
    }


# The branch check ---------------------------------------------------------------

ON_ANOTHER_BRANCH = [
    ("open", ("save", "general")),
    ("open", ("brief",)),
    ("open", ("round",)),
    ("stalled", ("diagnosed", "--note", "the cause")),
    ("ask", ("resume", "--note", "go on")),
    ("blocked", ("resume", "--note", "go on", "--rounds", "1")),
    ("ask", ("accept", "--note", "good enough")),
    ("ask", ("settle", "general", "I1", "--note", "not needed")),
]


@pytest.mark.parametrize(
    "outcome, argv",
    ON_ANOTHER_BRANCH,
    ids=[" ".join(a[:2]) for _, a in ON_ANOTHER_BRANCH],
)
def test_a_loop_command_on_another_branch_changes_nothing(sb, outcome, argv):
    judged_and_briefed(sb)
    sb.set_state(outcome=outcome)
    folder = sb.loopdir()
    before = snapshot(folder)
    sb.git("checkout", "-q", "-b", OTHER)
    run = sb.run(*argv, *WHICH)
    assert (run.code, run.last) == (2, elsewhere(OTHER)), run
    assert snapshot(folder) == before


def test_a_loop_command_on_a_detached_head(sb):
    judged_and_briefed(sb)
    folder = sb.loopdir()
    before = snapshot(folder)
    sb.git("checkout", "-q", "--detach")
    run = sb.run("round", *WHICH)
    assert (run.code, run.last) == (2, elsewhere("no branch")), run
    assert snapshot(folder) == before


def test_reading_and_abandoning_work_from_another_branch(sb):
    judged_and_briefed(sb)
    sb.set_state(outcome="ask")
    sb.git("checkout", "-q", "-b", OTHER)
    run = sb.run("status", *WHICH)
    assert run.code == 0, run
    assert run.lines[0].startswith("Loop: build feat-1-x"), run
    run = sb.run("abandon", "--note", "wrong branch", *WHICH)
    assert (run.code, run.last) == (0, loop.ABANDONED), run
    sb.git("checkout", "-q", "feat/1-x")
    assert sb.state()["outcome"] == "abandoned"


def test_status_json_names_the_loop_in_next_when_there_are_two(sb):
    plan_stage(sb)
    sb.start_build("--plan-loop", "p1")
    run = sb.run("status", "--json", *WHICH)
    assert run.code == 0, run
    assert json.loads(run.out)["next"] == "loop.py brief --kind build --name feat-1-x."
    run = sb.run("status", *WHICH)
    assert run.last.endswith(" Next: loop.py brief --kind build --name feat-1-x."), run


@pytest.mark.parametrize("flags, asked", [((), "no"), (("--user-ok",), "yes")])
def test_status_of_a_skip_gives_its_reason(sb, flags, asked):
    sb.change("c.py", 2)
    assert sb.run("skip", "--reason", "a typo\x1b[0m fix", *flags).code == 0
    run = sb.run("status")
    assert run.code == 0, run
    assert (
        f"Reason: {loop.clean('a typo' + chr(27) + '[0m fix')} (user asked: {asked})"
        in (run.lines)
    ), run
    assert "Outcome: skip" in run.lines, run
    assert not [line for line in run.lines if line.startswith(("Panel:", "Agents:"))]


# resume, diagnosed, accept, abandon -----------------------------------------------


@pytest.mark.parametrize("extra", [1, 5])
def test_resume_adds_rounds_to_a_spent_budget(sb, extra):
    run = play(sb, "build", 1, [9], blocking=True)
    assert run.last == loop.BLOCKED, run
    run = sb.run("resume", "--note", "two more", "--rounds", extra)
    assert run.code == 0, run
    assert run.last == (
        f"Open: the user's answer is recorded, {loop.count(extra, 'round')} left. "
        + FIX_BUILD
    )
    st = sb.state()
    assert (st["budget"], st["outcome"], st["streak"], st["final"]) == (
        1 + extra,
        "open",
        0,
        False,
    )
    sb.change("app.py", 7, tag="fix")
    run = sb.judge({"general": 10})
    assert run.lines[0].startswith(f"Round 2 of {1 + extra}: "), run


NOTE = "the\x1b[31m cause\x07 is\tfound"

NOTES = [
    ("stalled", ("diagnosed",), "diagnosed", "Open: the cause is recorded."),
    ("ask", ("resume",), "resume", "Open: the user's answer is recorded"),
    ("blocked", ("accept",), "accept", "Accepted: by the user in round 1"),
    ("open", ("abandon",), "abandon", "Abandoned: "),
]


@pytest.mark.parametrize(
    "outcome, argv, action, first", NOTES, ids=[n[2] for n in NOTES]
)
def test_each_decision_leaves_a_clean_note(sb, outcome, argv, action, first):
    one_round(sb)
    sb.set_state(outcome=outcome)
    run = sb.run(*argv, "--note", NOTE)
    assert run.code == 0, run
    assert run.last.startswith(first), run
    text = loop.clean(NOTE)
    assert text and all(ch.isprintable() for ch in text)
    assert sb.state()["notes"][-1] == {"round": 1, "action": action, "text": text}
    status = sb.run("status")
    assert f"note, round 1, {action}: {text}" in status.lines, status


SETTLE_NEXT = [
    ("open", "Next: loop.py brief."),
    (
        "ask",
        "Next: settle what else the decision closes, then loop.py resume --note "
        "(with --rounds N when no round is left).",
    ),
    (
        "blocked",
        "Next: settle what else the decision closes, then loop.py resume --note "
        "(with --rounds N when no round is left).",
    ),
    (
        "stalled",
        "Next: settle what else the decision closes, then loop.py diagnosed --note.",
    ),
]


@pytest.mark.parametrize("outcome, tail", SETTLE_NEXT, ids=[s[0] for s in SETTLE_NEXT])
def test_settle_names_the_next_step_for_each_outcome(sb, outcome, tail):
    one_round(sb)
    sb.set_state(outcome=outcome)
    run = sb.run("settle", "general", "I1", "--note", NOTE)
    assert run.code == 0, run
    assert run.last == f"Settled: general I1 (1 settled, 0 blocking). {tail}"
    text = loop.clean(NOTE)
    note = {"round": 1, "action": "settle", "text": f"general I1: {text}"}
    assert sb.state()["notes"][-1] == note


@pytest.mark.parametrize(
    "role, item_id, shown",
    [
        ("nobody", "I1", "nobody I1"),
        ("general", "I1;rm", "general that id"),
        ("x" * 300, "I1", "that role I1"),
        ("general", "I7", "general I7"),
    ],
    ids=["unknown role", "odd id", "long role", "no such item"],
)
def test_settle_of_an_item_that_is_not_open(sb, role, item_id, shown):
    one_round(sb)
    before = (sb.loopdir() / "state.json").read_bytes()
    run = sb.run("settle", role, item_id, "--note", "n")
    assert (run.code, run.last) == (
        2,
        f"Refused: {shown} is not an open item. Next: loop.py status.",
    ), run
    assert (sb.loopdir() / "state.json").read_bytes() == before


# brief and round while the user decides ---------------------------------------------

WAITS = [
    ("stalled", "brief", "STALLED_WAIT"),
    ("stalled", "round", "STALLED_WAIT"),
    ("ask", "brief", "USER_WAIT"),
    ("ask", "round", "USER_WAIT"),
    ("blocked", "brief", "USER_WAIT"),
    ("blocked", "round", "USER_WAIT"),
]


@pytest.mark.parametrize("outcome, command, line", WAITS)
def test_brief_and_round_wait_for_the_decision(sb, outcome, command, line):
    one_round(sb)
    sb.set_state(outcome=outcome)
    sb.change("app.py", 6, tag="more")
    folder = sb.loopdir()
    before = snapshot(folder)
    run = sb.run(command)
    assert (run.code, run.last) == (3, getattr(loop, line)), run
    assert snapshot(folder) == before


def test_a_base_ref_that_no_longer_resolves_keeps_the_base_before(sb):
    one_round(sb)
    base = sb.state()["rounds"][0]["base_sha"]
    sb.git("update-ref", "-d", "refs/remotes/origin/main")
    sb.change("app.py", 6, tag="more")
    run = sb.run("brief")
    assert run.code == 0, run
    assert (
        "refs/remotes/origin/main does not resolve: "
        "the base of the round before is kept"
    ) in run.lines, run
    assert sb.state()["pending"]["base_sha"] == base


def test_the_brief_of_a_build_names_its_plan(sb):
    plan_stage(sb)
    sb.start_build("--plan-loop", "p1")
    run = sb.run("brief")
    assert run.code == 0, run
    plans = [
        line for line in run.lines if line.startswith("The plan this build follows")
    ]
    assert plans and set(plans) == {
        "The plan this build follows: docs/loops/feat-1-x/build/plan.md"
    }, run


HELPS = [
    ((), "Exit codes: 0 done or go on"),
    (("accept",), "your own short summary of what the user said"),
    (("settle",), "only after the user said yes"),
    (("skip",), "only after the user said yes"),
    (("resume",), "1 to 5 more rounds"),
    (("start",), "the branch the work is compared with"),
    (("start",), "fallback: general-purpose agents"),
    (("brief",), "fallback: general-purpose agents"),
    (("settle",), "the item's id"),
]


@pytest.mark.parametrize("argv, words", HELPS)
def test_help_says_what_each_option_is(sb, argv, words):
    run = sb.command(*argv, "--help")
    assert run.code == 0
    assert words in " ".join(run.out.split())


def test_status_of_a_finished_loop_lists_items_left(sb):
    one_round(sb)
    assert "Items to fix, in this order:" in sb.run("status").lines
    assert sb.run("accept", "--note", "ship it").code == 0
    lines = sb.run("status").lines
    assert "Items left:" in lines
    assert "Items to fix, in this order:" not in lines
