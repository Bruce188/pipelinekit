"""ship.py against a fake gh and a throwaway repository with a bare origin."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from ship_fixtures import (
    BRANCH,
    SHIP,
    check,
    gates,
    held,
    last_line,
    refused,
    ship,
)

# ---------------------------------------------------------------- status


def test_status_lists_every_gate_with_its_reason(sb):
    done = sb.ship("status")
    assert done.returncode == 1
    for name in (
        "pr",
        "own",
        "policy",
        "release",
        "linked",
        "review",
        "current",
        "up-to-date",
        "judged",
        "tested",
        "ci",
    ):
        assert f" {name} " in done.stdout
    assert "no test record" in done.stdout
    assert "  ok    linked      closes #1 on the merge into main\n" in done.stdout
    assert "Result: not ready (judged, tested)" in done.stdout


def test_status_json_and_exit_zero(sb):
    done = sb.ship("status", "--json", "--exit-zero")
    assert done.returncode == 0
    data = json.loads(done.stdout)
    assert data["ready"] is False and data["pr"]["number"] == 7
    assert gates(done)["tested"]["state"] == "fail"
    assert gates(done)["ci"]["state"] == "pass"


def test_status_without_a_pull_request(sb):
    sb.state(pr=None)
    done = sb.ship("status", "--json")
    assert done.returncode == 1
    assert gates(done)["pr"]["state"] == "fail"
    assert gates(done)["own"]["state"] == "skip"
    assert "Result: not ready (pr, judged, tested)" in sb.ship("status").stdout


def test_status_outside_a_repository_is_a_tool_error(sb, tmp_path):
    cmd = [sys.executable, str(SHIP), "status"]
    done = subprocess.run(
        cmd, cwd=tmp_path / "home", env=sb.env, capture_output=True, text=True
    )
    assert done.returncode == 2 and "not inside a git repository" in done.stderr
    done = subprocess.run(
        [*cmd, "--exit-zero"],
        cwd=tmp_path / "home",
        env=sb.env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0 and "not inside a git repository" in done.stdout


# ---------------------------------------------------------------- merge refusals


def test_merge_refuses_without_a_test_record(sb):
    sb.judged()
    assert "no test record" in refused(sb, "tested", 1).stdout


def test_merge_refuses_a_failed_round(sb):
    sb.judged()
    sb.ship("record", "--result", "fail", "--open", "F1")
    assert "still open: F1" in refused(sb, "tested", 1).stdout


def test_merge_refuses_a_record_for_an_older_commit(sb):
    sb.passed()
    sb.commit("fix: after the test")
    sb.git("push", "-q")
    sb.state()
    assert "test again" in refused(sb, "tested", 1).stdout


def test_merge_refuses_a_failed_check(sb):
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint"), check("selftests", "FAILURE")]))
    done = refused(sb, "ci", 1)
    assert "failed: selftests" in done.stdout
    assert "gh run view 42 --log-failed" in done.stdout


def test_merge_refuses_a_check_that_is_still_running(sb):
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "", "IN_PROGRESS")]))
    assert "still running" in refused(sb, "ci", 1).stdout


def test_merge_refuses_a_branch_behind_its_base(sb):
    sb.passed()
    sb.advance_base()
    assert "1 commit behind origin/main" in refused(sb, "up-to-date", 1).stdout


def test_merge_refuses_a_conflicting_branch(sb):
    sb.passed()
    sb.state(pr=sb.pr(mergeable="CONFLICTING"))
    assert "conflicts with origin/main" in refused(sb, "up-to-date", 1).stdout


def test_merge_refuses_an_unpushed_commit_and_dirty_files(sb):
    sb.passed()
    pr = sb.pr()
    sb.commit("fix: not pushed")
    sb.state(pr=pr)
    assert "push or pull first" in refused(sb, "current", 1).stdout


def test_merge_refuses_someone_elses_pull_request(sb):
    sb.passed()
    sb.state(pr=sb.pr(author={"login": "someone"}))
    assert "opened by someone" in refused(sb, "own", 3).stdout


def test_merge_refuses_a_pull_request_from_a_fork(sb):
    sb.passed()
    sb.state(pr=sb.pr(isCrossRepository=True))
    refused(sb, "own", 3)


@pytest.mark.parametrize(
    "over",
    [
        {"reviewDecision": "REVIEW_REQUIRED"},
        {"reviewDecision": "CHANGES_REQUESTED"},
        {"reviewRequests": [{"login": "reviewer"}]},
        {"isDraft": False, "mergeStateStatus": "BLOCKED"},
    ],
)
def test_merge_refuses_when_a_review_stands_in_the_way(sb, over):
    sb.passed()
    sb.state(pr=sb.pr(**over))
    refused(sb, "review", 3)


@pytest.mark.parametrize(
    "over",
    [
        {"headRefName": "release/v1.0.0"},
        {"headRefName": "develop"},
        {"title": "chore(release): 1.2.0"},
        {"title": "Release v2.0"},
    ],
)
def test_merge_refuses_a_release(sb, over):
    sb.passed()
    sb.state(pr=sb.pr(**over))
    refused(sb, "release", 3)


def test_a_pull_request_into_a_release_branch_is_not_a_release(sb):
    sb.state(pr=sb.pr(baseRefName="main", headRefName="feat/release-notes"))
    assert gates(sb.ship("status", "--json"))["release"]["state"] == "pass"


@pytest.mark.parametrize(
    "line",
    [
        "Merges: ask first",
        "- Merges: ask first",
        "* merge: ask",
        "  MERGES : ASK FIRST",
    ],
)
def test_merge_refuses_in_a_project_that_opted_out(sb, line):
    sb.passed()
    (sb.work / "CLAUDE.md").write_text(f"# Project\n\n{line}\n")
    assert "Merges: ask first" in refused(sb, "policy", 3).stdout


def test_opt_out_in_other_places(sb):
    sb.passed()
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    (home / "CLAUDE.md").write_text("Merges: ask first\n")
    assert "user-level" in refused(sb, "policy", 3).stdout
    (home / "CLAUDE.md").unlink()
    for word in ("ask", "off", "no", "0", "Ask First"):
        done = sb.ship("merge", "--dry-run", PIPELINEKIT_MERGE=word)
        assert done.returncode == 3, word
        assert last_line(done).startswith(f"STOP: policy: PIPELINEKIT_MERGE={word}.")
    for word in ("auto", " AUTO ", ""):
        done = sb.ship("merge", "--dry-run", PIPELINEKIT_MERGE=word)
        assert done.returncode == 0, word


def test_a_sentence_about_the_opt_out_does_not_opt_out(sb):
    text = "- A project turns this off with the line `Merges: ask first`.\n"
    (sb.work / "CLAUDE.md").write_text(text)
    assert gates(sb.ship("status", "--json"))["policy"]["state"] == "pass"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes")
def test_a_named_pipe_as_the_user_level_claude_md_is_named_not_waited_on(sb):
    sb.passed()
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    os.mkfifo(home / "CLAUDE.md")
    policy = gates(sb.ship("status", "--json", timeout=20))["policy"]
    assert policy["state"] == "fail", policy
    assert policy["detail"].startswith("cannot read $CLAUDE_HOME/CLAUDE.md"), policy
    assert "named pipe" in policy["detail"]
    done = sb.ship("merge", "--grace", "0", "--timeout", "1", timeout=20)
    assert done.returncode == 3, done.stdout + done.stderr
    assert sb.calls("pr merge") == [] and sb.calls("pr ready") == []
    # The judged gate cannot see a `Judge loop: off` line in it either.
    assert last_line(done) == (
        f"STOP: policy: {policy['detail']}. Also not holding: judged. Ask the user."
    )


def test_a_project_claude_md_that_is_a_folder_is_named(sb):
    sb.passed()
    (sb.work / "CLAUDE.local.md").mkdir()
    policy = gates(sb.ship("status", "--json", timeout=20))["policy"]
    assert policy["state"] == "fail", policy
    assert policy["detail"].startswith("cannot read CLAUDE.local.md (a folder"), policy


def test_a_linked_user_level_claude_md_is_still_read(sb):
    sb.passed()
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    real = home.parent / "dotfiles-claude.md"
    real.write_text("Merges: ask first\n")
    (home / "CLAUDE.md").symlink_to(real)
    assert "user-level" in refused(sb, "policy", 3).stdout


# ---------------------------------------------------------------- merge


def test_merge_marks_ready_and_merges_exactly_the_tested_commit(sb):
    sb.passed()
    head = sb.head()
    done = sb.ship("merge")
    assert done.returncode == 0, done.stdout + done.stderr
    assert sb.calls("pr ready") == [["pr", "ready", "7"]]
    assert sb.calls("pr merge") == [
        ["pr", "merge", "7", "--squash", "--match-head-commit", head]
    ]
    base = sb.git("rev-parse", "main")[:7]
    assert last_line(done) == (
        f"Merged #7 into main (squash) at {head[:7]}. Now on main at {base}."
    )
    assert sb.git("branch", "--show-current") == "main"


def test_merge_follows_a_base_that_uses_merge_commits(sb):
    sb.git("checkout", "-q", "main")
    sb.git("checkout", "-q", "-b", "old")
    sb.commit("feat: old")
    sb.git("checkout", "-q", "main")
    sb.git("merge", "-q", "--no-ff", "-m", "chore: merge old", "old")
    sb.git("push", "-q", "origin", "main")
    sb.git("checkout", "-q", BRANCH)
    sb.git("merge", "-q", "-m", "chore: merge main", "main")
    sb.git("push", "-q")
    sb.state(pr=sb.pr(isDraft=False, mergeStateStatus="CLEAN"))
    sb.passed()
    done = sb.ship("merge", "--stay")
    assert done.returncode == 0, done.stdout + done.stderr
    assert sb.calls("pr ready") == []
    assert sb.calls("pr merge")[0][3:] == [
        "--merge",
        "--match-head-commit",
        sb.head(),
        f"--subject=chore: merge {BRANCH}",
    ]
    assert last_line(done) == f"Merged #7 into main (merge) at {sb.head()[:7]}."
    assert sb.git("branch", "--show-current") == BRANCH


def test_merge_never_passes_admin_and_has_no_option_for_it(sb):
    sb.passed()
    done = sb.ship("merge", "--admin")
    assert done.returncode == 2 and sb.calls("pr merge") == []
    assert sb.ship("merge").returncode == 0
    flat = [arg for call in sb.calls("pr merge") for arg in call]
    assert "--admin" not in flat and "--auto" not in flat
    scripts = sorted(SHIP.parent.glob("ship*.py"))
    assert len(scripts) >= 3, scripts
    for script in scripts:
        assert "--admin" not in script.read_text(), script.name


def test_a_missing_module_stops_ship_with_one_line(tmp_path):
    (tmp_path / "ship.py").write_text(SHIP.read_text())
    p = subprocess.run(
        [sys.executable, str(tmp_path / "ship.py"), "status"],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 2, p.stderr
    assert p.stdout == "" and len(p.stderr.splitlines()) == 1, p.stderr
    assert p.stderr.startswith("ship.py: cannot load its modules ("), p.stderr


def test_merge_dry_run_changes_nothing(sb):
    sb.passed()
    done = sb.ship("merge", "--dry-run")
    assert done.returncode == 0
    plan = "run: gh pr merge 7 --squash --match-head-commit"
    ready = "Dry run. Would mark #7 ready, watch it for 30 s, then "
    assert last_line(done).startswith(ready + plan)
    assert "for 4.5 s, then" in last_line(
        sb.ship("merge", "--dry-run", "--settle", "4.5")
    )
    assert sb.calls("pr merge") == [] and sb.calls("pr ready") == []
    assert sb.git("branch", "--show-current") == BRANCH
    sb.state(pr=sb.pr(isDraft=False, mergeStateStatus="CLEAN"))
    assert last_line(sb.ship("merge", "--dry-run")).startswith(f"Dry run. Would {plan}")


def test_merge_stops_when_protection_shows_after_marking_ready(sb):
    sb.passed()
    sb.state(after_ready="BLOCKED")
    done = sb.ship("merge")
    assert done.returncode == 3 and "branch protection" in done.stdout
    assert sb.calls("pr merge") == []


def test_merge_reports_a_refusal_by_github(sb):
    sb.passed()
    sb.state(merge_error="Pull request is not mergeable")
    done = sb.ship("merge")
    assert done.returncode == 1
    assert last_line(done).startswith("Not merged: gh pr merge failed: Pull request")
    assert last_line(done).endswith("#7 is no longer a draft.")
    assert sb.git("branch", "--show-current") == BRANCH


def test_merge_waits_for_checks_that_show_up_late(sb):
    sb.passed()
    late = [sb.pr(statusCheckRollup=[]), sb.pr(statusCheckRollup=[check("lint")])]
    sb.state(pr_sequence=[late[0], late[0], late[1]])
    done = sb.ship("merge", "--grace", "30")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 check finished" in done.stdout
    assert "waiting for the first check to show up" in done.stderr


# ---------------------------------------------------------------- wait


def test_wait_treats_a_conclusion_as_finished(sb):
    stuck = check("selftests", "SUCCESS", "IN_PROGRESS")
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint"), stuck]))
    done = sb.ship("wait", "--timeout", "2")
    assert done.returncode == 0 and "2 checks finished" in done.stdout


def test_wait_polls_until_the_checks_are_done(sb):
    running = sb.pr(statusCheckRollup=[check("lint", "", "QUEUED")])
    sb.state(pr_sequence=[running, running, sb.pr()])
    done = sb.ship("wait")
    assert done.returncode == 0
    assert "waiting for CI" in done.stderr
    assert len(sb.calls("pr view")) == 3


def test_wait_reports_a_failure_with_the_log_command(sb):
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "FAILURE")]))
    done = sb.ship("wait")
    assert done.returncode == 1
    assert (
        "failed: lint" in done.stdout and "gh run view 42 --log-failed" in done.stdout
    )


def test_wait_times_out(sb):
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "", "IN_PROGRESS")]))
    done = sb.ship("wait", "--timeout", "0")
    assert done.returncode == 1 and "still running" in done.stdout


def test_wait_without_checks(sb):
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    done = sb.ship("wait")
    assert done.returncode == 0 and "no CI checks" in done.stdout


def test_wait_reads_commit_statuses(sb):
    status = {"__typename": "StatusContext", "context": "ci/x", "state": "PENDING"}
    sb.state(pr=sb.pr(statusCheckRollup=[status]))
    assert sb.ship("wait", "--timeout", "0").returncode == 1
    sb.state(pr=sb.pr(statusCheckRollup=[dict(status, state="SUCCESS")]))
    assert sb.ship("wait").returncode == 0
    sb.state(pr=sb.pr(statusCheckRollup=[dict(status, state="ERROR")]))
    assert sb.ship("wait").returncode == 1


def test_wait_does_not_trust_checks_of_another_commit(sb):
    sb.state(pr=sb.pr(headRefOid="0" * 40))
    done = sb.ship("wait", "--grace", "0")
    assert done.returncode == 1 and "push first" in done.stdout


# ---------------------------------------------------------------- record


def test_record_writes_the_round_and_keeps_it_out_of_commits(sb):
    done = sb.ship("record", "--result", "fail", "--open", "F2", "F1", "--notes", "x")
    assert done.returncode == 0 and "Round 1: fail" in done.stdout
    data = json.loads((sb.work / "docs/uat/feat-1-thing.json").read_text())
    assert data["branch"] == BRANCH
    assert data["rounds"][0]["open"] == ["F1", "F2"]
    assert data["rounds"][0]["commit"] == sb.head()
    exclude = (sb.work / ".git/info/exclude").read_text()
    assert exclude.count("docs/uat/") == 1
    sb.ship("record", "--result", "fail", "--open", "F1")
    assert (sb.work / ".git/info/exclude").read_text() == exclude
    assert sb.git("status", "--porcelain") == ""


def exclude_bytes(sb):
    path = sb.work / ".git/info/exclude"
    return path.read_bytes() if path.exists() else None


def write_report(sb):
    (sb.work / "docs/uat/feat-1-thing").mkdir(parents=True)
    (sb.work / "docs/uat/feat-1-thing.md").write_text("# Report\n")
    (sb.work / "docs/uat/feat-1-thing/home.png").write_bytes(b"png")


def test_prepare_keeps_the_report_out_of_git_status_before_the_first_record(sb):
    done = sb.ship("prepare")
    assert done.returncode == 0, done.stderr
    assert "Report: docs/uat/feat-1-thing.md" in done.stdout
    assert "Screenshots: docs/uat/feat-1-thing/" in done.stdout
    write_report(sb)
    assert sb.git("status", "--porcelain") == ""
    exclude = (sb.work / ".git/info/exclude").read_text()
    assert exclude.count("docs/uat/") == 1
    assert sb.ship("prepare").returncode == 0
    assert (sb.work / ".git/info/exclude").read_text() == exclude
    assert not (sb.fake / "calls.jsonl").exists()  # no gh call, no network


def test_prepare_adds_no_line_where_another_rule_ignores_the_folder(sb):
    ignore = sb.tmp / "global-ignore"
    ignore.write_text("docs/\n")
    (sb.tmp / "gitconfig").write_text(f"[core]\n\texcludesFile = {ignore}\n")
    before = exclude_bytes(sb)
    assert sb.ship("prepare").returncode == 0
    assert exclude_bytes(sb) == before


def test_prepare_adds_the_line_where_another_rule_ignores_only_the_record(sb):
    exclude = sb.work / ".git/info/exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("*.json\n")
    assert sb.ship("prepare").returncode == 0
    write_report(sb)
    assert sb.git("status", "--porcelain") == ""
    assert exclude.read_text() == "*.json\ndocs/uat/\n"


def test_prepare_says_when_it_cannot_write_the_exclude_file(sb):
    exclude = sb.work / ".git/info/exclude"
    exclude.unlink(missing_ok=True)
    exclude.mkdir(parents=True)
    done = sb.ship("prepare")
    assert done.returncode == 1
    assert "could not add docs/uat/ to .git/info/exclude" in done.stdout
    assert "Report: docs/uat/feat-1-thing.md" in done.stdout


def test_status_and_a_dry_run_change_nothing_in_the_repository(sb):
    write_report(sb)
    before = exclude_bytes(sb)
    sb.ship("status")
    sb.ship("status", "--json", "--exit-zero")
    sb.ship("merge", "--dry-run")
    assert exclude_bytes(sb) == before
    assert sb.git("status", "--porcelain") == "?? docs/"


def test_record_checks_its_arguments(sb):
    assert sb.ship("record", "--result", "pass", "--open", "F1").returncode == 2
    assert sb.ship("record", "--result", "fail").returncode == 2
    assert sb.ship("record").returncode == 2
    assert not (sb.work / "docs").exists()


def test_record_refuses_a_pass_with_uncommitted_changes(sb):
    (sb.work / "file.txt").write_text("one\n")
    sb.git("add", "file.txt")
    sb.git("commit", "-q", "-m", "feat: file")
    (sb.work / "file.txt").write_text("two\n")
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 1 and "commit first" in done.stderr


def test_record_stops_after_five_failed_rounds(sb):
    for n in range(1, 5):
        done = sb.ship("record", "--result", "fail", "--open", f"F{n}")
        assert done.returncode == 0, n
    done = sb.ship("record", "--result", "fail", "--open", "F9")
    assert done.returncode == 3 and "5 failed rounds in a row" in done.stdout


def test_record_stops_when_a_finding_survives_two_fix_attempts(sb):
    assert sb.ship("record", "--result", "fail", "--open", "F1", "F2").returncode == 0
    sb.commit("fix: first attempt")
    assert sb.ship("record", "--result", "fail", "--open", "F2", "F3").returncode == 0
    sb.commit("fix: second attempt")
    done = sb.ship("record", "--result", "fail", "--open", "F2")
    assert (
        done.returncode == 3 and "F2 still open after two fix attempts" in done.stdout
    )


def test_a_passed_round_resets_the_count(sb):
    for _ in range(2):
        sb.ship("record", "--result", "fail", "--open", "F1")
    sb.passed()
    for _ in range(2):
        assert sb.ship("record", "--result", "fail", "--open", "F1").returncode == 0


def test_the_kit_template_names_the_opt_out_without_opting_out(sb):
    template = SHIP.parents[2] / "CLAUDE.md.template"
    if not template.exists():
        pytest.skip("not running from the repository")
    home = Path(sb.env["CLAUDE_HOME"])
    home.mkdir()
    (home / "CLAUDE.md").write_text(template.read_text())
    assert "`Merges: ask first`" in template.read_text()
    assert gates(sb.ship("status", "--json"))["policy"]["state"] == "pass"


# ---------------------------------------------------------------- after marking ready


def test_merge_reads_twice_after_marking_ready(sb):
    sb.passed()
    assert sb.ship("merge", "--settle", "0").returncode == 0
    assert sb.views_after_ready() == 2


def test_merge_watches_for_the_settle_time(sb):
    sb.passed()
    start = time.monotonic()
    done = sb.ship("merge", "--settle", "1.5")
    assert done.returncode == 0, done.stdout + done.stderr
    assert time.monotonic() - start >= 1.5
    assert sb.views_after_ready() >= 3
    assert "watching #7 for 1.5 s before the merge" in done.stderr


def settle_of(sb, *args):
    line = last_line(sb.ship("merge", "--dry-run", *args))
    return line.partition("watch it for ")[2].partition(" s, then ")[0]


def test_the_settle_time_follows_what_is_still_to_come(sb):
    sb.passed()
    assert settle_of(sb) == "30"
    sb.workflow()
    assert settle_of(sb) == "30"
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "SKIPPED")]))
    assert settle_of(sb, "--allow-no-checks") == "30"
    sb.state()
    sb.workflow("on:\n  pull_request:\n    types: [opened, ready_for_review]\n")
    assert settle_of(sb) == "90"


def test_the_settle_time_after_a_skipped_check_is_the_grace_time_when_longer():
    pr = {"isDraft": True, "statusCheckRollup": [check("lint", "SKIPPED")]}
    repo = SimpleNamespace(expects_checks=lambda: True, starts_on_ready=lambda: False)

    def settle(*argv):
        args = ship.build_parser().parse_args(["merge", *argv])
        return ship.settle_seconds(args, repo, pr)

    assert settle() == 90
    assert settle("--grace", "200") == 200
    assert settle("--grace", "5") == 30
    assert settle("--allow-no-checks") == 30
    assert settle("--settle", "5") == 5


def test_allow_no_checks_does_not_wait_for_a_first_check():
    repo = SimpleNamespace(expects_checks=lambda: True)

    def grace(*argv):
        return ship.grace_seconds(ship.build_parser().parse_args(argv), repo)

    for cmd in ("wait", "merge"):
        assert grace(cmd) == 90
        assert grace(cmd, "--allow-no-checks") == 0
        assert grace(cmd, "--allow-no-checks", "--grace", "20") == 20


def test_status_and_a_dry_run_say_a_check_is_still_to_come(sb):
    sb.workflow()
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "SKIPPED")]))
    done = sb.ship("status", "--json")
    ci = gates(done)["ci"]
    assert done.returncode == 1 and ci["state"] == "pending", ci
    assert "a check is still to come" in ci["detail"] and "lint" in ci["detail"]
    assert "Result: not ready (ci)" in sb.ship("status").stdout
    done = sb.ship("merge", "--dry-run")
    assert done.returncode == 1 and "a check is still to come" in last_line(done)
    assert sb.calls("pr ready") == [] and sb.calls("pr merge") == []
    allowed = sb.ship("status", "--json", "--allow-no-checks")
    assert gates(allowed)["ci"]["state"] == "pass"
    sb.state(
        pr=sb.pr(
            isDraft=False,
            mergeStateStatus="CLEAN",
            statusCheckRollup=[check("lint", "SKIPPED")],
        )
    )
    assert gates(sb.ship("status", "--json"))["ci"]["state"] == "pass"


def test_merge_takes_a_check_that_comes_after_the_skipped_one(sb):
    sb.workflow()
    sb.passed()
    sb.state(
        pr=sb.pr(statusCheckRollup=[check("lint", "SKIPPED")]),
        after_ready_sequence=[{}, {"statusCheckRollup": [check("lint")]}],
    )
    done = sb.ship("merge")
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(sb.calls("pr merge")) == 1


def test_the_gate_table_comes_before_the_watch_line_through_a_pipe(sb):
    sb.passed()
    done = subprocess.run(
        [sys.executable, str(SHIP), "merge", "--settle", "1"],
        cwd=sb.work,
        env=sb.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
        check=False,
    )
    out = done.stdout
    assert done.returncode == 0, out
    table, watch, merged = (
        out.index("Result: ready to merge"),
        out.index("watching #7 for 1 s"),
        out.index("Merged #7"),
    )
    assert table < watch < merged, out


def test_merge_waits_for_a_check_that_starts_when_marked_ready(sb):
    sb.passed()
    running = {"statusCheckRollup": [check("lint"), check("owners", "", "QUEUED")]}
    finished = {"statusCheckRollup": [check("lint"), check("owners")]}
    sb.state(after_ready_sequence=[{}, {}, {}, {}, running, running, finished])
    done = sb.ship("merge", "--settle", "3")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "waiting for CI: 1 running" in done.stderr
    assert sb.views_after_ready() >= 8
    assert len(sb.calls("pr merge")) == 1


def test_merge_sees_a_check_that_was_skipped_on_the_draft_fail(sb):
    sb.workflow()
    sb.passed()
    queued = {"statusCheckRollup": [check("lint", "", "QUEUED")]}
    failed = {"statusCheckRollup": [check("lint", "FAILURE")]}
    sb.state(
        pr=sb.pr(statusCheckRollup=[check("lint", "SKIPPED")]),
        after_ready_sequence=[{}, {}, {}, queued, failed],
    )
    done = sb.ship("merge", "--settle", "5")
    assert done.returncode == 1 and sb.calls("pr merge") == []
    assert "checks failed: lint" in last_line(done)


def test_merge_does_not_take_a_skipped_check_for_a_run(sb):
    sb.workflow()
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "SKIPPED")]))
    done = sb.ship("merge", "--settle", "0.5")
    assert done.returncode == 1 and sb.calls("pr merge") == []
    assert last_line(done).startswith("Not merged: no check ran on #7 in the ")
    assert last_line(done).endswith("--allow-no-checks. #7 is no longer a draft.")
    done = sb.ship("merge", "--allow-no-checks")
    assert done.returncode == 0, done.stdout + done.stderr


def test_merge_stops_when_the_pull_request_turns_into_a_draft(sb):
    sb.passed()
    ready = sb.pr(isDraft=False, mergeStateStatus="CLEAN")
    sb.state(pr_sequence=[ready, ready, ready, sb.pr()])
    done = sb.ship("merge", "--settle", "5")
    assert done.returncode == 1 and sb.calls("pr merge") == []
    assert last_line(done) == "Not merged: #7 was turned into a draft."


def test_merge_gives_up_on_a_check_that_keeps_running(sb):
    sb.passed()
    running = {"statusCheckRollup": [check("lint"), check("owners", "", "QUEUED")]}
    sb.state(after_ready_sequence=[running])
    done = sb.ship("merge", "--timeout", "1")
    assert done.returncode == 1 and sb.calls("pr merge") == []
    assert last_line(done).startswith("Not merged: checks still running")
    assert "#7 is no longer a draft." in last_line(done)


@pytest.mark.parametrize(
    ("later", "code", "words"),
    [
        (
            {"statusCheckRollup": [check("owners", "FAILURE")]},
            1,
            "checks failed: owners",
        ),
        ({"reviewRequests": [{"login": "owner"}]}, 3, "review requested from owner"),
        ({"reviewDecision": "REVIEW_REQUIRED"}, 3, "requires a review"),
        ({"headRefOid": "1" * 40}, 1, "pull and test again"),
        ({"mergeStateStatus": "BEHIND"}, 1, "behind origin/main, GitHub says"),
        ({"mergeStateStatus": "BLOCKED"}, 3, "branch protection blocks the merge"),
        ({"mergeStateStatus": "UNKNOWN"}, 1, "has not said"),
        ({"isDraft": True}, 1, "still shows #7 as a draft"),
        ({"state": "CLOSED"}, 1, "#7 was closed"),
        ({"state": "MERGED"}, 1, "#7 is already merged, not by this run"),
    ],
)
def test_merge_stops_on_what_shows_up_after_marking_ready(sb, later, code, words):
    sb.passed()
    sb.state(after_ready_sequence=[{}, {}, {}, {}, later])
    done = sb.ship("merge", "--settle", "20")
    gone = "state" in later or "isDraft" in later
    assert ("no longer a draft" in last_line(done)) != gone
    assert done.returncode == code, done.stdout + done.stderr
    assert sb.calls("pr merge") == []
    assert words in last_line(done)
    if code == 3:
        assert last_line(done).startswith("STOP: ")
        assert last_line(done).endswith("#7 is no longer a draft. Ask the user.")
    else:
        assert last_line(done).startswith("Not merged: ")
    if "FAILURE" in json.dumps(later):
        assert "gh run view 42 --log-failed" in done.stdout


def test_merge_reports_a_failed_ready_last_on_stdout(sb):
    sb.passed()
    sb.state(ready_error="GraphQL: Resource not accessible by integration")
    done = sb.ship("merge")
    assert done.returncode == 2 and sb.calls("pr merge") == []
    assert last_line(done).startswith("Not merged: gh pr ready failed: GraphQL")


# ---------------------------------------------------------------- releases

RELEASES = [
    {"title": "chore: release 2.0.0"},
    {"title": "chore: release v2.0.0"},
    {"title": "chore(main): release 1.2.3"},
    {"title": "chore(release): prepare notes"},
    {"title": "build: release 1.0.0"},
    {"title": "chore: prepare release 0.2.0"},
    {"title": "Version Packages"},
    {"title": "v1.2.3"},
    {"title": "chore: bump version to 1.4.0"},
    {"title": "chore: cut v0.2.0"},
    {"title": "release: 1.2.0"},
    {"title": "Release 1.2.3"},
    {"headRefName": "integration"},
    {"headRefName": "integration/q3"},
    {"headRefName": "release"},
    {"headRefName": "releases/1.0"},
    {"headRefName": "rel/1.0"},
    {"headRefName": "hotfix/1.0.1"},
    {"headRefName": "stage"},
    {"headRefName": "chore/release-2.0.0"},
    {"headRefName": "changeset-release/main"},
    {"headRefName": "release-please--branches--main"},
    {"headRefName": "v1.2.3"},
    {"headRefName": "prerelease/1.0"},
    {"headRefName": "rc/1.0"},
    {"baseRefName": "production"},
    {"headRefName": "main", "baseRefName": "production"},
    {"headRefName": "main", "baseRefName": "customer-a"},
]
NOT_RELEASES = [
    {"title": "Release: notes page layout"},
    {"title": "feat: release notes page"},
    {"title": "fix: release the lock before retrying"},
    {"title": "chore(deps): bump lodash from 4.17.20 to 4.17.21"},
    {"title": "docs: versioning policy"},
    {"headRefName": "feat/release-notes"},
    {"headRefName": "hotfix/login-crash"},
    {"headRefName": "release-notes-page"},
    {"headRefName": "integration-tests/add-db"},
    {"headRefName": "fix/7-rc-file"},
    {"baseRefName": "release/v0.1.0"},
    {"headRefName": "fix/9-typo", "baseRefName": "develop"},
]


@pytest.mark.parametrize("over", RELEASES, ids=str)
def test_releases_are_recognised(over):
    assert held(over) == ("fail", True)


@pytest.mark.parametrize("over", NOT_RELEASES, ids=str)
def test_changes_that_only_mention_a_release_are_not_releases(over):
    assert held(over) == ("pass", False)


# ---------------------------------------------------------------- stuck loop, opt-out

OPT_OUTS = [
    "Merges: off",
    "**Merges:** ask first",
    "- **Merges**: ask first",
    "__Merges:__ ask first",
    "> Merges: ask first",
    "`Merges: ask first`",
    "- `Merges: ask first`.",
    "<!-- Merges: ask first -->",
    "<!--\nMerges: ask first\n-->",
    "1. Merges: ask first",
    "2) Merges: ask first",
    "- [x] Merges: ask first",
    "- [ ] Merges: ask first",
    "+ Merges: ask first",
    "## Merges: ask first",
    "| Merges: ask first |",
    "| Rule | Merges: ask first |",
    "| Merges | ask first |",
    "| **Merges** | ask first |",
    "Merges - ask first",
    "Merges \u2014 ask first",
    "Merging: ask first",
    "Merges: always ask first",
    "Merges: never",
    "Merges: manual",
    "<!-- pipelinekit: Merges: ask first -->",
    '"Merges: ask first"',
    "'Merges: ask first'",
    "\u201cMerges: ask first\u201d",
    '- "Merges: ask first".',
    "> \u2018Merges: ask first\u2019",
]
NOT_OPT_OUTS = [
    "To turn this off, add `Merges: ask first` to this file.",
    "`Merges: ask first` turns the automatic merge off.",
    "Merges are asked for first in other projects.",
    "## Merges\n\nAsk the team in the channel.",
    "We do not use Merges: ask first here.",
    "To opt out, add the line `Merges: ask first`.",
    "| Merges | squash only |",
    "| Step | Merges |",
    "Merging - how it works here",
    "Merges: squash",
]


@pytest.mark.parametrize("line", OPT_OUTS)
def test_the_opt_out_line_in_its_markdown_forms(line):
    assert ship.opts_out(f"# Project\n\n{line}\n")


@pytest.mark.parametrize("line", NOT_OPT_OUTS)
def test_a_text_about_the_opt_out_line_does_not_opt_out(line):
    assert not ship.opts_out(f"# Project\n\n{line}\n")


def test_the_opt_out_is_read_from_a_file_with_a_byte_order_mark(sb):
    (sb.work / "CLAUDE.md").write_text("\ufeffMerges: ask first\n", encoding="utf-8")
    assert gates(sb.ship("status", "--json"))["policy"]["state"] == "fail"


def test_a_stuck_loop_shows_in_status_and_merge(sb):
    for n in range(3):
        sb.commit(f"fix: attempt {n}")
        last = sb.ship("record", "--result", "fail", "--open", "F2", f"F{n + 5}")
    assert last.returncode == 3
    sb.git("push", "-q")
    sb.state()
    done = sb.ship("status", "--json")
    assert done.returncode == 3 and json.loads(done.stdout)["stop"] is True
    assert "F2 still open after two fix attempts" in gates(done)["tested"]["detail"]
    done = refused(sb, "tested", 3)
    assert "Result: stop and ask the user (tested)" in done.stdout


def test_rounds_on_one_commit_are_one_fix_attempt(sb):
    for _ in range(4):
        done = sb.ship("record", "--result", "fail", "--open", "F2")
        assert done.returncode == 0, done.stdout


def test_finding_ids_ignore_case_and_blanks(sb):
    done = sb.ship("record", "--result", "fail", "--open", "f1", "F1", " F2 ", "")
    assert done.returncode == 0
    data = json.loads((sb.work / "docs/uat/feat-1-thing.json").read_text())
    assert data["rounds"][0]["open"] == ["F2", "f1"]
    assert sb.ship("record", "--result", "fail", "--open", " ").returncode == 2
    for name in ("f2", "F2 "):
        sb.commit("fix: again")
        done = sb.ship("record", "--result", "fail", "--open", name)
    assert done.returncode == 3
    assert "F2 still open after two fix attempts" in done.stdout


def test_an_unreadable_record_is_not_overwritten(sb):
    path = sb.work / "docs/uat/feat-1-thing.json"
    path.parent.mkdir(parents=True)
    for text in ("{not json", '{"rounds": "none"}', "[]"):
        path.write_text(text)
        done = sb.ship("record", "--result", "pass", "--release", "no")
        assert done.returncode == 2 and "not a readable test record" in done.stderr
        assert path.read_text() == text
        done = sb.ship("status", "--json")
        assert "not a readable test record" in gates(done)["tested"]["detail"]


# ---------------------------------------------------------------- checks, arguments


def test_no_check_is_not_a_pass_when_workflows_run_on_pull_requests(sb):
    sb.workflow()
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    done = sb.ship("status", "--json")
    assert gates(done)["ci"]["state"] == "pending"
    done = sb.ship("status", "--json", "--allow-no-checks")
    assert gates(done)["ci"]["state"] == "pass"
    done = sb.ship("wait", "--grace", "0")
    assert done.returncode == 1 and "no check has shown up" in done.stdout
    assert sb.ship("wait", "--grace", "0", "--allow-no-checks").returncode == 0
    assert sb.ship("wait", "--allow-no-checks", timeout=40).returncode == 0
    assert "--allow-no-checks" in refused(sb, "ci", 1).stdout
    done = sb.ship("merge", "--grace", "0", "--allow-no-checks")
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(sb.calls("pr merge")) == 1


def test_no_check_is_fine_when_no_workflow_runs_on_pull_requests(sb):
    sb.workflow("on:\n  push:\n    branches: [main]\n")
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    assert gates(sb.ship("status", "--json"))["ci"]["state"] == "pass"
    assert sb.ship("wait", "--grace", "0").returncode == 0


@pytest.mark.parametrize(
    "args",
    [
        ("wait", "--timeout", "-1"),
        ("merge", "--grace", "-5"),
        ("wait", "--grace", "soon"),
        ("wait", "--timeout", "nan"),
        ("wait", "--timeout", "inf"),
        ("merge", "--settle", "-1"),
    ],
)
def test_seconds_must_be_a_number_that_is_not_negative(sb, args):
    done = sb.ship(*args)
    assert done.returncode == 2 and sb.all_calls() == []


def test_merge_passes_the_subject_as_one_argument(sb):
    sb.passed()
    assert sb.ship("merge", "--subject", "feat: thing (#7)").returncode == 0
    assert sb.calls("pr merge")[0][-1] == "--subject=feat: thing (#7)"


def test_merge_refuses_a_method_the_repository_does_not_allow(sb):
    sb.passed()
    done = sb.ship("merge", "--method", "rebase")
    assert done.returncode == 2
    assert "does not allow rebase merges" in last_line(done)
    assert sb.calls("pr ready") == [] and sb.calls("pr merge") == []


def test_wait_without_a_pull_request(sb):
    sb.state(pr=None)
    done = sb.ship("wait", "--grace", "0")
    assert done.returncode == 1 and "no open pull request" in done.stdout


def test_status_names_a_pull_request_that_is_not_open(sb):
    sb.state(pr=sb.pr(state="MERGED"))
    done = sb.ship("status")
    first = done.stdout.splitlines()[0]
    assert first.endswith("(merged)") and "draft" not in first
    assert "Result: not ready (pr, judged, tested)" in done.stdout
