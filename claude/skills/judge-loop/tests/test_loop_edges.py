"""Tests of loop.py: a reader of its output that goes away, what status counts
as saved, and the wording of notes and refusals."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from loop_fixtures import loop, nine, one_round, result, scored

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
        "$CLAUDE_HOME/CLAUDE.md is a folder where a file was expected: not used"
        in run.lines
    ), run
    assert sb.state()["outcome"] == "open"


# Panel order ---------------------------------------------------------------------


def test_status_lists_judges_in_panel_order(sb):
    sb.start_build("--panel", "full")
    run = sb.judge({role: scored(9) for role in loop.FULL_PANEL})
    assert run.code == 1, run
    sb.change("app.py", 5, tag="r2")
    run = sb.judge({role: scored(9) for role in loop.FULL_PANEL})
    assert run.code in (1, 3), run
    card = (sb.loopdir() / "scorecard.md").read_text().splitlines()
    shown = [line for line in sb.run("status").lines if line.startswith("r")]
    assert shown[:2] == card
    for line in card:
        judges = line.split(" | ")[1].split(", ")
        assert [j.split()[0] for j in judges] == list(loop.FULL_PANEL), line


# What status counts -------------------------------------------------------------


def test_an_answer_that_failed_save_is_not_counted_as_saved(sb):
    sb.two_judges()
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", 9).code == 0
    assert sb.save("tests", b"not json").code == 3
    run = sb.run("status")
    assert run.last.startswith(
        "Open: round 1 of 5, 1 of 2 results saved (missing: tests). Next: start each "
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
