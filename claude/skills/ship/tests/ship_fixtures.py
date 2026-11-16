"""The shared helpers of the ship.py tests: the loaded module, a sandbox with a fake gh,
and the merge refusal and release gate checks both test files use."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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
if kind == ["pr", "view"] and "body,closingIssuesReferences" in args:
    if state.get("links_error"):
        sys.exit(state["links_error"])
    seq = state.get("pr_sequence")
    pr = state.get("links") or (seq[-1] if seq else state.get("pr")) or {}
    keys = ("body", "closingIssuesReferences")
    print(json.dumps({k: pr.get(k) for k in keys if k in pr}))
elif kind == ["pr", "view"] and "pr_raw" in state:
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
elif kind == ["pr", "list"] and "--head" in args:
    if state.get("release_error"):
        sys.exit(state["release_error"])
    print(json.dumps(state.get("release_prs", [])))
elif kind == ["pr", "edit"]:
    if state.get("edit_error"):
        sys.exit(state["edit_error"])
    with open(args[args.index("--body-file") + 1], encoding="utf-8") as f:
        body = f.read()
    with open(os.path.join(d, "edits.jsonl"), "a") as f:
        f.write(json.dumps({"number": args[2], "body": body}) + "\n")
elif kind == ["issue", "view"]:
    if state.get("issue_error"):
        sys.exit(state["issue_error"])
    n = args[2]
    value = state.get("issues", {}).get(n)
    if value is None:
        sys.exit("GraphQL: Could not resolve to an issue or pull request with "
                 "the number of " + n + ".")
    if isinstance(value, list):
        counter = os.path.join(d, "issue_" + n)
        k = int(open(counter).read()) if os.path.exists(counter) else 0
        with open(counter, "w") as f:
            f.write(str(k + 1))
        value = value[min(k, len(value) - 1)]
    print(json.dumps({"state": value}))
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


def ref(number, repo="o/r"):
    """An issue in closingIssuesReferences."""
    owner, name = repo.split("/")
    return {"number": number, "repository": {"name": name, "owner": {"login": owner}}}


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
            "body": "Closes #1",
            "closingIssuesReferences": [ref(1)],
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
        state = {
            "user": "me",
            "repo": self.repo(),
            "pr": self.pr(),
            "issues": {"1": "CLOSED"},
        }
        state.update(over)
        (self.fake / "state.json").write_text(json.dumps(state))
        # A new state starts its sequence of pull request views again.
        (self.fake / "views").unlink(missing_ok=True)

    def ship(self, *args, timeout=300, **env):
        """Run ship.py; a merge settles in 0.2 s here unless the test says more."""
        if args[:1] == ("merge",) and not {"--dry-run", "--settle"} & set(args):
            args = (*args, "--settle", "0.2")
        return subprocess.run(
            [sys.executable, str(SHIP), *args],
            cwd=self.work,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def all_calls(self):
        log = self.fake / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def edits(self):
        """The bodies `gh pr edit` was given: [{"number", "body"}]."""
        log = self.fake / "edits.jsonl"
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
        return sum(
            row[:2] == ["pr", "view"] and "body,closingIssuesReferences" not in row
            for row in rows[start:stop]
        )

    def workflow(self, text="on: [push, pull_request]\n"):
        path = self.work / ".github" / "workflows" / "ci.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def passed(self, release="no"):
        """A judge record and a passed test record for the head."""
        self.judged()
        done = self.ship("record", "--result", "pass", "--release", release)
        assert done.returncode == 0, done.stderr

    def judged(self, outcome="done", commit=None, **fields):
        """Write the judge loop's record of the current branch; return its path."""
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        name = ship.slug(branch)
        commit = commit or self.head()
        state = {
            "schema": 1,
            "kind": "build",
            "name": name,
            "branch": branch,
            "base": "main",
            "base_ref": "refs/remotes/origin/main",
            "base_sha": "",
            "base_source": "",
            "panel": ["general"],
            "panel_reason": "",
            "panel_forced": "",
            "budget": 5,
            "switches": [],
            "agents": "kit",
            "plan_loop": {},
            "pending": {},
            "rounds": [{"n": 1, "commit": commit, "scores": {"general": 10}}],
            "items": {},
            "streak": 0,
            "final": False,
            "notes": [],
            "outcome": outcome,
            "commit": commit,
            "skip": {},
        }
        if outcome == "skip":
            state["rounds"] = []
            state["skip"] = {
                "reason": "docs only",
                "files": 1,
                "lines": 2,
                "user_ok": False,
            }
        state.update(fields)
        path = self.work / "docs" / "loops" / name / "build" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
        return path

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


def gates(done):
    return {g["gate"]: g for g in json.loads(done.stdout)["gates"]}


def last_line(done):
    return done.stdout.strip().splitlines()[-1]


def refused(sb, gate_name, code):
    done = sb.ship("merge", "--grace", "0", "--timeout", "1")
    assert done.returncode == code, done.stdout + done.stderr
    assert f"FAIL  {gate_name} " in done.stdout or f"wait  {gate_name} " in done.stdout
    assert sb.calls("pr merge") == [] and sb.calls("pr ready") == []
    start = "STOP: " if code == 3 else "Not merged: "
    assert last_line(done).startswith(f"{start}{gate_name}: "), last_line(done)
    assert last_line(done).endswith("Ask the user.") == (code == 3)
    return done


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
