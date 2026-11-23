"""ship.py and a pull request of a judged stack: the stack gate and the move of
the pull requests above it after a merge."""

import json
import os
from pathlib import Path

import pytest
from test_ship import BRANCH, Sandbox, gates, last_line

STACK = Path(__file__).resolve().parents[1] / "ship_stack.py"


def stack_state(sandbox, rounds=1, items=None, prs=None, head=None, folder=None):
    """Write the state of a stack loop with PR #7 on the checked-out branch."""
    prs = prs or [{"pr": 7, "issue": 1, "branch": BRANCH}]
    heads = {str(e["pr"]): head or sandbox.head() for e in prs}
    st = {
        "kind": "build",
        "branch": prs[-1]["branch"],
        "stack": {"base": "main", "prs": prs},
        "rounds": [{"n": n + 1, "heads": heads} for n in range(rounds)],
        "items": items or {},
    }
    path = sandbox.work / "docs" / "loops" / (folder or "stack") / "build"
    path.mkdir(parents=True, exist_ok=True)
    (path / "state.json").write_text(json.dumps(st))
    exclude = sandbox.work / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text() + "docs/\n")
    return path / "state.json"


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


def item(pr, open_=True, settled=None):
    return {"open": open_, "pr": pr, "settled": settled or {}}


def stack_gate(sandbox):
    return gates(sandbox.ship("status", "--json"))["stack"]


def test_a_pull_request_outside_a_stack_passes(sb):
    got = stack_gate(sb)
    assert got["state"] == "pass" and got["detail"] == "not in a judged stack"


def test_status_lists_the_stack_gate_before_ci(sb):
    names = [g["gate"] for g in json.loads(sb.ship("status", "--json").stdout)["gates"]]
    assert names[-2:] == ["stack", "ci"]


def test_a_stack_without_a_judged_round_holds(sb):
    stack_state(sb, rounds=0)
    got = stack_gate(sb)
    assert got["state"] == "fail" and "no judged round" in got["detail"]


def test_an_open_item_on_the_pull_request_holds(sb):
    stack_state(sb, items={"general:1": item(7)})
    got = stack_gate(sb)
    assert got["state"] == "fail"
    assert got["detail"].startswith("1 item open at or below #7 (general:1)")


def test_an_open_item_below_holds_and_one_above_does_not(sb):
    prs = [
        {"pr": 6, "issue": 0, "branch": "feat/0-below"},
        {"pr": 7, "issue": 1, "branch": BRANCH},
        {"pr": 8, "issue": 2, "branch": "feat/2-above"},
    ]
    stack_state(sb, prs=prs, items={"a:1": item(8)})
    assert stack_gate(sb)["state"] == "pass"
    stack_state(sb, prs=prs, items={"a:1": item(8), "b:2": item(6)})
    assert "1 item open at or below #7 (b:2)" in stack_gate(sb)["detail"]


def test_a_settled_or_closed_item_does_not_hold(sb):
    settled = {"note": "the user takes it"}
    stack_state(
        sb, items={"a:1": item(7, settled=settled), "b:2": item(7, open_=False)}
    )
    assert stack_gate(sb)["state"] == "pass"


def test_an_item_raised_again_holds(sb):
    again = {"note": "taken", "raised_again": True}
    stack_state(sb, items={"a:1": item(7, settled=again)})
    assert stack_gate(sb)["state"] == "fail"


def test_the_stack_merges_bottom_up(sb):
    prs = [
        {"pr": 6, "issue": 0, "branch": "feat/0-below"},
        {"pr": 7, "issue": 1, "branch": BRANCH},
    ]
    stack_state(sb, prs=prs)
    sb.state(pr=sb.pr(baseRefName="feat/0-below"))
    got = stack_gate(sb)
    assert got["state"] == "fail"
    assert got["detail"] == "#6 below it merges first: a stack merges bottom-up"


def test_a_commit_after_the_judged_head_holds(sb):
    stack_state(sb)
    sb.commit("fix: unjudged")
    sb.git("push", "-q")
    sb.state()
    got = stack_gate(sb)
    assert got["state"] == "fail"
    assert got["detail"].startswith("1 commit on #7 not judged since round 1")


def test_a_merge_of_the_base_after_the_judged_head_passes(sb):
    stack_state(sb)
    sb.git("checkout", "-q", "main")
    sb.commit("fix: on main")
    sb.git("push", "-q", "origin", "main")
    sb.git("checkout", "-q", BRANCH)
    sb.git("merge", "-q", "--no-ff", "-m", "chore: merge main", "main")
    sb.git("push", "-q")
    sb.state()
    got = stack_gate(sb)
    assert got["state"] == "pass", got
    assert got["detail"].startswith("judged in round 1 of the stack")


def test_the_newest_stack_state_counts(sb):
    old = stack_state(sb, rounds=0, folder="old")
    newer = stack_state(sb, folder="newer")
    stat = newer.stat()
    os.utime(old, (stat.st_atime - 100, stat.st_mtime - 100))
    assert stack_gate(sb)["state"] == "pass"


def test_a_damaged_state_is_passed_over(sb):
    path = sb.work / "docs" / "loops" / "bad" / "build"
    path.mkdir(parents=True)
    (path / "state.json").write_text("{not json")
    exclude = sb.work / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text() + "docs/\n")
    assert stack_gate(sb)["detail"] == "not in a judged stack"


def test_merge_is_held_by_the_stack_gate(sb):
    stack_state(sb, items={"general:1": item(7)})
    sb.passed()
    done = sb.ship("merge")
    assert done.returncode != 0
    assert sb.calls("pr merge") == []


def above(number, login="me", cross=False):
    return {
        "number": number,
        "author": {"login": login},
        "isCrossRepository": cross,
        "headRefName": f"feat/{number}-above",
    }


def test_after_a_merge_own_pull_requests_above_move_to_the_base(sb):
    stack_state(sb)
    sb.passed()
    sb.state(stacked=[above(8), above(9, login="you"), above(10, cross=True)])
    done = sb.ship("merge", "--stay")
    assert done.returncode == 0, done.stdout + done.stderr
    asked = sb.calls("pr list")[-1]
    assert asked[:6] == ["pr", "list", "--base", BRANCH, "--state", "open"]
    assert sb.calls("pr edit") == [["pr", "edit", "8", "--base", "main"]]
    assert sb.calls("pr update-branch") == [["pr", "update-branch", "8"]]
    out = done.stdout
    assert "Moved #8 to main and merged main into its branch." in out
    assert "Not moved: #9 on feat/1-thing is not yours" in out
    assert "Not moved: #10 on feat/1-thing is not yours" in out
    assert last_line(done).startswith("Merged #7 into main")


def test_a_failed_move_is_named_and_the_merge_still_counts(sb):
    sb.passed()
    sb.state(stacked=[above(8)], edit_error="HTTP 422: base invalid")
    done = sb.ship("merge", "--stay")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Not moved: #8: gh pr edit failed (HTTP 422: base invalid)" in done.stdout
    assert sb.calls("pr update-branch") == []
    assert last_line(done).startswith("Merged #7 into main")


def test_a_failed_update_names_the_merge_to_do_by_hand(sb):
    sb.passed()
    sb.state(stacked=[above(8)], update_error="merge conflict")
    done = sb.ship("merge", "--stay")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Moved #8 to main, not updated: gh pr update-branch failed" in done.stdout
    assert "merge main into feat/8-above by hand (never rebase)" in done.stdout


def test_nothing_above_moves_nothing(sb):
    sb.passed()
    done = sb.ship("merge", "--stay")
    assert done.returncode == 0, done.stdout + done.stderr
    assert sb.calls("pr edit") == [] and "Moved" not in done.stdout


def test_the_stack_code_has_no_way_past_a_review():
    text = STACK.read_text()
    assert "--admin" not in text and "--auto" not in text
