"""ship.py against a fake gh and a throwaway repository with a bare origin."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SHIP = Path(__file__).resolve().parents[1] / "ship.py"
BRANCH = "feat/1-thing"

FAKE_GH = r"""#!/usr/bin/env python3
import json
import os
import sys

d = os.environ["FAKE_GH"]
args = sys.argv[1:]
with open(os.path.join(d, "calls.jsonl"), "a") as f:
    f.write(json.dumps(args) + "\n")
with open(os.path.join(d, "state.json")) as f:
    state = json.load(f)
kind = args[:2]
if kind == ["pr", "view"]:
    counter = os.path.join(d, "views")
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    with open(counter, "w") as f:
        f.write(str(n + 1))
    seq = state.get("pr_sequence")
    pr = seq[min(n, len(seq) - 1)] if seq else state.get("pr")
    if pr is None:
        sys.exit('no pull requests found for branch "x"')
    if os.path.exists(os.path.join(d, "ready")) and pr.get("isDraft"):
        pr = dict(pr, isDraft=False, mergeStateStatus=state.get("after_ready", "CLEAN"))
    print(json.dumps(pr))
elif kind == ["api", "user"]:
    print(state.get("user", "me"))
elif kind == ["repo", "view"]:
    print(json.dumps(state["repo"]))
elif kind == ["pr", "ready"]:
    open(os.path.join(d, "ready"), "w").close()
elif kind == ["pr", "merge"]:
    if state.get("merge_error"):
        sys.exit(state["merge_error"])
else:
    sys.exit("fake gh: unexpected call " + " ".join(args))
"""


def check(name, conclusion="SUCCESS", status="COMPLETED"):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": "https://github.com/o/r/actions/runs/42/job/1",
    }


class Sandbox:
    def __init__(self, tmp):
        self.tmp = tmp
        self.fake = tmp / "fake"
        self.work = tmp / "work"
        bindir = tmp / "bin"
        for d in (self.fake, bindir, tmp / "home"):
            d.mkdir()
        gh = bindir / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp / "home"),
            "CLAUDE_HOME": str(tmp / "home" / ".claude"),
            "GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "FAKE_GH": str(self.fake),
            "SHIP_POLL_SECONDS": "0.05",
        }
        self.env.pop("PIPELINEKIT_MERGE", None)
        origin = tmp / "origin.git"
        self.git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp)
        self.git("init", "-q", "-b", "main", str(self.work), cwd=tmp)
        self.git("remote", "add", "origin", str(origin))
        self.commit("chore: start")
        self.git("push", "-q", "-u", "origin", "main")
        self.git("checkout", "-q", "-b", BRANCH)
        self.commit("feat: thing")
        self.git("push", "-q", "-u", "origin", BRANCH)
        self.state()

    def git(self, *args, cwd=None):
        done = subprocess.run(
            ["git", *args],
            cwd=cwd or self.work,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.strip()

    def commit(self, subject):
        self.git("commit", "-q", "--allow-empty", "-m", subject)

    def head(self):
        return self.git("rev-parse", "HEAD")

    def pr(self, **over):
        pr = {
            "number": 7,
            "url": "https://example.test/pull/7",
            "title": "feat: thing",
            "state": "OPEN",
            "isDraft": True,
            "isCrossRepository": False,
            "baseRefName": "main",
            "headRefName": BRANCH,
            "headRefOid": self.head(),
            "author": {"login": "me"},
            "reviewDecision": "",
            "reviewRequests": [],
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "DRAFT",
            "statusCheckRollup": [check("lint"), check("selftests")],
        }
        pr.update(over)
        return pr

    def state(self, **over):
        state = {
            "user": "me",
            "repo": {
                "nameWithOwner": "o/r",
                "defaultBranchRef": {"name": "main"},
                "mergeCommitAllowed": True,
                "squashMergeAllowed": True,
                "rebaseMergeAllowed": False,
            },
            "pr": self.pr(),
        }
        state.update(over)
        (self.fake / "state.json").write_text(json.dumps(state))

    def ship(self, *args, **env):
        return subprocess.run(
            [sys.executable, str(SHIP), *args],
            cwd=self.work,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def calls(self, kind):
        log = self.fake / "calls.jsonl"
        if not log.exists():
            return []
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        return [row for row in rows if row[:2] == kind.split()]

    def passed(self):
        done = self.ship("record", "--result", "pass")
        assert done.returncode == 0, done.stderr

    def advance_base(self):
        other = self.tmp / "other"
        self.git("clone", "-q", str(self.tmp / "origin.git"), str(other), cwd=self.tmp)
        self.git("commit", "-q", "--allow-empty", "-m", "fix: elsewhere", cwd=other)
        self.git("push", "-q", "origin", "main", cwd=other)


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


def gates(done):
    return {g["gate"]: g for g in json.loads(done.stdout)["gates"]}


# ---------------------------------------------------------------- status


def test_status_lists_every_gate_with_its_reason(sb):
    done = sb.ship("status")
    assert done.returncode == 1
    for name in (
        "pr",
        "own",
        "policy",
        "release",
        "review",
        "current",
        "up-to-date",
        "tested",
        "ci",
    ):
        assert f" {name} " in done.stdout
    assert "no test record" in done.stdout
    assert "Result: not ready (tested)" in done.stdout


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


def refused(sb, gate_name, code):
    done = sb.ship("merge", "--grace", "0", "--timeout", "1")
    assert done.returncode == code, done.stdout + done.stderr
    assert f"FAIL  {gate_name} " in done.stdout or f"wait  {gate_name} " in done.stdout
    assert sb.calls("pr merge") == [] and sb.calls("pr ready") == []
    return done


def test_merge_refuses_without_a_test_record(sb):
    assert "no test record" in refused(sb, "tested", 1).stdout


def test_merge_refuses_a_failed_round(sb):
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
    assert "1 commit behind main" in refused(sb, "up-to-date", 1).stdout


def test_merge_refuses_a_conflicting_branch(sb):
    sb.passed()
    sb.state(pr=sb.pr(mergeable="CONFLICTING"))
    assert "conflicts with main" in refused(sb, "up-to-date", 1).stdout


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
    done = sb.ship("merge", "--dry-run", PIPELINEKIT_MERGE="ask")
    assert done.returncode == 3 and "PIPELINEKIT_MERGE=ask" in done.stdout


def test_a_sentence_about_the_opt_out_does_not_opt_out(sb):
    text = "- A project turns this off with the line `Merges: ask first`.\n"
    (sb.work / "CLAUDE.md").write_text(text)
    assert gates(sb.ship("status", "--json"))["policy"]["state"] == "pass"


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
    assert "Merged #7 into main" in done.stdout
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
        "--subject",
        f"chore: merge {BRANCH}",
    ]
    assert sb.git("branch", "--show-current") == BRANCH


def test_merge_never_passes_admin_and_has_no_option_for_it(sb):
    sb.passed()
    done = sb.ship("merge", "--admin")
    assert done.returncode == 2 and sb.calls("pr merge") == []
    assert sb.ship("merge").returncode == 0
    flat = [arg for call in sb.calls("pr merge") for arg in call]
    assert "--admin" not in flat and "--auto" not in flat
    assert "--admin" not in SHIP.read_text()


def test_merge_dry_run_changes_nothing(sb):
    sb.passed()
    done = sb.ship("merge", "--dry-run")
    assert done.returncode == 0
    assert "Would run: gh pr merge 7 --squash --match-head-commit" in done.stdout
    assert sb.calls("pr merge") == [] and sb.calls("pr ready") == []
    assert sb.git("branch", "--show-current") == BRANCH


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
    assert done.returncode == 1 and "not mergeable" in done.stderr
    assert sb.git("branch", "--show-current") == BRANCH


def test_merge_waits_for_checks_that_show_up_late(sb):
    sb.passed()
    late = [sb.pr(statusCheckRollup=[]), sb.pr(statusCheckRollup=[check("lint")])]
    sb.state(pr_sequence=[late[0], late[0], late[1]])
    done = sb.ship("merge", "--grace", "30")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 check finished" in done.stdout


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
    done = sb.ship("record", "--result", "pass")
    assert done.returncode == 1 and "commit first" in done.stderr


def test_record_stops_after_five_failed_rounds(sb):
    for n in range(1, 5):
        done = sb.ship("record", "--result", "fail", "--open", f"F{n}")
        assert done.returncode == 0, n
    done = sb.ship("record", "--result", "fail", "--open", "F9")
    assert done.returncode == 3 and "5 failed rounds in a row" in done.stdout


def test_record_stops_when_a_finding_survives_two_fix_attempts(sb):
    assert sb.ship("record", "--result", "fail", "--open", "F1", "F2").returncode == 0
    assert sb.ship("record", "--result", "fail", "--open", "F2", "F3").returncode == 0
    done = sb.ship("record", "--result", "fail", "--open", "F2")
    assert (
        done.returncode == 3 and "F2 still open after two fix attempts" in done.stdout
    )


def test_a_passed_round_resets_the_count(sb):
    for _ in range(2):
        sb.ship("record", "--result", "fail", "--open", "F1")
    assert sb.ship("record", "--result", "pass").returncode == 0
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
