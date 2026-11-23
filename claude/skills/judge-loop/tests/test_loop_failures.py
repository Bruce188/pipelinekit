"""Tests of loop.py: git that fails before a loop is found, writes that fail
half-way, role files that are missing and a plan copy that changed."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from loop_fixtures import (
    CANNOT_CHECK,
    LOOP_PY,
    NAME,
    ROLES_DIR,
    item,
    loop,
    nine,
    one_round,
    plan_stage,
    result,
)

FOLDER = f"docs/loops/{NAME}/build"
GIT_FAILED = (
    "Error: git rev-parse failed with code 128. "
    "Next: fix the repository, then the same command."
)


# git that fails at the start ------------------------------------------------------


def test_git_that_cannot_be_started(sb):
    sb.mp.setenv("PATH", str(sb.bin))
    run = sb.run("status")
    assert (run.code, run.last) == (
        2,
        "Error: git could not be started. "
        "Next: install git or fix PATH, then the same command.",
    )


def test_git_that_will_not_read_the_repository(sb):
    real = loop.loop_state.subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "rev-parse"] and "--show-toplevel" in cmd:
            said = b"fatal: detected dubious ownership in repository at '/x'\n"
            return loop.loop_state.subprocess.CompletedProcess(cmd, 128, b"", said)
        return real(cmd, *args, **kwargs)

    sb.mp.setattr(loop.loop_state.subprocess, "run", run)
    out = sb.run("status")
    assert out.code == 2, out
    assert out.lines[-2:] == [
        "  fatal: detected dubious ownership in repository at '/x'",
        GIT_FAILED,
    ]


def test_a_broken_git_file_is_not_called_no_repository(sb):
    folder = sb.tmp / "elsewhere"
    folder.mkdir()
    (folder / ".git").write_text("gitdir: /nonexistent/x\n")
    sb.mp.chdir(folder)
    sb.mp.setenv("GIT_CEILING_DIRECTORIES", str(sb.tmp))
    run = sb.run("status")
    assert run.code == 2, run
    # Git words this by version ("not a git repository" or "gitfile does not
    # point to a valid repository"); the helper passes it on as it is.
    assert run.lines[-2].startswith("  fatal: "), run
    assert run.last == GIT_FAILED


# Writes that fail half-way --------------------------------------------------------


def fail_once(sb, name):
    """The first write of a build-loop file of this name fails, as on a full disk."""
    real = loop.loop_state.write_atomic
    failed = []

    def write(path, data):
        here = Path(path)
        if here.name == name and here.parent.name == "build" and not failed:
            failed.append(path)
            raise OSError(28, "No space left on device")
        return real(path, data)

    sb.mp.setattr(loop.loop_state, "write_atomic", write)
    return failed


@pytest.mark.parametrize("name", ["plan.md", "criteria.md", "state.json"])
def test_a_start_from_a_plan_loop_that_cannot_write(sb, name):
    plan_stage(sb, "p1")
    sb.change()
    failed = fail_once(sb, name)
    run = sb.run("start", "build", "--plan-loop", "p1")
    assert run.code == 2, run
    assert failed
    for left in ("plan.md", "criteria.md", "state.json"):
        assert not (sb.loopdir() / left).exists(), left
    run = sb.run("start", "build", "--plan-loop", "p1")
    assert run.code == 0, run
    plan = (sb.loopdir("plan", "p1") / "plan.md").read_bytes()
    assert (sb.loopdir() / "plan.md").read_bytes() == plan


TOO_BIG = (
    "Error: the new {folder}/state.json would be {size:,} bytes, over the "
    "{limit:,} bytes loop.py reads back; the saved one is kept. Next: tell the "
    "user; {next}"
)
KEEP_ITEMS = (
    "loop.py abandon, then loop.py leftovers --dir to keep the open items (the "
    f"refused round's results stay in {FOLDER}/judge/), then move the folder "
    f"{FOLDER} away and loop.py start again."
)
COPY_ITEMS = (
    "loop.py status to copy the open items, then move the folder "
    f"{FOLDER} away and loop.py start again."
)


def files_of(folder):
    """Every file under the folder and its bytes."""
    return {
        str(p.relative_to(folder)): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def limit_state(sb, limit):
    sb.mp.setattr(loop.loop_state, "MAX_STATE", limit)


def second_round_saved(sb):
    """One counted round with item I1 open, then round 2 briefed and saved."""
    one_round(sb)
    sb.change("app.py", 4, tag="r1")
    assert sb.run("brief").code == 0
    assert sb.save("general", nine("I1")).code == 0


def test_a_state_of_exactly_the_limit_is_saved_and_one_byte_more_is_not(sb):
    second_round_saved(sb)
    folder = sb.loopdir()
    kept = sb.tmp / "kept"
    shutil.copytree(folder, kept)
    assert sb.run("round").code == 1
    size = (folder / "state.json").stat().st_size
    shutil.rmtree(folder)
    shutil.copytree(kept, folder)
    before = files_of(folder)
    limit_state(sb, size - 1)
    run = sb.run("round")
    assert (run.code, run.last) == (
        2,
        TOO_BIG.format(folder=FOLDER, size=size, limit=size - 1, next=KEEP_ITEMS),
    ), run
    assert files_of(folder) == before
    limit_state(sb, size)
    assert sb.run("round").code == 1
    assert (folder / "state.json").stat().st_size == size
    assert sb.run("status").code == 0


def test_a_settle_too_big_to_save_writes_nothing(sb):
    one_round(sb)
    folder = sb.loopdir()
    before = files_of(folder)
    limit_state(sb, len(before["state.json"]))
    run = sb.run("settle", "general", "I1", "--note", "not needed")
    assert run.code == 2, run
    assert run.last.endswith(f"Next: tell the user; {KEEP_ITEMS}"), run
    assert files_of(folder) == before


def test_a_brief_too_big_to_save_writes_nothing(sb):
    one_round(sb)
    sb.change("app.py", 4, tag="r1")
    folder = sb.loopdir()
    before = files_of(folder)
    limit_state(sb, len(before["state.json"]))
    run = sb.run("brief")
    assert run.code == 2, run
    assert run.last.endswith(f"Next: tell the user; {KEEP_ITEMS}"), run
    assert files_of(folder) == before


def test_a_rebrief_too_big_to_save_leaves_the_old_round_in_place(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", 9).code == 0
    sb.change("app.py", 4)
    folder = sb.loopdir()
    before = files_of(folder)
    limit_state(sb, len(before["state.json"]))
    run = sb.run("brief", "--fix-tokens", "1000")
    assert run.code == 2, run
    assert run.last.endswith(f"Next: tell the user; {KEEP_ITEMS}"), run
    assert not any(line.startswith("The work changed") for line in run.lines), run
    assert files_of(folder) == before
    assert not (folder / "judge" / "stale").exists()


def test_a_state_too_big_to_save_keeps_its_open_items(sb):
    second_round_saved(sb)
    state = sb.loopdir() / "state.json"
    before = state.read_bytes()
    limit_state(sb, len(before))
    run = sb.run("round")
    assert run.code == 2, run
    assert run.last.endswith(f"Next: tell the user; {KEEP_ITEMS}"), run
    assert state.read_bytes() == before
    assert sb.run("status").code == 0
    assert f" (the refused round's results stay in {FOLDER}/judge/), " in run.last
    assert (sb.loopdir() / "judge" / "r2_general.json").is_file()
    assert sb.run("abandon", "--note", "too big").code == 0
    run = sb.run("leftovers", "--dir")
    assert run.code == 0, run
    assert (sb.loopdir() / "leftovers" / "general-I1.md").is_file()
    assert (sb.loopdir() / "leftovers" / "all.md").is_file()
    assert (sb.loopdir() / "judge" / "r2_general.json").is_file()


def test_an_abandon_too_big_to_save_points_to_status(sb):
    one_round(sb)
    state = sb.loopdir() / "state.json"
    before = state.read_bytes()
    limit_state(sb, len(before))
    run = sb.run("abandon", "--note", "too big")
    assert run.code == 2, run
    assert run.last.startswith(f"Error: the new {FOLDER}/state.json would be "), run
    assert run.last.endswith(
        f" bytes, over the {len(before):,} bytes loop.py reads back; the saved one "
        f"is kept. Next: tell the user; {COPY_ITEMS}"
    ), run
    assert state.read_bytes() == before
    run = sb.run("status")
    assert run.code == 0, run
    assert any(line.startswith("  [general I1] ") for line in run.lines), run


def test_a_round_whose_scorecard_cannot_be_written_can_be_run_again(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", nine("I1")).code == 0
    fail_once(sb, "scorecard.md")
    run = sb.run("round")
    assert run.code == 2, run
    assert run.last.endswith(
        "Next: free space or fix the permissions, then the same command."
    ), run
    assert sb.rounds() == 0
    run = sb.run("round")
    assert run.code == 1, run
    assert run.last.startswith("Fix: 1 item (0 blocking)."), run
    assert sb.rounds() == 1
    assert (sb.loopdir() / "scorecard.md").is_file()


def test_round_after_a_counted_round_points_to_status(sb):
    one_round(sb)
    run = sb.run("round")
    assert (run.code, run.last) == (
        2,
        "Refused: no round is briefed. Next: loop.py status.",
    )


# A plan copy that changed ---------------------------------------------------------

PLAN_REFUSED = (
    f"Refused: {FOLDER}/plan.md is not the plan of plan loop p1. Next: tell the "
    f"user; loop.py abandon --kind build --name {NAME}, then loop.py start build "
    "--plan-loop p1."
)


@pytest.mark.parametrize("command", ["brief", "round"])
@pytest.mark.parametrize("spoil", ["edited", "deleted"])
def test_a_build_whose_plan_copy_changed_is_refused(sb, command, spoil):
    plan_stage(sb, "p1")
    sb.change()
    assert sb.run("start", "build", "--plan-loop", "p1").code == 0
    if command == "round":
        assert sb.run("brief").code == 0
        assert sb.save("general", nine("I1")).code == 0
    before = sb.state()
    path = sb.loopdir() / "plan.md"
    if spoil == "edited":
        path.write_text(path.read_text() + "more\n")
    else:
        path.unlink()
    run = sb.run(command)
    assert (run.code, run.last) == (2, PLAN_REFUSED), run
    assert sb.state() == before


# A role file that is missing ------------------------------------------------------

MODULES = ("loop_text", "loop_state", "loop_start", "loop_results", "loop_modes")
MODULES += ("loop_rounds", "loop_commands")
MISSING_ROLE = "Refused: roles/tests.md is not installed. Next: run /kit."


def without_role(sb, role):
    skill = sb.tmp / "skill"
    shutil.copytree(ROLES_DIR, skill / "roles")
    (skill / "roles" / f"{role}.md").unlink()
    for module in (loop, *(sys.modules.get(name) for name in MODULES)):
        if module is not None and hasattr(module, "skill_dir"):
            sb.mp.setattr(module, "skill_dir", lambda: skill)


def test_a_start_with_a_role_file_missing_is_refused(sb):
    without_role(sb, "tests")
    sb.change()
    run = sb.run("start", "build", "--panel", "full")
    assert (run.code, run.last) == (2, MISSING_ROLE), run
    assert not (sb.loopdir() / "state.json").exists()
    assert sb.run("start", "build", "--panel", "single").code == 0


def test_a_brief_with_a_role_file_missing_is_refused(sb):
    sb.start_build("--panel", "full")
    without_role(sb, "tests")
    run = sb.run("brief")
    assert (run.code, run.last) == (2, MISSING_ROLE), run
    assert sb.pending() == 0


# Empty answers --------------------------------------------------------------------

EMPTY = [
    ("stalled", ("diagnosed", "--note", " "), "the cause"),
    ("ask", ("resume", "--note", " "), "the user's answer"),
    ("ask", ("accept", "--note", " "), "the user's answer"),
    ("open", ("abandon", "--note", " "), "the user's answer"),
    ("open", ("settle", "general", "I1", "--note", " "), "the user's answer"),
]


@pytest.mark.parametrize(
    "outcome, argv, words", EMPTY, ids=[argv[0] for _, argv, _ in EMPTY]
)
def test_an_empty_note_is_refused(sb, outcome, argv, words):
    one_round(sb)
    sb.set_state(outcome=outcome)
    before = (sb.loopdir() / "state.json").read_bytes()
    run = sb.run(*argv)
    assert (run.code, run.last) == (
        2,
        f"Refused: --note is empty. Next: the same command with {words} in a few "
        "words.",
    ), run
    assert (sb.loopdir() / "state.json").read_bytes() == before


def test_an_empty_reason_is_refused(sb):
    sb.change()
    run = sb.run("skip", "--reason", " ")
    assert (run.code, run.last) == (
        2,
        "Refused: --reason is empty. Next: the same command with the reason in a few "
        "words.",
    ), run
    assert not (sb.loopdir() / "state.json").exists()


# Output that the terminal cannot show ---------------------------------------------


def test_round_and_status_on_an_ascii_terminal(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    arrow = item("I1", problem="a \u2192 b", fix="use \u2192 here")
    assert sb.save("general", result(9, improvements=[arrow])).code == 0
    sb.mp.setenv("PYTHONIOENCODING", "ascii")
    run = sb.command("round")
    assert run.code == 1, run
    assert "Traceback" not in run.err
    assert "\\u2192" in run.out
    run = sb.command("abandon", "--note", "na\u00efve \u2192 done")
    assert run.code == 0, run
    run = sb.command("status")
    assert run.code == 0, run
    assert "Traceback" not in run.err
    assert "na\\xefve \\u2192 done" in run.out


# A .gitignore that takes the loop folders back in ---------------------------------

BACK_IN = (
    "note: a .gitignore rule takes docs/loops/ back in; never stage it "
    "(git add with explicit paths only)."
)


@pytest.mark.parametrize("rules", ["!docs/loops/\n", "!docs/\n!docs/**\n"])
def test_a_gitignore_that_takes_the_loops_back_in(sb, rules):
    sb.write(".gitignore", rules)
    sb.commit("chore: ignore rules")
    run = sb.start_build()
    assert run.lines.count(BACK_IN) == 1, run
    exclude = sb.root / ".git" / "info" / "exclude"
    assert exclude.read_text().splitlines().count("docs/loops/") == 1
    run = sb.run("brief")
    assert run.code == 0, run
    assert run.lines.count(BACK_IN) <= 1, run
    assert exclude.read_text().splitlines().count("docs/loops/") == 1


def test_no_note_without_a_rule_that_takes_the_loops_back_in(sb):
    run = sb.start_build()
    assert BACK_IN not in run.lines, run


# Single paths ---------------------------------------------------------------------


def test_a_brief_with_uncommitted_work_is_refused(sb):
    sb.start_build()
    (sb.root / "app.py").write_text("not committed\n")
    run = sb.run("brief")
    assert (run.code, run.last) == (2, loop.DIRTY), run
    assert sb.pending() == 0


def test_status_json_without_a_loop(sb):
    run = sb.run("status", "--json")
    assert run.code == 0, run
    assert run.out.count("\n") == 1 and run.out.endswith("\n"), run
    assert json.loads(run.out) == {
        "outcome": "none",
        "next": "loop.py start plan --name <issue>-<slug> or loop.py start build.",
    }


def test_a_linked_state_without_o_nofollow(sb):
    sb.start_build()
    state = sb.loopdir() / "state.json"
    outside = sb.tmp / "outside.json"
    outside.write_bytes(state.read_bytes())
    state.unlink()
    state.symlink_to(outside)
    sb.mp.delattr(os, "O_NOFOLLOW")
    run = sb.run("status")
    assert (run.code, run.last) == (
        2,
        f"Error: {FOLDER}/state.json is tracked by git or reached through a link. "
        f"Next: move the folder {FOLDER} away, then loop.py start again.",
    ), run


CUT = b"\n----- the diff is cut here at 2 MB -----\n"


def test_cut_diff_keeps_a_body_at_the_limit():
    body = b"x" * loop.MAX_DIFF
    assert loop.cut_diff(body) == body
    assert loop.cut_diff(body + b"y") == body + CUT


def test_a_long_change_is_cut_in_the_delta(sb):
    sb.two_judges()
    sb.start_build()
    (sb.loopdir() / "map.md").write_text("code | app.py | tests\n")
    assert sb.judge({"general": 10, "tests": nine("T1")}).code == 1
    sb.change("app.py", 200, tag="r2")
    sb.mp.setattr(sys.modules["loop_modes"], "MAX_DIFF", 200)
    assert sb.run("brief").code == 0
    deltas = sorted((sb.loopdir() / "judge").glob("r2_*.delta.diff"))
    assert deltas
    for path in deltas:
        body = path.read_bytes().partition(b"\n\n")[2]
        assert body.startswith(b"diff --git"), path
        assert body.endswith(CUT) and len(body) == 200 + len(CUT), path


LONG = "x" * 400


def test_cut_fields_name_each_result_file_once(sb):
    sb.two_judges()
    sb.start_build()
    general = [item("I1", fix=LONG), item("I2", problem=LONG)]
    run = sb.judge(
        {
            "general": result(9, improvements=general),
            "tests": result(9, improvements=[item("T1", evidence=LONG)]),
        }
    )
    assert run.code == 1, run
    lines = [line for line in run.lines if "in full:" in line or "full text" in line]
    assert lines == [
        f"  [cut] fields in full: {FOLDER}/judge/r1_general.json",
        f"  [cut] fields in full: {FOLDER}/judge/r1_tests.json",
    ], run


def test_no_cut_line_without_a_cut_field(sb):
    one_round(sb)
    assert not [line for line in sb.run("status").lines if "in full:" in line]


MISSING_ARGUMENTS = [
    (("save",), "save", "role"),
    (("settle", "general"), "settle", "id, --note"),
    (("skip",), "skip", "--reason"),
]


@pytest.mark.parametrize(
    "argv, command, what", MISSING_ARGUMENTS, ids=[m[1] for m in MISSING_ARGUMENTS]
)
def test_a_missing_argument_is_named(sb, argv, command, what):
    run = sb.run(*argv)
    assert (run.code, run.last) == (
        2,
        f"Refused: loop.py {command} needs {what}. "
        f"Next: the same command with it; loop.py {command} --help.",
    ), run


def test_the_open_items_keep_their_order_within_a_judge():
    def open_item(first):
        return {"kind": "improvement", "first": first, "open": True, "settled": {}}

    st = {
        "panel": ["general", "tests"],
        "rounds": [{}, {}],
        "items": {
            "tests:T9": open_item(1),
            "tests:T2": open_item(2),
            "tests:T1": open_item(2),
            "general:I1": open_item(1),
        },
    }
    keys = [key for key, _ in loop.ordered_open(st)]
    assert keys == ["general:I1", "tests:T9", "tests:T1", "tests:T2"]


def test_a_brief_with_every_result_kept_names_round(sb):
    sb.two_judges()
    sb.start_build()
    assert sb.run("brief").code == 0
    for role, data in (("general", nine("I1")), ("tests", nine("T1"))):
        assert sb.save(role, data).code == 0
    stored = {role: sb.stored(role).read_bytes() for role in ("general", "tests")}
    run = sb.run("brief")
    budget = sb.state()["budget"]
    assert (run.code, run.last) == (
        0,
        f"Open: round 1 of {budget} is briefed already, 2 of 2 results kept "
        "(missing: none). Next: loop.py round.",
    ), run
    assert {role: sb.stored(role).read_bytes() for role in stored} == stored


# What comes next ------------------------------------------------------------------


def test_status_with_a_result_missing_names_brief(sb):
    sb.two_judges()
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", nine("I1")).code == 0
    want = (
        "loop.py brief prints the briefs of the missing judges again; start them, "
        "write each answer to its answer file, loop.py save <role>."
    )
    run = sb.run("status")
    assert run.last.endswith(f"Next: {want}"), run
    assert json.loads(sb.run("status", "--json").out)["next"] == want


@pytest.mark.parametrize("row, first", [("owner", True), ("fixed", False)])
def test_a_brief_that_waits_for_the_user_says_so_last(sb, row, first):
    sb.two_judges()
    sb.start_build()
    (sb.loopdir() / "map.md").write_text("code | app.py | tests\n")
    scores = {
        "general": result(10, improvements=[item("G1", needed_for_10=False)]),
        "tests": nine("T1"),
    }
    assert sb.judge(scores).code == 1
    (sb.loopdir() / "changes.md").write_text(
        f"- r1 [general G1] {row}: the user picks the name\n"
        "- r1 [tests T1] fixed: app.py checks the input\n"
    )
    sb.change("app.py", 4, tag="r2")
    run = sb.run("brief")
    assert run.code == 0, run
    lead = "ask the user first (the note above), then " if first else ""
    assert run.last.endswith(
        f"Next: {lead}start each judge, write its answer to its answer file, "
        "loop.py save <role>."
    ), run


def test_the_help_does_not_say_fix_for_every_exit_1(sb):
    run = sb.run("--help")
    assert run.code == 0, run
    words = " ".join(run.out.split())
    assert "1 another round is needed: fix first when the line says Fix" in words
    assert "1 fix, then another round" not in words
    doc = " ".join(LOOP_PY.read_text().split())
    assert "1 another round is needed: fix first when the line says Fix" in doc


def test_diagnosed_help_does_not_ask_for_the_users_words(sb):
    run = sb.run("diagnosed", "--help")
    assert run.code == 0, run
    words = " ".join(run.out.split())
    assert "the cause you found, in a few words" in words
    assert "what the user said" not in words


def test_the_schema_says_which_items_a_score_below_ten_needs():
    text = " ".join(loop.SCHEMA_TEXT.split())
    assert (
        "A score below 10 needs a blocking item or an improvement that is not marked "
        '"needed_for_10": false.'
    ) in text
    assert "A score below 10 needs an item." not in text


def test_leftovers_of_a_loop_on_another_branch_only_reads(sb):
    one_round(sb)
    folder = sb.loopdir()
    before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    sb.git("checkout", "-q", "-b", "feat/9-other")
    run = sb.run("leftovers", "--kind", "build", "--name", NAME)
    assert (run.code, run.last) == (
        0,
        "Open: 1 item open (0 blocking), the loop is not finished. "
        "Next: loop.py status.",
    ), run
    assert {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()} == before


# Numbers and names from the answer file -------------------------------------------


@pytest.mark.parametrize("again", [False, True], ids=["as stored", "saved again"])
def test_a_stored_token_count_below_zero_is_not_counted(sb, again):
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", nine("I1")).code == 0
    meta = sb.stored("general", ext="meta")
    data = json.loads(meta.read_text())
    data["tokens"] = -1
    meta.write_text(json.dumps(data))
    if again:
        assert sb.run("save", "general").code == 0
    assert sb.run("round").code == 1
    assert sb.run("status").code == 0
    assert "general" not in (sb.state()["rounds"][0].get("tokens") or {})


GENERAL_PURPOSE = (
    "STOP: this project has its own agent named general-purpose ({rel}). "
    "Next: ask the user: rename it."
)


@pytest.mark.parametrize(
    "rel, text",
    [
        (".claude/agents/general-purpose.md", "no front matter\n"),
        (".claude/agents/helper.md", "---\nname: General-Purpose\n---\n"),
    ],
    ids=["file name", "front matter"],
)
def test_fallback_agents_with_a_project_agent_named_general_purpose(sb, rel, text):
    sb.write(rel, text)
    sb.commit("chore: an agent")
    sb.change()
    run = sb.run("start", "build", "--agents", "fallback")
    assert (run.code, run.last) == (3, GENERAL_PURPOSE.format(rel=rel)), run
    assert not (sb.loopdir() / "state.json").exists()


UNCHECKED = "note: {rel} could not be checked for the name general-purpose"


UNREADABLE = ["a file", "a folder"]
NOT_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root reads mode 000")


def unreadable_agent(sb, how):
    """A project agent file, or a folder holding one, of mode 000. git ignores
    it: git status would read it and find it changed."""
    rel = ".claude/agents/helper.md" if how == "a file" else ".claude/agents/sub"
    exclude = sb.root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)
    with exclude.open("a") as fh:
        fh.write(rel + "\n")
    sb.write(rel if how == "a file" else f"{rel}/helper.md", "---\nname: helper\n---\n")
    sb.change()
    (sb.root / rel).chmod(0)
    return rel


@NOT_ROOT
@pytest.mark.parametrize("how", UNREADABLE)
def test_fallback_agents_pass_over_a_file_that_cannot_be_read(sb, how):
    rel = unreadable_agent(sb, how)
    try:
        run = sb.run("start", "build", "--agents", "fallback")
    finally:
        (sb.root / rel).chmod(0o755)
    assert run.code == 0, run
    assert run.lines.count(UNCHECKED.format(rel=rel)) == 1, run


@NOT_ROOT
@pytest.mark.parametrize("how", UNREADABLE)
def test_kit_agents_stop_at_a_file_that_cannot_be_read(sb, how):
    rel = unreadable_agent(sb, how)
    try:
        run = sb.run("start", "build")
    finally:
        (sb.root / rel).chmod(0o755)
    assert (run.code, run.last) == (3, CANNOT_CHECK.format(rel=rel)), run
    assert not (sb.loopdir() / "state.json").exists()


@pytest.mark.parametrize("mode", ["kit", "fallback"])
def test_an_agents_folder_that_cannot_be_looked_at(sb, mode):
    """lstat of .claude/agents fails with something other than not-found. A
    .claude folder of mode 000 stops earlier, at .claude/CLAUDE.md, so the
    failure is made here by hand."""
    sb.write(".claude/agents/helper.md", "---\nname: helper\n---\n")
    sb.change()
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if os.fspath(path).endswith(os.path.join(".claude", "agents")):
            raise PermissionError(13, "Permission denied", os.fspath(path))
        return real(path, *args, **kwargs)

    sb.mp.setattr(os, "lstat", lstat)
    run = sb.run(
        "start", "build", *(["--agents", "fallback"] if mode == "fallback" else [])
    )
    sb.mp.setattr(os, "lstat", real)
    if mode == "fallback":
        assert run.code == 0, run
        assert run.lines.count(UNCHECKED.format(rel=".claude/agents")) == 1, run
    else:
        assert (run.code, run.last) == (3, CANNOT_CHECK.format(rel=".claude/agents"))
        assert not (sb.loopdir() / "state.json").exists()


UNCHECKED_AGENTS = [
    "an unreadable name",
    "a link",
    "a linked folder",
    "a linked agents folder",
    "a file over 64 kB",
]


@pytest.mark.parametrize("how", UNCHECKED_AGENTS)
def test_fallback_agents_note_what_they_cannot_check(sb, how):
    agents = sb.root / ".claude" / "agents"
    outside = sb.tmp / "outside"
    outside.mkdir()
    (outside / "general-purpose.md").write_text("---\nname: general-purpose\n---\n")
    rel = ".claude/agents/x.md"
    if how == "an unreadable name":
        sb.write(rel, "---\n&a name: general-purpose\n---\n")
    elif how == "a link":
        agents.mkdir(parents=True)
        (sb.root / rel).symlink_to(outside / "general-purpose.md")
    elif how == "a linked folder":
        agents.mkdir(parents=True)
        (agents / "sub").symlink_to(outside)
        rel = ".claude/agents/sub"
    elif how == "a file over 64 kB":
        sb.write(rel, "x" * (64 * 1024 + 1))
    else:
        agents.parent.mkdir(parents=True)
        agents.symlink_to(outside)
        rel = ".claude/agents"
    sb.change()
    run = sb.run("start", "build", "--agents", "fallback")
    note = UNCHECKED.format(rel=rel)
    assert run.code == 0, run
    assert run.lines.count(note) == 1, run
    sb.criteria()
    run = sb.run("brief", "--agents", "fallback")
    assert run.code == 0, run
    assert run.lines.count(note) == 1, run
