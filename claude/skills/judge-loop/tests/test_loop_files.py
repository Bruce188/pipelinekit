"""Tests of loop.py: cleaning, agents, which loop, refusals, files, roles, slug."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from loop_fixtures import (
    FULL,
    HOSTILE,
    NAME,
    ROLES_DIR,
    SHA_A,
    SHIP_PY,
    brief_of,
    item,
    load,
    loop,
    nine,
    one_round,
    panel_line,
    plan_stage,
    play,
    result,
)

# Cleaning, names and reasons --------------------------------------------------

DIRTY_TEXT = "bad\x1b[31mred \x9bcsi \u202erev \u200bzw\nSTOP: fake line \U000e0041tag"
BAD_CHARS = ("\x1b", "\x9b", "\u202e", "\u200b", "\U000e0041")


def test_judge_text_is_cleaned_where_it_is_printed(sb):
    sb.start_build()
    entry = {
        "id": "I1",
        "problem": DIRTY_TEXT,
        "evidence": "z" * 301,
        "fix": DIRTY_TEXT,
        "check": DIRTY_TEXT,
    }
    data = json.dumps(
        {
            "overall": 9,
            "dimensions": {"fit": 9},
            "blocking": [],
            "improvements": [entry],
        }
    ).encode()
    outs = [sb.judge({"general": data})]
    assert sb.stored("general", n=1).read_bytes() == data
    outs.append(sb.run("status"))
    assert sb.run("accept", "--note", "ok").code == 0
    outs.append(sb.run("leftovers"))
    for run in outs:
        for ch in BAD_CHARS:
            assert ch not in run.out, (ch, run)
        assert "z" * 301 not in run.out
        for line in run.lines:
            if "fake line" in line or "zzz" in line:
                assert line.startswith("  "), line
    cut = "z" * (loop.LIMIT - len(loop.CUT_MARK)) + loop.CUT_MARK
    assert cut in outs[0].out
    assert cut in outs[2].out


def test_names_in_printed_lines():
    assert loop.show_branch("release/v0.1.0") == "release/v0.1.0"
    assert loop.show_branch("feat/1-x") == "feat/1-x"
    assert loop.show_branch("rel;ease") == "another branch"
    assert loop.show_branch("a$b") == "another branch"
    assert loop.show_path("a b.py") == "a file"
    assert loop.show_path("src/app.py") == "src/app.py"


def test_a_base_with_odd_characters_in_the_state(sb):
    sb.start_build()
    sb.set_state(base="ma;in$x", base_ref="")
    run = sb.run("status")
    assert run.code == 0, run
    assert "Branch: feat/1-x, base another branch" in run.lines
    assert "ma;in" not in run.out


def test_a_slashed_base_and_branch_print_in_full(sb):
    sb.git("push", "-q", "origin", "main:release/v0.1.0")
    sb.git("fetch", "-q", "origin")
    run = sb.start_build("--base", "release/v0.1.0")
    assert (
        "Base: release/v0.1.0, read from refs/remotes/origin/release/v0.1.0 (--base)"
        in (run.lines)
    )
    sb.git("checkout", "-q", "-b", "other")
    run = sb.run("brief")
    assert run.last == (
        "Refused: this loop is for feat/1-x, other is checked out. "
        "Next: check out feat/1-x, or loop.py start build here."
    )


def test_a_path_with_a_space_prints_as_a_file(sb):
    sb.write("a b.bin", b"\x00\x01")
    run = sb.start_build(lines=0)
    assert panel_line(run) == f"Panel: {FULL} (auto: a file has no line count)"


HOSTILE_RESULTS = {
    "a dimension name": result(9, dimensions={HOSTILE: "high"}),
    "a still_open entry": result(9, still_open=[HOSTILE]),
    "a judge value": result(9, judge=HOSTILE),
    "an id": json.dumps(
        {
            "overall": 9,
            "dimensions": {},
            "blocking": [],
            "improvements": [item(HOSTILE)],
        }
    ).encode(),
}


@pytest.mark.parametrize("data", HOSTILE_RESULTS.values(), ids=HOSTILE_RESULTS.keys())
def test_a_reason_never_repeats_judge_text(sb, data):
    sb.start_build()
    assert sb.run("brief").code == 0
    for run in (sb.save("general", data), sb.run("round")):
        assert run.code == 3, run
        assert "accept --note" not in run.last
        assert "x)" not in run.last
        assert run.last.count("Next:") == 1


def test_a_hostile_plan_name(sb):
    run = sb.run("start", "plan", "--name", HOSTILE)
    assert run.code == 2
    assert run.last.startswith("Refused: ")
    assert run.last.count("Next:") == 1
    assert run.last.endswith("Next: the same command with another --name.")


# Agents -----------------------------------------------------------------------


def project_agent(
    sb, rel=".claude/agents/sub/x.md", text="---\nname: kit-judge\n---\n"
):
    path = sb.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    return path


OWN_AGENT = (
    "STOP: this project has its own agent named kit-judge ({rel}). "
    "Next: ask the user: rename it, or loop.py {again} --agents fallback."
)
CANNOT_CHECK = (
    "STOP: {rel} cannot be checked for an agent name (a link, or over 64 kB). "
    "Next: ask the user: make it a plain file or folder, or the same command with "
    "--agents fallback."
)


def test_a_missing_agent_file(sb):
    (sb.agents / "kit-judge.md").unlink()
    sb.change("app.py", 3)
    run = sb.run("start", "build")
    assert (run.code, run.last) == (
        2,
        "Refused: agents/kit-judge.md is not installed. Next: run /kit.",
    )


NAME_LINES = {
    "plain": b"---\nname: kit-judge\n---\n",
    "double quotes": b'---\nname: "kit-judge"\n---\n',
    "single quotes": b"---\nname: 'kit-judge'\n---\n",
    "crlf": b"---\r\nname: kit-judge\r\n---\r\n",
    "byte order mark": b"\xef\xbb\xbf---\nname: kit-judge\n---\n",
    "upper case": b"---\nname: KIT-JUDGE\n---\n",
    "a comment": b"---\nname: kit-judge # the judge\n---\n",
    "a name in a block above": (
        b"---\ndescription: |\n  name: helper\nname: kit-judge\n---\n"
    ),
    "an indented kit name": b"---\nmeta:\n  name: kit-judge\nname: helper\n---\n",
}


@pytest.mark.parametrize("text", NAME_LINES.values(), ids=NAME_LINES.keys())
def test_a_project_agent_of_the_same_name(sb, text):
    project_agent(sb, text=text)
    sb.change("app.py", 3)
    run = sb.run("start", "build")
    rel = ".claude/agents/sub/x.md"
    assert (run.code, run.last) == (3, OWN_AGENT.format(rel=rel, again="start ..."))


def test_a_project_agent_file_named_like_a_kit_agent(sb):
    project_agent(sb, ".claude/agents/kit-judge.md", "no front matter\n")
    sb.change("app.py", 3)
    run = sb.run("start", "build")
    assert run.code == 3
    assert run.last == OWN_AGENT.format(
        rel=".claude/agents/kit-judge.md", again="start ..."
    )


def outside_folder(sb):
    folder = sb.tmp / "outside"
    folder.mkdir()
    (folder / "kit-judge.md").write_text("---\nname: kit-judge\n---\n")
    return folder


UNREADABLE_NAMES = {
    "an empty name": b"---\nname:\n  kit-judge\n---\n",
    "a folded name": b"---\nname: >\n  kit-judge\n---\n",
    "an anchor": b"---\nname: &a kit-judge\n---\n",
    "a tag": b"---\nname: !!str kit-judge\n---\n",
    "a quoted key": b'---\n"name": helper\n---\n',
    "an escape in quotes": b'---\nname: "kit\\x2djudge"\n---\n',
    "a flow mapping": b"---\n{name: kit-judge}\n---\n",
}


@pytest.mark.parametrize("text", UNREADABLE_NAMES.values(), ids=UNREADABLE_NAMES.keys())
def test_a_project_agent_name_that_cannot_be_read(sb, text):
    project_agent(sb, text=text)
    sb.change("app.py", 3)
    run = sb.run("start", "build")
    rel = ".claude/agents/sub/x.md"
    assert (run.code, run.last) == (3, CANNOT_CHECK.format(rel=rel))


def test_a_project_agent_with_another_name_and_a_block(sb):
    project_agent(sb, text=b"---\nname: helper\ndescription: |\n  name:\n---\n")
    sb.change("app.py", 3)
    assert sb.run("start", "build").code == 0


UNCHECKABLE = ["a link", "over 64 kB", "a linked folder", "a linked agents folder"]


@pytest.mark.parametrize("how", UNCHECKABLE)
def test_a_project_agent_that_cannot_be_checked(sb, how):
    agents = sb.root / ".claude" / "agents"
    if how == "a link":
        agents.mkdir(parents=True)
        (agents / "x.md").symlink_to(outside_folder(sb) / "kit-judge.md")
        rel = ".claude/agents/x.md"
    elif how == "over 64 kB":
        project_agent(sb, ".claude/agents/x.md", "x" * (64 * 1024 + 1))
        rel = ".claude/agents/x.md"
    elif how == "a linked folder":
        agents.mkdir(parents=True)
        (agents / "sub").symlink_to(outside_folder(sb))
        rel = ".claude/agents/sub"
    else:
        agents.parent.mkdir(parents=True)
        agents.symlink_to(outside_folder(sb))
        rel = ".claude/agents"
    sb.change("app.py", 3)
    run = sb.run("start", "build")
    assert (run.code, run.last) == (3, CANNOT_CHECK.format(rel=rel))


def test_a_project_agent_that_appears_after_round_one(sb):
    one_round(sb)
    project_agent(sb)
    sb.change("app.py", 6)
    run = sb.run("brief")
    rel = ".claude/agents/sub/x.md"
    assert (run.code, run.last) == (3, OWN_AGENT.format(rel=rel, again="brief"))
    run = sb.run("brief", "--agents", "fallback")
    assert run.code == 0, run
    assert run.lines[0] == (
        "note: no changes.md row for [general I1] (a row reads: - r1 [general I1] "
        "fixed|answered|owner: <text>)"
    )
    assert run.lines[1] == "Agents: fallback"
    assert loop.FALLBACK_SENTENCE in run.lines
    st = sb.state()
    assert (len(st["rounds"]), st["agents"]) == (1, "fallback")
    assert {"round": 2, "action": "agents", "text": "fallback"} in st["notes"]
    assert json.loads(sb.run("status", "--json").out)["agents"] == "fallback"


def test_fallback_from_the_start(sb):
    project_agent(sb)
    sb.change("app.py", 3)
    run = sb.run("start", "build", "--agents", "fallback")
    assert run.code == 0, run
    assert "Agents: fallback" in run.lines
    assert loop.FALLBACK_SENTENCE in run.lines
    sb.criteria()
    run = sb.run("brief")
    above, prompt = brief_of(run, sb.state()["panel"][0], 1)
    assert above[0] == "Start: general-purpose, model fable"
    assert prompt[0] == (
        f"Read `{sb.agents / 'kit-judge.md'}` and follow it as your instructions."
    )
    assert prompt[0].startswith(f"Read `{sb.tmp}")
    assert json.loads(sb.run("status", "--json").out)["agents"] == "fallback"


def test_the_default_brief_names_kit_judge(sb):
    sb.start_build()
    above, _ = brief_of(sb.run("brief"), "general", 1)
    assert above[0] == "Start: kit-judge"
    assert json.loads(sb.run("status", "--json").out)["agents"] == "kit"


def test_a_meta_whose_commit_is_not_a_sha(sb):
    sb.start_build()
    sb.run("brief")
    assert sb.save("general", 9).code == 0
    meta = sb.stored("general", n=1, ext="meta")
    data = json.loads(meta.read_text())
    data["briefed"] = "HEAD"
    meta.write_text(json.dumps(data))
    run = sb.run("round")
    assert run.code == 3
    assert run.last.startswith(
        "STOP: no score from general (general's result is for other work)."
    )


OTHER_WORK_STOP = (
    "STOP: no score from general (general's result is for other work). Next: do not "
    "fix; judge again for that role and loop.py save general, else tell the user."
)
BAD_METAS = {
    "not JSON": lambda data: "not json",
    "a list": lambda data: "[1]",
    "another round": lambda data: json.dumps({**data, "round": 2}),
}


@pytest.mark.parametrize("spoil", BAD_METAS.values(), ids=BAD_METAS.keys())
def test_a_meta_that_is_not_json_or_of_another_round(sb, spoil):
    sb.start_build()
    sb.run("brief")
    assert sb.save("general", 9).code == 0
    meta = sb.stored("general", n=1, ext="meta")
    meta.write_text(spoil(json.loads(meta.read_text())))
    run = sb.run("round")
    assert (run.code, run.last) == (3, OTHER_WORK_STOP)
    assert sb.rounds() == 0


# Which loop -------------------------------------------------------------------


def test_none_one_and_two_unfinished_loops(sb):
    sb.change("app.py", 3)
    assert (sb.run("brief").code, sb.run("brief").last) == (2, loop.NO_OPEN)
    sb.start_build(lines=0)
    assert sb.run("brief").code == 0
    sb.start_plan()
    run = sb.run("status")
    assert run.code == 2
    assert run.last.startswith("Refused: more than one loop is open (")
    assert "build feat-1-x" in run.last and "plan p1" in run.last
    assert run.last.endswith("Next: the same command with --kind and --name.")


@pytest.mark.parametrize("command", ["status", "leftovers"])
def test_no_loop_folder(sb, command):
    assert (lambda r: (r.code, r.last))(sb.run(command)) == (0, loop.NO_LOOP)


def test_status_and_leftovers_after_budget_used(sb):
    play(sb, "build", 3, [9, 9, 9])
    status = sb.run("status")
    assert status.code == 0, status
    assert status.last.startswith("Budget used:")
    leftovers = sb.run("leftovers")
    assert leftovers.code == 0, leftovers
    assert "general I1" in leftovers.out


def test_the_later_finished_loop_is_taken(sb):
    plan_stage(sb, "p1")
    plan_stage(sb, "p2")
    for older, newer in (("p2", "p1"), ("p1", "p2")):
        os.utime(sb.loopdir("plan", older) / "state.json", (1_000_000, 1_000_000))
        os.utime(sb.loopdir("plan", newer) / "state.json", (2_000_000, 2_000_000))
        assert (
            sb.run("status").lines[0]
            == f"Loop: plan {newer} in docs/loops/{newer}/plan/"
        )


def test_an_archived_folder_is_never_taken(sb):
    sb.start_build()
    assert sb.judge({"general": 10}).code == 0
    sb.loopdir().rename(sb.loopdir().parent / "build.1")
    run = sb.run("status")
    assert (run.code, run.last) == (0, loop.NO_LOOP)


def test_an_unfinished_loop_of_another_branch(sb):
    sb.start_build()
    sb.git("checkout", "-q", "-b", "feat/2-y")
    sb.start_build()
    assert sb.judge({"general": 10}).code == 0
    run = sb.run("status")
    assert run.lines[0] == "Loop: build feat-2-y in docs/loops/feat-2-y/build/"
    assert (sb.run("brief").code, sb.run("brief").last) == (2, loop.NO_OPEN)


def test_no_such_loop(sb):
    sb.start_build()
    run = sb.run("status", "--kind", "build", "--name", "nosuch")
    assert (run.code, run.last) == (2, loop.NO_SUCH)


def test_status_of_a_blocked_loop(sb):
    play(sb, "build", 1, [9], blocking=True)
    run = sb.run("status")
    assert run.code == 0
    assert run.last.startswith("STOP: blocking items left after the last round.")


NEXT_COMMAND = re.compile(r"loop\.py ([a-z-]+)")


def qualified(line, kind, name):
    tail = line.split(" Next: ", 1)[1]
    found = 0
    for m in NEXT_COMMAND.finditer(tail):
        if m.group(1) in ("start", "skip"):
            continue
        found += 1
        assert tail[m.end() :].startswith(f" --kind {kind} --name {name}"), line
    return found


def test_with_two_folders_every_next_is_qualified(sb):
    plan_stage(sb)
    run = sb.start_build()
    assert qualified(run.last, "build", NAME)
    which = ("--kind", "build", "--name", NAME)
    runs = [sb.run("status"), sb.run("brief", *which)]
    sb.answer("general", nine("I1"))
    runs += [sb.run("save", "general", *which), sb.run("round", *which)]
    runs += [sb.run("status", *which), sb.run("accept", "--note", "ok", *which)]
    assert runs[0].code == 0 and runs[3].code == 1, runs
    counts = [qualified(r.last, "build", NAME) for r in runs]
    assert all(counts), (counts, runs)
    run = sb.run("leftovers", "--kind", "plan", "--name", "p1")
    assert run.code == 0
    qualified(run.last, "plan", "p1")


# Refusals ---------------------------------------------------------------------


def detach(sb):
    sb.git("checkout", "-q", "--detach")


def on_main(sb):
    sb.git("checkout", "-q", "main")


def on_main_without_remote(sb):
    sb.git("remote", "remove", "origin")
    on_main(sb)


def long_branch(sb):
    sb.git("checkout", "-q", "-b", "feat/" + "y" * 76)
    sb.change()


def missing_plan(sb):
    sb.change()


def open_plan(sb):
    sb.start_plan()
    sb.change()


def edited_plan(sb):
    plan_stage(sb)
    (sb.loopdir("plan", "p1") / "plan.r1.md").write_text("# Other\n")
    sb.change()


def files_no_state(sb):
    sb.change()
    folder = sb.loopdir()
    folder.mkdir(parents=True)
    (folder / "x.txt").write_text("x\n")


def dirty(sb):
    sb.change()
    sb.write("app.py", "edited\n")


def blocked_without_rounds(sb):
    play(sb, "build", 1, [9], blocking=True)


def blocked_with_rounds(sb):
    play(sb, "build", 1, [9], blocking=True)
    sb.set_state(budget=3)


BUILD_NAME = (
    "Refused: a build loop is named after its branch. "
    "Next: loop.py start build without --name."
)
NO_BRANCH = "Refused: no branch is checked out. Next: check out the work branch."
IS_BASE = (
    "Refused: main is the base branch. "
    "Next: git switch -c <work branch>, then the same command."
)
BAD_PLAN = (
    "Refused: {v} cannot name a judge record "
    "(letters, digits, '.', '_', '-'; at most 80). Next: {t}."
)
ANOTHER = "the same command with another --name"
ROUNDS = (
    "Refused: --rounds takes 1 to 5. Next: the same command with --rounds N (1 to 5)."
)
FOLDER = f"docs/loops/{NAME}/build"

REFUSALS = [
    # id, set-up, command, exit, last line (or its start)
    ("build --name", missing_plan, ("start", "build", "--name", "x"), 2, BUILD_NAME),
    ("build --name detached", detach, ("start", "build", "--name", "x"), 2, BUILD_NAME),
    ("start on main", on_main, ("start", "build"), 2, IS_BASE),
    ("skip on main", on_main, ("skip", "--reason", "x"), 2, IS_BASE),
    (
        "start on main, no remote",
        on_main_without_remote,
        ("start", "build"),
        2,
        IS_BASE,
    ),
    (
        "skip on main, no remote",
        on_main_without_remote,
        ("skip", "--reason", "x"),
        2,
        IS_BASE,
    ),
    ("build detached", detach, ("start", "build"), 2, NO_BRANCH),
    ("plan detached", detach, ("start", "plan"), 2, NO_BRANCH),
    (
        "plan ../x",
        None,
        ("start", "plan", "--name", "../x"),
        2,
        BAD_PLAN.format(v="../x", t=ANOTHER),
    ),
    ("plan 81", None, ("start", "plan", "--name", "p" * 81), 2, ANOTHER + "."),
    (
        "branch 81",
        long_branch,
        ("start", "build"),
        2,
        "Refused: the branch name cannot name a judge record. Next: rename the branch.",
    ),
    (
        "plan-loop ../x",
        missing_plan,
        ("start", "build", "--plan-loop", "../x"),
        2,
        "see loop.py status.",
    ),
    (
        "plan-loop on a plan",
        None,
        ("start", "plan", "--name", "p2", "--plan-loop", "p1"),
        2,
        "Refused: --plan-loop is for start build. Next: loop.py start plan without it.",
    ),
    (
        "plan-loop missing",
        missing_plan,
        ("start", "build", "--plan-loop", "p1"),
        2,
        "Refused: plan loop p1 has no judged plan (no plan loop p1 in this checkout). "
        "Next: copy the folder docs/loops/p1/plan/ from the checkout that holds it, "
        "or start without --plan-loop.",
    ),
    (
        "plan-loop open",
        open_plan,
        ("start", "build", "--plan-loop", "p1"),
        2,
        "Refused: plan loop p1 has no judged plan (that loop is open). "
        "Next: finish that loop, or start without --plan-loop.",
    ),
    (
        "plan-loop edited",
        edited_plan,
        ("start", "build", "--plan-loop", "p1"),
        2,
        "Refused: plan loop p1 has no judged plan (plan.r1.md is not the plan that was "
        "judged). Next: finish that loop, or start without --plan-loop.",
    ),
    (
        "files but no state",
        files_no_state,
        ("start", "build"),
        2,
        f"Error: {FOLDER} holds files but no loop state. "
        f"Next: move the folder {FOLDER} away, then loop.py start again.",
    ),
    ("dirty", dirty, ("start", "build"), 2, loop.DIRTY),
    (
        "empty diff",
        None,
        ("start", "build"),
        2,
        "Refused: nothing is built yet. Next: build and commit first; loop.py skip is "
        "only for a head with nothing to judge.",
    ),
    (
        "rounds 0",
        blocked_without_rounds,
        ("resume", "--note", "x", "--rounds", "0"),
        2,
        ROUNDS,
    ),
    (
        "rounds 6",
        blocked_with_rounds,
        ("resume", "--note", "x", "--rounds", "6"),
        2,
        ROUNDS,
    ),
    (
        "no round left",
        blocked_without_rounds,
        ("resume", "--note", "x"),
        2,
        "Refused: no round is left. Next: the same command with --rounds N (1 to 5).",
    ),
]


@pytest.mark.parametrize(
    "setup, argv, code, line", [r[1:] for r in REFUSALS], ids=[r[0] for r in REFUSALS]
)
def test_the_refusals(sb, setup, argv, code, line):
    if setup:
        setup(sb)
    run = sb.run(*argv)
    assert run.code == code, run
    assert run.last.endswith(line), run
    assert run.last.split(" ", 1)[0] in ("Refused:", "Error:")
    assert run.last.count("Next:") == 1


def test_a_plan_on_a_detached_head(sb):
    detach(sb)
    run = sb.run("start", "plan", "--name", "x")
    assert run.code == 0, run


BAD_STATES = {
    "a round commit like an option": lambda st: st["rounds"][0].update(
        commit="--output=x"
    ),
    "a round commit of HEAD": lambda st: st["rounds"][0].update(commit="HEAD"),
    "another name": lambda st: st.update(name="feat-2-y"),
    "a plan loop name ../x": lambda st: st.update(
        plan_loop={"name": "../x", "sha256": "0" * 64}
    ),
    "a panel ../x": lambda st: st.update(panel=["../x"]),
    "an outcome won": lambda st: st.update(outcome="won"),
    "a kind x": lambda st: st.update(kind="x"),
    "a base ref HEAD~1": lambda st: st.update(base_ref="HEAD~1"),
    "a mode won": lambda st: st["rounds"][0].update(modes={"general": "won"}),
    "a mode of another role": lambda st: st["rounds"][0].update(
        modes={"tests": "full"}
    ),
    "a read half": lambda st: st["rounds"][0].update(read={"general": "half"}),
    "skipped to its own round": lambda st: st["rounds"][0].update(
        skipped={"general": 1}
    ),
    "tokens -1": lambda st: st["rounds"][0].update(tokens={"general": -1}),
    "tokens over 1e9": lambda st: st["rounds"][0].update(tokens={"general": 10**9 + 1}),
    "fix tokens as text": lambda st: st["rounds"][0].update(fix_tokens="5"),
    "item counts below 0": lambda st: st["rounds"][0].update(
        items={"open": -1, "closed": 0, "new": 0}
    ),
    "item counts missing one": lambda st: st["rounds"][0].update(
        items={"open": 1, "closed": 0}
    ),
    "a pending mode won": lambda st: st.update(
        pending={
            "round": 2,
            "commit": SHA_A,
            "base_sha": SHA_A,
            "modes": {"general": "x"},
        }
    ),
    "final as text": lambda st: st.update(final="yes"),
    "a check that is a number": lambda st: st["items"]["general:I1"].update(check=5),
    "a skip record on an open loop": lambda st: st.update(
        skip={"reason": "x", "files": 1, "lines": 1, "user_ok": False}
    ),
    "a skip of -1 lines": lambda st: st.update(
        outcome="skip",
        skip={"reason": "x", "files": 1, "lines": -1, "user_ok": False},
    ),
    "a skip without user_ok": lambda st: st.update(
        outcome="skip", skip={"reason": "x", "files": 1, "lines": 1}
    ),
    "a skip outcome without a record": lambda st: st.update(outcome="skip"),
}


@pytest.mark.parametrize("spoil", BAD_STATES.values(), ids=BAD_STATES.keys())
def test_a_state_that_does_not_fit(sb, spoil):
    one_round(sb)
    st = sb.state()
    spoil(st)
    sb.put_state(st)
    before = (sb.loopdir() / "state.json").read_bytes()
    run = sb.run("status")
    assert (run.code, run.last) == (
        2,
        f"Error: {FOLDER}/state.json is not a readable loop state. "
        f"Next: move the folder {FOLDER} away, then loop.py start again.",
    )
    assert (sb.loopdir() / "state.json").read_bytes() == before


@pytest.mark.parametrize("command", [("start", "build"), ("skip", "--reason", "x")])
def test_an_off_line_comes_before_the_branch_name(sb, command):
    sb.on_base("CLAUDE.md", "Judge loop: off\n")
    long_branch(sb)
    run = sb.run(*command)
    assert (run.code, run.last) == (
        0,
        "Off: judge loop switched off by CLAUDE.md:1 on main. Next: work without it.",
    )


def test_an_accepted_plan_edited_later(sb):
    sb.start_plan()
    assert sb.judge({"general": nine("I1")}, "plan", "p1").code == 1
    assert sb.run("accept", "--note", "ok").code == 0
    plan = sb.loopdir("plan", "p1")
    (plan / "plan.md").write_text("# Changed later\n")
    sb.change()
    assert sb.run("start", "build", "--plan-loop", "p1").code == 0
    assert (sb.loopdir() / "plan.md").read_bytes() == (plan / "plan.r1.md").read_bytes()


def test_the_keys_of_status_json(sb):
    sb.start_build()
    data = json.loads(sb.run("status", "--json").out)
    assert set(data) >= {
        "kind",
        "name",
        "outcome",
        "round",
        "budget",
        "panel",
        "agents",
        "scores",
        "saved",
        "missing",
        "open",
        "settled",
        "next",
    }


# Files ------------------------------------------------------------------------


def exclude_count(sb):
    path = Path(sb.git("rev-parse", "--git-path", "info/exclude"))
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    return path.read_text().splitlines().count("docs/loops/")


def test_the_exclude_line_is_added_once(sb):
    sb.start_build()
    assert exclude_count(sb) == 1
    assert sb.run("abandon", "--note", "again").code == 0
    sb.change("app.py", 5)
    assert sb.run("start", "build").code == 0
    assert exclude_count(sb) == 1
    tree = sb.tmp / "tree"
    sb.git("worktree", "add", "-q", "-b", "feat/2-y", str(tree))
    sb.mp.chdir(tree)
    sb.change("other.py", 3)
    run = sb.run("start", "build")
    assert run.code == 0, run
    assert exclude_count(sb) == 1
    assert sb.git("status", "--porcelain") == ""


def link_docs(sb, outside):
    (sb.root / "docs").symlink_to(outside)


def link_loops(sb, outside):
    (sb.root / "docs").mkdir()
    (sb.root / "docs" / "loops").symlink_to(outside)


def link_name(sb, outside):
    (sb.root / "docs" / "loops").mkdir(parents=True)
    (sb.root / "docs" / "loops" / NAME).symlink_to(outside)


LINKS = {"docs": link_docs, "docs/loops": link_loops, "the name folder": link_name}


@pytest.mark.parametrize("make", LINKS.values(), ids=LINKS.keys())
def test_a_linked_loop_folder(sb, make):
    outside = sb.tmp / "outside"
    outside.mkdir()
    sb.change()
    make(sb, outside)
    for argv in (("start", "build"), ("status",)):
        run = sb.run(*argv)
        assert run.code == 2, run
        assert run.last.startswith("Error: ")
        assert "is tracked by git or reached through a link." in run.last
    assert list(outside.iterdir()) == []


def test_a_linked_judge_folder(sb):
    sb.start_build()
    outside = sb.tmp / "outside"
    outside.mkdir()
    (sb.loopdir() / "judge").symlink_to(outside)
    run = sb.run("brief")
    assert run.code == 2, run
    assert "is tracked by git or reached through a link." in run.last
    assert list(outside.iterdir()) == []


def test_a_tracked_state(sb):
    sb.start_build()
    sb.git("add", "-f", str(sb.loopdir() / "state.json"))
    sb.git("commit", "-q", "-m", "chore: state")
    run = sb.run("status")
    rel = f"docs/loops/{NAME}/build"
    assert (run.code, run.last) == (
        2,
        f"Error: {rel}/state.json is tracked by git or reached through a link. "
        f"Next: move the folder {rel} away, then loop.py start again.",
    )


def test_a_state_that_cannot_be_read_is_kept(sb):
    sb.start_build()
    path = sb.loopdir() / "state.json"
    rel = f"docs/loops/{NAME}/build"
    path.write_text("{")
    sb.change("app.py", 5)
    for argv in (("start", "build"), ("status",), ("abandon", "--note", "x")):
        run = sb.run(*argv)
        assert (run.code, run.last) == (
            2,
            f"Error: {rel}/state.json is not a readable loop state. "
            f"Next: move the folder {rel} away, then loop.py start again.",
        )
        assert path.read_text() == "{"


def test_a_state_of_another_schema_is_kept(sb):
    sb.start_build()
    st = sb.set_state(schema=2)
    before = (sb.loopdir() / "state.json").read_bytes()
    sb.change("app.py", 5)
    for argv in (("start", "build"), ("status",)):
        run = sb.run(*argv)
        assert (run.code, run.last) == (
            2,
            f"Error: docs/loops/{NAME}/build/state.json was written by another version "
            "of the kit. Next: run the installer.",
        )
    assert (sb.loopdir() / "state.json").read_bytes() == before
    assert st["schema"] == 2


def damaged_notice(rel):
    return (
        f"note: {rel}/state.json is not a readable loop state and is left out. "
        f"Next: move the folder {rel} away."
    )


def test_a_damaged_state_of_another_loop_is_left_out(sb):
    plan_stage(sb, "p1")
    path = sb.loopdir("plan", "p1") / "state.json"
    path.write_text("{")
    notice = damaged_notice("docs/loops/p1/plan")
    sb.change()
    start = sb.run("start", "build")
    assert start.code == 0, start
    assert notice in start.lines
    sb.criteria()
    brief = sb.run("brief")
    assert brief.code == 0, brief
    assert brief.lines[0] == notice
    status = sb.run("status")
    assert status.code == 0, status
    assert status.lines[:2] == [notice, f"Loop: build {NAME} in {FOLDER}/"]
    data = sb.run("status", "--json")
    assert json.loads(data.out)["name"] == NAME
    assert data.err.splitlines() == [notice]
    assert path.read_text() == "{"


@pytest.mark.parametrize("which", [(), ("--kind", "build", "--name", NAME)])
def test_a_damaged_chosen_loop_is_still_refused(sb, which):
    plan_stage(sb, "p1")
    sb.start_build()
    (sb.loopdir() / "state.json").write_text("{")
    run = sb.run("brief", *which)
    assert (run.code, run.last) == (
        2,
        f"Error: {FOLDER}/state.json is not a readable loop state. "
        f"Next: move the folder {FOLDER} away, then loop.py start again.",
    )
    assert damaged_notice(FOLDER) not in run.lines


def test_a_second_start(sb):
    sb.start_build()
    sb.change("app.py", 5)
    run = sb.run("start", "build")
    assert (run.code, run.last) == (
        2,
        "Refused: this loop is not finished (open, round 1 of 5). "
        "Next: loop.py status; loop.py accept or abandon ends it.",
    )
    assert sb.judge({"general": 10}).code == 0
    sb.change("app.py", 6)
    run = sb.run("start", "build")
    assert run.code == 0, run
    assert f"Earlier loop moved to docs/loops/{NAME}/build.1" in run.lines
    old = json.loads((sb.loopdir().parent / "build.1" / "state.json").read_text())
    assert old["outcome"] == "done"
    assert sb.state()["outcome"] == "open"


# Role files -------------------------------------------------------------------


def sections(text):
    out, name = {}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            out[name] = []
        elif name:
            out[name].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


@pytest.mark.parametrize("role", loop.ROLES)
def test_a_role_file_names_its_dimensions_and_the_output(role):
    text = (ROLES_DIR / f"{role}.md").read_text()
    parts = sections(text)
    assert set(parts) == {"Dimensions", "A 10 means", "Output"}, parts.keys()
    dims = re.findall(r"^- `([a-z_]+)`: \S", parts["Dimensions"], re.M)
    assert 3 <= len(dims) <= 20, dims
    for dim in dims:
        assert f"`{dim}`" in parts["Output"], dim
    for key in ("overall", "dimensions", "blocking", "improvements", "still_open"):
        assert f'`"{key}"`' in parts["Output"], key
    for key in ("id", "problem", "evidence", "fix", "check", "read"):
        assert f'`"{key}"`' in parts["Output"], key
    output = " ".join(parts["Output"].split())
    for words in (
        "Score in steps of 0.5.",
        "The score is 10 minus named items: no item, no deduction.",
        "List every gap now, not the top few.",
        "a file and line, or the criterion it misses.",
        "A dimension the work gives you nothing to judge on gets a 10 and no item.",
    ):
        assert words in output, words
    assert "a command and its output" not in output
    assert parts["A 10 means"].strip()
    assert len(text.splitlines()) <= 40


# slug -------------------------------------------------------------------------

SLUGS = [
    ("feat/1-x", "feat-1-x"),
    ("release/v0.1.0", "release-v0.1.0"),
    ("Feat_A.b", "Feat_A.b"),
    ("a//b c", "a-b-c"),
    ("-lead/", "lead"),
    ("fix/\u00fcber", "fix-ber"),
    ("", "branch"),
    ("///", "branch"),
]


def ship_module():
    if not SHIP_PY.is_file():
        pytest.skip("ship.py is not next to this skill")
    return load(SHIP_PY, "ship_for_slug")


@pytest.mark.parametrize("branch, want", SLUGS)
def test_slug_matches_ship(branch, want):
    assert loop.slug(branch) == want
    assert ship_module().slug(branch) == want
