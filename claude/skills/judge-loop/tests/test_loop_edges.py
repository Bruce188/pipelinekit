"""Tests of loop.py: a reader of its output that goes away, what status counts
as saved, and the wording of notes and refusals."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from loop_fixtures import (
    NAME,
    item,
    loop,
    nine,
    one_round,
    plan_stage,
    result,
    scored,
)

PATTERN = (
    "Refused: map.md line 2 has a pattern ({path}); paths are files or folders "
    "ending in /. Next: write each path as a file or a folder ending in /, then "
    "loop.py brief."
)


def closed_stdout(sb, *argv):
    """Run loop.py with its stdout closed before it writes; (code, stderr)."""
    proc = sb.spawn(*argv)
    proc.stdout.close()
    err = proc.stderr.read()
    proc.stderr.close()
    return proc.wait(timeout=120), err


# A closed output pipe ---------------------------------------------------------


def test_status_into_a_closed_pipe_is_quiet(sb):
    one_round(sb)
    code, err = closed_stdout(sb, "status")
    assert "Traceback" not in err and "Exception ignored" not in err, err
    assert err == ""
    assert code == 0


def test_brief_into_a_closed_pipe_still_finishes(sb):
    one_round(sb)
    sb.change("app.py", 5, tag="r2")
    code, err = closed_stdout(sb, "brief")
    assert err == ""
    assert code == 0
    assert sb.state()["pending"]["round"] == 2


def test_help_into_a_closed_pipe_is_quiet(sb):
    code, err = closed_stdout(sb, "--help")
    assert (code, err) == (0, "")


def test_status_with_stdout_closed_is_quiet(sb):
    one_round(sb)
    proc = subprocess.run(
        ["sh", "-c", 'exec "$@" >&-', "sh", sys.executable, str(sb.kit()), "status"],
        cwd=os.getcwd(),
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.stderr == "", proc.stderr
    assert proc.returncode == 0


# A folder where a file belongs -------------------------------------------------

FOLDER = (
    "Refused: {path} is a folder where a file was expected. "
    "Next: move or remove that folder, then the same command."
)


def rel(sb, path):
    return path.relative_to(sb.root).as_posix()


def test_an_answer_path_that_is_a_folder_is_named(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    path = sb.answer("general", b"x")
    path.unlink()
    path.mkdir()
    run = sb.run("save", "general")
    assert (run.code, run.last) == (2, FOLDER.format(path=rel(sb, path))), run
    assert "Traceback" not in run.out


def test_a_result_file_that_is_a_folder_is_named(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    path = sb.stored("general")
    path.mkdir(parents=True)
    run = sb.save("general", 9)
    assert (run.code, run.last) == (2, FOLDER.format(path=rel(sb, path))), run


def test_a_state_file_that_is_a_folder_is_named(sb):
    sb.start_build()
    path = sb.loopdir() / "state.json"
    path.unlink()
    path.mkdir()
    for command in ("status", "brief"):
        run = sb.run(command)
        assert (run.code, run.last) == (2, FOLDER.format(path=rel(sb, path))), run


def test_a_user_file_that_is_a_folder_is_a_notice(sb):
    (sb.claude_home / "CLAUDE.md").mkdir()
    sb.change()
    run = sb.run("start", "build")
    assert run.code == 0, run
    assert (
        "cannot read $CLAUDE_HOME/CLAUDE.md (a folder, not a file): not used"
        in run.lines
    ), run
    assert sb.state()["outcome"] == "open"


# Panel order ---------------------------------------------------------------------


def test_status_lists_judges_in_panel_order(sb):
    sb.start_build("--panel", "full")
    run = sb.judge({role: scored(9) for role in loop.FULL_PANEL})
    assert run.code == 1, run
    sb.change("app.py", 5, tag="r2")
    run = sb.judge({j: nine(f"{loop.covers(j)[1]}:I1") for j in loop.COMBINED})
    assert run.code in (1, 3), run
    card = (sb.loopdir() / "scorecard.md").read_text().splitlines()
    shown = [line for line in sb.run("status").lines if line.startswith("r")]
    assert shown[:2] == card
    for line, panel in zip(card, (loop.FULL_PANEL, loop.COMBINED), strict=True):
        judges = line.split(" | ")[1].split(", ")
        assert [j.split()[0] for j in judges] == list(panel), line


# What status counts -------------------------------------------------------------


def test_an_answer_that_failed_save_is_not_counted_as_saved(sb):
    sb.two_judges()
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", 9).code == 0
    assert sb.save("tests", b"not json").code == 3
    run = sb.run("status")
    assert run.last.startswith(
        "Open: round 1 of 5, 1 of 2 results saved (missing: tests). Next: loop.py "
        "brief prints the briefs of the missing judges again; "
    ), run
    data = json.loads(sb.run("status", "--json").out)
    assert (data["saved"], data["missing"]) == (["general"], ["tests"])


def test_saving_the_same_answer_again_keeps_its_tokens(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    sb.answer("general", nine("I1"))
    assert sb.run("save", "general", "--tokens", "5").code == 0
    assert sb.run("save", "general").code == 0
    meta = json.loads(sb.stored("general", ext="meta").read_text())
    assert meta["tokens"] == 5
    assert sb.run("round").code == 1
    assert sb.state()["rounds"][0]["tokens"] == {"general": 5}


# Wording ------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["web/**", "web/*.js", "a?.py", "[ab].py"])
def test_a_pattern_in_map_md_has_its_own_refusal(sb, path):
    sb.start_build()
    (sb.loopdir() / "map.md").write_text(f"# areas\nweb | app.py, {path} | tests\n")
    run = sb.run("brief")
    assert (run.code, run.last) == (2, PATTERN.format(path=path))
    assert not sb.state()["pending"]


def test_a_base_branch_that_does_not_exist_is_named(sb):
    sb.change()
    run = sb.run("start", "build", "--base", "nope")
    assert (run.code, run.last) == (
        2,
        "Refused: no base branch nope found. "
        "Next: the same command with --base <branch>.",
    )


@pytest.mark.parametrize(
    "outcome, words",
    [
        ("ask", "waiting for the user"),
        ("blocked", "waiting for the user on blocking items"),
    ],
)
def test_an_outcome_in_a_refusal_reads_as_english(sb, outcome, words):
    one_round(sb)
    sb.set_state(outcome=outcome)
    run = sb.run("diagnosed", "--note", "x")
    assert run.code == 2
    assert run.last.startswith(
        f"Refused: the loop is {words}; diagnosed does not apply. Next: "
    ), run


@pytest.mark.parametrize(
    "dimensions, field",
    [
        ({"fit": 10, "correctness": 12}, "dimensions.correctness"),
        ({"a b": 12}, "dimensions[1]"),
    ],
)
def test_a_dimension_error_names_the_dimension(sb, dimensions, field):
    sb.start_build()
    assert sb.run("brief").code == 0
    run = sb.save("general", result(9, improvements=["I1"], dimensions=dimensions))
    assert run.code == 3
    assert f"({field}: outside 0 to 10)" in run.last, run


def test_the_missing_row_note_shows_the_row_form_once(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1", "I2")}).code == 1
    sb.change("app.py", 5, tag="r2")
    run = sb.run("brief")
    assert run.code == 0, run
    assert run.lines[:2] == [
        "note: no changes.md row for [general I1] (a row reads: - r1 [general I1] "
        "fixed|answered|owner: <text>)",
        "note: no changes.md row for [general I2]",
    ]


def test_a_ten_with_an_unmarked_improvement_is_no_score(sb):
    text = " ".join(loop.SCHEMA_TEXT.split())
    assert "without the mark it counts as needed" not in text
    assert (
        "A 10 is refused for a read that is not full, a blocking item or an "
        'improvement that is not marked "needed_for_10": false.'
    ) in text
    sb.start_build()
    assert sb.run("brief").code == 0
    run = sb.save("general", result(10, improvements=[item("I1")]))
    assert (run.code, run.last) == (
        3,
        "STOP: not a score from general (overall: a 10 with open items). Next: have "
        "that judge mark each improvement it does not need for the 10 as "
        '"needed_for_10": false, or score below 10; write it to '
        "docs/loops/feat-1-x/build/judge/in/r1_general.txt, loop.py save general.",
    ), run
    marked = result(10, improvements=[item("I1", needed_for_10=False)])
    run = sb.save("general", marked)
    assert (run.code, run.last) == (
        0,
        "Saved: general scored 10 (0 blocking, 1 improvement). Next: loop.py round.",
    )


def test_a_ten_with_a_blocking_item_has_its_own_hint(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    run = sb.save("general", result(10, blocking=["B1"]))
    assert (run.code, run.last) == (
        3,
        "STOP: not a score from general (overall: a 10 with a blocking item). Next: "
        "have that judge score below 10, since a blocking item rules out a 10; write "
        "it to docs/loops/feat-1-x/build/judge/in/r1_general.txt, loop.py save "
        "general.",
    ), run


def test_evidence_without_a_place_says_the_form(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    vague = result(9, improvements=[item("I1", evidence="somewhere vague")])
    run = sb.save("general", vague)
    assert (run.code, run.last) == (
        3,
        "STOP: not a score from general (improvements[1].evidence: names no "
        "file:line or plan section). Next: have that judge give each item evidence "
        "that names a place: a file:line such as app.py:42, a plan section such as "
        "plan.md ## Steps, or a criterion such as criterion 2; write it to "
        "docs/loops/feat-1-x/build/judge/in/r1_general.txt, loop.py save general.",
    ), run
    assert sb.save("general", result(9)).code == 0


def test_every_option_has_help():
    top = loop.parser()
    subs = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    missing = [
        f"{name} {action.dest}"
        for name, sub in subs.choices.items()
        for action in sub._actions
        if not isinstance(action, argparse._HelpAction) and not action.help
    ]
    assert missing == []


def test_a_blank_reason_moves_no_folder(sb):
    one_round(sb)
    assert sb.run("abandon", "--note", "again").code == 0
    run = sb.run("skip", "--reason", " ", "--user-ok")
    assert run.code == 2, run
    assert run.last.startswith("Refused: --reason is empty."), run
    assert not (sb.loopdir().parent / "build.1").exists()
    assert sb.state()["outcome"] == "abandoned"


# Next lines with two loop folders ------------------------------------------------


def test_save_with_two_loops_names_the_loop_in_each_save(sb):
    plan_stage(sb)
    sb.two_judges()
    sb.start_build()
    assert sb.run("brief").code == 0
    sb.answer("general", nine("I1"))
    run = sb.run("save", "general")
    assert run.code == 0, run
    which = f"--kind build --name {NAME}"
    assert run.last.endswith(
        f"Next: loop.py save {which} tests, then loop.py round {which}."
    ), run


def test_save_of_a_skipped_role_with_two_loops_names_the_loop(sb):
    plan_stage(sb, "p0")
    sb.two_judges()
    sb.start_plan()
    assert sb.judge({"general": 10, "tests": nine("T1")}, "plan", "p1").code == 1
    flags = ("--kind", "plan", "--name", "p1")
    assert sb.run("settle", "tests", "T1", "--note", "fine as it is", *flags).code == 0
    assert sb.run("brief").code == 0
    run = sb.save("general", 10, "plan", "p1")
    which = "--kind plan --name p1"
    assert (run.code, run.last) == (
        2,
        "Refused: general is skipped in this round. "
        f"Next: loop.py save {which} tests, then loop.py round {which}.",
    )


# Fallback agents -------------------------------------------------------------------

FALLBACK_FIX = (
    "Next: have a general-purpose agent fix these items and commit, then loop.py brief."
)


def test_a_fallback_build_loop_names_no_kit_agent(sb):
    sb.start_build("--agents", "fallback")
    run = sb.judge({"general": nine("I1")})
    assert run.code == 1, run
    assert run.last.endswith(FALLBACK_FIX), run
    assert "kit-builder" not in sb.run("status").last


def test_a_fallback_plan_loop_names_no_kit_agent(sb):
    run = sb.run("start", "plan", "--name", "p1", "--agents", "fallback")
    assert run.code == 0, run
    assert run.last.endswith(
        "Next: write criteria.md, have a general-purpose agent write plan.md, then "
        "loop.py brief."
    ), run
    sb.criteria("plan", "p1")
    run = sb.run("brief")
    assert run.code == 2 and "kit-planner" not in run.last, run
    (sb.loopdir("plan", "p1") / "plan.md").write_text("# Plan\n\nstep one\n")
    run = sb.judge({"general": nine("I1")}, "plan", "p1")
    assert run.code == 1 and "kit-planner" not in run.last, run
    (sb.loopdir("plan", "p1") / "plan.md").write_text(
        "# Plan" + chr(10) + "step two" + chr(10)
    )
    run = sb.judge({"general": 10}, "plan", "p1")
    assert run.code == 0, run
    assert "have a general-purpose agent build" in run.last, run
    assert "kit-builder" not in run.last


# Carried items ---------------------------------------------------------------------


def test_a_skipped_judges_item_is_listed_as_carried():
    def open_item(kind, first):
        return {"kind": kind, "first": first, "open": True, "settled": {}}

    st = {
        "panel": ["general", "tests"],
        "rounds": [{}, {}],
        "items": {
            "tests:T2": open_item("improvement", 2),
            "general:I1": open_item("improvement", 1),
            "tests:B1": open_item("blocking", 2),
        },
    }
    keys = [key for key, _ in loop.ordered_open(st)]
    assert keys == ["tests:B1", "general:I1", "tests:T2"]
    doc = " ".join(loop.ordered_open.__doc__.split())
    assert "an item of a skipped judge carries over unchanged" in doc


# A closed stderr -------------------------------------------------------------------


def damaged_plan_and_a_build(sb):
    plan_stage(sb)
    (sb.loopdir("plan", "p1") / "state.json").write_text("{")
    sb.start_build()


def test_a_notice_with_stderr_closed_keeps_the_json(sb):
    damaged_plan_and_a_build(sb)
    proc = subprocess.run(
        [
            "sh",
            "-c",
            'exec "$@" 2>&-',
            "sh",
            sys.executable,
            str(sb.kit()),
            "status",
            "--json",
        ],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120,
    )
    assert json.loads(proc.stdout)["name"] == NAME, proc.stdout
    assert proc.returncode == 0


def test_a_notice_into_a_closed_stderr_pipe_keeps_the_json(sb):
    damaged_plan_and_a_build(sb)
    proc = sb.spawn("status", "--json")
    proc.stderr.close()
    out = proc.stdout.read()
    proc.stdout.close()
    assert proc.wait(timeout=120) == 0
    assert "Traceback" not in out
    assert json.loads(out)["name"] == NAME, out


# The exclude line ------------------------------------------------------------------


def test_the_exclude_line_is_added_when_another_rule_ignores_the_folder(sb):
    ignore = sb.tmp / "ignore"
    ignore.write_text("docs/loops/\n")
    (sb.tmp / "gitconfig").write_text(f"[core]\n\texcludesFile = {ignore}\n")
    sb.start_build()
    path = Path(sb.git("rev-parse", "--git-path", "info/exclude"))
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    assert path.read_text().splitlines().count("docs/loops/") == 1
    assert sb.run("abandon", "--note", "again").code == 0
    sb.change("app.py", 5)
    assert sb.run("start", "build").code == 0
    assert path.read_text().splitlines().count("docs/loops/") == 1


# A build that follows a plan loop -------------------------------------------------


def test_a_build_from_a_plan_loop_is_named_after_its_branch(sb):
    plan_stage(sb)
    sb.start_build("--plan-loop", "p1")
    assert sb.state()["plan_loop"]["name"] == "p1"
    assert (sb.loopdir() / "plan.md").is_file()
    assert not sb.loopdir("build", "p1").exists()
    data = json.loads(sb.run("status", "--json", "--kind", "build").out)
    assert (data["kind"], data["name"]) == ("build", "feat-1-x")


def test_skip_sees_the_open_build_of_a_plan_loop(sb):
    plan_stage(sb)
    sb.start_build("--plan-loop", "p1")
    run = sb.run("skip", "--reason", "small", "--user-ok")
    assert (run.code, run.last) == (
        2,
        "Refused: a judge loop is open on this branch. "
        "Next: finish it, or loop.py accept or abandon.",
    )


def test_a_loop_started_again_with_the_plan_loop_stays_with_its_branch(sb):
    sb.start_build()
    assert sb.run("abandon", "--note", "forgot the plan loop").code == 0
    plan_stage(sb)
    sb.change("app.py", 5)
    run = sb.run("start", "build", "--plan-loop", "p1")
    assert run.code == 0, run
    assert "Earlier loop moved to docs/loops/feat-1-x/build.1" in run.lines
    run = sb.run("skip", "--reason", "small", "--user-ok")
    assert (run.code, run.last.split(" Next:")[0]) == (
        2,
        "Refused: a judge loop is open on this branch.",
    )
    run = sb.run("start", "build")
    assert run.code == 2
    assert run.last.startswith("Refused: this loop is not finished")


@pytest.mark.parametrize("first_done", [True, False], ids=["done", "open"])
def test_two_branches_build_from_one_plan_loop(sb, first_done):
    plan_stage(sb)
    sb.start_build("--plan-loop", "p1")
    if first_done:
        assert sb.judge({"general": 10}).code == 0
    sb.git("checkout", "-q", "-b", "feat/2-y")
    run = sb.start_build("--plan-loop", "p1")
    assert "accept or abandon" not in run.out
    assert sb.state()["plan_loop"]["name"] == "p1"
    first = sb.state("build", "feat-1-x")
    assert first["outcome"] == ("done" if first_done else "open")
    assert not list((sb.root / "docs" / "loops").glob("*/build.*"))
    data = json.loads(sb.run("status", "--json").out)
    assert data["name"] == "feat-2-y"
    sb.git("checkout", "-q", "feat/1-x")
    data = json.loads(sb.run("status", "--json").out)
    times = [
        os.lstat(sb.loopdir(*where) / "state.json").st_mtime_ns
        for where in (("plan", "p1"), ("build", "feat-1-x"))
    ]
    assert (data["name"], data["outcome"]) == ("feat-1-x", first["outcome"]), (
        f"status named {data['name']}; state.json mtime_ns: plan p1 {times[0]}, "
        f"build feat-1-x {times[1]}"
    )
    run = sb.run("skip", "--reason", "small", "--user-ok")
    assert run.code == 2
    if first_done:
        assert run.last.startswith("Refused: this branch is already judged (")
    else:
        assert run.last.startswith("Refused: a judge loop is open on this branch.")


def test_status_on_a_judged_branch_names_its_build_loop(sb):
    plan_stage(sb)
    sb.start_build("--plan-loop", "p1")
    assert sb.judge({"general": 10}).code == 0
    later = (sb.loopdir() / "state.json").stat().st_mtime + 3600
    os.utime(sb.loopdir("plan", "p1") / "state.json", (later, later))
    run = sb.run("status")
    assert run.lines[0] == "Loop: build feat-1-x in docs/loops/feat-1-x/build/"
    data = json.loads(sb.run("status", "--json").out)
    assert (data["kind"], data["name"], data["outcome"]) == (
        "build",
        "feat-1-x",
        "done",
    )
    data = json.loads(sb.run("status", "--json", "--kind", "plan").out)
    assert (data["kind"], data["name"]) == ("plan", "p1")
