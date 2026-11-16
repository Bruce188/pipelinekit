"""Tests of loop.py: brief, panel, start, base and switch lines."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from loop_fixtures import (
    CASES,
    FULL,
    NAME,
    SHA_A,
    brief_of,
    loop,
    nine,
    orphan_commit,
    panel_line,
    plan_stage,
    result,
)

# brief ------------------------------------------------------------------------


def test_brief_refusals_of_a_plan_in_order(sb):
    assert sb.run("start", "plan", "--name", "p1").code == 0
    run = sb.run("brief")
    assert (run.code, run.last) == (
        2,
        "Refused: docs/loops/p1/plan/criteria.md is missing or empty. "
        "Next: write it, then loop.py brief.",
    )
    sb.criteria("plan", "p1")
    run = sb.run("brief")
    assert (run.code, run.last) == (
        2,
        "Refused: docs/loops/p1/plan/plan.md is missing or empty. "
        "Next: have kit-planner write it, then loop.py brief.",
    )


def test_brief_on_another_branch_records_nothing(sb):
    sb.start_build()
    before = (sb.loopdir() / "state.json").read_bytes()
    sb.git("checkout", "-q", "-b", "feat/9-other")
    run = sb.run("brief", "--kind", "build", "--name", NAME)
    assert run.code == 2
    assert run.last.startswith("Refused: this loop is for feat/1-x, feat/9-other is")
    assert (sb.loopdir(name=NAME) / "state.json").read_bytes() == before
    assert not (sb.loopdir(name=NAME) / "judge").exists()


def test_brief_writes_settled_md_anew(sb):
    sb.start_build()
    sb.run("brief")
    settled = sb.loopdir() / "settled.md"
    assert settled.read_text() == "Nothing is settled.\n"
    settled.write_text("- [general I9] settled by hand\n")
    sb.run("brief")
    assert settled.read_text() == "Nothing is settled.\n"


def test_brief_refuses_an_edited_counted_result(sb):
    sb.start_build()
    assert sb.judge({"general": nine("I1")}).code == 1
    sb.stored("general", n=1).write_bytes(result(10))
    sb.change("app.py", 5)
    run = sb.run("brief")
    assert run.code == 2
    assert run.last == (
        "Error: docs/loops/feat-1-x/build/judge/r1_general.json is not the result that "
        "was counted. Next: tell the user; loop.py abandon, then loop.py start again."
    )


def test_a_diff_over_2_mb_is_cut(sb):
    sb.write("big.txt", "".join(f"line {i:07d} of a big file\n" for i in range(90000)))
    sb.write("small.py", "x = 1\n")
    sb.start_build()
    assert sb.run("brief").code == 0
    data = (sb.loopdir() / "judge" / "r1.diff").read_bytes()
    assert data.endswith(b"\n----- the diff is cut here at 2 MB -----\n")
    head = data.split(b"\n\n", 1)[0].decode().splitlines()
    assert head[0] == "Changed files (added deleted path):"
    assert sorted(row.split(" ", 2)[2] for row in head[1:]) == [
        "app.py",
        "big.txt",
        "small.py",
    ]


def test_git_output_is_read_up_to_its_limit(sb):
    sb.write("big.txt", "y" * 100_000)
    sb.commit()
    git = loop.loop_state.Git(sb.root)
    assert git.capped("show", "HEAD:big.txt", limit=1000) == b"y" * 1001
    assert git.capped("show", "HEAD:big.txt", limit=200_000) == b"y" * 100_000
    with pytest.raises(loop.GitFailed):
        git.capped("show", "HEAD:nosuch.txt", limit=1000)


def test_the_diff_is_read_through_the_limit(sb, monkeypatch):
    calls = []
    real = loop.loop_state.Git.capped

    def spy(self, *args, limit):
        calls.append((args[0], limit))
        return real(self, *args, limit=limit)

    monkeypatch.setattr(loop.loop_state.Git, "capped", spy)
    sb.start_build()
    assert sb.run("brief").code == 0
    assert calls == [("diff", loop.MAX_DIFF)]


def moved_base(sb, how):
    """Two judges; general 10 twice, tests rising; the base moves; round 3 is
    briefed."""
    sb.two_judges()
    sb.start_build()
    assert sb.judge({"general": 10, "tests": result(8, improvements=["T1"])}).code == 1
    sb.change("app.py", 4, tag="fix")
    assert sb.judge({"general": 10, "tests": nine("T1")}).code == 1
    sb.on_base("base.txt", "on the base\n")
    if how == "merge":
        sb.git("merge", "-q", "--no-edit", "origin/main")
    else:
        sb.git("rebase", "-q", "origin/main")
    return sb.run("brief")


@pytest.mark.parametrize("how", ["merge", "rebase"])
def test_the_base_moved_between_rounds(sb, how):
    run = moved_base(sb, how)
    assert run.code == 0, run
    new = sb.git("merge-base", "HEAD", "origin/main")
    old = sb.state()["rounds"][-1]["base_sha"]
    assert f"base moved: {old[:7]} -> {new[:7]}" in run.lines
    assert not any(": skipped, " in line for line in run.lines)
    assert sb.state()["pending"]["modes"] == {"general": "full", "tests": "full"}
    head = (sb.loopdir() / "judge" / "r3.diff").read_text().split("\n\n", 1)[0]
    assert "base.txt" not in head and "app.py" in head
    assert sb.save("general", 10).code == 0
    assert sb.save("tests", result(9.5, improvements=["T1"])).code == 0
    assert sb.run("round").code == 1
    last = sb.state()["rounds"][-1]
    assert last["base_sha"] == new
    assert last["modes"] == {"general": "full", "tests": "full"}


def test_a_branch_behind_its_base_at_start(sb):
    sb.on_base("base.txt", "ahead\n")
    sb.start_build()
    run = sb.run("brief")
    assert not any(line.startswith("base moved:") for line in run.lines)
    fork = sb.git("merge-base", "HEAD", "origin/main")
    assert sb.state()["pending"]["base_sha"] == fork
    sb.save("general", 9)
    sb.run("round")
    assert sb.state()["rounds"][0]["base_sha"] == fork


def test_a_base_with_another_history(sb):
    sb.start_build()
    sb.git("update-ref", "refs/remotes/origin/main", orphan_commit(sb))
    run = sb.run("brief")
    assert run.code == 2
    assert run.last == (
        "Refused: feat/1-x and main share no history. Next: loop.py abandon, then "
        "loop.py start build with --base and the right base branch."
    )


def test_a_file_name_with_a_newline_is_one_row(sb):
    sb.write("a\ndiff --git a/x b/x", "text\n")
    sb.start_build()
    assert sb.run("brief").code == 0
    head = (sb.loopdir() / "judge" / "r1.diff").read_text().split("\n\n", 1)[0]
    rows = head.splitlines()[1:]
    assert len(rows) == 2, rows
    assert len([r for r in rows if r.endswith(" (name cleaned)")]) == 1


def test_plan_r1_is_the_plan(sb):
    sb.start_plan()
    assert sb.run("brief").code == 0
    folder = sb.loopdir("plan", "p1")
    assert (folder / "plan.r1.md").read_bytes() == (folder / "plan.md").read_bytes()


def test_the_layout_of_a_brief(sb):
    sb.start_build()
    st = sb.state()
    st["notes"] = [{"round": 0, "action": "accept", "text": "NOTE-TEXT-HERE"}]
    sb.put_state(st)
    run = sb.run("brief")
    assert "NOTE-TEXT-HERE" not in run.out
    above, prompt = brief_of(run, "general", 1)
    rel = "docs/loops/feat-1-x/build"
    assert above == [
        "Start: kit-judge",
        f"Repository: {sb.root}",
        f"Answer file: {rel}/judge/in/r1_general.txt",
    ]
    assert prompt[0] == f"Repository: {sb.root}"
    text = "\n".join(prompt)
    for part in (
        "roles/general.md",
        f"{rel}/judge/r1.diff",
        f"{rel}/criteria.md",
        f"{rel}/settled.md",
        "there is no result of yours before it",
        '"overall": a number from 0 to 10',
    ):
        assert part in text, part
    sb.save("general", nine("I1"))
    sb.run("round")
    sb.change("app.py", 4)
    run = sb.run("brief", "--agents", "fallback")
    above, prompt = brief_of(run, "general", 2)
    assert above[0] == "Start: general-purpose, model fable"
    assert prompt[0].startswith("Read `") and prompt[0].endswith(
        "kit-judge.md` and follow it as your instructions."
    )
    assert prompt[1] == f"Repository: {sb.root}"
    assert f"Your last counted result (round 1): {rel}/judge/r1_general.json" in prompt
    assert "NOTE-TEXT-HERE" not in run.out


# Panel ------------------------------------------------------------------------


def size_of(*rows, subs=()):
    return loop.Size(list(rows), list(subs))


def spread(lines, files):
    """Rows of `files` files that change `lines` lines in all."""
    each, extra = divmod(lines, files)
    return [(f"src/f{i}.py", each + (i < extra), 0) for i in range(files)]


def test_size_by_lines_and_files():
    small = size_of(*spread(400, 2))
    assert (small.full, small.reason) == (False, "auto: 400 changed lines in 2 files")
    big = size_of(*spread(401, 2))
    assert (big.full, big.reason) == (True, "auto: 401 changed lines")
    many = size_of(*spread(15, 15))
    assert (many.full, many.reason) == (False, "auto: 15 changed lines in 15 files")
    more = size_of(*spread(16, 16))
    assert (more.full, more.reason) == (True, "auto: 16 files")
    one = size_of(("a.py", 10, 0))
    assert (one.full, one.exempt) == (False, True)
    assert (
        one.reason
        == "auto: within the exempt size (loop.py skip --reason would also do)"
    )
    assert size_of(("a.py", 6, 5)).exempt is False
    assert size_of(("a.md", 300, 0), ("b.rst", 50, 0)).exempt is True


def test_a_large_documentation_diff_is_exempt():
    rows = [(f"pages/p{i}.md", 25 + (i == 0), 0) for i in range(16)]
    size = size_of(*rows)
    assert (size.lines, size.files) == (401, 16)
    assert (size.full, size.exempt) == (False, True)
    assert size.reason == (
        "auto: within the exempt size (loop.py skip --reason would also do)"
    )


SENSITIVE = [f"src/my_{word}.py" for word in sorted(loop.SENSITIVE_WORDS)] + [
    ".github/workflows/x.yml",
    "CLAUDE.md",
    "sub/claude.md",
    "tools/SKILL.md",
    ".mcp.json",
    ".claude/settings.json",
    "agents/x.md",
]
NOT_SENSITIVE = [
    "src/author.py",
    "docs/installation.md",
    "webhook_client.py",
    "uninstall.sh",
]


def test_sensitive_paths():
    for path in SENSITIVE:
        assert loop.is_sensitive(path), path
        size = size_of((path, 1, 0))
        assert size.full, path
        assert size.reason.startswith("auto: sensitive path "), path
    for path in NOT_SENSITIVE:
        assert not loop.is_sensitive(path), path
        assert not size_of((path, 1, 0)).full, path


def test_names_with_a_space_and_a_newline(sb):
    sb.write("a b.py", "x\n")
    sb.write("c\nd.py", "y\n")
    run = sb.start_build(lines=0)
    assert panel_line(run) == "Panel: general (auto: 2 changed lines in 2 files)"


def test_a_rename_counts_as_two_files(sb):
    sb.change("old.py", 3)
    sb.git("push", "-q", "origin", "HEAD:main")
    sb.git("mv", "old.py", "new.py")
    sb.commit()
    run = sb.start_build(lines=0)
    assert run.lines[run.lines.index(panel_line(run)) - 1] == (
        "Measured: 2 files, 6 changed lines"
    )


def test_a_binary_file_gets_the_full_panel(sb):
    sb.write("img.bin", b"\x00\x01\x02\x00")
    run = sb.start_build(lines=0)
    assert panel_line(run) == f"Panel: {FULL} (auto: img.bin has no line count)"


def test_a_branch_that_turns_off_diffs(sb):
    sb.write(".gitattributes", "* -diff\n")
    sb.write("data.txt", "".join(f"row {i}\n" for i in range(500)))
    run = sb.start_build(lines=0)
    assert panel_line(run) == f"Panel: {FULL} (auto: .gitattributes has no line count)"
    assert sb.run("brief").code == 0
    diff = (sb.loopdir() / "judge" / "r1.diff").read_text()
    assert "+row 499" in diff


def test_a_path_the_base_marks_without_diff(sb):
    sb.on_base(".gitattributes", "data.txt -diff\n")
    sb.git("merge", "-q", "--ff-only", "origin/main")
    sb.change("data.txt", 1)
    run = sb.run("skip", "--reason", "small")
    assert run.code == 3, run
    run = sb.start_build(lines=0)
    assert panel_line(run) == f"Panel: {FULL} (auto: data.txt has no line count)"


def test_a_submodule_pointer_alone(sb):
    sb.git("update-index", "--add", "--cacheinfo", f"160000,{SHA_A},sub")
    sb.git("commit", "-q", "-m", "feat: sub")
    (sb.root / "sub").mkdir()  # how a submodule that is not checked out looks
    run = sb.run("skip", "--reason", "small")
    assert run.code == 3, run
    run = sb.start_build(lines=0)
    assert panel_line(run) == f"Panel: {FULL} (auto: sub is a submodule pointer)"


def test_an_off_line_added_on_the_branch(sb):
    sb.change("CLAUDE.md", 0)
    sb.write("CLAUDE.md", "Judge loop: off\n")
    sb.commit()
    run = sb.start_build(lines=0)
    assert panel_line(run) == f"Panel: {FULL} (auto: sensitive path CLAUDE.md)"
    assert "line 1 of CLAUDE.md is not on main yet: not used" in run.lines


def test_a_small_change_gets_one_judge(sb):
    run = sb.start_build()
    assert panel_line(run) == (
        "Panel: general (auto: within the exempt size "
        "(loop.py skip --reason would also do))"
    )


@pytest.mark.parametrize(
    "flag, panel", [("single", ["general"]), ("full", list(loop.FULL_PANEL))]
)
def test_the_panel_flag(sb, flag, panel):
    sb.write("big.py", "".join(f"v{i} = {i}\n" for i in range(450)))
    sb.start_build("--panel", flag)
    st = sb.state()
    assert (st["panel"], st["panel_forced"], st["panel_reason"]) == (
        panel,
        flag,
        f"--panel {flag}",
    )


@pytest.mark.parametrize(
    "line, flags, panel, said",
    [
        ("correctness, tests", (), ["correctness", "tests"], None),
        ("correctness, tests", ("--panel", "full"), list(loop.FULL_PANEL), None),
        ("tests, Tests", (), ["tests"], None),
        (", ".join(loop.ROLES), (), list(loop.ROLES), None),
        (
            "nobody, nothing",
            (),
            ["general"],
            "switch line CLAUDE.md:1 on main (Judges) is not valid: not used",
        ),
    ],
    ids=["alone", "flag wins", "duplicate", "seven", "no valid name"],
)
def test_the_judges_line(sb, line, flags, panel, said):
    sb.two_judges(line)
    run = sb.start_build(*flags)
    assert sb.state()["panel"] == panel
    if flags:
        assert sb.state()["panel_forced"] == "full"
    if said:
        assert said in run.lines
        assert "CLAUDE.md:1 on main: nobody is not a role: dropped" in run.lines


def test_the_judges_line_in_a_plan_loop(sb):
    sb.two_judges("security")
    sb.start_plan()
    assert sb.state("plan", "p1")["panel"] == ["security"]
    assert sb.state("plan", "p1")["panel_reason"] == "Judges line"


def test_the_panel_does_not_change_after_start(sb):
    sb.start_build()
    sb.two_judges("correctness, tests")
    assert sb.judge({"general": nine("I1")}).code == 1
    assert sb.state()["panel"] == ["general"]


# start output -----------------------------------------------------------------


def test_the_start_output_of_a_build(sb):
    sb.two_judges("correctness, tests")
    sb.on_base(".claude/CLAUDE.md", "Judge rounds: 3\nJudge rounds: 0\n")
    run = sb.start_build()
    rel = "docs/loops/feat-1-x/build"
    assert run.lines[0] == f"Repository: {sb.root}"
    assert f"Loop: build feat-1-x in {rel}/" in run.lines
    assert (
        "Base: main, read from refs/remotes/origin/main (the default name main)"
        in run.lines
    )
    kept = [line for line in run.lines if ": result kept in " in line]
    assert kept == [
        f"{role}: result kept in {rel}/judge/r1_{role}.json (written by loop.py save; "
        "the answer file is named in the brief)"
        for role in ("correctness", "tests")
    ]
    assert "Budget: 3 rounds" in run.lines
    assert "switch used: Judges: correctness, tests (CLAUDE.md:1 on main)" in run.lines
    assert "switch used: Judge rounds: 3 (.claude/CLAUDE.md:1 on main)" in run.lines
    assert (
        "switch line .claude/CLAUDE.md:2 on main (Judge rounds) is not valid: "
        "not used" in run.lines
    )
    assert (
        "Expected cost: 2 judge runs per round, at most 3 rounds (6 judge runs), "
        "one fix pass between rounds"
    ) in run.lines
    assert "Agents: kit" in run.lines
    assert loop.FALLBACK_SENTENCE not in run.lines
    assert (
        run.lines[-2] == f"Criteria: write the acceptance criteria to {rel}/criteria.md"
    )
    assert run.last == (
        "Started: build loop feat-1-x, 2 judges, at most 3 rounds. "
        "Next: write criteria.md, then loop.py brief."
    )


def test_the_start_output_of_a_plan(sb):
    run = sb.run("start", "plan", "--name", "p1", "--agents", "fallback")
    assert run.code == 0
    assert "Budget: 5 rounds" in run.lines
    assert "Agents: fallback" in run.lines
    assert loop.FALLBACK_SENTENCE in run.lines
    assert run.last == (
        "Started: plan loop p1, 1 judge, at most 5 rounds. Next: write criteria.md, "
        "have a general-purpose agent write plan.md, then loop.py brief."
    )


def test_the_start_output_with_a_plan_loop(sb):
    plan_stage(sb)
    sb.change()
    run = sb.run("start", "build", "--plan-loop", "p1")
    assert run.code == 0, run
    rel = "docs/loops/feat-1-x/build"
    assert run.lines[-2] == (
        f"plan.md and criteria.md copied from plan loop p1; add to {rel}/criteria.md "
        "before the first brief if needed"
    )
    assert run.last == (
        "Started: build loop feat-1-x, 1 judge, at most 5 rounds. "
        "Next: loop.py brief --kind build --name feat-1-x."
    )
    plan = sb.loopdir("plan", "p1")
    assert (sb.loopdir() / "criteria.md").read_bytes() == (
        plan / "criteria.md"
    ).read_bytes()
    assert (sb.loopdir() / "plan.md").read_bytes() == (plan / "plan.r1.md").read_bytes()


# Base -------------------------------------------------------------------------


def develop(sb):
    sb.git("push", "-q", "origin", "main:develop")


def gh_develop(sb):
    develop(sb)
    sb.fake_gh('{"baseRefName": "develop"}')


def gh_fails(sb):
    sb.fake_gh(code=1, err="something went wrong")


def no_pull_request(sb):
    sb.fake_gh(code=1, err="no pull requests found for branch")


def origin_head(sb):
    develop(sb)
    sb.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")


def only_local(name):
    def apply(sb):
        sb.git("remote", "remove", "origin")
        if name != "main":
            sb.git("branch", "-m", "main", name)

    return apply


def other_remote(sb):
    sb.git("remote", "rename", "origin", "up")
    sb.git("config", "branch.feat/1-x.remote", "up")


def gh_times_out(sb):
    sb.fake_gh('{"baseRefName": "main"}')
    real = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd[0] == sb.gh:
            raise subprocess.TimeoutExpired(cmd, loop.GH_TIMEOUT)
        return real(cmd, *args, **kwargs)

    sb.mp.setattr(subprocess, "run", run)


GH_NOTES = [
    ("timeout", gh_times_out, f"gave no answer in {loop.GH_TIMEOUT} seconds"),
    ("not json", lambda sb: sb.fake_gh("a page of text"), "gave no JSON"),
    ("no name", lambda sb: sb.fake_gh('{"title": "x"}'), "gave no base branch"),
    (
        "bad name",
        lambda sb: sb.fake_gh('{"baseRefName": "a b"}'),
        "gave no base branch",
    ),
]


@pytest.mark.parametrize("how, setup, why", GH_NOTES, ids=[g[0] for g in GH_NOTES])
def test_gh_that_gives_no_base_says_so(sb, how, setup, why):
    setup(sb)
    run = sb.start_build()
    assert f"note: gh pr view {why}, so the pull request does not set the base" in (
        run.lines
    ), run
    assert sb.state()["base"] == "main"


@pytest.mark.parametrize("setup", [no_pull_request, gh_fails, gh_develop])
def test_gh_that_answers_gives_no_note(sb, setup):
    setup(sb)
    run = sb.start_build()
    assert not [line for line in run.lines if "gh pr view" in line], run


BASES = [
    (
        "--base wins",
        gh_develop,
        ("--base", "main"),
        "main",
        "--base",
        "refs/remotes/origin/main",
    ),
    (
        "gh answers",
        gh_develop,
        (),
        "develop",
        "the pull request",
        "refs/remotes/origin/develop",
    ),
    (
        "gh fails",
        gh_fails,
        (),
        "main",
        "the default name main",
        "refs/remotes/origin/main",
    ),
    (
        "no gh",
        lambda sb: None,
        (),
        "main",
        "the default name main",
        "refs/remotes/origin/main",
    ),
    (
        "no pull request",
        no_pull_request,
        (),
        "main",
        "the default name main",
        "refs/remotes/origin/main",
    ),
    (
        "origin/HEAD",
        origin_head,
        (),
        "develop",
        "refs/remotes/origin/HEAD",
        "refs/remotes/origin/develop",
    ),
    (
        "only main",
        only_local("main"),
        (),
        "main",
        "the default name main",
        "refs/heads/main",
    ),
    (
        "only master",
        only_local("master"),
        (),
        "master",
        "the default name master",
        "refs/heads/master",
    ),
    (
        "remote up",
        other_remote,
        (),
        "main",
        "the default name main",
        "refs/remotes/up/main",
    ),
    (
        "--base origin/main",
        lambda sb: None,
        ("--base", "origin/main"),
        "main",
        "--base",
        "refs/remotes/origin/main",
    ),
]


@pytest.mark.parametrize(
    "how, flags, base, source, ref", [b[1:] for b in BASES], ids=[b[0] for b in BASES]
)
def test_the_base(sb, how, flags, base, source, ref):
    how(sb)
    run = sb.start_build(*flags)
    st = sb.state()
    assert (st["base"], st["base_source"], st["base_ref"]) == (base, source, ref)
    assert f"Base: {base}, read from {ref} ({source})" in run.lines


def test_no_base_found(sb):
    only_local("trunk")(sb)
    sb.change()
    run = sb.run("start", "build")
    assert (run.code, run.last) == (
        2,
        "Refused: no base branch found. Next: the same command with --base <branch>.",
    )
    run = sb.run("start", "plan", "--name", "p1")
    assert run.code == 0
    assert "no base branch found: only the user-level switch lines count" in run.lines


@pytest.mark.parametrize("command", [("start", "build"), ("skip", "--reason", "x")])
def test_an_orphan_branch(sb, command):
    sb.git("checkout", "-q", "--orphan", "feat/2-o")
    sb.change()
    run = sb.run(*command)
    assert (run.code, run.last) == (
        2,
        "Refused: feat/2-o and main share no history. "
        "Next: the same command with --base and the right base branch.",
    )


def test_a_local_base_behind_its_remote(sb):
    sb.on_base("CLAUDE.md", "Judge rounds: 2\n")
    sb.git("branch", "-f", "main", "main~1")
    run = sb.start_build()
    assert (
        "Base: main, read from refs/remotes/origin/main (the default name main)"
        in run.lines
    )
    assert sb.state()["budget"] == 2
    assert sb.state()["base_sha"] == sb.git("merge-base", "HEAD", "origin/main")


NOT_A_BRANCH = "is not a branch name. Next: --base <branch>."
BASE_OPTIONS = [
    (("--base=--output=x",), f"Refused: --output?x {NOT_A_BRANCH}"),
    (
        ("--base", "-x"),
        "Refused: these arguments do not fit loop.py start. "
        "Next: loop.py start --help.",
    ),
    (("--base=" + "a " * 30,), f"Refused: {'a?' * 20} {NOT_A_BRANCH}"),
]


@pytest.mark.parametrize("flags, last", BASE_OPTIONS, ids=["output", "-x", "long"])
def test_a_base_that_is_an_option(sb, flags, last):
    sb.change()
    run = sb.run("start", "build", *flags)
    assert (run.code, run.last) == (2, last), run
    assert not (sb.root / "docs").exists()
    assert not (sb.root / "x").exists()


@pytest.mark.parametrize("field, value", [("base", "-x"), ("commit", "HEAD")])
def test_a_state_with_an_option_for_a_ref(sb, field, value):
    sb.start_build()
    sb.set_state(**{field: value})
    run = sb.run("status")
    assert run.code == 2
    assert run.last.startswith(
        "Error: docs/loops/feat-1-x/build/state.json is not a readable"
    )


# Switch lines -----------------------------------------------------------------


def test_switch_cases():
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 30
    for case in cases:
        assert loop.first_switches(case["text"]) == case["switches"], case["name"]


def user_md(text):
    path = Path(os.environ["CLAUDE_HOME"]) / "CLAUDE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.mark.parametrize("how", ["a link", "over 1 MB"])
def test_a_user_file_that_is_not_read(sb, how):
    path = Path(os.environ["CLAUDE_HOME"]) / "CLAUDE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if how == "a link":
        target = sb.tmp / "dotfiles.md"
        target.write_text("Judges: tests\n")
        path.symlink_to(target)
    else:
        path.write_text("Judges: tests\n" + "x" * loop.MAX_TEXT_FILE)
    sb.change()
    run = sb.run("start", "build")
    assert run.code == 0, run
    assert "$CLAUDE_HOME/CLAUDE.md is a link or over 1 MB: not used" in run.lines
    assert "Panel: tests (Judges line)" not in run.lines


@pytest.mark.parametrize("how", ["unset", "empty"])
def test_the_user_file_without_claude_home(sb, how):
    if how == "unset":
        sb.mp.delenv("CLAUDE_HOME")
    else:
        sb.mp.setenv("CLAUDE_HOME", "")
    path = sb.home / ".claude" / "CLAUDE.md"
    path.parent.mkdir(parents=True)
    path.write_text("Judges: tests\n")
    sb.change()
    run = sb.run("start", "build")
    assert run.code == 0, run
    assert "switch used: Judges: tests (~/.claude/CLAUDE.md:1)" in run.lines
    assert sb.state()["panel"] == ["tests"]


def on_local_main(sb, text):
    sb.git("checkout", "-q", "main")
    sb.write("CLAUDE.md", text)
    sb.commit("docs: switches")
    sb.git("checkout", "-q", "feat/1-x")


KEYS = {
    "Judge loop": ("Judge loop: off\n", "Judge loop: off\n"),
    "Judge rounds": ("Judge rounds: 3\n", "Judge rounds: 4\n"),
    "Judges": ("Judges: tests\n", "Judges: security\n"),
}
PLACES = {
    "base": ("CLAUDE.md:1 on main", None),
    "checkout": (None, "line 1 of CLAUDE.md is not on main yet: not used"),
    "user": ("$CLAUDE_HOME/CLAUDE.md:1", None),
    "base and user": ("CLAUDE.md:1 on main", None),
    "no remote ref": (
        None,
        "no refs/remotes/origin/main: no switch line of the project counts",
    ),
    "no remote": ("CLAUDE.md:1 on main", None),
}


def place_line(sb, where, line, other):
    if where in ("base", "base and user"):
        sb.on_base("CLAUDE.md", line)
    if where == "base and user":
        user_md(other)
    elif where == "user":
        user_md(line)
    elif where == "checkout":
        sb.write("CLAUDE.md", line)
        sb.commit()
    elif where == "no remote ref":
        on_local_main(sb, line)
        sb.git("update-ref", "-d", "refs/remotes/origin/main")
    elif where == "no remote":
        sb.git("remote", "remove", "origin")
        on_local_main(sb, line)


@pytest.mark.parametrize("where", list(PLACES))
@pytest.mark.parametrize("key", list(KEYS))
def test_where_a_switch_line_counts(sb, key, where):
    line, other = KEYS[key]
    place_line(sb, where, line, other)
    used, said = PLACES[where]
    sb.change()
    run = sb.run("start", "build")
    if said:
        assert said in run.lines, run
    if key == "Judge loop":
        if used:
            assert run.code == 0
            assert run.last == (
                f"Off: judge loop switched off by {used}. Next: work without it."
            )
            assert not (sb.root / "docs").exists()
        else:
            assert run.last.startswith("Started: "), run
        return
    assert run.code == 0, run
    st = sb.state()
    value = st["budget"] if key == "Judge rounds" else st["panel"]
    if not used:
        assert value == (
            5
            if key == "Judge rounds"
            else ["general"]
            if where != "checkout"
            else list(loop.FULL_PANEL)
        )
        return
    assert value == (3 if key == "Judge rounds" else ["tests"])
    assert f"switch used: {line.strip()} ({used})" in run.lines
    if where == "base and user":
        assert (
            f"switch line $CLAUDE_HOME/CLAUDE.md:1 ({key}): an earlier line wins, "
            "not used"
        ) in run.lines


def test_off_on_the_base_writes_nothing(sb):
    sb.on_base("CLAUDE.md", "Judge loop: off\n")
    sb.change()
    exclude = Path(sb.git("rev-parse", "--git-path", "info/exclude"))
    before = exclude.read_bytes() if exclude.exists() else None
    for command in (
        ("start", "build"),
        ("start", "plan", "--name", "p1"),
        ("skip", "--reason", "x"),
    ):
        run = sb.run(*command)
        assert run.code == 0, run
        assert run.last == (
            "Off: judge loop switched off by CLAUDE.md:1 on main. "
            "Next: work without it."
        )
    assert not (sb.root / "docs").exists()
    assert (exclude.read_bytes() if exclude.exists() else None) == before
