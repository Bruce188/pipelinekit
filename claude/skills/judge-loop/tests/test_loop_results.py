"""Tests of loop.py: messages, main, results, save, stale results and round."""

from __future__ import annotations

import json
import os

import pytest
from loop_fixtures import (
    FIX_BUILD,
    NAME,
    SHA_A,
    WHICH,
    ends,
    item,
    loop,
    nine,
    result,
)

# Messages ---------------------------------------------------------------------


def test_messages_walk_a_build_loop(sb):
    """The table of last lines, walked in the order a session meets them."""
    steps = [
        (("status",), 0, "Open:", "loop.py start plan or loop.py start build."),
        (("leftovers",), 0, "Open:", "loop.py start plan or loop.py start build."),
        (("brief",), 2, "Refused:", "loop.py start plan or loop.py start build."),
        (("round",), 2, "Refused:", "loop.py start plan or loop.py start build."),
    ]
    for argv, code, first, tail in steps:
        ends(sb.run(*argv), code, first, tail)
    sb.change()
    ends(
        sb.run("start", "build"),
        0,
        f"Started: build loop {NAME}, 1 judge(s), at most 5 rounds.",
        "Next: write criteria.md, then loop.py brief.",
    )
    ends(sb.run("brief"), 2, "Refused: criteria.md is empty.", "loop.py brief.")
    sb.criteria()
    ends(
        sb.run("save", "general"), 2, "Refused: no round is briefed.", "loop.py brief."
    )
    ends(sb.run("round"), 2, "Refused: no round is briefed.", "loop.py brief.")
    ends(
        sb.run("brief"),
        0,
        "Open: round 1 of 5 briefed for 1 judge(s).",
        "Next: start each judge, write its answer to its answer file, "
        "loop.py save <role>.",
    )
    status = sb.run("status")
    ends(status, 0, "Open: round 1 of 5, 0 of 1 results saved (missing: general).")
    ends(sb.run("round"), 3, "STOP: round 1 has no results yet.", "do not fix.")
    ends(sb.run("save", "general"), 2, "Refused: no answer file for general.")
    ends(sb.save("general", nine("I1")), 0, "Saved: general scored 9", "loop.py round.")
    ends(
        sb.run("status"),
        0,
        "Open: round 1 of 5, 1 of 1 results saved",
        "loop.py round.",
    )
    run = sb.run("round")
    assert run.lines[0] == "Round 1 of 5: average 9.0; general 9"
    ends(run, 1, "Fix: 1 item (0 blocking).", FIX_BUILD)
    ends(sb.run("status"), 0, "Open: round 2 of 5", FIX_BUILD.removeprefix("Next: "))
    ends(sb.run("leftovers"), 0, "Open: 1 item open (0 blocking), the loop is not")
    run = sb.judge({"general": 10})
    assert run.lines[0] == "Round 2 of 5: average 10.0 (round before: 9.0); general 10"
    assert run.code == 0
    assert (
        run.last == "Done: 10 from every judge in 2 rounds. Next: the acceptance test."
    )
    ends(sb.run("status"), 0, "Done: 10 from every judge in 2 rounds.")
    ends(sb.run("round"), 2, "Refused: no loop is open here.")
    ended = "Refused: this loop ended (done). Next: loop.py status."
    ends(sb.run("round", *WHICH), 2, ended)
    ends(sb.run("brief", *WHICH), 2, ended)
    ends(sb.run("leftovers"), 0, "Open: nothing left. Next: nothing to file.")
    for command in ("diagnosed", "resume", "accept", "abandon"):
        ends(
            sb.run(command, "--note", "x", *WHICH),
            2,
            f"Refused: the loop is done; {command} does not apply.",
            "Next: the acceptance test.",
        )


def test_the_five_outcome_lines_in_full(sb):
    sb.on_base("CLAUDE.md", "Judge rounds: 2\n")
    sb.start_build()
    sb.judge({"general": nine("I1")})
    run = sb.judge({"general": nine("I1", "I2")})
    assert run.code == 0
    assert run.last == (
        "Budget used: 2 rounds, average 9.0, 2 items left. Next: loop.py leftovers, "
        "file each as an issue, then the acceptance test."
    )
    sb.git("checkout", "-q", "-b", "feat/2-y", "main")
    sb.start_build(rel="b.py")
    sb.judge({"general": nine("I1")}, name="feat-2-y")
    run = sb.run(
        "accept", "--note", "good enough", "--kind", "build", "--name", "feat-2-y"
    )
    assert run.code == 0
    assert run.last == (
        "Accepted: by the user in round 1 of 2 with 1 item left (0 blocking). "
        "Next: loop.py leftovers --kind build --name feat-2-y, file each as an "
        "issue, then the acceptance test."
    )
    sb.git("checkout", "-q", "-b", "feat/3-z", "main")
    sb.change("c.py", 2)
    run = sb.run("skip", "--reason", "typo")
    head = sb.head()
    assert run.code == 0
    assert run.last == (
        f"Skipped: {head[:7]} (1 file, 2 lines) is recorded as not judged. "
        "Next: the acceptance test."
    )
    sb.git("checkout", "-q", "-b", "feat/4-w", "main")
    sb.start_build(rel="d.py")
    run = sb.run(
        "abandon", "--note", "dropped", "--kind", "build", "--name", "feat-4-w"
    )
    assert run.code == 0
    assert run.last == loop.ABANDONED
    assert run.last == (
        "Abandoned: nothing counts as judged. "
        "Next: loop.py start when the work is to be judged again."
    )


def test_every_stop_line_ends_on_the_commands_it_names():
    assert loop.STALLED.endswith("then loop.py diagnosed --note.")
    assert loop.STALLED_WAIT.endswith("then loop.py diagnosed --note.")
    assert loop.ASK.endswith("then loop.py resume, accept or abandon.")
    assert loop.USER_WAIT.endswith("then loop.py resume, accept or abandon.")
    assert loop.BLOCKED.endswith("then loop.py resume --rounds N, accept or abandon.")
    for line in (loop.STALLED, loop.ASK, loop.BLOCKED):
        assert line.startswith("STOP: ")
        assert line.count("Next:") == 1


def test_not_in_a_repository(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert loop.main(["status"]) == 2
    assert capsys.readouterr().out.splitlines()[-1] == loop.NOT_A_REPO


# main -------------------------------------------------------------------------


def test_main_turns_any_exception_into_exit_2(sb, monkeypatch):
    def boom(args):
        raise RuntimeError("secret detail")

    configure = loop.COMMANDS["status"][0]
    monkeypatch.setitem(loop.COMMANDS, "status", (configure, boom))
    run = sb.run("status")
    assert run.code == 2
    assert (
        run.last
        == "Error: RuntimeError. Next: run /kit; when it is healthy, report this."
    )
    assert "secret" not in run.out


def test_bad_arguments_get_the_kits_words_not_argparses(sb):
    run = sb.command("round", "--what")
    assert run.code == 2, run
    assert run.last == (
        "Refused: these arguments do not fit loop.py round. Next: loop.py round --help."
    )
    assert "usage:" not in run.out + run.err
    run = sb.command("start", "build", "--panel", "huge")
    assert run.code == 2
    assert run.last.startswith("Refused:")
    assert run.last.endswith("Next: loop.py start --help.")
    run = sb.command("nosuch")
    assert (
        run.last == "Refused: nosuch is not a command of loop.py. Next: loop.py --help."
    )
    run = sb.command()
    assert run.last == "Refused: no command given. Next: loop.py --help."
    assert sb.command("--help").code == 0


def test_a_failing_git_call(sb, monkeypatch):
    sb.start_build()
    real = loop.Git.run

    def run(self, *args, ok=(0,)):
        if args and args[0] == "status":
            args = ("status", "--no-such-option")
        return real(self, *args, ok=ok)

    monkeypatch.setattr(loop.Git, "run", run)
    out = sb.run("brief")
    assert out.code == 2
    assert out.last == (
        "Error: git status failed with code 129. "
        "Next: fix the repository, then the same command."
    )
    assert out.lines[-2].startswith("  ")
    assert "no-such-option" in out.lines[-2]


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes anywhere"
)
def test_a_read_only_loop_folder(sb):
    sb.start_build()
    sb.run("brief")
    judge = sb.loopdir() / "judge"
    sb.answer("general", result(10))
    judge.chmod(0o555)
    try:
        run = sb.run("save", "general")
    finally:
        judge.chmod(0o755)
    assert run.code == 2
    assert run.last.startswith("Error: PermissionError (")
    assert run.last.endswith(
        "Next: free space or fix the permissions, then the same command."
    )


# Results ----------------------------------------------------------------------


def obj(**fields):
    data = {"overall": 9, "dimensions": {"fit": 9}, "blocking": [], "improvements": []}
    for key, value in fields.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return json.dumps(data).encode()


VALID = obj()
REJECTED = [
    ("not json", b"a score of 9", "json: not one JSON object"),
    ("code fence", b"```json\n" + VALID + b"\n```", "json: not one JSON object"),
    ("text before", b"Here it is: " + VALID, "json: not one JSON object"),
    ("text after", VALID + b"\nThat is all.", "json: not one JSON object"),
    ("bom", b"\xef\xbb\xbf" + VALID, "json: not one JSON object"),
    ("empty", b"", "json: not one JSON object"),
    ("a list", b"[" + VALID + b"]", "json: not one JSON object"),
    ("no overall", obj(overall=None), "overall: missing"),
    ("true", obj(overall=True), "overall: not a number"),
    ("false", obj(overall=False), "overall: not a number"),
    ("nan", obj(overall=float("nan")), "overall: not a number"),
    ("infinity", obj(overall=float("inf")), "overall: not a number"),
    ("string 10", obj(overall="10"), "overall: not a number"),
    ("10.5", obj(overall=10.5), "overall: outside 0 to 10"),
    ("-1", obj(overall=-1), "overall: outside 0 to 10"),
    ("dimension text", obj(dimensions={"fit": "high"}), "dimensions[1]: not a number"),
    (
        "21 dimensions",
        obj(dimensions={f"d{i}": 5 for i in range(21)}),
        "dimensions: too many",
    ),
    (
        "51 items",
        obj(improvements=[item(f"I{i}") for i in range(51)]),
        "improvements: too many",
    ),
    (
        "no id",
        obj(improvements=[{"problem": "p", "evidence": "e", "fix": "f"}]),
        "improvements[1].id: missing",
    ),
    ("id b1", obj(improvements=[item("b1")]), "improvements[1].id: not a valid id"),
    (
        "id of 21",
        obj(improvements=[item("A" * 21)]),
        "improvements[1].id: not a valid id",
    ),
    (
        "empty evidence",
        obj(improvements=[item("I1", evidence="  ")]),
        "improvements[1].evidence: empty",
    ),
    (
        "field of 2001",
        obj(improvements=[item("I1", problem="x" * 2001)]),
        "improvements[1].problem: too long",
    ),
    (
        "duplicate id",
        obj(improvements=[item("I1"), item("I1")]),
        "improvements[2].id: not unique",
    ),
    (
        "unknown still_open",
        obj(improvements=[item("I2")], still_open=["I2"]),
        "still_open[1]: not an open id",
    ),
    (
        "10 with blocking",
        obj(overall=10, blocking=[item("B1")]),
        "overall: a 10 with open items",
    ),
    (
        "10 with still_open",
        obj(overall=10, improvements=[item("I1")], still_open=["I1"]),
        "overall: a 10 with open items",
    ),
    (
        "needed_for_10 text",
        obj(improvements=[item("I1", needed_for_10="no")]),
        "improvements[1].needed_for_10: wrong type",
    ),
    ("judge of another role", obj(judge="tests"), "judge: not the role"),
    ("not utf-8", b"\xff\xfe{", "encoding: not UTF-8"),
    (
        "problem a number",
        obj(blocking=[item("B1", problem=5)]),
        "blocking[1].problem: not a string",
    ),
]


def padded(data, size):
    return data + b" " * (size - len(data))


ACCEPTED = [
    ("overall 0", obj(overall=0)),
    ("overall 10", obj(overall=10)),
    ("overall 9.5", obj(overall=9.5)),
    ("exactly 200 kB", padded(VALID, loop.MAX_RESULT)),
    ("field of 2000", obj(improvements=[item("I1", fix="y" * 2000)])),
    ("20 dimensions", obj(dimensions={f"d{i}": 5 for i in range(20)})),
    ("50 items", obj(improvements=[item(f"I{i}") for i in range(50)])),
    ("no still_open, no judge", obj(still_open=None, judge=None)),
    (
        "10 with still_open marked",
        obj(
            overall=10,
            improvements=[item("I1", needed_for_10=False)],
            still_open=["I1"],
            judge="general",
        ),
    ),
]


def test_result_rules_alone():
    for name, data, reason in REJECTED:
        with pytest.raises(loop.NoScore) as err:
            loop.check_result(data, "general", {"I1"})
        assert err.value.reason == reason, name
        field, why = reason.split(": ", 1)
        assert why in loop.WHY_PHRASES, name
    for name, data in ACCEPTED:
        assert loop.check_result(data, "general", {"I1"}), name
    with pytest.raises(loop.NoScore) as err:
        loop.check_result(padded(VALID, loop.MAX_RESULT + 1), "general")
    assert err.value.reason == "size: over 200 kB"


def round_two(sb):
    """A build loop in round 2, briefed; general has I1 open from round 1."""
    sb.start_build()
    sb.judge({"general": nine("I1")})
    assert sb.run("brief").code == 0
    return sb.stored("general", ext="meta")


def test_results_through_save_and_round(sb):
    meta = round_two(sb)
    for name, data, reason in REJECTED:
        meta.unlink(missing_ok=True)
        run = sb.save("general", data)
        assert run.code == 3, (name, run)
        assert f"({reason})" in run.last, (name, run)
        assert run.last.startswith(f"STOP: not a score from general ({reason}). Next:")
        run = sb.run("round")
        assert run.code == 3, (name, run)
        assert run.last.startswith(
            f"STOP: no score from general ({reason}). Next: do not fix"
        )
        assert sb.rounds() == 1, name
    for name, data in ACCEPTED:
        meta.unlink(missing_ok=True)
        run = sb.save("general", data)
        assert run.code == 0, (name, run)
        assert run.last.startswith("Saved: general scored "), name
    big = padded(VALID, loop.MAX_RESULT + 1)
    answer = sb.answer("general", big)
    run = sb.run("save", "general")
    assert run.code == 2
    assert run.last == (
        f"Refused: {answer.relative_to(sb.root)} is not a plain file of at most "
        "200 kB. "
        "Next: write the judge's answer there with the Write tool."
    )
    sb.stored("general").write_bytes(big)
    st = sb.state()
    meta.write_text(
        json.dumps(
            {
                "round": 2,
                "briefed": st["pending"]["commit"],
                "sha256": loop.sha256(big),
                "misses": 0,
            }
        )
    )
    run = sb.run("round")
    assert run.code == 3
    assert run.last.startswith("STOP: no score from general (size: over 200 kB).")
    assert sb.rounds() == 1


# save -------------------------------------------------------------------------


def test_save_stores_the_answer_byte_for_byte(sb):
    sb.start_build()
    sb.run("brief")
    first = b'{"overall": 9, "dimensions": {}, "blocking": [], "improvements": []}\n'
    assert sb.save("general", first).code == 0
    assert sb.stored("general").read_bytes() == first
    second = obj(overall=8)
    assert sb.save("general", second).code == 0
    assert sb.stored("general").read_bytes() == second
    run = sb.save("tests", VALID)
    assert run.code == 2
    assert (
        run.last
        == "Refused: tests is not on the panel (general). Next: loop.py status."
    )


@pytest.mark.parametrize("how", ["link inside", "link outside", "too big", "missing"])
def test_save_refuses_an_answer_that_is_not_a_plain_file(sb, how):
    sb.start_build()
    sb.run("brief")
    answer = sb.answer("general", VALID)
    if how == "link inside":
        other = answer.with_name("other.txt")
        other.write_bytes(VALID)
        answer.unlink()
        answer.symlink_to(other)
    elif how == "link outside":
        outside = sb.tmp / "outside.txt"
        outside.write_bytes(VALID)
        answer.unlink()
        answer.symlink_to(outside)
    elif how == "too big":
        answer.write_bytes(padded(VALID, loop.MAX_RESULT + 1))
    else:
        answer.unlink()
    run = sb.run("save", "general")
    assert run.code == 2, run
    rel = answer.relative_to(sb.root)
    if how == "missing":
        assert run.last == (
            "Refused: no answer file for general. "
            f"Next: write the judge's answer to {rel} with the Write tool."
        )
    else:
        assert run.last.startswith(
            f"Refused: {rel} is not a plain file of at most 200 kB."
        )
    assert not sb.stored("general").exists()


def test_save_counts_the_misses(sb):
    sb.start_build()
    sb.run("brief")
    answer = sb.answer("general", b"no")
    run = sb.run("save", "general")
    assert run.code == 3
    assert run.last == (
        "STOP: not a score from general (json: not one JSON object). Next: ask that "
        "judge once for the JSON object alone, write it to "
        f"{answer.relative_to(sb.root)}, "
        "loop.py save general."
    )
    run = sb.run("save", "general")
    assert run.code == 3
    assert run.last == (
        "STOP: second miss from general. Next: ask the user (the skill's options for a "
        "second miss); a fresh judge for this role needs their yes."
    )
    run = sb.run("save", "general")
    assert run.code == 3
    assert run.last.startswith("STOP: miss 3 from general. Next: ask the user")


def test_two_saves_at_the_same_time(sb):
    sb.two_judges()
    sb.start_build()
    sb.run("brief")
    state = (sb.loopdir() / "state.json").read_bytes()
    sb.answer("general", result(10))
    sb.answer("tests", result(9))
    procs = [sb.spawn("save", role) for role in ("general", "tests")]
    for proc in procs:
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, (out, err)
    assert sb.stored("general").read_bytes() == result(10)
    assert sb.stored("tests").read_bytes() == result(9)
    assert (sb.loopdir() / "state.json").read_bytes() == state


# Stale and copied results -----------------------------------------------------


def test_a_result_copied_in_without_save(sb):
    sb.start_build()
    sb.run("brief")
    sb.stored("general").write_bytes(result(10))
    run = sb.run("round")
    assert run.code == 3
    assert run.last.startswith("STOP: no score from general (the save did not finish).")
    assert sb.rounds() == 0


def test_a_result_edited_after_save(sb):
    sb.start_build()
    sb.run("brief")
    assert sb.save("general", 9).code == 0
    sb.stored("general").write_bytes(result(10))
    run = sb.run("round")
    assert run.code == 3
    assert run.last.startswith(
        "STOP: no score from general (the result changed after it was saved)."
    )
    assert sb.rounds() == 0


def test_a_commit_after_brief_makes_the_results_stale(sb):
    sb.start_build()
    sb.run("brief")
    assert sb.save("general", 9).code == 0
    sb.change("app.py", 4)
    run = sb.run("brief")
    assert run.code == 0
    assert "The work changed: 4 files of round 1 moved to judge/stale/" in run.lines
    stale = list((sb.loopdir() / "judge" / "stale").glob("*/r1_general.json"))
    assert len(stale) == 1
    assert not sb.stored("general").exists()
    run = sb.run("round")
    assert run.code == 3
    assert run.last.startswith("STOP: round 1 has no results yet.")


def test_brief_again_without_a_change_keeps_the_results(sb):
    sb.start_build()
    sb.run("brief")
    assert sb.save("general", 9).code == 0
    run = sb.run("brief")
    assert run.code == 0
    assert not any(line.startswith("The work changed") for line in run.lines)
    assert sb.stored("general").read_bytes() == result(9)
    assert sb.run("round").code == 1


def test_identical_tens_in_two_rounds_both_count(sb):
    sb.two_judges()
    sb.start_build()
    run = sb.judge({"general": 10, "tests": nine("T1")})
    assert run.code == 1
    sb.change("app.py", 4, tag="fix")
    run = sb.judge({"general": 10, "tests": nine("T1")})
    assert run.code == 1, run
    assert sb.rounds() == 2
    assert [r["scores"]["general"] for r in sb.state()["rounds"]] == [10, 10]
    assert "Changes only next round: general" in run.lines
    sb.change("app.py", 5, tag="again")
    run = sb.run("brief")
    assert "Changes only this round: general" in run.lines
    assert (sb.loopdir() / "judge" / "r3_general.delta.diff").is_file()


def test_status_lists_saved_and_missing_roles(sb):
    sb.two_judges()
    sb.start_build()
    run = sb.run("status")
    assert run.last == (
        "Open: round 1 of 5, 0 of 2 results saved (missing: general, tests). "
        "Next: loop.py brief."
    )
    sb.run("brief")
    sb.save("general", 9)
    run = sb.run("status")
    assert run.code == 0
    assert run.last == (
        "Open: round 1 of 5, 1 of 2 results saved (missing: tests). Next: start each "
        "judge, write its answer to its answer file, loop.py save <role>."
    )
    sb.save("tests", 9)
    run = sb.run("status")
    assert run.last == (
        "Open: round 1 of 5, 2 of 2 results saved (missing: none). Next: loop.py round."
    )


# round pre-checks -------------------------------------------------------------


def briefed_pair(sb):
    """Two judges, round 1 briefed and both saved."""
    sb.two_judges()
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", 9).code == 0
    assert sb.save("tests", 9).code == 0


def set_outcome(outcome):
    def apply(sb):
        sb.set_state(outcome=outcome)

    return apply


def other_meta(sb):
    meta = sb.stored("general", ext="meta")
    data = json.loads(meta.read_text())
    data["briefed"] = SHA_A
    meta.write_text(json.dumps(data))


def checkout_other(sb):
    sb.git("checkout", "-q", "-b", "feat/9-other")


BRIEF = "Refused: the work changed after the judges were briefed."
PRE_CHECKS = [
    ("commit after brief", lambda sb: sb.change("app.py", 9), 2, BRIEF),
    ("dirty tracked file", lambda sb: sb.write("app.py", "dirty\n"), 2, BRIEF),
    ("stalled", set_outcome("stalled"), 3, "STOP: the loop is stalled."),
    ("ask", set_outcome("ask"), 3, "STOP: waiting for the user's answer."),
    ("blocked", set_outcome("blocked"), 3, "STOP: waiting for the user's answer."),
    ("done", set_outcome("done"), 2, "Refused: this loop ended (done)."),
    (
        "no pending round",
        lambda sb: sb.set_state(pending={}),
        2,
        "Refused: no round is briefed.",
    ),
    (
        "a judge off the panel",
        lambda sb: sb.stored("scope").write_bytes(result(9)),
        3,
        "STOP: docs/loops/feat-1-x/build/judge/r1_scope.json is from a judge that is "
        "not on the panel.",
    ),
    (
        "meta of another commit",
        other_meta,
        3,
        "STOP: no score from general (general's result is for aaaaaaa, not the briefed",
    ),
    (
        "no meta",
        lambda sb: sb.stored("general", ext="meta").unlink(),
        3,
        "STOP: no score from general (the save did not finish).",
    ),
    (
        "a role without a result",
        lambda sb: sb.stored("tests").unlink(),
        3,
        "STOP: no score from tests (no result saved).",
    ),
    (
        "edited after save",
        lambda sb: sb.stored("tests").write_bytes(result(8)),
        3,
        "STOP: no score from tests (the result changed after it was saved).",
    ),
    (
        "another branch",
        checkout_other,
        2,
        "Refused: this loop is for feat/1-x, feat/9-other is checked out.",
    ),
]


@pytest.mark.parametrize(
    "how, code, first", [row[1:] for row in PRE_CHECKS], ids=[r[0] for r in PRE_CHECKS]
)
def test_round_pre_checks(sb, how, code, first):
    briefed_pair(sb)
    how(sb)
    run = sb.run("round", "--kind", "build", "--name", NAME)
    assert run.code == code, run
    assert run.last.startswith(first), run
    assert sb.rounds(name=NAME) == 0


def test_round_without_meta_names_save_again(sb):
    briefed_pair(sb)
    sb.stored("general", ext="meta").unlink()
    run = sb.run("round")
    assert run.last.endswith(
        "loop.py save general again, else judge again for that role."
    )


@pytest.mark.parametrize("which", ["plan.md", "plan.r1.md"])
def test_round_refuses_an_edited_plan(sb, which):
    sb.start_plan()
    assert sb.run("brief").code == 0
    assert sb.save("general", 9, "plan", "p1").code == 0
    path = sb.loopdir("plan", "p1") / which
    path.write_text(path.read_text() + "more\n")
    run = sb.run("round")
    assert run.code == 2
    assert run.last.startswith(BRIEF)
    assert sb.rounds("plan", "p1") == 0
