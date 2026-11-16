"""The up-to-date gate: a branch behind the base its pull request targets.

The next step is a rebase for a branch that was never pushed and a merge for a
pushed one; no command ship.py prints holds --force, and ship.py itself never
rebases, merges or pushes to bring a branch up to date.
"""

import json

import pytest
from ship_fixtures import gates, last_line, refused

NEW = "feat/2-new"
REBASE = (
    "the branch was never pushed: git rebase origin/main, "
    "run the tests again, then push"
)
MERGE = (
    "the branch is pushed: git merge origin/main (no rebase, no force push), "
    "run the tests again, then push"
)
DEFAULT = (
    f"{'':19}no pull request yet: compared with main, the default branch; "
    "another base: ship.py status --base BRANCH"
)


def line(name, word, detail):
    return f"  {word:<5} {name:<11} {detail}"


def lines(done):
    return done.stdout.splitlines()


def unpushed(sb, *start):
    """A new branch that was never pushed, and no pull request."""
    sb.git("switch", "-q", "-c", NEW, *(start or ("main",)))
    sb.commit("feat: new")
    sb.state(pr=None)


def other_clone(sb):
    other = sb.tmp / "other"
    if not other.exists():
        sb.git("clone", "-q", str(sb.tmp / "origin.git"), str(other), cwd=sb.tmp)
    return other


def test_a_never_pushed_branch_behind_its_base_is_told_to_rebase(sb):
    unpushed(sb)
    sb.advance_base()
    head = sb.head()
    done = sb.ship("status")
    assert done.returncode == 1
    behind = line("up-to-date", "FAIL", f"1 commit behind origin/main: {REBASE}")
    assert behind in lines(done)
    assert lines(done)[lines(done).index(behind) + 1] == DEFAULT
    assert line(
        "pr",
        "FAIL",
        f"no pull request for {NEW}: bring it up to date with its base "
        "(see up-to-date), push, then gh pr create --draft",
    ) in lines(done)
    assert "git merge" not in done.stdout
    assert sb.head() == head and sb.git("status", "--porcelain") == ""


def test_a_pushed_branch_behind_its_base_is_told_to_merge(sb):
    sb.state(pr=None)
    sb.advance_base()
    done = sb.ship("status")
    assert line("up-to-date", "FAIL", f"1 commit behind origin/main: {MERGE}") in (
        lines(done)
    )
    assert "git rebase" not in done.stdout


def test_a_pull_request_behind_its_base_is_told_to_merge(sb):
    sb.passed()
    sb.advance_base()
    done = refused(sb, "up-to-date", 1)
    assert line("up-to-date", "FAIL", f"1 commit behind origin/main: {MERGE}") in (
        lines(done)
    )
    assert (
        last_line(done)
        == f"Not merged: up-to-date: 1 commit behind origin/main: {MERGE}."
    )


def test_the_count_names_every_missing_commit(sb):
    unpushed(sb)
    sb.advance_base()
    other = other_clone(sb)
    sb.git("pull", "-q", "origin", "main", cwd=other)
    sb.git("commit", "-q", "--allow-empty", "-m", "fix: again", cwd=other)
    sb.git("push", "-q", "origin", "main", cwd=other)
    done = sb.ship("status")
    assert line("up-to-date", "FAIL", f"2 commits behind origin/main: {REBASE}") in (
        lines(done)
    )


@pytest.mark.parametrize("pull_request", [True, False])
def test_an_up_to_date_branch_passes(sb, pull_request):
    if not pull_request:
        unpushed(sb)
    done = sb.ship("status")
    assert line("up-to-date", "ok", "contains the tip of origin/main") in lines(done)


def test_an_upstream_on_the_base_is_not_a_push(sb):
    """`git switch -c feat origin/main` sets origin/main as the upstream."""
    unpushed(sb, "--track", "origin/main")
    assert sb.git("config", "--get", f"branch.{NEW}.merge") == "refs/heads/main"
    sb.advance_base()
    done = sb.ship("status")
    assert line("up-to-date", "FAIL", f"1 commit behind origin/main: {REBASE}") in (
        lines(done)
    )


def test_an_upstream_of_the_same_name_counts_as_pushed(sb):
    unpushed(sb)
    sb.git("config", f"branch.{NEW}.remote", "origin")
    sb.git("config", f"branch.{NEW}.merge", f"refs/heads/{NEW}")
    sb.advance_base()
    done = sb.ship("status")
    assert line("up-to-date", "FAIL", f"1 commit behind origin/main: {MERGE}") in (
        lines(done)
    )


def dev_base(sb):
    """A `dev` branch on the remote, one commit past main, then a branch from it
    that was never pushed, and one more commit on `dev` the branch lacks."""
    other = other_clone(sb)
    sb.git("switch", "-q", "-c", "dev", cwd=other)
    sb.git("commit", "-q", "--allow-empty", "-m", "feat: dev", cwd=other)
    sb.git("push", "-q", "origin", "dev", cwd=other)
    sb.git("fetch", "-q", "origin")
    unpushed(sb, "origin/dev", "--no-track")
    sb.git("commit", "-q", "--allow-empty", "-m", "fix: on dev", cwd=other)
    sb.git("push", "-q", "origin", "dev", cwd=other)


def test_the_base_comes_from_the_base_option(sb):
    dev_base(sb)
    done = sb.ship("status", "--base", "dev")
    rebase = REBASE.replace("origin/main", "origin/dev")
    behind = line("up-to-date", "FAIL", f"1 commit behind origin/dev: {rebase}")
    assert behind in lines(done)
    hint = f"{'':19}no pull request yet: compared with dev, from --base"
    assert lines(done)[lines(done).index(behind) + 1] == hint
    data = gates(sb.ship("status", "--json", "--base", "dev"))["up-to-date"]
    assert data["detail"] == f"1 commit behind origin/dev: {rebase}"


def test_the_base_comes_from_gh_merge_base(sb):
    dev_base(sb)
    sb.git("config", f"branch.{NEW}.gh-merge-base", "dev")
    done = sb.ship("status")
    rebase = REBASE.replace("origin/main", "origin/dev")
    behind = line("up-to-date", "FAIL", f"1 commit behind origin/dev: {rebase}")
    assert behind in lines(done)
    hint = (
        f"{'':19}no pull request yet: compared with dev, from "
        f"branch.{NEW}.gh-merge-base; another base: ship.py status --base BRANCH"
    )
    assert lines(done)[lines(done).index(behind) + 1] == hint


def test_the_pull_request_base_wins_over_the_option(sb):
    done = sb.ship("status", "--base", "dev")
    ok = line("up-to-date", "ok", "contains the tip of origin/main")
    assert ok in lines(done)
    hint = f"{'':19}the pull request targets main; --base dev is not used"
    assert lines(done)[lines(done).index(ok) + 1] == hint


@pytest.mark.parametrize("name", ["-x", "a..b", "a b", "a:b", "x\x1b[31m", "x/", "@"])
@pytest.mark.parametrize("cmd", [("status",), ("record", "--result", "pass")])
def test_the_base_option_takes_only_a_branch_name(sb, name, cmd):
    done = sb.ship(*cmd, f"--base={name}", "--release", "no")
    assert done.returncode == 2 and done.stdout == ""
    shown = repr(name.replace("\x1b", "?"))
    assert done.stderr.splitlines()[-1] == (
        f"ship.py {cmd[0]}: error: argument --base: {shown} is not a branch name; "
        "name the branch the pull request targets, for example --base main"
    )
    assert "\x1b" not in done.stderr


def test_a_base_that_cannot_be_fetched(sb):
    unpushed(sb)
    done = sb.ship("status", "--base", "nope")
    assert done.returncode == 1
    (found,) = [x for x in lines(done) if x.startswith("  FAIL  up-to-date  ")]
    assert found == line(
        "up-to-date",
        "FAIL",
        "could not fetch nope from origin: "
        "fatal: couldn't find remote ref refs/heads/nope; "
        "check the base and the remote, then run ship.py status again",
    )


def test_the_base_branch_itself_is_skipped(sb):
    sb.git("switch", "-q", "main")
    sb.state(pr=None)
    done = sb.ship("status")
    assert line("up-to-date", "-", "main is the base branch itself") in lines(done)


# ---------------------------------------------------------------- record


def test_record_refuses_a_pass_while_behind(sb):
    sb.judged()
    sb.advance_base()
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 1 and done.stdout == ""
    assert done.stderr == (
        f"ship: not recorded: 1 commit behind origin/main: {MERGE}; "
        "after that, run the acceptance test again\n"
    )
    assert "no test record" in sb.ship("status").stdout
    assert sb.ship("record", "--result", "fail", "--open", "F1").returncode == 0
    sb.git("merge", "-q", "--no-edit", "origin/main")
    sb.git("push", "-q")
    sb.state()
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 0, done.stderr


def test_record_names_the_rebase_for_a_never_pushed_branch(sb):
    unpushed(sb)
    sb.advance_base()
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 1
    assert done.stderr == (
        f"ship: not recorded: 1 commit behind origin/main: {REBASE}; "
        "after that, run the acceptance test again\n"
    )


# ---------------------------------------------------------------- no --force


SCENARIOS = {
    "never pushed": lambda sb: (unpushed(sb), sb.advance_base()),
    "pushed": lambda sb: (sb.state(pr=None), sb.advance_base()),
    "pull request": lambda sb: sb.advance_base(),
    "conflict": lambda sb: sb.state(pr=sb.pr(mergeable="CONFLICTING")),
    "GitHub behind": lambda sb: sb.state(pr=sb.pr(mergeStateStatus="BEHIND")),
    "up to date": lambda sb: None,
}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_no_suggested_command_holds_force(sb, scenario):
    SCENARIOS[scenario](sb)
    head = sb.head()
    origin = sb.git("for-each-ref", cwd=sb.tmp / "origin.git")
    outputs = [
        sb.ship("status"),
        sb.ship("status", "--json"),
        sb.ship("record", "--result", "pass", "--release", "no"),
        sb.ship("merge", "--dry-run", "--grace", "0"),
    ]
    for done in outputs:
        text = done.stdout + done.stderr
        assert "--force" not in text and "-f " not in text, text
        assert "push --force" not in text and "force-with-lease" not in text
    detail = json.loads(outputs[1].stdout)["gates"]
    (found,) = [g for g in detail if g["gate"] == "up-to-date"]
    assert ("never pushed" in found["detail"]) == (scenario == "never pushed")
    assert sb.head() == head
    assert sb.git("for-each-ref", cwd=sb.tmp / "origin.git") == origin


def test_conflicts_and_github_behind_are_told_to_merge(sb):
    sb.state(pr=sb.pr(mergeable="CONFLICTING"))
    done = sb.ship("status")
    assert line(
        "up-to-date",
        "FAIL",
        "conflicts with origin/main: git merge origin/main, resolve the conflicts "
        "and say so in the pull request, run the tests again, then push",
    ) in lines(done)
    sb.state(pr=sb.pr(mergeStateStatus="BEHIND"))
    done = sb.ship("status")
    assert line(
        "up-to-date", "FAIL", f"behind origin/main, GitHub says: {MERGE}"
    ) in lines(done)
