"""ship.py against a fake gh and a throwaway repository with a bare origin."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SHIP = Path(__file__).resolve().parents[1] / "ship.py"
BRANCH = "feat/1-thing"


def load_ship():
    spec = importlib.util.spec_from_file_location("ship", SHIP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ship = load_ship()

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
if kind == ["pr", "view"] and "pr_raw" in state:
    print(state["pr_raw"])
elif kind == ["pr", "view"]:
    counter = os.path.join(d, "views")
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    with open(counter, "w") as f:
        f.write(str(n + 1))
    seq = state.get("pr_sequence")
    pr = seq[min(n, len(seq) - 1)] if seq else state.get("pr")
    if pr is None:
        sys.exit('no pull requests found for branch "x"')
    if os.path.exists(os.path.join(d, "ready")):
        counter = os.path.join(d, "ready_views")
        k = int(open(counter).read()) if os.path.exists(counter) else 0
        with open(counter, "w") as f:
            f.write(str(k + 1))
        if pr.get("isDraft"):
            now = state.get("after_ready", "CLEAN")
            pr = dict(pr, isDraft=False, mergeStateStatus=now)
        later = state.get("after_ready_sequence")
        if later:
            pr = dict(pr, **later[min(k, len(later) - 1)])
    print(json.dumps(pr))
elif kind == ["api", "user"]:
    print(state.get("user", "me"))
elif kind == ["repo", "view"]:
    print(json.dumps(state["repo"]))
elif kind == ["pr", "ready"]:
    if state.get("ready_error"):
        sys.exit(state["ready_error"])
    open(os.path.join(d, "ready"), "w").close()
elif kind == ["pr", "merge"]:
    if state.get("merge_error"):
        sys.exit(state["merge_error"])
    if state.get("on_merge"):
        import subprocess
        subprocess.run(state["on_merge"], check=True)
elif kind == ["pr", "list"]:
    if state.get("list_error"):
        sys.exit(state["list_error"])
    print(json.dumps(state.get("merged_into", [])))
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

    def repo(self, **over):
        repo = {
            "nameWithOwner": "o/r",
            "defaultBranchRef": {"name": "main"},
            "mergeCommitAllowed": True,
            "squashMergeAllowed": True,
            "rebaseMergeAllowed": False,
        }
        repo.update(over)
        return repo

    def state(self, **over):
        state = {"user": "me", "repo": self.repo(), "pr": self.pr()}
        state.update(over)
        (self.fake / "state.json").write_text(json.dumps(state))

    def ship(self, *args, **env):
        """Run ship.py; a merge settles in 0.2 s here unless the test says more."""
        if args[:1] == ("merge",) and not {"--dry-run", "--settle"} & set(args):
            args = (*args, "--settle", "0.2")
        return subprocess.run(
            [sys.executable, str(SHIP), *args],
            cwd=self.work,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def all_calls(self):
        log = self.fake / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def calls(self, kind):
        return [row for row in self.all_calls() if row[:2] == kind.split()]

    def views_after_ready(self):
        """How often the pull request was read between `ready` and the merge."""
        rows = self.all_calls()
        start = rows.index(["pr", "ready", "7"])
        merges = [i for i, row in enumerate(rows) if row[:2] == ["pr", "merge"]]
        stop = merges[0] if merges else len(rows)
        return sum(row[:2] == ["pr", "view"] for row in rows[start:stop])

    def workflow(self, text="on: [push, pull_request]\n"):
        path = self.work / ".github" / "workflows" / "ci.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def passed(self, release="no"):
        done = self.ship("record", "--result", "pass", "--release", release)
        assert done.returncode == 0, done.stderr

    def change(self, path, before, after):
        """Commit `before` to the base and `after` to the branch, both pushed."""
        file = self.work / path
        file.parent.mkdir(parents=True, exist_ok=True)
        for branch, text in (("main", before), (BRANCH, after)):
            self.git("checkout", "-q", branch)
            if branch == BRANCH:
                self.git("merge", "-q", "--no-edit", "main")
            file.write_text(text)
            self.git("add", "--", path)
            self.git("commit", "-q", "-m", "chore: edit")
            self.git("push", "-q", "origin", branch)
        self.state()

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


def last_line(done):
    return done.stdout.strip().splitlines()[-1]


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
    assert "Result: not ready (pr, tested)" in sb.ship("status").stdout


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
    start = "STOP: " if code == 3 else "Not merged: "
    assert last_line(done).startswith(f"{start}{gate_name}: "), last_line(done)
    assert last_line(done).endswith("Ask the user.") == (code == 3)
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
    assert "--admin" not in SHIP.read_text()


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
    assert settle_of(sb) == "90"
    assert settle_of(sb, "--grace", "200") == "200"
    assert settle_of(sb, "--allow-no-checks") == "30"
    assert settle_of(sb, "--settle", "5") == "5"
    sb.state()
    sb.workflow("on:\n  pull_request:\n    types: [opened, ready_for_review]\n")
    assert settle_of(sb) == "90"


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
        ({"mergeStateStatus": "BEHIND"}, 1, "behind main"),
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


@pytest.fixture(autouse=True)
def nobodys_rules(monkeypatch):
    """No test reads the rules file of whoever runs the tests."""
    monkeypatch.setenv("CLAUDE_HOME", "/nonexistent/claude-home")


def held(over, default="main", name="o/r", merged="[]"):
    """The release gate itself, without a repository: (state, stop)."""
    info = {"nameWithOwner": name, "defaultBranchRef": {"name": default}}
    pr = {"title": "feat: thing", "headRefName": BRANCH, "baseRefName": "main"}
    nowhere = Path("/nonexistent/checkout")
    repo = SimpleNamespace(
        info=lambda: info,
        remote="origin",
        root=nowhere,
        record_file=nowhere / "record.json",
        try_git=lambda *args: (0, "", ""),
        gh=lambda *args, **more: (0, merged, ""),
    )
    found = ship.release_gate(repo, {**pr, **over})
    return found["state"], found["stop"]


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
    assert "Result: not ready (pr, tested)" in done.stdout


# ---------------------------------------------------------------- release wording

RELEASE_TITLES = [
    "chore: version bump",
    "chore: bump version",
    "chore: bump package version",
    "chore: increment version",
    "Bump version: 1.2.3 to 1.2.4",
    "Bump version: 1.2.3 \u2192 1.2.4",
    "chore: bump version (1.2.4)",
    "chore: bump version to v2",
    "chore: set version to 0.2.0",
    "chore: update version to 0.2.0",
    "Version 1.2.3",
    "chore: version 1.2.3",
    "build: version 0.2.0",
    "Prepare for 2.0 release",
    "chore: release",
    "Release",
    "ci: release",
    "chore: new release",
    "chore: cut release",
    "chore: prepare release",
    "Prepare release",
    "chore: release prep",
    "chore: release candidate",
    "chore: prepare 0.3.0",
    "chore: prepare v0.2.0",
    "Prepare 1.2.0",
    "chore: prepare 0.2.0 release",
    "chore: 1.2.4 release",
    "[release] 1.2.0",
    "[Release] v1.2.0",
    "Release-1.2.0",
    "chore: pre-release 1.0.0-beta.1",
    "chore: prerelease 1.0.0-beta.1",
    "chore: finalize v1.0",
    "chore: publish to npm",
    "chore: publish v2",
    "chore: publish packages",
    "chore: publish 1.2.0",
    "chore: release notes and version bump for 0.2.0",
    "chore: update changelog for 0.2.0",
    "chore: ship 0.2.0",
    "chore: deploy to production",
    "Merge develop into main",
    "feat: add thing (release 0.2.0)",
    "Bump to 1.2.4",
    "chore(release): prepare",
    "chore: release pipelinekit 0.2.0",
    "Cut 1.2.0",
    "chore: version packages",
    "chore: tag 1.0.0",
    "chore: 0.2.0",
    "chore: bump patch version",
    "bump minor version",
    "chore: bump app version to 1.2.4",
    "chore: bump version to 1.2.4 [skip ci]",
    "chore: release 1.2.3 [ci skip]",
    "Bumped version to 1.2.4",
    "Bumping version",
    "increase version",
    "update version number",
    "Hotfix 1.0.1",
    "chore: create release 1.2.0",
    "Initial release",
    "first release",
    "final release",
    "major release",
    "patch release",
    "stable release",
    "preparing release",
    "do the release",
    "finish 1.2.0",
    "Beta 2",
    "chore: rc1",
    "Promote to production",
    "chore: merge develop into main",
    "[maven-release-plugin] prepare release v1.2.3",
    "[Gradle Release Plugin] - new version commit: 1.2.4",
    "chore : release 1.2.3",
    "feat: 1.2.0",
    "feat!: 2.0.0",
    "chore: pipelinekit 0.2.0",
    "chore: bump version in package.json",
    "chore: release main",
    "chore: weekly release",
    "chore: next version",
    "chore: bump versions",
    "chore: v2.0.0 :tada:",
    "chore: re-release 1.2.3",
    "chore: upgrade version to 1.2.4",
    "chore: LTS release 1.2.4",
    "GA release",
    "REL 1.2.4",
    "chore: patch",
    "Deploy",
    "chore: rel 1.2.4",
]
ORDINARY_TITLES = [
    "fix: release 1.2.0 broke the installer",
    "fix: publish 1.2.0 fails on Windows",
    "fix: tag 1.0.0 not found by the resolver",
    "docs: release 1.2.0 notes",
    "chore(release): fix changelog script",
    "ci(release): pin action versions",
    "feat: cut 0.2 s from startup",
    "feat: add release notes page",
    "fix: version check in the installer",
    "docs: explain the release process",
    "chore: bump pipelinekit to 0.2.0",
    "chore(deps): bump lodash from 4.17.20 to 4.17.21 [skip ci]",
    "chore: update next to 15.0.1",
    "chore: update node to 20.1",
    "chore(deps): update dependency typescript to v5",
    "fix: hotfix script exits early",
    "hotfix: login crash",
    "fix: beta 2 flag is ignored",
    "chore: merge main into develop",
    "ci: bump python version to 3.12",
    "chore: update .NET version to 9.0",
    "chore: release script",
    "chore: minor update",
]
RELEASE_HEADS = [
    "chore/212-release-v0.2.0",
    "chore/212-release-0.2.0",
    "chore/212-release",
    "chore/213-version-bump",
    "build/214-release-0.2.0",
    "chore/release",
    "chore/prepare-release",
    "chore/bump-version-1.2.3",
    "chore/v0.2.0",
    "build/99-version-0.2.0",
    "version/2.0",
    "bump/1.2.3",
    "1.x",
    "1.2.x",
    "v2",
    "v1.2",
    "beta",
    "uat",
    "qa",
    "preprod",
    "release-candidate",
    "staging/eu",
    "staging",
    "test",
    "testing",
    "canary",
    "preview",
    "trunk",
    "master",
    "release/212-v0.2.0",
    "chore/release-0.2",
    "development",
    "develop",
    "dev",
    "next",
    "chore/12-bump-patch-version",
    "chore/12-patch-version",
    "chore/12-major-version-bump",
    "chore/12-hotfix-1.0.1",
    "chore/12-rc1",
    "staging-eu",
    "snapshot",
]
ORDINARY_HEADS = [
    "fix/release-1.2-regression",
    "feat/release-2.0-banner",
    "docs/release-1.2-notes",
    "feat/12-release-notes",
    "feat/21-v2",
    "feat/3-v2",
    "feat/61-v2",
    "release-notes-page",
]
# (head, base, default branch)
RELEASE_BRANCHES = [
    (BRANCH, "gh-pages", "main"),
    (BRANCH, "deploy/prod", "main"),
    (BRANCH, "env/production", "main"),
    (BRANCH, "prod", "main"),
    (BRANCH, "live", "main"),
    (BRANCH, "deploy", "main"),
    (BRANCH, "stable", "main"),
    ("main", "staging", "main"),
    ("main", "develop", "main"),
    ("main", "release/v1.0", "main"),
    (BRANCH, "main", "develop"),
    (BRANCH, "master", "develop"),
    ("release/1.0", "master", "develop"),
    ("release/1.0", "main", "develop"),
    ("develop", "main", "develop"),
    (BRANCH, "master", "main"),
    (BRANCH, "release", "main"),
    (BRANCH, "customer-a", "main"),
    (BRANCH, "prd", "main"),
    (BRANCH, "production-eu", "main"),
    (BRANCH, "production_eu", "main"),
    (BRANCH, "production-v2", "main"),
    (BRANCH, "prod-us", "main"),
    (BRANCH, "eu-production", "main"),
    (BRANCH, "aws-prod", "main"),
    (BRANCH, "azure-production", "main"),
    (BRANCH, "live-eu", "main"),
    (BRANCH, "deploy-prod", "main"),
    (BRANCH, "cloudflare-pages", "main"),
    (BRANCH, "heroku", "main"),
    (BRANCH, "netlify", "main"),
    (BRANCH, "vercel", "main"),
    (BRANCH, "publish", "main"),
    (BRANCH, "released", "main"),
    (BRANCH, "latest", "main"),
    ("staging", "production-eu", "main"),
    ("develop", "staging", "main"),
    ("develop", "release/1.0", "main"),
    ("changeset-release/next", "next", "main"),
    ("release/1.0", "develop", "main"),
]
ORDINARY_BRANCHES = [
    (BRANCH, "develop", "develop"),
    (BRANCH, "release/v0.1.0", "main"),
    ("fix/9-typo", "staging", "main"),
    (BRANCH, "feat/2-base", "main"),
    (BRANCH, "1.x", "main"),
    (BRANCH, "v2", "main"),
    (BRANCH, "staging/eu", "main"),
    (BRANCH, "next", "main"),
    (BRANCH, "release-1.2", "main"),
    (BRANCH, "hotfix/1.0.1", "main"),
    (BRANCH, "trunk", "trunk"),
]


@pytest.mark.parametrize("title", RELEASE_TITLES)
def test_a_title_that_names_a_release_is_held(title):
    assert held({"title": title}) == ("fail", True)


@pytest.mark.parametrize("title", ORDINARY_TITLES)
def test_a_title_about_a_release_is_not_held(title):
    assert held({"title": title}) == ("pass", False)


def test_the_name_of_the_repository_counts_as_a_release_word():
    for title in ("chore: pipelinekit 0.2.0", "chore: bump pipelinekit to 0.2.0"):
        assert held({"title": title}, name="o/pipelinekit") == ("fail", True), title


@pytest.mark.parametrize("head", RELEASE_HEADS)
def test_a_branch_that_names_a_release_is_held(head):
    assert held({"headRefName": head}) == ("fail", True)


@pytest.mark.parametrize("head", ORDINARY_HEADS)
def test_a_branch_about_a_release_is_not_held(head):
    assert held({"headRefName": head}) == ("pass", False)


@pytest.mark.parametrize(("head", "base", "default"), RELEASE_BRANCHES)
def test_a_deploy_or_a_promotion_is_held(head, base, default):
    over = {"headRefName": head, "baseRefName": base}
    assert held(over, default) == ("fail", True)


@pytest.mark.parametrize(("head", "base", "default"), ORDINARY_BRANCHES)
def test_a_change_into_a_working_branch_is_not_held(head, base, default):
    over = {"headRefName": head, "baseRefName": base}
    assert held(over, default) == ("pass", False)


def test_merge_refuses_what_goes_into_main_when_it_is_not_the_default(sb):
    sb.passed()
    sb.state(repo=sb.repo(defaultBranchRef={"name": "develop"}))
    done = refused(sb, "release", 3)
    assert "main is not the default branch (develop)" in last_line(done)


PACKAGE = (
    '{\n  "name": "x",\n  "version": "%s",\n  "dependencies": {"lodash": "%s"}\n}\n'
)
PYPROJECT = '[project]\nname = "x"\nversion = "%s"\ndependencies = ["requests>=%s"]\n'
CSPROJ = (
    "<Project>\n  <PropertyGroup>\n    <Version>%s</Version>\n"
    "  </PropertyGroup>\n</Project>\n"
)
LOG = "# Changelog\n\n%s## 1.0.0\n\n- first\n"
# (file, on the base, on the branch, what the gate says)
VERSION_CHANGES = [
    ("VERSION", "1.0.0\n", "1.1.0\n", "the diff changes VERSION"),
    ("pkg/VERSION", "1.0.0\n", "1.1.0\n", "the diff changes pkg/VERSION"),
    (
        "package.json",
        PACKAGE % ("1.0.0", "4.17.20"),
        PACKAGE % ("1.1.0", "4.17.20"),
        "the diff sets a version in package.json",
    ),
    (
        "pyproject.toml",
        PYPROJECT % ("1.0.0", "2.0"),
        PYPROJECT % ("1.1.0", "2.0"),
        "the diff sets a version in pyproject.toml",
    ),
    (
        "src/App/App.csproj",
        CSPROJ % "1.0.0",
        CSPROJ % "1.1.0",
        "the diff sets a version in src/App/App.csproj",
    ),
    (
        "src/x/__init__.py",
        '__version__ = "1.0.0"\n',
        '__version__ = "1.1.0"\n',
        "the diff sets a version in src/x/__init__.py",
    ),
    (
        "CHANGELOG.md",
        LOG % "",
        LOG % "## [1.1.0] - 2026-11-10\n\n- second\n\n",
        "the diff adds a version heading to CHANGELOG.md",
    ),
]
ORDINARY_CHANGES = [
    ("package.json", PACKAGE % ("1.0.0", "4.17.20"), PACKAGE % ("1.0.0", "4.17.21")),
    ("pyproject.toml", PYPROJECT % ("1.0.0", "2.0"), PYPROJECT % ("1.0.0", "2.1")),
    ("CHANGELOG.md", LOG % "", LOG % "## Unreleased\n\n### Added\n\n- second\n\n"),
    ("docs/guide.md", "# Guide\n", "# Guide\n\n## 2.0.0\n\nversion = 2\n"),
    ("src/x/__init__.py", "import os\n", "import os\nimport sys\n"),
]


@pytest.mark.parametrize(("path", "before", "after", "words"), VERSION_CHANGES)
def test_merge_refuses_a_change_of_the_version(sb, path, before, after, words):
    sb.change(path, before, after)
    sb.passed()
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        f"STOP: release: {words}: a new version is a release. Ask the user."
    )


@pytest.mark.parametrize(("path", "before", "after"), ORDINARY_CHANGES)
def test_a_change_next_to_the_version_is_not_a_release(sb, path, before, after):
    sb.change(path, before, after)
    assert gates(sb.ship("status", "--json"))["release"]["state"] == "pass"


def test_a_diff_that_cannot_be_read_is_not_taken_for_ordinary(sb):
    sb.state(pr=sb.pr(baseRefName="develop"))
    release = gates(sb.ship("status", "--json"))["release"]
    assert release["state"] == "fail"
    assert release["detail"].startswith("cannot read what changes against develop: ")


def test_many_files_that_can_hold_a_version_are_held():
    count = ship.MAX_VERSION_FILES + 1
    meta = ":100644 100644 " + "1" * 40 + " " + "2" * 40 + " M"
    raw = "".join(f"{meta}\0pkg{n}/package.json\0" for n in range(count))
    repo = SimpleNamespace(remote="origin", try_git=lambda *args: (0, raw, ""))
    assert ship.version_change(repo, "main") == (
        f"the diff changes {count} files that can hold a version: "
        "a new version is a release",
        "",
    )


def test_merge_says_where_a_base_that_cannot_be_moved_left_the_checkout(sb):
    sb.git("checkout", "-q", "main")
    sb.commit("chore: local only")
    sb.git("checkout", "-q", BRANCH)
    sb.passed()
    head = sb.head()
    origin = str(sb.tmp / "origin.git")
    sb.state(
        on_merge=["git", "--git-dir", origin, "update-ref", "refs/heads/main", head]
    )
    done = sb.ship("merge")
    assert done.returncode == 0, done.stdout + done.stderr
    last = last_line(done)
    assert last.startswith(
        f"Merged #7 into main (squash) at {head[:7]}. Now on main, which could "
        "not be brought up to origin/main: git merge -q --ff-only origin/main "
        "failed: fatal: "
    ), last
    assert "hint:" not in last and "Still on" not in last
    assert sb.git("branch", "--show-current") == "main"


def test_a_failed_git_command_is_told_without_its_hints():
    text = "hint: Diverging branches\nhint:\nfatal: Not possible to fast-forward.\n"
    assert ship.git_said(text, 128) == "fatal: Not possible to fast-forward."
    assert ship.git_said("hint: only\nplain words\n", 1) == "plain words"
    assert ship.git_said("", 7) == "exit 7"


# ---------------------------------------------------------------- what the diff holds

OLD, NEW = "1" * 40, "2" * 40


def verdict(path, before, after, own=()):
    """What the diff rules say about one changed file, without a repository."""
    old = OLD if before else "0" * 40
    raw = f":100644 100644 {old} {NEW} M\0{path}\0"
    was = before.splitlines()
    added = "".join(f"+{line}\n" for line in after.splitlines() if line not in was)
    patch = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n"

    def try_git(*args):
        if "--raw" in args:
            return 0, raw, ""
        if args[0] == "cat-file":
            return 0, {OLD: before, NEW: after}[args[2]], ""
        return 0, patch + added, ""

    repo = SimpleNamespace(remote="origin", try_git=try_git)
    why, error = ship.version_change(repo, "main", own)
    assert not error
    return why


def bump(path, text, old="1.2.3", new="1.2.4"):
    return path, text % old, text % new


POM = (
    "<project>\n  <modelVersion>4.0.0</modelVersion>\n"
    "  <parent>\n    <artifactId>base</artifactId>\n"
    "    <version>%s</version>\n  </parent>\n"
    "  <artifactId>demo</artifactId>\n  <version>%s</version>\n"
    "  <dependencies>\n    <dependency>\n      <artifactId>junit</artifactId>\n"
    "      <version>%s</version>\n    </dependency>\n  </dependencies>\n"
    "</project>\n"
)
PLIST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0">\n<dict>\n'
    "  <key>CFBundleName</key>\n  <string>Demo</string>\n"
    "  <key>CFBundleShortVersionString</key>\n  <string>%s</string>\n"
    "</dict>\n</plist>\n"
)
CHART = (
    'apiVersion: v2\nname: demo\nversion: %s\nappVersion: "%s"\n'
    "dependencies:\n  - name: redis\n    version: %s\n"
)
CARGO = (
    '[package]\nname = "demo"\nversion = "%s"\n\n'
    '[dependencies.clap]\nversion = "%s"\nfeatures = ["derive"]\n'
)
ENGINES = '{\n  "name": "x",\n  "version": "1.0.0",\n  "engines": {"node": ">=%s"}\n}\n'
WORKFLOW = (
    'steps:\n  - uses: actions/setup-python@%s\n    with:\n      python-version: "%s"\n'
)
HELD_FILES = [
    ("pom.xml", POM % ("3.0.0", "1.2.3", "4.13.1"), POM % ("3.0.0", "1.2.4", "4.13.1")),
    bump(
        "demo.nuspec",
        "<package>\n  <metadata>\n    <id>demo</id>\n"
        "    <version>%s</version>\n  </metadata>\n</package>\n",
    ),
    bump("src/App/Properties/AssemblyInfo.cs", '[assembly: AssemblyVersion("%s.0")]\n'),
    bump("ios/Demo/Info.plist", PLIST),
    bump(
        "CMakeLists.txt",
        "cmake_minimum_required(VERSION 3.20)\nproject(demo VERSION %s)\n",
    ),
    bump("DESCRIPTION", "Package: demo\nVersion: %s\n"),
    bump(".bumpversion.cfg", "[bumpversion]\ncurrent_version = %s\n"),
    bump(".release-please-manifest.json", '{\n  ".": "%s"\n}\n'),
    bump("VERSION.md", "%s\n"),
    bump("build/version.properties", "version=%s\n"),
    bump("package.json", '{"name":"demo-app","version":"%s","private":true}\n'),
    bump("Cargo.toml", '[package]\nname = "demo"\nversion = "%s"\n'),
    (
        "Chart.yaml",
        CHART % ("1.2.3", "1.2.3", "17.0.0"),
        CHART % ("1.2.4", "1.2.3", "17.0.0"),
    ),
    (
        "charts/demo/Chart.yaml",
        CHART % ("1.2.3", "1.2.3", "17.0.0"),
        CHART % ("1.2.3", "1.2.4", "17.0.0"),
    ),
    bump(
        "openapi.yaml",
        "openapi: 3.0.3\ninfo:\n  title: Demo\n  version: %s\npaths: {}\n",
    ),
    bump("demo.cabal", "name: demo\nversion: %s\n"),
    bump("meson.build", "project('demo', 'c', version : '%s')\n"),
    bump("snapcraft.yaml", "name: demo\nversion: '%s'\n"),
    bump("galaxy.yml", "namespace: acme\nname: demo\nversion: %s\n"),
    bump(
        "deno.jsonc",
        '{\n  // the package\n  "name": "@acme/demo",\n  "version": "%s"\n}\n',
    ),
    bump(
        "src-tauri/tauri.conf.json",
        '{\n  "productName": "demo",\n  "version": "%s"\n}\n',
    ),
    bump(
        "setup.py", 'from setuptools import setup\n\nsetup(name="demo", version="%s")\n'
    ),
    bump("include/version.h", '#define DEMO_VERSION "%s"\n'),
    bump(
        "app/build.gradle",
        'android {\n  defaultConfig {\n    versionName "%s"\n  }\n}\n',
    ),
    bump("MODULE.bazel", 'module(name = "app", version = "%s")\n'),
]
ORDINARY_FILES = [
    ("pom.xml", POM % ("3.0.0", "1.2.3", "4.13.1"), POM % ("3.0.1", "1.2.3", "4.13.1")),
    ("pom.xml", POM % ("3.0.0", "1.2.3", "4.13.1"), POM % ("3.0.0", "1.2.3", "4.13.2")),
    ("Cargo.toml", CARGO % ("1.0.0", "4.4"), CARGO % ("1.0.0", "4.5")),
    (
        "Chart.yaml",
        CHART % ("1.2.3", "1.2.3", "17.0.0"),
        CHART % ("1.2.3", "1.2.3", "17.0.1"),
    ),
    ("package.json", ENGINES % "18.0.0", ENGINES % "20.0.0"),
    bump("package-lock.json", '{\n  "name": "demo",\n  "version": "%s"\n}\n'),
    bump("tests/fixtures/package.json", '{"name": "x", "version": "%s"}\n'),
    bump("vendor/lib/VERSION", "%s\n"),
    (".github/workflows/ci.yml", WORKFLOW % ("v5", "3.12"), WORKFLOW % ("v6", "3.13")),
    bump("docker-compose.yml", 'version: "%s"\nservices: {}\n', "3.8", "3.9"),
    bump(".nvmrc", "%s\n", "20.1.0", "22.0.0"),
    bump("README.md", "# Demo\n\nInstall version %s.\n"),
    ("docs/guide.md", "# Guide\n", "# Guide\n\n## 2.0.0\n\nversion = 2.0.0\n"),
    (".readthedocs.yaml", "", "version: 2\nbuild:\n  os: ubuntu-22.04\n"),
    bump("config/app.yaml", "host: %s\nport: 8080\n", "10.0.0.1", "10.0.0.2"),
    bump("config/app.ini", "[server]\nhost = %s\n", "10.0.0.1", "10.0.0.2"),
    bump(
        "packages.config",
        '<packages>\n  <package id="Json" version="%s" targetFramework="net48" />\n'
        "</packages>\n",
    ),
    bump(
        "MODULE.bazel",
        'module(name = "app", version = "1.0.0")\n'
        'bazel_dep(name = "rules_go", version = "%s")\n',
    ),
    bump("deps.edn", '{:deps {org.clojure/clojure {:mvn/version "%s"}}}\n'),
    bump(
        "Package.swift",
        "let package = Package(\n  dependencies: [\n"
        '    .package(url: "https://example.invalid/x.git", from: "%s"),\n  ]\n)\n',
    ),
    bump("paket.dependencies", "source https://example.invalid\nnuget Json %s\n"),
]


@pytest.mark.parametrize(("path", "before", "after"), HELD_FILES)
def test_a_version_of_the_project_is_held_in_any_manifest(path, before, after):
    assert verdict(path, before, after).endswith(": a new version is a release")


@pytest.mark.parametrize(("path", "before", "after"), ORDINARY_FILES)
def test_a_version_of_something_else_is_ordinary(path, before, after):
    assert verdict(path, before, after) == ""


HELD_CODE = [
    bump(
        "app.config.js",
        "module.exports = {\n  expo: {\n    version: '%s',\n  },\n};\n",
    ),
    bump("app.config.ts", 'export default {\n  name: "demo",\n  version: "%s",\n};\n'),
    bump(
        "app.config.js",
        "export default {\n  android: { versionCode: %s },\n};\n",
        "7",
        "8",
    ),
    bump("src/meta.ts", 'export const meta = {\n  version: "%s",\n} as const;\n'),
    bump("meta.js", "module.exports = {\n  'version': '%s',\n};\n"),
    bump("src/AppInfo.cs", '    public static readonly string Version = "%s";\n'),
    bump("src/AppInfo.cs", '    public static string Version { get; } = "%s";\n'),
    bump("src/AppInfo.cs", '    public static string Version => "%s";\n'),
    bump("src/config.h", '#define APP_VERSION "%s"\n'),
    bump("src/app.cpp", 'static const std::string VERSION = "%s";\n'),
    bump("src/app.c", 'static const char *VERSION = "%s";\n'),
    bump("src/app.ts", 'export class App {\n  static readonly version = "%s";\n}\n'),
    bump("cmd/root.go", 'var rootCmd = &cobra.Command{\n\tVersion: "%s",\n}\n'),
    bump("lib/demo.ex", '  @version "%s"\n'),
    bump("lib/Demo.pm", "our $VERSION = '%s';\n"),
    bump("demo.lua", 'local VERSION = "%s"\n'),
    bump("demo.php", "define('APP_VERSION', '%s');\n"),
    bump("config/app.php", "return [\n    'version' => '%s',\n];\n"),
    bump("src/x/__init__.py", '__version__ = "%s"\n'),
]
ORDINARY_CODE = [
    bump("src/client.ts", 'const options = {\n  apiVersion: "%s",\n};\n'),
    bump("src/app.js", 'version === "%s" ? migrate() : start();\n'),
    bump("src/config.h", '#define PYTHON_VERSION "%s"\n'),
    bump("src/app.ts", 'const format = {\n  version: "%s",\n};\n', "1", "2"),
    bump("src/app.py", '    print("version: %s")\n'),
    bump("tests/meta.js", "module.exports = {\n  version: '%s',\n};\n"),
    bump("src/app.js", "  // version: '%s' was the last one with the old login\n"),
]


@pytest.mark.parametrize(("path", "before", "after"), HELD_CODE)
def test_a_version_set_in_source_code_is_held(path, before, after):
    assert verdict(path, before, after) == (
        f"the diff sets a version in {path}: a new version is a release"
    )


@pytest.mark.parametrize(("path", "before", "after"), ORDINARY_CODE)
def test_source_code_that_only_names_a_version_is_ordinary(path, before, after):
    assert verdict(path, before, after) == ""


@pytest.mark.parametrize("parser", ["tomllib", "by line"])
def test_toml_is_read_the_same_without_a_parser(monkeypatch, parser):
    if parser == "by line":
        monkeypatch.setattr(ship, "tomllib", None)
    held_one = bump("Cargo.toml", '[package]\nname = "demo"\nversion = "%s"\n')
    assert verdict(*held_one).startswith("the diff sets a version in Cargo.toml")
    assert (
        verdict("Cargo.toml", CARGO % ("1.0.0", "4.4"), CARGO % ("1.0.0", "4.5")) == ""
    )
    assert (
        verdict(
            "pyproject.toml", PYPROJECT % ("1.0.0", "2.0"), PYPROJECT % ("1.0.0", "2.1")
        )
        == ""
    )


NOTES = "Changelog\n=========\n\n%s1.2.3\n-----\n\n- first\n"
# (file, what the branch adds above the last version)
HELD_NOTES = [
    ("CHANGELOG.md", "1.2.4\n=====\n\n- second\n\n"),
    ("CHANGELOG.md", "1.2.4 (2026-11-10)\n------------------\n\n- second\n\n"),
    ("CHANGELOG.md", "## demo-app 1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "## demo-app@1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "#### [1.2.4]\n\n- second\n\n"),
    ("CHANGELOG.md", "## \U0001f389 1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "**1.2.4**\n\n- second\n\n"),
    ("CHANGELOG.md", "demo-app 1.2.4 - November 10, 2026\n\n- second\n\n"),
    ("CHANGELOG.md", "Version 1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "[1.2.4]: https://example.test/compare/v1.2.3...v1.2.4\n\n"),
    ("RELEASE_NOTES.md", "## 1.2.4\n\n- second\n\n"),
    ("CHANGELOG", "1.2.4\n-----\n\n- second\n\n"),
    ("docs/CHANGELOG.rst", "1.2.4\n-----\n\n- second\n\n"),
    ("HISTORY.rst", "1.2.4 (2026-11-10)\n++++++++++++++++++\n\n- second\n\n"),
    ("NEWS", "demo-app 1.2.4\n\n- second\n\n"),
]
ORDINARY_NOTES = [
    "Unreleased\n----------\n\n- bump lodash to 4.17.21\n\n",
    "Unreleased\n----------\n\n- needs Python 3.12 or newer\n\n",
    "Unreleased\n----------\n\n- fix a crash that 1.2.3 brought in\n\n",
    "Unreleased\n----------\n\n- second\n\n",
]


@pytest.mark.parametrize(("path", "added"), HELD_NOTES)
def test_a_new_version_in_the_release_notes_is_held(path, added):
    own = ship.own_words({"nameWithOwner": "o/demo-app"})
    why = verdict(path, NOTES % "", NOTES % added, own)
    assert (
        why == f"the diff adds a version heading to {path}: a new version is a release"
    )


@pytest.mark.parametrize("added", ORDINARY_NOTES)
def test_a_note_about_another_version_is_ordinary(added):
    own = ship.own_words({"nameWithOwner": "o/demo-app"})
    assert verdict("CHANGELOG.md", NOTES % "", NOTES % added, own) == ""


def test_a_new_file_of_release_notes_for_one_version_is_held():
    why = verdict("docs/releases/1.2.4.md", "", "# What is new\n\n- second\n")
    assert why == "the diff changes docs/releases/1.2.4.md: a new version is a release"


# ---------------------------------------------------------------- promotions


def test_a_branch_that_pull_requests_were_merged_into_is_a_stage():
    assert held({"headRefName": "team-blue"}) == ("pass", False)
    assert held({"headRefName": "team-blue"}, merged='[{"number": 3}]') == (
        "fail",
        True,
    )


def test_a_topic_branch_is_not_asked_about():
    def gh(*args, **more):
        raise AssertionError("asked GitHub about a topic branch")

    assert ship.promoted(SimpleNamespace(gh=gh), BRANCH) == ("", "")


@pytest.mark.parametrize(
    "answer", [(1, "", "HTTP 502"), (0, "<html>", ""), (0, "", ""), (0, "null", "")]
)
def test_no_answer_about_a_branch_is_not_taken_for_no(answer):
    repo = SimpleNamespace(gh=lambda *args, **more: answer)
    why, error = ship.promoted(repo, "team-blue")
    assert not why
    assert error.startswith("cannot ask GitHub what was merged into team-blue: ")


def test_merge_refuses_a_branch_that_pull_requests_were_merged_into(sb):
    sb.passed()
    sb.state(pr=sb.pr(headRefName="team-blue"), merged_into=[{"number": 3}])
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: pull requests were merged into team-blue: merging it on "
        "is a promotion. Ask the user."
    )
    asked = sb.calls("pr list")[0]
    assert asked[asked.index("--base") + 1] == "team-blue"
    assert asked[asked.index("--state") + 1] == "merged"


def test_merge_waits_when_github_does_not_say_what_was_merged(sb):
    sb.passed()
    sb.state(pr=sb.pr(headRefName="team-blue"), list_error="HTTP 502")
    done = refused(sb, "release", 1)
    assert "cannot ask GitHub what was merged into team-blue: " in last_line(done)


# ---------------------------------------------------------------- the recorded answer


def test_a_passed_round_has_to_say_whether_it_is_a_release(sb):
    done = sb.ship("record", "--result", "pass")
    assert done.returncode == 2
    assert "--release yes or no" in done.stderr
    assert not (sb.work / "docs").exists()
    assert sb.ship("record", "--result", "fail", "--open", "F1").returncode == 0


def test_merge_refuses_what_the_record_calls_a_release(sb):
    sb.passed("yes")
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: the test record says this is a release. Ask the user."
    )


def test_a_record_without_the_answer_does_not_pass(sb):
    sb.passed()
    file = sb.work / "docs" / "uat" / "feat-1-thing.json"
    data = json.loads(file.read_text())
    del data["rounds"][-1]["release"]
    file.write_text(json.dumps(data))
    assert "--release yes or no" in last_line(refused(sb, "release", 1))


# ---------------------------------------------------------------- project lines


def test_project_lines_name_release_files_and_branches():
    texts = [
        "# Rules\n\nRelease files: app/build.txt, deploy/\n"
        "- **Release branches:** `team-*`\n",
        "Release file: *.ver\nThe release files: are listed above.\n"
        "Release branch: Shipping\n",
    ]
    files, branches = ship.project_lines(texts)
    assert files == ["app/build.txt", "deploy/", "*.ver"]
    assert branches == ["team-*", "shipping"]


def test_merge_refuses_a_change_to_a_release_file_of_the_project(sb):
    sb.change("CLAUDE.md", "# Rules\n", "# Rules\n\nRelease files: app/build.txt\n")
    sb.change("app/build.txt", "7\n", "8\n")
    sb.passed()
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: the diff changes app/build.txt, a release file of this "
        "project. Ask the user."
    )


def test_a_file_the_project_does_not_name_is_ordinary(sb):
    sb.change("app/build.txt", "7\n", "8\n")
    assert gates(sb.ship("status", "--json"))["release"]["state"] == "pass"


def test_merge_refuses_a_release_branch_of_the_project(sb):
    sb.change("CLAUDE.md", "# Rules\n", "# Rules\n\nRelease branches: feat/1-*\n")
    sb.passed()
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: feat/1-thing is a release branch of this project. Ask the user."
    )


# ---------------------------------------------------------------- answers, limits


def test_a_branch_cannot_drop_the_opt_out_of_its_base(sb):
    sb.git("checkout", "-q", "main")
    (sb.work / "CLAUDE.md").write_text("Merges: ask first\n")
    sb.git("add", "CLAUDE.md")
    sb.git("commit", "-q", "-m", "docs: ask before merging")
    sb.git("push", "-q", "origin", "main")
    sb.git("checkout", "-q", BRANCH)
    sb.git("merge", "-q", "-m", "chore: merge main", "main")
    sb.git("rm", "-q", "CLAUDE.md")
    sb.git("commit", "-q", "-m", "docs: drop the rules file")
    sb.git("push", "-q")
    sb.state()
    sb.passed()
    done = refused(sb, "policy", 3)
    assert "CLAUDE.md on main says `Merges: ask first`" in last_line(done)


@pytest.mark.parametrize(
    ("state", "words"),
    [("BEHIND", "behind main, GitHub says"), ("DIRTY", "conflicts with main")],
)
def test_merge_refuses_what_github_calls_behind_or_in_conflict(sb, state, words):
    sb.passed()
    sb.state(pr=sb.pr(isDraft=False, mergeStateStatus=state))
    assert words in last_line(refused(sb, "up-to-date", 1))


def test_finding_ids_split_on_commas_and_semicolons(sb):
    done = sb.ship("record", "--result", "fail", "--open", "F1,F2", "F3; F4")
    assert done.returncode == 0
    data = json.loads((sb.work / "docs/uat/feat-1-thing.json").read_text())
    assert data["rounds"][0]["open"] == ["F1", "F2", "F3", "F4"]


def test_record_refuses_the_default_branch(sb):
    sb.git("checkout", "-q", "main")
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 2
    assert "main is not the branch of a pull request" in done.stderr
    assert not (sb.work / "docs").exists()


def test_seconds_may_be_decimals(sb):
    assert sb.ship("wait", "--timeout", "0.5", "--grace", "0.25").returncode == 0


@pytest.mark.parametrize("raw", ["<html>502 Bad Gateway</html>", "[]", "null", ""])
def test_an_unreadable_answer_from_gh_is_a_tool_error(sb, raw):
    sb.passed()
    sb.state(pr_raw=raw)
    done = sb.ship("status")
    assert done.returncode == 2
    assert "gh pr view: unreadable answer" in done.stderr
    done = sb.ship("merge")
    assert done.returncode == 2
    assert last_line(done) == "Not merged: gh pr view: unreadable answer."
    assert sb.calls("pr ready") == [] and sb.calls("pr merge") == []


def test_wait_does_not_sleep_past_its_timeout(sb):
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "", "IN_PROGRESS")]))
    start = time.monotonic()
    done = sb.ship("wait", "--timeout", "1", SHIP_POLL_SECONDS="15")
    assert done.returncode == 1 and "still running after 1 s" in done.stdout
    assert time.monotonic() - start < 6
