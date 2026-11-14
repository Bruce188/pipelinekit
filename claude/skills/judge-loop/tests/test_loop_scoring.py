"""Tests of loop.py: what a judge read, the final round, the stall rule, the
scorecard and the token numbers."""

from __future__ import annotations

import json

import pytest
from loop_fixtures import item, loop, nine, one_round, result, scored

FOLDER = "docs/loops/feat-1-x/build"
FIVE = "correctness, security, operations, tests, scope"
TEN_NOT_FULL_STOP = (
    "STOP: not a score from general (overall: a 10 without a full read). Next: have "
    'that judge read the whole work, then answer again with "read": "full"; write it '
    "to {folder}/judge/in/r{n}_general.txt, loop.py save general."
)
NO_ITEM_STOP = (
    "STOP: not a score from general (overall: below 10 without an item). Next: have "
    "that judge name the item behind the score, or do the full read for a 10; write "
    "it to {folder}/judge/in/r{n}_general.txt, loop.py save general."
)
TOKENS_REFUSED = (
    "Refused: {flag} takes a whole number from 0 to 1000000000. "
    "Next: the same command with the number, or without the flag."
)


def meta(sb, n, role="general"):
    return json.loads(sb.stored(role, n=n, ext="meta").read_text())


def half(x):
    return result(9.5, improvements=[x])


# What a judge read ------------------------------------------------------------


def round_two_briefed(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1")}).code == 1
    sb.change("app.py", 5, tag="r2")
    assert sb.run("brief").code == 0
    assert sb.state()["pending"]["modes"] == {"general": "changes"}


def test_a_ten_on_a_changes_brief_needs_a_full_read(sb):
    round_two_briefed(sb)
    run = sb.save("general", result(10, read=None))
    assert (run.code, run.last) == (3, TEN_NOT_FULL_STOP.format(folder=FOLDER, n=2))
    assert meta(sb, 2)["mode"] == "changes"
    assert "read" not in meta(sb, 2)
    run = sb.save("general", result(10, read="changes"))
    assert run.code == 3
    assert run.last.startswith(
        "STOP: second miss from general (overall: a 10 without a full read)."
    )
    run = sb.save("general", result(10))
    assert run.code == 0, run
    assert (meta(sb, 2)["mode"], meta(sb, 2)["read"]) == ("changes", "full")
    assert sb.run("round").code == 0
    assert sb.state()["rounds"][1]["read"] == {"general": "full"}


def test_a_ten_on_a_full_brief_from_a_read_of_the_changes(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    run = sb.save("general", result(10, read="changes"))
    assert (run.code, run.last) == (3, TEN_NOT_FULL_STOP.format(folder=FOLDER, n=1))


def test_without_the_field_the_read_is_the_mode(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1")}).code == 1
    assert (meta(sb, 1)["mode"], meta(sb, 1)["read"]) == ("full", "full")
    assert sb.state()["rounds"][0]["read"] == {"general": "full"}
    sb.change("app.py", 5, tag="r2")
    assert sb.judge({"general": nine("I1")}).code == 1
    assert (meta(sb, 2)["mode"], meta(sb, 2)["read"]) == ("changes", "changes")
    assert sb.state()["rounds"][1]["read"] == {"general": "changes"}


def test_below_ten_without_an_item_names_its_own_next(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    run = sb.save("general", result(9, improvements=[item("I1", needed_for_10=False)]))
    assert (run.code, run.last) == (3, NO_ITEM_STOP.format(folder=FOLDER, n=1))


def test_save_of_a_skipped_role(sb):
    sb.two_judges()
    sb.start_plan()
    assert sb.judge({"general": 10, "tests": nine("T1")}, "plan", "p1").code == 1
    assert sb.run("brief").code == 0
    run = sb.save("general", 10, "plan", "p1")
    assert (run.code, run.last) == (
        2,
        "Refused: general is skipped in this round. "
        "Next: loop.py save tests, then loop.py round.",
    )


# The final round --------------------------------------------------------------


def test_a_final_round_with_a_judge_below_ten(sb):
    sb.two_judges(FIVE)
    sb.start_build()
    tens = {"correctness": 10, "security": 10, "operations": 10, "scope": 10}
    assert sb.judge({**tens, "tests": half("T1")}).code == 1
    assert sb.state()["rounds"][0]["average"] == pytest.approx(9.9)
    (sb.loopdir() / "map.md").write_text("code | app.py | tests\n")
    sb.change("app.py", 4, tag="r2")
    run = sb.judge({"tests": 10})
    assert (run.code, run.last) == (
        1,
        "Final round: every judge is at 10, 4 of them on earlier work. "
        "Next: loop.py brief; those judges read everything once.",
    )
    assert sb.state()["final"] is True
    run = sb.judge({**tens, "correctness": half("C1")})
    assert run.code == 1, run
    assert run.last.startswith("Fix: 1 item (0 blocking).")
    st = sb.state()
    assert st["rounds"][2]["modes"] == {
        **dict.fromkeys(tens, "full"),
        "tests": "skipped",
    }
    assert (st["outcome"], st["streak"], st["final"]) == ("open", 0, False)


@pytest.mark.parametrize(
    "command, outcome", [("diagnosed", "stalled"), ("resume", "ask")]
)
def test_the_way_back_clears_final_and_streak(sb, command, outcome):
    one_round(sb)
    sb.set_state(outcome=outcome, streak=2, final=True)
    assert sb.run(command, "--note", "go on").code == 0
    st = sb.state()
    assert (st["outcome"], st["streak"], st["final"]) == ("open", 0, False)
    sb.change("app.py", 9)
    assert sb.judge({"general": scored(9)}).code == 1
    assert sb.state()["streak"] == 1


# The stall rule ---------------------------------------------------------------


GAINS = [
    # sum times 2 before, now, judges, counts for the streak, gain
    (94, 96, 5, False, "+0.20"),
    (94, 97, 5, False, "+0.30"),
    (57, 58, 3, True, "+0.16"),
    (57, 58, 6, True, "+0.08"),
    (58, 57, 3, True, "-0.16"),
    (40, 39, 2, True, "-0.25"),
    (40, 40, 2, True, "+0.00"),
]


@pytest.mark.parametrize("before, now, judges, low, text", GAINS)
def test_the_gain_in_whole_numbers(before, now, judges, low, text):
    assert loop.low_gain(now, before, judges) is low
    assert loop.gain_text(now, before, judges) == text


def test_a_rise_of_a_sixth_counts_for_the_streak(sb):
    sb.two_judges("general, tests, scope")
    sb.start_build()
    assert (
        sb.judge({"general": half("G1"), "tests": half("T1"), "scope": half("S1")}).code
        == 1
    )
    sb.change("app.py", 5, tag="r2")
    run = sb.judge({"general": 10, "tests": half("T1"), "scope": half("S1")})
    assert run.code == 1, run
    assert run.lines[1].startswith("r2: average 9.7 (gain +0.16) | ")
    assert sb.state()["streak"] == 1


def test_a_rise_of_exactly_two_tenths_is_a_gain(sb):
    sb.two_judges(FIVE)
    sb.start_build()
    first = {r: half(r[0].upper() + "1") for r in FIVE.split(", ")}
    assert sb.judge({**first, "scope": nine("P1")}).code == 1
    sb.change("app.py", 5, tag="r2")
    run = sb.judge({**first, "scope": 10})
    assert run.code == 1, run
    assert run.lines[1].startswith("r2: average 9.6 (gain +0.20) | ")
    assert sb.state()["streak"] == 0


# The scorecard ----------------------------------------------------------------


def a_round(n, scores, modes, tokens, fix=None, items=(0, 0, 0)):
    rnd = {
        "n": n,
        "scores": scores,
        "average": sum(scores.values()) / len(scores),
        "modes": modes,
        "tokens": tokens,
        "items": dict(zip(("open", "closed", "new"), items, strict=True)),
    }
    if fix is not None:
        rnd["fix_tokens"] = fix
    return rnd


def test_scorecard_lines_alone():
    first = a_round(
        1,
        {"general": 9.5, "tests": 9.5, "scope": 9.5},
        dict.fromkeys(("general", "tests", "scope"), "full"),
        {"general": 100, "tests": 20, "scope": 3},
        items=(3, 0, 3),
    )
    later = {
        "scores": {"general": 10, "tests": 9.5, "scope": 10},
        "modes": {"general": "skipped", "tests": "changes", "scope": "changes"},
    }
    both = a_round(
        2, **later, tokens={"tests": 5, "scope": 6}, fix=900, items=(1, 2, 0)
    )
    some = a_round(2, **later, tokens={"tests": 5})
    none = a_round(2, **later, tokens={})
    both["read"] = {"tests": "changes", "scope": "full"}
    st = {"rounds": [first, both]}
    assert loop.scorecard_line(st, first) == (
        "r1: average 9.5 | general 9.5 full, tests 9.5 full, scope 9.5 full | items: 3 "
        "open, 0 closed, 3 new | judge tokens: 123 | fix tokens: not given"
    )
    assert loop.scorecard_line(st, both) == (
        "r2: average 9.8 (gain +0.33) | general 10 skipped, tests 9.5 changes, "
        "scope 10 changes, read full | items: 1 open, 2 closed, 0 new | judge "
        "tokens: 11 | "
        "fix tokens: 900"
    )
    assert loop.scorecard_line(st, some).endswith(
        "| judge tokens: 5 (1 of 2 judges) | fix tokens: not given"
    )
    assert loop.scorecard_line(st, none).endswith(
        "| judge tokens: not given | fix tokens: not given"
    )


def test_the_item_counts_of_a_round(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1", "I2")}).code == 1
    assert sb.run("settle", "general", "I2", "--note", "fine as it is").code == 0
    sb.change("app.py", 5, tag="r2")
    run = sb.judge({"general": nine("I3")})
    assert run.code == 1, run
    assert "| items: 1 open, 1 closed, 1 new |" in run.lines[1]
    assert sb.state()["rounds"][1]["items"] == {"open": 1, "closed": 1, "new": 1}


def test_the_token_numbers(sb):
    sb.start_build()
    assert sb.run("brief", "--fix-tokens", "1000000000").code == 0
    assert sb.state()["pending"]["fix_tokens"] == 10**9
    assert sb.run("brief", "--fix-tokens", "0").code == 0
    assert sb.run("brief").code == 0
    assert sb.state()["pending"]["fix_tokens"] == 0
    sb.answer("general", nine("I1"))
    assert sb.run("save", "general", "--tokens", "5").code == 0
    assert meta(sb, 1)["tokens"] == 5
    assert sb.run("save", "general").code == 0
    assert meta(sb, 1)["tokens"] == 5
    sb.answer("general", nine("I1") + b"\n")
    assert sb.run("save", "general").code == 0
    assert "tokens" not in meta(sb, 1)
    assert sb.run("save", "general", "--tokens", "1000000000").code == 0
    run = sb.run("round")
    assert run.code == 1, run
    rnd = sb.state()["rounds"][0]
    assert (rnd["tokens"], rnd["fix_tokens"]) == ({"general": 10**9}, 0)
    line = (
        "r1: average 9.0 | general 9 full | items: 1 open, 0 closed, 1 new | "
        "judge tokens: 1000000000 | fix tokens: 0"
    )
    assert run.lines[:2] == ["Round 1 of 5: average 9.0; general 9 full", line]
    assert (sb.loopdir() / "scorecard.md").read_text() == line + "\n"


def test_a_token_number_alone():
    for value in ("-1", "1000000001", "many", "1e3", "", "5 "):
        with pytest.raises(loop.Exit):
            loop.whole(value, "--tokens")
    assert loop.whole("0", "--tokens") == 0
    assert loop.whole("1000000000", "--tokens") == 10**9
    assert loop.whole(None, "--tokens") is None


@pytest.mark.parametrize("value", ["-1", "1000000001", "many"])
@pytest.mark.parametrize(
    "argv, flag",
    [
        (("save", "general", "--tokens"), "--tokens"),
        (("brief", "--fix-tokens"), "--fix-tokens"),
    ],
)
def test_a_token_flag_out_of_bounds(sb, argv, flag, value):
    sb.start_build()
    run = sb.run(*argv, value)
    assert (run.code, run.last) == (2, TOKENS_REFUSED.format(flag=flag))
    assert not sb.state()["pending"]


def test_status_shows_the_scorecard_and_the_pending_round(sb):
    one_round(sb)
    sb.change("app.py", 5, tag="r2")
    assert sb.run("brief").code == 0
    run = sb.run("status")
    assert run.code == 0, run
    assert (
        "r1: average 9.0 | general 9 full | items: 1 open, 0 closed, 1 new | "
        "judge tokens: not given | fix tokens: not given"
    ) in run.lines
    assert "Pending round 2: general changes" in run.lines
