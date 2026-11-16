"""The judged gate: the build was judged before the acceptance test."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import ship_judged
from ship_fixtures import BRANCH, SHIP, gates, last_line, refused, ship

SLUG = "feat-1-thing"
RECORD = f"docs/loops/{SLUG}/build/state.json"
MOVE = f"move the folder docs/loops/{SLUG}/build away and judge again"
UNREADABLE = f"not a readable judge record ({RECORD}): {MOVE}"
NO_RECORD = (
    f"no judge record ({RECORD}, in this checkout): run the judge loop "
    "(loop.py start build), or loop.py skip --reason for a change with nothing "
    "to judge"
)
LOOP = SHIP.parents[1] / "judge-loop" / "loop.py"
SWITCH_CASES = SHIP.parents[1] / "judge-loop" / "tests" / "switch_cases.json"
ROOT = SHIP.parents[3]


def judged(sb, **env):
    done = sb.ship("status", "--json", **env)
    return gates(done)["judged"]


def stops(sb):
    return json.loads(sb.ship("status", "--json").stdout)["stop"]


def detail(sb, **env):
    return judged(sb, **env)["detail"]


def short(sb, ref="HEAD"):
    return sb.git("rev-parse", "--short=7", ref)


# ---------------------------------------------------------------- the gate in place


def test_the_judged_gate_stands_just_before_tested(sb):
    names = list(gates(sb.ship("status", "--json")))
    assert names.index("judged") == names.index("tested") - 1


def test_a_passed_test_without_a_judge_record_is_not_merged(sb):
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 0, done.stderr
    done = refused(sb, "judged", 1)
    assert last_line(done) == f"Not merged: judged: {NO_RECORD}."


def test_a_judged_and_tested_branch_merges(sb):
    sb.passed()
    done = sb.ship("merge", "--grace", "0")
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(sb.calls("pr merge")) == 1


def test_without_a_pull_request_the_record_is_still_read(sb):
    sb.state(pr=None)
    assert detail(sb) == NO_RECORD
    sb.judged()
    assert detail(sb) == f"done, 10 from 1 judge in 1 round on {short(sb)}"


# ---------------------------------------------------------------- Judge loop: off


@pytest.mark.parametrize("rel", ["CLAUDE.md", ".claude/CLAUDE.md"])
def test_off_on_the_base_branch_passes(sb, rel):
    text = "# Project\n\nJudge loop: off\n"
    sb.change(rel, text, text + "More.\n")
    gate = judged(sb)
    assert gate["state"] == "pass"
    assert gate["detail"] == f"off ({rel}:3 on main)"


def test_off_only_on_the_branch_does_not_count(sb):
    sb.change("CLAUDE.md", "# Project\n", "Judge loop: off\n")
    assert detail(sb) == NO_RECORD


def test_off_inside_a_code_block_does_not_count(sb):
    text = "```\nJudge loop: off\n```\n"
    sb.change("CLAUDE.md", text, text + "More.\n")
    assert detail(sb) == NO_RECORD


def test_off_after_blank_lines_on_the_base_branch_names_its_line(sb):
    text = "\n\nJudge loop: off\n"
    sb.change("CLAUDE.md", text, text + "More.\n")
    assert detail(sb) == "off (CLAUDE.md:3 on main)"


def test_an_indented_off_line_on_the_base_branch_is_code(sb):
    text = "    Judge loop: off\n"
    sb.change("CLAUDE.md", text, text + "More.\n")
    assert detail(sb) == NO_RECORD


def test_a_base_file_over_a_megabyte_is_not_read(sb):
    text = "Judge loop: off\n" + "\u00e9" * 600_000 + "\n"
    sb.change("CLAUDE.md", text, text + "More.\n")
    assert detail(sb) == NO_RECORD


def test_off_in_the_user_file_under_claude_home(sb):
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    (home / "CLAUDE.md").write_text("Judge loop: OFF\n")
    assert detail(sb) == "off ($CLAUDE_HOME/CLAUDE.md:1)"


def test_off_in_the_user_file_under_home(sb):
    home = Path(sb.env["HOME"]) / ".claude"
    home.mkdir()
    (home / "CLAUDE.md").write_text("# Me\n\nJudge loop: off\n")
    assert detail(sb, CLAUDE_HOME="") == "off (~/.claude/CLAUDE.md:3)"


def test_a_linked_user_file_is_not_read(sb):
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    target = sb.tmp / "elsewhere.md"
    target.write_text("Judge loop: off\n")
    (home / "CLAUDE.md").symlink_to(target)
    assert detail(sb) == NO_RECORD


def test_the_kit_template_as_user_file_does_not_switch_the_judge_off(sb):
    template = SHIP.parents[2] / "CLAUDE.md.template"
    if not template.exists():
        pytest.skip("not running from the repository")
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    (home / "CLAUDE.md").write_text(template.read_text())
    assert detail(sb) == NO_RECORD


def test_the_switch_rule_is_the_judge_loops(sb):
    if not SWITCH_CASES.exists():
        pytest.skip("not running from the repository")
    cases = json.loads(SWITCH_CASES.read_text())["cases"]
    assert len(cases) >= 30
    for case in cases:
        assert ship_judged.first_switches(case["text"]) == case["switches"], case[
            "name"
        ]


# ---------------------------------------------------------------- the record's path


def test_a_branch_name_that_cannot_name_a_record(sb):
    sb.git("checkout", "-q", "-b", "feat/" + "a" * 90)
    sb.state(pr=None)
    assert detail(sb) == "the branch name cannot name a judge record: rename the branch"


def test_an_off_line_comes_before_the_branch_name(sb):
    sb.git("checkout", "-q", "-b", "feat/" + "a" * 90)
    sb.state(pr=None)
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    (home / "CLAUDE.md").write_text("Judge loop: off\n")
    assert judged(sb) == {
        "gate": "judged",
        "state": "pass",
        "detail": "off ($CLAUDE_HOME/CLAUDE.md:1)",
        "hints": [],
    }


@pytest.mark.parametrize(
    "level",
    ["docs", "docs/loops", f"docs/loops/{SLUG}", f"docs/loops/{SLUG}/build", RECORD],
)
def test_a_record_reached_through_a_link_fails(sb, level):
    path = sb.judged()
    moved = sb.tmp / "moved"
    (sb.work / level).rename(moved)
    (sb.work / level).symlink_to(moved)
    assert path.exists()
    assert detail(sb) == (
        f"the judge record is reached through a link ({RECORD}): replace the "
        f"link with a plain folder, then {MOVE}"
    )


@pytest.mark.parametrize("rel", ["docs/loops/x/notes.md", "DOCS/Loops/x/notes.md"])
def test_tracked_files_under_docs_loops_fail(sb, rel):
    file = sb.work / rel
    file.parent.mkdir(parents=True)
    file.write_text("x\n")
    sb.git("add", "-f", "--", rel)
    sb.git("commit", "-q", "-m", "chore: notes")
    sb.judged()
    assert detail(sb) == (
        "files under docs/loops are tracked by git; the judge record must be a "
        "local file: git rm -r --cached docs/loops, then judge again"
    )


def gate_with(sb, monkeypatch, failing, answer):
    """The gate in this process, where the git calls `failing` picks give `answer`."""
    monkeypatch.setenv("CLAUDE_HOME", sb.env["CLAUDE_HOME"])

    def try_git(*args):
        if failing(args):
            return answer
        return ship.run(["git", *args], cwd=sb.work)

    repo = SimpleNamespace(
        root=sb.work, branch=BRANCH, remote="origin", try_git=try_git
    )
    found = ship_judged.judged_gate(repo, sb.head(), "main")
    assert found["state"] == "fail"
    return found["detail"]


GIT_FAILS = (128, "", "hint: x\nfatal: bad object")


def test_a_git_failure_is_told_apart_from_no_tracked_files(sb, monkeypatch):
    sb.judged()
    found = gate_with(
        sb,
        monkeypatch,
        lambda args: args[0] == "ls-files",
        (128, "", "hint: x\nfatal: bad index file"),
    )
    assert found == (
        "git ls-files could not say whether files under docs/loops are tracked: "
        "fatal: bad index file"
    )


# ---------------------------------------------------------------- reading the record


def test_a_folder_where_the_record_should_be_is_unreadable(sb):
    (sb.work / RECORD).mkdir(parents=True)
    assert detail(sb) == UNREADABLE


def test_a_record_over_five_megabytes_is_unreadable(sb):
    path = sb.judged()
    with path.open("a") as fh:
        fh.write(" " * (5 * 1024 * 1024))
    assert detail(sb) == UNREADABLE


BAD_FIELDS = {
    "budget is a bool": {"budget": True},
    "items is a list": {"items": []},
    "an item is a string": {"items": {"I1": "x"}},
    "an item has no open": {"items": {"I1": {"kind": "blocking", "settled": {}}}},
    "raised_again is text": {
        "items": {
            "I1": {
                "kind": "blocking",
                "open": True,
                "settled": {"round": 1, "raised_again": "1"},
            }
        }
    },
    "a switch is a string": {"switches": ["Judges: x"]},
    "panel is text": {"panel": "general"},
    "the commit is not a hash": {"commit": "HEAD"},
    "the commit is an option": {"commit": "-x"},
    "an unknown outcome": {"outcome": "merged"},
    "an unknown kind": {"kind": "x;y"},
    "a skip without counts": {"outcome": "skip", "skip": {"reason": "x"}},
}


@pytest.mark.parametrize("fields", BAD_FIELDS.values(), ids=BAD_FIELDS.keys())
def test_a_record_with_a_wrong_field_is_unreadable(sb, fields):
    sb.judged(**fields)
    assert detail(sb) == UNREADABLE


@pytest.mark.parametrize("text", ["{", "[]", '{"schema": "1"}', "\xff"])
def test_a_record_that_is_not_a_json_object_is_unreadable(sb, text):
    path = sb.judged()
    path.write_bytes(text.encode("latin-1"))
    assert detail(sb) == UNREADABLE


def test_a_record_of_another_schema(sb):
    sb.judged(schema=2)
    assert detail(sb) == (
        f"the judge record {RECORD} was written by another version of the kit: "
        "run the installer"
    )


def test_a_plan_record(sb):
    sb.judged(kind="plan")
    assert detail(sb) == f"the record {RECORD} is for a plan loop: {MOVE}"


@pytest.mark.parametrize(
    ("branch", "shown"),
    [("feat/2-other", "feat/2-other"), ("feat/\x1b[2J", "another branch")],
)
def test_a_record_for_another_branch(sb, branch, shown):
    sb.judged(branch=branch)
    assert detail(sb) == f"the record {RECORD} is for {shown}: {MOVE}"


@pytest.mark.parametrize(
    ("outcome", "tail"),
    [
        (
            "skip",
            "skipped against develop, the pull request goes to main: loop.py "
            "skip again with --base main",
        ),
        (
            "done",
            "judged against develop, the pull request goes to main: loop.py "
            "start build --base main",
        ),
        (
            "open",
            "judged against develop, the pull request goes to main: loop.py "
            "abandon, then loop.py start build --base main",
        ),
    ],
)
def test_a_record_against_another_base(sb, outcome, tail):
    sb.judged(outcome=outcome, base="develop")
    assert detail(sb) == tail


# ---------------------------------------------------------------- outcomes


@pytest.mark.parametrize(("outcome", "n"), [("open", 2), ("stalled", 1)])
def test_an_unfinished_loop(sb, outcome, n):
    sb.judged(outcome=outcome)
    assert detail(sb) == f"judge loop not finished (round {n} of 5): loop.py status"


@pytest.mark.parametrize("outcome", ["ask", "blocked"])
def test_a_loop_waiting_for_the_user_stops_the_merge(sb, outcome):
    sb.passed()
    sb.judged(outcome=outcome)
    assert stops(sb) is True
    done = refused(sb, "judged", 3)
    assert last_line(done) == (
        "STOP: judged: the judge loop is waiting for the user: loop.py status. "
        "Ask the user."
    )


def test_an_abandoned_loop(sb):
    sb.judged(outcome="abandoned")
    assert detail(sb) == "abandoned: loop.py start build"


def test_a_skip_on_the_head_passes(sb):
    sb.judged(outcome="skip")
    gate = judged(sb)
    assert gate["state"] == "pass"
    assert gate["detail"] == f"skipped on {short(sb)} (1 file, 2 lines): docs only"


def test_a_skip_the_user_asked_for_says_so_and_its_reason_is_cleaned(sb):
    skip = {"reason": "a\x1b[31mb\nc\u200b", "files": 3, "lines": 1, "user_ok": True}
    sb.judged(outcome="skip", skip=skip)
    assert detail(sb) == (
        f"skipped on {short(sb)} (3 files, 1 line, user asked): a [31mb c"
    )


def test_a_skip_before_new_commits_fails(sb):
    sb.judged(outcome="skip")
    sb.commit("feat: more")
    sb.git("push", "-q", "origin", BRANCH)
    sb.state()
    assert detail(sb) == (
        "new commits since the skip: judge them (loop.py start build), or skip "
        "again if there is still nothing to judge"
    )


def test_commits_after_the_judged_one_are_counted(sb):
    sb.judged()
    first = short(sb)
    (sb.work / "app.py").write_text("a\nb\n")
    sb.git("add", "app.py")
    sb.git("commit", "-q", "-m", "fix: after")
    sb.git("push", "-q", "origin", BRANCH)
    sb.state()
    gate = judged(sb)
    assert gate["state"] == "pass"
    assert gate["detail"] == (
        f"done, 10 from 1 judge in 1 round on {first} (1 commit before the head); "
        "1 file, 2 lines since"
    )


def test_a_judged_commit_no_longer_on_the_branch(sb):
    tree = sb.git("rev-parse", "HEAD^{tree}")
    other = sb.git("commit-tree", tree, "-m", "elsewhere")
    sb.judged(commit=other)
    assert detail(sb) == (
        f"the judged commit {other[:7]} is no longer on this branch (rebased or "
        "amended): judge again"
    )


def test_an_unknown_judged_commit_names_the_git_error(sb):
    sb.judged(commit="0" * 40)
    found = detail(sb)
    assert found.startswith(
        "the judged commit 0000000 is no longer on this branch (rebased or "
        "amended): judge again (fatal: "
    ), found


def judged_before_the_head(sb):
    """A done record one commit before the head; the judged commit, short."""
    sb.judged()
    first = short(sb)
    sb.commit("fix: after")
    return first


def test_a_git_failure_placing_the_judged_commit_against_the_base(sb, monkeypatch):
    first = judged_before_the_head(sb)
    found = gate_with(
        sb,
        monkeypatch,
        lambda args: args[0] == "merge-base" and args[-1].startswith("refs/"),
        GIT_FAILS,
    )
    assert found == (
        f"git merge-base could not place {first} against main: fatal: bad object"
    )


@pytest.mark.parametrize(
    ("command", "answer", "why"),
    [
        ("rev-list", GIT_FAILS, "fatal: bad object"),
        ("rev-list", (0, "many", ""), "git rev-list gave no count"),
        ("diff", GIT_FAILS, "fatal: bad object"),
    ],
    ids=["rev-list fails", "rev-list gives no count", "the size fails"],
)
def test_a_git_failure_measuring_the_commits_since_the_judged_one(
    sb, monkeypatch, command, answer, why
):
    first = judged_before_the_head(sb)
    found = gate_with(sb, monkeypatch, lambda args: args[0] == command, answer)
    assert found == f"git could not measure the commits since {first}: {why}"


def test_a_judged_commit_already_on_the_base(sb):
    sb.judged(commit=sb.git("rev-parse", "origin/main"))
    assert detail(sb) == (
        f"the judged commit {short(sb, 'origin/main')} is already on main: judge "
        "the branch's own commits (loop.py start build)"
    )


def item(kind, open_=True, settled=None):
    return {"kind": kind, "open": open_, "settled": settled or {}}


SETTLED = {"round": 1, "user_ok": False, "note": "n", "raised_again": 0}
PASSES = {
    "budget": (
        {"outcome": "budget", "items": {"I1": item("improvement"), "I2": item("x")}},
        "budget used, 2 items left, on {sha}",
    ),
    "accepted": (
        {"outcome": "accepted", "items": {"B1": item("blocking")}},
        "accepted by the user in round 1 of 5 with 1 item left (1 blocking), on {sha}",
    ),
    "settled": (
        {"items": {"B1": item("blocking", settled=SETTLED)}},
        "done, 10 from 1 judge in 1 round on {sha}; 1 settled (1 blocking)",
    ),
    "raised again": (
        {
            "outcome": "budget",
            "items": {"I1": item("improvement", settled=dict(SETTLED, raised_again=1))},
        },
        "budget used, 1 item left, on {sha}",
    ),
    "panel forced": (
        {"panel_forced": "full", "panel": ["general", "tests"]},
        "done, 10 from 2 judges in 1 round on {sha}; panel forced: --panel full",
    ),
    "judge rounds": (
        {"switches": [{"key": "Judge rounds", "value": 3, "where": "CLAUDE.md:1"}]},
        "done, 10 from 1 judge in 1 round on {sha}; Judge rounds: 3",
    ),
    "fallback agents": (
        {"agents": "fallback"},
        "done, 10 from 1 judge in 1 round on {sha}; agents: fallback",
    ),
}


@pytest.mark.parametrize(("fields", "reason"), PASSES.values(), ids=PASSES.keys())
def test_the_pass_reason(sb, fields, reason):
    sb.judged(**fields)
    gate = judged(sb)
    assert gate["state"] == "pass"
    assert gate["detail"] == reason.format(sha=short(sb))


OPEN_BLOCKING = {
    "done": {"items": {"B1": item("blocking")}},
    "budget": {"outcome": "budget", "items": {"B1": item("blocking")}},
    "budget, raised again": {
        "outcome": "budget",
        "items": {"B1": item("blocking", settled=dict(SETTLED, raised_again=1))},
    },
}


@pytest.mark.parametrize("fields", OPEN_BLOCKING.values(), ids=OPEN_BLOCKING.keys())
def test_a_finished_record_with_an_open_blocking_item_is_unreadable(sb, fields):
    sb.judged(**fields)
    assert detail(sb) == UNREADABLE


# ---------------------------------------------------------------- with the judge loop


def loop(sb, *args):
    done = subprocess.run(
        [sys.executable, str(LOOP), *args],
        cwd=sb.work,
        env=sb.env,
        capture_output=True,
        text=True,
        check=False,
    )
    return done


FOLDER = Path("docs") / "loops" / SLUG / "build"


def finding(x):
    return {
        "id": x,
        "problem": f"problem {x}",
        "evidence": f"evidence {x}",
        "fix": f"fix {x}",
        "check": f"check {x}",
    }


ANSWERS = {
    10: {"overall": 10, "blocking": [], "improvements": [], "read": "full"},
    9: {"overall": 9, "blocking": [], "improvements": [finding("I1")]},
    5: {"overall": 5, "blocking": [finding("B1")], "improvements": []},
}


def ok(done):
    assert done.returncode in (0, 1), done.stdout + done.stderr
    return done


def start(sb, *flags):
    ok(loop(sb, "start", "build", *flags))
    (sb.work / FOLDER / "criteria.md").write_text("- it works\n")


def record(sb):
    return json.loads((sb.work / FOLDER / "state.json").read_text())


def rewrite(sb, **fields):
    st = record(sb)
    st.update(fields)
    (sb.work / FOLDER / "state.json").write_text(json.dumps(st))


def judge_round(sb, score):
    """brief, the answer file, save, round: the loop's exit code."""
    ok(loop(sb, "brief"))
    n = record(sb)["pending"]["round"]
    folder = sb.work / FOLDER / "judge" / "in"
    folder.mkdir(parents=True, exist_ok=True)
    data = dict(ANSWERS[score], dimensions={"fit": score})
    (folder / f"r{n}_general.txt").write_text(json.dumps(data))
    ok(loop(sb, "save", "general"))
    return loop(sb, "round").returncode


def more(sb, n):
    (sb.work / "app.py").write_text("a\n" * (n + 3))
    sb.git("commit", "-q", "-am", f"fix: more {n}")
    sb.state()


@pytest.fixture
def real(sb):
    if not LOOP.exists():
        pytest.skip("not running from the repository")
    sb.change("app.py", "a\n", "a\nb\nc\n")
    return sb


def test_the_done_record_the_judge_loop_writes(real):
    sb = real
    start(sb, "--base", "origin/main")
    budget = record(sb)["budget"]
    assert (
        detail(sb) == f"judge loop not finished (round 1 of {budget}): loop.py status"
    )
    assert judge_round(sb, 10) == 0
    assert record(sb)["outcome"] == "done"
    gate = judged(sb)
    assert gate["state"] == "pass"
    assert gate["detail"] == f"done, 10 from 1 judge in 1 round on {short(sb)}"
    rewrite(sb, outcome="ask")  # loop.py reaches it for a plan only
    assert stops(sb) is True


def test_the_budget_and_blocked_records_the_judge_loop_writes(real):
    sb = real
    start(sb)
    rewrite(sb, budget=1)
    judge_round(sb, 9)
    assert record(sb)["outcome"] == "budget"
    assert detail(sb) == f"budget used, 1 item left, on {short(sb)}"
    more(sb, 1)
    start(sb)
    rewrite(sb, budget=1)
    judge_round(sb, 5)
    assert record(sb)["outcome"] == "blocked"
    assert stops(sb) is True
    assert detail(sb) == "the judge loop is waiting for the user: loop.py status"


def test_the_accepted_and_stalled_records_the_judge_loop_writes(real):
    sb = real
    start(sb)
    budget = record(sb)["budget"]
    assert judge_round(sb, 9) == 1
    ok(loop(sb, "accept", "--note", "good enough"))
    assert record(sb)["outcome"] == "accepted"
    assert detail(sb) == (
        f"accepted by the user in round 1 of {budget} with 1 item left (0 blocking), "
        f"on {short(sb)}"
    )
    more(sb, 1)
    start(sb)
    rewrite(sb, budget=5)
    rounds = 0
    while record(sb)["outcome"] == "open" and rounds < 4:
        judge_round(sb, 9)
        rounds += 1
        more(sb, rounds + 1)
    assert record(sb)["outcome"] == "stalled"
    assert detail(sb) == (
        f"judge loop not finished (round {rounds} of 5): loop.py status"
    )


def test_the_skip_and_the_abandon_the_judge_loop_writes(real):
    sb = real
    done = loop(sb, "skip", "--reason", "tests only")
    assert done.returncode == 0, done.stdout + done.stderr
    assert detail(sb) == f"skipped on {short(sb)} (1 file, 2 lines): tests only"
    (sb.work / "app.py").write_text("a\nb\nc\nd\n")
    sb.git("commit", "-q", "-am", "feat: more")
    done = loop(sb, "start", "build")
    assert done.returncode == 0, done.stdout + done.stderr
    done = loop(sb, "abandon", "--note", "not needed")
    assert done.returncode == 0, done.stdout + done.stderr
    assert detail(sb) == "abandoned: loop.py start build"


# ---------------------------------------------------------------- the docs


@pytest.mark.parametrize(
    "rel",
    [
        "claude/skills/ship/SKILL.md",
        "README.md",
        "docs-source/components.md",
        "documentation/components.html",
    ],
)
def test_the_docs_name_the_judged_gate(rel):
    path = ROOT / rel
    if not path.exists():
        pytest.skip("not running from the repository")
    text = path.read_text()
    assert "`judged`" in text or "<code>judged</code>" in text, rel


def repo_text(rel):
    path = ROOT / rel
    if not path.exists():
        pytest.skip("not running from the repository")
    return path.read_text()


def test_the_ship_skill_judges_the_build_before_the_acceptance_test():
    text = repo_text("claude/skills/ship/SKILL.md")
    judge = text.index(
        "\n3. **Judge.** Before the acceptance test, the build is judged"
    )
    assert judge < text.index("\n4. **Test.**")
    assert ", Bash(python3 ~/.claude/skills/judge-loop/loop.py *)\n" in text
    assert "`python3 ~/.claude/skills/judge-loop/loop.py <command>`" in text
    assert "\n- The branch's judge loop is waiting for the user." in text


def test_the_template_judges_the_build_before_the_acceptance_test():
    text = repo_text("claude/CLAUDE.md.template")
    assert (
        "- A PR you opened is yours to finish. The build is judged before the"
        " acceptance test. Use the `ship` skill:"
    ) in text
    assert "user says so. Record them with `loop.py skip --reason`.\n" in text


LIMITS = (
    "not that a judge ran or judged well",
    "the session can write or remove",
    "rest on the session's word, like",
    "a build needs no plan loop",
    "commits after the judged one are covered by the acceptance test",
    "the pass reason shows the size since the judged commit",
    "the pass reason names where the line stands",
    'under "changes since install"',
)


@pytest.mark.parametrize(
    "rel", ["claude/skills/ship/SKILL.md", "docs-source/installation.md"]
)
def test_the_docs_state_the_limits_of_the_judge_record(rel):
    text = repo_text(rel).lower()
    for words in LIMITS:
        assert words in text, (rel, words)
