"""Tests of the panels per round: the full panel in round 1 and in the final
round, three combined judges in the rounds between, one judge for a small change."""

from __future__ import annotations

import json

from loop_fixtures import brief_of, item, loop, result, scored

COMBINED = list(loop.COMBINED)
FINAL_LINE = (
    "Final round: every combined judge is at 10. Next: loop.py brief; the full "
    "panel reads everything once."
)


def full(score=9):
    return {role: scored(score) for role in loop.FULL_PANEL}


def combined(score=9, x="I1"):
    """Answers of the three combined judges, an item of the second role each."""
    if score == 10:
        return {judge: result(10) for judge in COMBINED}
    return {
        judge: result(9, improvements=[f"{judge.split('+')[1]}:{x}"])
        for judge in COMBINED
    }


def two_rounds(sb, second=9):
    """Round 1 by the full panel at 9, round 2 by the combined judges."""
    sb.start_build("--panel", "full")
    assert sb.judge(full()).code == 1
    sb.change("app.py", 5, tag="r2")
    return sb.judge(combined(second))


def starts(run):
    return [line for line in run.lines if line.startswith("Start: ")]


def test_round_one_runs_the_full_panel(sb):
    sb.start_build("--panel", "full")
    run = sb.run("brief")
    assert run.code == 0, run
    assert sb.state()["pending"]["panel"] == "full"
    assert sorted(sb.state()["pending"]["modes"]) == sorted(loop.FULL_PANEL)
    assert starts(run) == ["Start: kit-judge"] * 6
    assert f"Panel of round 1: full ({', '.join(loop.FULL_PANEL)})" in run.lines


def test_the_rounds_between_run_three_combined_judges_at_high_effort(sb):
    sb.start_build("--panel", "full")
    assert sb.judge(full()).code == 1
    sb.change("app.py", 5, tag="r2")
    (sb.loopdir() / "changes.md").write_text("- r1 [tests I1] fixed: done\n")
    run = sb.run("brief")
    assert run.code == 0, run
    pending = sb.state()["pending"]
    assert pending["panel"] == "combined"
    assert sorted(pending["modes"]) == sorted(COMBINED)
    assert starts(run) == ["Start: kit-judge, effort high"] * 3
    assert f"Panel of round 2: combined ({', '.join(COMBINED)})" in run.lines
    assert run.last.startswith("Open: round 2 of 5 briefed for 3 judges."), run
    _, prompt = brief_of(run, "correctness+tests", 2)
    text = "\n".join(prompt)
    assert (
        "You are the correctness+tests judge of round 2 of a build loop: one judge "
        "for two roles, correctness and tests." in prompt
    )
    assert "roles/correctness.md and " in text and text.count("roles/tests.md") == 1
    rel = "docs/loops/feat-1-x/build/judge"
    assert (
        f"The last counted results for your roles (round 1): {rel}/r1_correctness.json"
        f", {rel}/r1_tests.json" in prompt
    )
    assert loop.COMBINED_TEN in prompt and loop.COMBINED_IDS in prompt
    assert "The author's change log: docs/loops/feat-1-x/build/changes.md" in prompt
    assert f"The delta since round 1: {rel}/r2_correctness+tests.delta.diff" in prompt
    assert (sb.loopdir() / "judge" / "r2_correctness+tests.delta.diff").is_file()
    _, other = brief_of(run, "security+operations", 2)
    assert not any(line.startswith("The author's change log") for line in other)


def test_the_fallback_agents_also_run_combined_judges_at_high_effort(sb):
    sb.start_build("--panel", "full", "--agents", "fallback")
    assert sb.judge(full()).code == 1
    sb.change("app.py", 5, tag="r2")
    run = sb.run("brief")
    assert starts(run) == ["Start: general-purpose, model fable, effort high"] * 3


def test_a_one_role_judge_is_refused_in_a_combined_round(sb):
    sb.start_build("--panel", "full")
    assert sb.judge(full()).code == 1
    sb.change("app.py", 5, tag="r2")
    assert sb.run("brief").code == 0
    run = sb.save("tests", 9)
    assert (run.code, run.last) == (
        2,
        f"Refused: tests is not on the panel ({', '.join(COMBINED)}). "
        "Next: loop.py status.",
    ), run


def test_a_combined_judge_names_each_item_by_one_of_its_roles(sb):
    sb.start_build("--panel", "full")
    assert sb.judge(full()).code == 1
    sb.change("app.py", 5, tag="r2")
    assert sb.run("brief").code == 0
    for x in ("I2", "security:I2", "tests:i2"):
        run = sb.save("correctness+tests", result(9, improvements=[x]))
        assert run.code == 3, run
        assert f"correctness+tests (improvements[1].id: {loop.NOT_ROLE_ID})" in (
            run.last
        ), run
    data = result(9, improvements=["tests:I1"], still_open=["tests:I1"])
    assert sb.save("correctness+tests", data).code == 0
    data = result(9, improvements=["security:I1"], still_open=["tests:I1"])
    run = sb.save("security+operations", data)
    assert "(still_open[1]: not an open id)" in run.last, run


def test_combined_items_keep_the_one_role_keys(sb):
    run = two_rounds(sb)
    assert run.code == 1, run
    items = sb.state()["items"]
    assert items["tests:I1"]["open"] and items["tests:I1"]["judge"] == (
        "correctness+tests"
    )
    assert not items["correctness:I1"]["open"]
    assert (
        "  [tests I1] problem tests:I1 | evidence: evidence tests:I1 at app.py:1 "
        in ("\n".join(run.lines))
    )
    rnd = sb.state()["rounds"][-1]
    assert rnd["panel"] == "combined"
    assert sorted(rnd["scores"]) == sorted(COMBINED)


def test_all_combined_tens_lead_to_a_full_final_round(sb):
    run = two_rounds(sb, second=10)
    assert (run.code, run.last) == (1, FINAL_LINE), run
    st = sb.state()
    assert st["final"] and st["outcome"] == "open"
    assert json.loads(sb.run("status", "--json").out)["next"] == (
        "loop.py brief; the full panel reads everything once."
    )
    run = sb.run("brief")
    assert run.code == 0, run
    pending = sb.state()["pending"]
    assert pending["panel"] == "full"
    assert pending["modes"] == {role: "full" for role in loop.FULL_PANEL}
    _, prompt = brief_of(run, "tests", 3)
    rel = "docs/loops/feat-1-x/build/judge"
    assert (
        f"Your last counted result (round 2): {rel}/r2_correctness+tests.json" in prompt
    )
    assert loop.BARE_IDS.format(role="tests") in prompt
    assert loop.READ_TOUCHED in prompt
    for role in loop.FULL_PANEL:
        assert sb.save(role, 10).code == 0
    run = sb.run("round")
    assert run.code == 0, run
    assert sb.state()["outcome"] == "done"
    assert sb.state()["rounds"][-1]["panel"] == "full"


def test_a_final_round_below_ten_starts_another_combined_round(sb):
    two_rounds(sb, second=10)
    scores = {role: 10 for role in loop.FULL_PANEL}
    scores["tests"] = scored(9)
    run = sb.judge(scores)
    assert run.code == 1, run
    assert sb.state()["final"] is False
    assert sb.state()["streak"] == 0
    sb.change("app.py", 7, tag="r4")
    run = sb.run("brief")
    assert run.code == 0, run
    assert sb.state()["pending"]["panel"] == "combined"
    _, prompt = brief_of(run, "correctness+tests", 4)
    rel = "docs/loops/feat-1-x/build/judge"
    assert (
        f"The last counted results for your roles (round 3): {rel}/r3_correctness.json"
        f", {rel}/r3_tests.json" in prompt
    )


def test_an_item_kept_open_by_a_combined_ten_is_answered_by_its_own_judge(sb):
    sb.start_build("--panel", "full")
    assert sb.judge(full()).code == 1
    sb.change("app.py", 5, tag="r2")
    answers = combined(10)
    answers["correctness+tests"] = result(
        10, improvements=[item("tests:I3", needed_for_10=False)]
    )
    run = sb.judge(answers)
    assert (run.code, run.last) == (1, FINAL_LINE), run
    assert sb.state()["items"]["tests:I3"]["open"]
    assert sb.run("brief").code == 0
    data = result(10, improvements=[item("I3", needed_for_10=False)], still_open=["I3"])
    assert sb.save("tests", data).code == 0


def test_a_small_change_keeps_one_judge_every_round(sb):
    sb.start_build()
    assert sb.state()["panel"] == ["general"]
    assert sb.judge({"general": scored(9)}).code == 1
    sb.change("app.py", 5, tag="r2")
    run = sb.run("brief")
    assert starts(run) == ["Start: kit-judge"]
    assert not any(line.startswith("Panel of round") for line in run.lines)
    assert sb.save("general", scored(9)).code == 0
    assert sb.run("round").code == 1
    rounds = sb.state()["rounds"]
    assert [r["panel"] for r in rounds] == ["single", "single"]
    assert [list(r["scores"]) for r in rounds] == [["general"], ["general"]]
    card = (sb.loopdir() / "scorecard.md").read_text().splitlines()
    assert card[1].startswith("r2: average 9.0 (gain +0.00) | general 9 changes")


def test_the_scorecard_and_status_name_the_panel_of_each_round(sb):
    run = two_rounds(sb)
    assert run.lines[0].startswith("Round 2 of 5: average 9.0; correctness+tests 9 ")
    card = (sb.loopdir() / "scorecard.md").read_text().splitlines()
    assert card[0].startswith("r1 (full panel): average 9.0 | correctness 9 full")
    assert card[1].startswith(
        "r2 (combined panel): average 9.0 | correctness+tests 9 changes"
    )
    data = json.loads(sb.run("status", "--json").out)
    assert [r["panel"] for r in data["scores"]] == ["full", "combined"]
    assert data["next_panel"] == "combined"
    status = sb.run("status")
    assert status.last.startswith(
        f"Open: round 3 of 5, 0 of 3 results saved (missing: {', '.join(COMBINED)})."
    ), status
    sb.change("app.py", 7, tag="r3")
    assert sb.run("brief").code == 0
    shown = [line for line in sb.run("status").lines if line.startswith("Pending")]
    assert shown == [
        "Pending round 3 (combined panel): correctness+tests changes, "
        "security+operations changes, user-experience+scope changes"
    ]


def test_the_stall_count_compares_rounds_of_one_panel(sb):
    two_rounds(sb)
    assert sb.state()["streak"] == 0
    sb.change("app.py", 7, tag="r3")
    run = sb.judge(combined())
    assert run.code == 1, run
    assert sb.state()["streak"] == 1
    assert "(round before: 9.0)" in run.lines[0]
    card = (sb.loopdir() / "scorecard.md").read_text().splitlines()
    assert card[2].startswith("r3 (combined panel): average 9.0 (gain +0.00)")


def test_the_start_names_the_cost_of_the_panels(sb):
    run = sb.start_build("--panel", "full")
    assert (
        "Expected cost: 6 judge runs in round 1 and in the final round, 3 in each "
        "round between; at most 5 rounds and one final round after them, one fix "
        "pass between rounds" in run.lines
    ), run


def test_a_combined_panel_on_a_loop_of_one_judge_is_a_damaged_state(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    st = sb.state()
    st["pending"]["panel"] = "combined"
    sb.put_state(st)
    run = sb.run("status")
    assert run.code == 2 and "state.json" in run.last, run


def test_a_round_scored_by_judges_off_its_panel_is_a_damaged_state(sb):
    two_rounds(sb)
    st = sb.state()
    st["rounds"][1]["panel"] = "full"
    sb.put_state(st)
    run = sb.run("status")
    assert run.code == 2 and "state.json" in run.last, run
