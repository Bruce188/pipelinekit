"""Tests of loop.py: the areas of map.md, skipped judges, the change log, the
sentences of a brief, the size limit and the layout of the modules."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from loop_fixtures import LOOP_PY, brief_of, loop, nine, one_round, result

FOLDER = "docs/loops/feat-1-x/build"
SKILL = LOOP_PY.parent
MAP_LINE = (
    "Refused: map.md line {n} is not an area line. "
    "Next: write it as name | paths | roles, then loop.py brief."
)
WAIT_ONE = (
    "note: 1 item waits for the user. Ask in one batch and record the answers "
    "(questions.md, loop.py settle) before the judges run."
)


def write_map(sb, text, kind="build", name=None):
    (sb.loopdir(kind, name) / "map.md").write_text(text)


def modes(sb, kind="build", name=None):
    return sb.state(kind, name)["pending"]["modes"]


def ten_and_nine(sb, area="code | app.py | tests\n"):
    sb.two_judges()
    sb.start_build()
    if area:
        write_map(sb, area)
    assert sb.judge({"general": 10, "tests": nine("T1")}).code == 1


# Areas ------------------------------------------------------------------------


def test_an_area_covers_a_folder_or_a_file():
    areas = [
        ([loop.area_path("claude/hooks/")], {"security"}),
        ([loop.area_path("app.py")], {"tests"}),
    ]
    assert loop.roles_of("claude/hooks/x.py", areas) == {"security"}
    assert loop.roles_of("claude/hooks/sub/y.py", areas) == {"security"}
    assert loop.roles_of("claude/hooksx.py", areas) == set(loop.ROLES)
    assert loop.roles_of("app.py", areas) == {"tests"}
    assert loop.roles_of("app.py.bak", areas) == set(loop.ROLES)
    assert loop.roles_of("app.py", None) == set(loop.ROLES)


def test_lines_of_map_md_that_are_read_or_ignored(sb):
    sb.start_build()
    write_map(
        sb,
        "# areas\n\n a | b , c/ | general \nno bars here\none | bar\n"
        "three | bars | x | y\n  # c | d | e\nhooks | claude/hooks/ | all\r\n"
        f"long | {'p' * 120} | tests, scope\n",
    )
    run = sb.run("brief")
    assert run.code == 0, run


BAD_LINES = {
    "a double slash": "a | b// | all",
    "an empty path": "a | | all",
    "an empty path entry": "a | b, | all",
    "an empty name": " | b | all",
    "an unknown role": "a | b | nobody",
    "an empty role entry": "a | b | general,",
    "a path over 120 characters": f"a | {'p' * 121} | all",
    "a path out of the repository": "a | ../b | all",
    "an absolute path": "a | /etc/x | all",
}


@pytest.mark.parametrize("line", BAD_LINES.values(), ids=BAD_LINES.keys())
def test_a_line_of_map_md_that_is_not_an_area(sb, line):
    sb.start_build()
    write_map(sb, f"# areas\n{line}\n")
    run = sb.run("brief")
    assert (run.code, run.last) == (2, MAP_LINE.format(n=2))
    assert not sb.state()["pending"]


@pytest.mark.parametrize("role, code", [("security", 0), ("secutiry", 2)])
def test_an_area_of_a_role_that_is_not_on_the_panel(sb, role, code):
    one_round(sb)
    write_map(sb, f"hooks | claude/hooks/ | {role}\n")
    sb.change("app.py", 5, tag="r2")
    run = sb.run("brief")
    assert run.code == code, run
    if code:
        assert run.last == MAP_LINE.format(n=1)


@pytest.mark.parametrize("sub", ["map.md", "changes.md"])
@pytest.mark.parametrize("extra, code", [(0, 0), (1, 2)])
def test_an_area_file_at_the_size_limit(sb, sub, extra, code):
    sb.start_build()
    (sb.loopdir() / sub).write_text("#" * (loop.MAX_AREA_FILE + extra - 1) + "\n")
    run = sb.run("brief")
    assert run.code == code, run
    if code:
        assert run.last == (
            f"Refused: {FOLDER}/{sub} is not a plain file of at most 200 kB. "
            "Next: shorten it, then loop.py brief."
        )
        assert not sb.state()["pending"]


# Skipped judges ---------------------------------------------------------------


def test_no_skip_by_area_in_the_last_round_of_the_budget(sb):
    sb.two_judges()
    sb.start_build()
    sb.set_state(budget=3)
    write_map(sb, "code | app.py | tests\n")
    assert sb.judge({"general": 10, "tests": nine("T1")}).code == 1
    sb.change("app.py", 4, tag="r2")
    assert sb.judge({"tests": nine("T1")}).code == 1
    rnd = sb.state()["rounds"][1]
    assert rnd["modes"] == {"general": "skipped", "tests": "changes"}
    assert rnd["skipped"] == {"general": 1}
    sb.change("app.py", 5, tag="r3")
    assert sb.run("brief").code == 0
    assert modes(sb) == {"general": "changes", "tests": "changes"}


def test_no_skip_by_area_after_the_base_moved(sb):
    ten_and_nine(sb, "code | app.py, base.txt | tests\n")
    sb.on_base("base.txt", "on the base\n")
    sb.git("merge", "-q", "--no-edit", "origin/main")
    run = sb.run("brief")
    assert run.code == 0, run
    assert modes(sb) == {"general": "full", "tests": "full"}


def test_no_skip_by_area_in_a_plan_loop(sb):
    sb.two_judges()
    sb.start_plan()
    write_map(sb, "code | other.md | tests\n", "plan", "p1")
    assert sb.judge({"general": 10, "tests": nine("T1")}, "plan", "p1").code == 1
    (sb.loopdir("plan", "p1") / "plan.md").write_text("# Plan\n\nstep one\nstep two\n")
    assert sb.run("brief").code == 0
    assert modes(sb, "plan", "p1") == {"general": "changes", "tests": "changes"}


def test_the_guard_when_every_judge_is_skipped(sb):
    ten_and_nine(sb, None)
    st = sb.state()
    rnd = st["rounds"][0]
    rnd["scores"]["tests"] = 10
    rnd["average"] = 10.0
    sb.put_state(st)
    run = sb.run("brief")
    assert (run.code, run.last) == (
        2,
        "Refused: no judge has anything to read. "
        "Next: tell the user; loop.py abandon, then loop.py start again.",
    )


def test_a_second_brief_keeps_the_modes(sb):
    ten_and_nine(sb, None)
    sb.change("app.py", 4, tag="r2")
    assert sb.run("brief").code == 0
    assert modes(sb) == {"general": "changes", "tests": "changes"}
    assert sb.save("general", 10).code == 0
    write_map(sb, "code | app.py | tests\n")
    run = sb.run("brief")
    assert run.code == 0, run
    assert modes(sb) == {"general": "changes", "tests": "changes"}
    assert "----- brief general r2 -----" not in run.lines
    assert run.last.startswith(
        "Open: round 2 of 5 is briefed already, 1 of 2 results kept (missing: tests)."
    )
    assert sb.save("tests", 10).code == 0
    assert sb.run("round").code == 0
    assert sb.state()["rounds"][1]["modes"] == {
        "general": "changes",
        "tests": "changes",
    }


# The change log ---------------------------------------------------------------


def test_the_rows_that_count_for_each_judge(sb):
    sb.two_judges()
    sb.start_build()
    write_map(sb, "code | app.py | tests\n")
    assert (
        sb.judge({"general": result(10, improvements=["G1"]), "tests": nine("T1")}).code
        == 1
    )
    log = sb.loopdir() / "changes.md"
    log.write_text(
        "- r1 [general G1] owner: the user picks the name\n"
        "- r1 [tests T1] fixed: app.py checks the input\n"
    )
    sb.change("app.py", 4, tag="r2")
    run = sb.run("brief")
    assert run.code == 0, run
    assert not [line for line in run.lines if line.startswith("note: no changes.md")]
    assert WAIT_ONE in run.lines
    assert run.lines.index(WAIT_ONE) < run.lines.index("----- brief tests r2 -----")
    prompt = brief_of(run, "tests", 2)[1]
    assert f"The author's change log: {FOLDER}/changes.md" in prompt
    assert sb.save("tests", nine("T1")).code == 0
    assert sb.run("round").code == 1
    log.write_text(log.read_text() + "- r2 [tests T1] done: nothing\n")
    counted = sb.stored("general", n=1)
    data = counted.read_bytes()
    counted.write_bytes(data + b" ")
    sb.change("other.py", 2, tag="r3")
    run = sb.run("brief")
    assert (run.code, run.last) == (
        2,
        f"Error: {FOLDER}/judge/r1_general.json is not the result that was counted. "
        "Next: tell the user; loop.py abandon, then loop.py start again.",
    )
    counted.write_bytes(data)
    run = sb.run("brief")
    assert run.code == 0, run
    assert "note: no changes.md row for [tests T1]" in run.lines
    assert "note: no changes.md row for [general G1]" not in run.lines
    assert WAIT_ONE in run.lines
    general = brief_of(run, "general", 3)[1]
    assert (
        f"Your last counted result (round 1): {FOLDER}/judge/r1_general.json" in general
    )
    assert f"The author's change log: {FOLDER}/changes.md" in general
    assert (
        "The author's change log holds claims, not proof. Use only its rows marked r1 "
        "or later: check a `fixed` row in the work, weigh the evidence of an "
        "`answered` row, and do not mark down what an `owner` row leaves to the user."
    ) in general
    tests = brief_of(run, "tests", 3)[1]
    assert f"Your last counted result (round 2): {FOLDER}/judge/r2_tests.json" in tests
    assert not [line for line in tests if "changes.md" in line]
    head = sb.stored("general", ext="delta.diff").read_text().split("\n\n", 1)[0]
    assert "app.py" in head and "other.py" in head


@pytest.mark.parametrize("settle", [False, True])
def test_a_missing_row_and_a_settled_item(sb, settle):
    one_round(sb)
    if settle:
        assert sb.run("settle", "general", "I1", "--note", "fine as it is").code == 0
    sb.change("app.py", 5, tag="r2")
    run = sb.run("brief")
    assert run.code == 0, run
    note = "note: no changes.md row for [general I1]"
    assert (note in run.lines) is not settle
    again = sb.run("brief")
    assert not [line for line in again.lines if line.startswith("note:")]


# The sentences of a brief -----------------------------------------------------


def test_the_sentences_word_for_word():
    assert loop.TEN_MINUS == (
        "Your score is 10 minus named items: each lost point needs an item that says "
        "where, what is wrong, the smallest fix and the check that proves it. No item, "
        "no deduction."
    )
    assert (
        loop.EVERY_GAP == "List every gap you can find in this round, not the top few."
    )
    assert loop.NO_MARK_DOWN == (
        "Do not mark down for what waits on the user, needs the host, or stands in "
        "settled.md."
    )
    assert loop.NO_RAISE_AGAIN == (
        "Do not raise a closed item again without showing where it is still wrong."
    )
    assert loop.HALF_STEPS == "Score in steps of 0.5."
    assert loop.READ_FULL == (
        "Read a file you judge whole, once. For a single fact, search first and read "
        "those lines. Read nothing twice."
    )
    assert loop.START_FROM_LAST == (
        "Start from your last result and the delta. Read only what changed and what it "
        'touches. Before you give a 10, read the whole work again and answer "read": '
        '"full".'
    )
    assert loop.READ_CHANGES == (
        "Read the delta once. For a single fact outside it, search first and read "
        "those lines. The full read before a 10 is the one second read."
    )
    assert loop.ONE_OBJECT == "Answer with one compact JSON object and nothing else."
    assert loop.REAL_DEFECT == (
        "From this round on a new item must be a real defect or a gap against "
        "criteria.md or the plan, not something that could be nicer."
    )
    assert '"check"' in loop.SCHEMA_TEXT
    assert '"read"' in loop.SCHEMA_TEXT
    for path in SKILL.glob("loop*.py"):
        assert "Judge only whether" not in path.read_text(), path.name


EVERY_BRIEF = ("TEN_MINUS", "EVERY_GAP", "NO_MARK_DOWN", "NO_RAISE_AGAIN", "HALF_STEPS")


def test_the_sentences_by_round_and_mode(sb):
    sb.start_build()
    prompts = []
    for n in (1, 2, 3):
        if n > 1:
            sb.change("app.py", 3 + n, tag=f"r{n}")
        run = sb.run("brief")
        assert run.code == 0, run
        prompts.append("\n".join(brief_of(run, "general", n)[1]))
        if n < 3:
            assert sb.save("general", nine("I1")).code == 0
            assert sb.run("round").code == 1
    for prompt in prompts:
        for name in (*EVERY_BRIEF, "ONE_OBJECT", "READ_ONLY"):
            assert getattr(loop, name) in prompt, name
    first, second, third = prompts
    assert loop.READ_FULL in first
    assert loop.START_FROM_LAST not in first
    for later in (second, third):
        assert loop.START_FROM_LAST in later
        assert loop.READ_CHANGES in later
        assert "Read nothing twice." not in later
    assert loop.REAL_DEFECT not in first + second
    assert loop.REAL_DEFECT in third


# The size limit and the layout ------------------------------------------------


MAX_LINES, MAX_BYTES = 1500, 50_000


def over_limit(folder):
    """The text files of a folder over 1,500 lines or 50,000 bytes."""
    out = []
    for path in sorted(Path(folder).rglob("*")):
        if "__pycache__" in path.parts or path.suffix not in (".py", ".md", ".json"):
            continue
        if path.is_file():
            data = path.read_bytes()
            if len(data.splitlines()) > MAX_LINES or len(data) > MAX_BYTES:
                out.append(path.relative_to(folder).as_posix())
    return out


def test_no_file_of_the_skill_is_over_the_limit(tmp_path):
    assert over_limit(SKILL) == []
    lines = tmp_path / "lines"
    lines.mkdir()
    (lines / "loop_x.py").write_text("x = 1\n" * 1501)
    assert over_limit(lines) == ["loop_x.py"]
    (lines / "loop_x.py").write_text("x = 1\n" * 1500)
    assert over_limit(lines) == []
    size = tmp_path / "size"
    (size / "__pycache__").mkdir(parents=True)
    (size / "__pycache__" / "a.json").write_bytes(b"x" * 60_000)
    (size / "a.md").write_bytes(b"x" * 50_001)
    assert over_limit(size) == ["a.md"]
    (size / "a.md").write_bytes(b"x" * 50_000)
    assert over_limit(size) == []


def test_no_module_imports_loop():
    parts = sorted(SKILL.glob("loop_*.py"))
    assert parts
    for path in parts:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert "loop" not in names, path.name
        assert not os.stat(path).st_mode & 0o111, path.name
    assert os.stat(LOOP_PY).st_mode & 0o100


@pytest.mark.parametrize("safe", [False, True], ids=["plain", "PYTHONSAFEPATH"])
def test_loop_py_finds_its_modules_from_another_folder(tmp_path, safe):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if safe:
        env["PYTHONSAFEPATH"] = "1"
    proc = subprocess.run(
        [sys.executable, str(LOOP_PY), "status"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Traceback" not in proc.stderr, proc.stderr
    assert proc.returncode == 2, proc
    assert proc.stdout.strip(), proc
