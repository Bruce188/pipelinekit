#!/usr/bin/env python3
"""Finish a pull request you opened: test record, CI wait, gated merge.

  ship.py status [--json] [--exit-zero]    every merge gate and why it holds or not
  ship.py record --result pass|fail ...    store one round of the acceptance test
  ship.py wait [--timeout S] [--grace S]   return when CI on the head commit is done
  ship.py merge [--dry-run] [--stay]       check the gates, wait for CI, merge

Exit codes: 0 ok; 1 a gate or a check failed; 2 usage or tool error; 3 stop and
ask the user (a review, a release, someone else's pull request, a project that
asks first, or a test loop that does not converge).

Standard library only. Needs git and a signed-in gh.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
PR_FIELDS = (
    "number,url,title,state,isDraft,isCrossRepository,baseRefName,headRefName,"
    "headRefOid,author,reviewDecision,reviewRequests,mergeable,mergeStateStatus,"
    "statusCheckRollup"
)
REPO_FIELDS = (
    "nameWithOwner,defaultBranchRef,mergeCommitAllowed,squashMergeAllowed,"
    "rebaseMergeAllowed"
)
METHODS = {
    "merge": "mergeCommitAllowed",
    "squash": "squashMergeAllowed",
    "rebase": "rebaseMergeAllowed",
}
PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILING = {"FAILURE", "ERROR"}
OPT_OUT = re.compile(r"^\s*(?:[-*]\s*)?merges?\s*:\s*ask\b", re.I | re.M)
RELEASE_HEAD = re.compile(
    r"^(?:release[/-].*|develop|development|dev|staging|next)$", re.I
)
RELEASE_TITLE = re.compile(
    r"^(?:chore\(release\)\s*:|release\s*[:(]|release\s+v?\d)", re.I
)
CONVENTIONAL = re.compile(r"^[a-z]+(?:\([^)]*\))?!?: ")
MAX_FAILED_ROUNDS = 5
MAX_ROUNDS_OPEN = 3
EXIT_FAIL, EXIT_TOOL, EXIT_STOP = 1, 2, 3
WORD = {"pass": "ok", "fail": "FAIL", "pending": "wait", "skip": "-"}


class ToolError(Exception):
    """git or gh is missing, timed out or answered with an error."""


def run(cmd, cwd=None, timeout=60):
    """Run a command; return (exit code, stdout, stderr) and never raise."""
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} gave no answer within {timeout} s"
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def slug(branch):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "branch"


def short(sha):
    return (sha or "")[:7] or "none"


def count(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def poll_seconds():
    try:
        return max(0.01, float(os.environ.get("SHIP_POLL_SECONDS", "15")))
    except ValueError:
        return 15.0


class Repo:
    """The checkout ship.py runs in, with its git and gh calls."""

    def __init__(self):
        rc, out, _ = run(["git", "rev-parse", "--show-toplevel"])
        if rc:
            raise ToolError("not inside a git repository")
        self.root = Path(out)
        self.branch = self.git("branch", "--show-current")
        if not self.branch:
            raise ToolError("no branch is checked out")
        self.head = self.git("rev-parse", "HEAD")
        remote = self.try_git("config", f"branch.{self.branch}.remote")[1]
        self.remote = remote if remote and remote != "." else "origin"
        self._info = None
        self._user = None

    def try_git(self, *args):
        return run(["git", *args], cwd=self.root)

    def git(self, *args):
        rc, out, err = self.try_git(*args)
        if rc:
            raise ToolError(f"git {' '.join(args)}: {err or out or f'exit {rc}'}")
        return out

    def gh(self, *args, timeout=30):
        return run(["gh", *args], cwd=self.root, timeout=timeout)

    def gh_json(self, *args):
        rc, out, err = self.gh(*args)
        what = "gh " + " ".join(args[:2])
        if rc:
            raise ToolError(f"{what}: {err or out or f'exit {rc}'}")
        try:
            return json.loads(out)
        except ValueError as exc:
            raise ToolError(f"{what}: unreadable answer") from exc

    def pr(self):
        """The pull request of the current branch, or None when there is none."""
        rc, out, err = self.gh("pr", "view", "--json", PR_FIELDS)
        if rc and "no pull requests found" in err.lower():
            return None
        if rc:
            raise ToolError(f"gh pr view: {err or out or f'exit {rc}'}")
        try:
            return json.loads(out)
        except ValueError as exc:
            raise ToolError("gh pr view: unreadable answer") from exc

    def info(self):
        if self._info is None:
            self._info = self.gh_json("repo", "view", "--json", REPO_FIELDS)
        return self._info

    def user(self):
        if self._user is None:
            rc, out, err = self.gh("api", "user", "--jq", ".login")
            if rc or not out:
                raise ToolError(f"gh api user: {err or 'no login'}")
            self._user = out
        return self._user

    def dirty(self):
        return bool(self.git("status", "--porcelain", "--untracked-files=no"))

    @property
    def record_file(self):
        return self.root / "docs" / "uat" / f"{slug(self.branch)}.json"

    def has_workflows(self):
        return any((self.root / ".github" / "workflows").glob("*.y*ml"))


# ---------------------------------------------------------------- test record


def load_record(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    rounds = data.get("rounds") if isinstance(data, dict) else None
    if not isinstance(rounds, list):
        return {"schema": SCHEMA, "rounds": []}
    data["rounds"] = [r for r in rounds if isinstance(r, dict)]
    return data


def ensure_ignored(repo):
    """Test records are local working notes: keep them out of commits."""
    if repo.try_git("check-ignore", "-q", "docs/uat/record.json")[0] == 0:
        return
    rc, out, _ = repo.try_git("rev-parse", "--git-path", "info/exclude")
    if rc:
        return
    exclude = repo.root / out
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        old = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        gap = "" if not old or old.endswith("\n") else "\n"
        exclude.write_text(f"{old}{gap}docs/uat/\n", encoding="utf-8")
    except OSError:
        return


def stop_reason(rounds):
    """Why the test loop should go back to the user, or an empty string."""
    tail = []
    for entry in reversed(rounds):
        if entry.get("result") != "fail":
            break
        tail.append(entry)
    if len(tail) >= MAX_FAILED_ROUNDS:
        return f"{len(tail)} failed rounds in a row"
    if len(tail) >= MAX_ROUNDS_OPEN:
        stuck = set(tail[0].get("open") or [])
        for entry in tail[1:MAX_ROUNDS_OPEN]:
            stuck &= set(entry.get("open") or [])
        if stuck:
            return f"{', '.join(sorted(stuck))} still open after two fix attempts"
    return ""


def cmd_record(args, repo):
    if args.result == "pass" and repo.dirty():
        print(
            "ship: tracked files have uncommitted changes; commit first, "
            "a passed round is tied to a commit",
            file=sys.stderr,
        )
        return EXIT_FAIL
    path = repo.record_file
    data = load_record(path)
    rounds = data["rounds"]
    rounds.append(
        {
            "round": len(rounds) + 1,
            "commit": repo.head,
            "result": args.result,
            "tester": args.tester,
            "open": sorted(set(args.open)),
            "notes": args.notes,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    data.update(schema=SCHEMA, branch=repo.branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    ensure_ignored(repo)
    left = f", open: {', '.join(sorted(set(args.open)))}" if args.open else ""
    print(
        f"Round {len(rounds)}: {args.result} on {short(repo.head)} "
        f"({args.tester}){left}"
    )
    print(f"Record: {path.relative_to(repo.root).as_posix()}")
    reason = stop_reason(rounds)
    if reason:
        print(f"STOP: {reason}. Tell the user what is stuck instead of trying again.")
        return EXIT_STOP
    return 0


# ---------------------------------------------------------------- gates


def gate(name, state, detail, stop=False, hints=()):
    return {
        "gate": name,
        "state": state,
        "detail": detail,
        "stop": bool(stop and state == "fail"),
        "hints": list(hints),
    }


def skipped(name):
    return gate(name, "skip", "needs an open pull request")


def sort_checks(rollup):
    """Split checks into passed, failed and still running.

    A check run counts as finished as soon as it has a conclusion: GitHub can
    leave `status` on IN_PROGRESS after the job is done.
    """
    passed, failed, pending = [], [], []
    for item in rollup or []:
        if item.get("__typename") == "StatusContext":
            word = (item.get("state") or "").upper()
            done = word in PASSING | FAILING
        else:
            word = (item.get("conclusion") or "").upper()
            done = bool(word)
        if not done:
            pending.append(item)
        elif word in PASSING:
            passed.append(item)
        else:
            failed.append(item)
    return passed, failed, pending


def check_names(items):
    return ", ".join(
        sorted({i.get("name") or i.get("context") or "check" for i in items})
    )


def log_hints(failed):
    ids = []
    for item in failed:
        m = re.search(r"/actions/runs/(\d+)", item.get("detailsUrl") or "")
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return [f"read the log: gh run view {i} --log-failed" for i in ids]


def pr_gate(repo, pr):
    if pr is None:
        return gate(
            "pr",
            "fail",
            f"no pull request for {repo.branch}: push, then gh pr create --draft",
        )
    state = pr.get("state") or "UNKNOWN"
    if state != "OPEN":
        return gate("pr", "fail", f"#{pr.get('number')} is {state.lower()}")
    draft = ", draft" if pr.get("isDraft") else ""
    return gate(
        "pr", "pass", f"#{pr.get('number')} into {pr.get('baseRefName')}{draft}"
    )


def own_gate(repo, pr):
    user = repo.user()
    author = (pr.get("author") or {}).get("login") or ""
    if author.lower() != user.lower():
        who = author or "someone else"
        return gate("own", "fail", f"opened by {who}, not by {user}", stop=True)
    if pr.get("isCrossRepository"):
        return gate(
            "own", "fail", "comes from a fork: the maintainers merge it", stop=True
        )
    return gate("own", "pass", f"opened by {user}")


def policy_gate(repo):
    if os.environ.get("PIPELINEKIT_MERGE", "").strip().lower() == "ask":
        return gate("policy", "fail", "PIPELINEKIT_MERGE=ask", stop=True)
    home = Path(os.environ.get("CLAUDE_HOME") or Path.home() / ".claude")
    places = (
        ("CLAUDE.md", repo.root / "CLAUDE.md"),
        (".claude/CLAUDE.md", repo.root / ".claude" / "CLAUDE.md"),
        ("CLAUDE.local.md", repo.root / "CLAUDE.local.md"),
        ("your user-level CLAUDE.md", home / "CLAUDE.md"),
    )
    for label, path in places:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if OPT_OUT.search(text):
            return gate(
                "policy", "fail", f"{label} says `Merges: ask first`", stop=True
            )
    return gate("policy", "pass", "no `Merges: ask first` line")


def release_gate(repo, pr):
    head, base = pr.get("headRefName") or "", pr.get("baseRefName") or ""
    default = (repo.info().get("defaultBranchRef") or {}).get("name") or ""
    if RELEASE_TITLE.match(pr.get("title") or ""):
        return gate("release", "fail", "the title reads like a release", stop=True)
    if base == default and RELEASE_HEAD.match(head):
        return gate("release", "fail", f"{head} into {base} is a release", stop=True)
    return gate("release", "pass", "not a release")


def review_gate(pr):
    decision = pr.get("reviewDecision") or ""
    if decision == "CHANGES_REQUESTED":
        return gate("review", "fail", "a reviewer requested changes", stop=True)
    if decision == "REVIEW_REQUIRED":
        return gate("review", "fail", "the base branch requires a review", stop=True)
    asked = [
        r.get("login") or r.get("name") or r.get("slug") or "a reviewer"
        for r in pr.get("reviewRequests") or []
    ]
    if asked:
        return gate(
            "review", "fail", f"review requested from {', '.join(asked)}", stop=True
        )
    _, failed, pending = sort_checks(pr.get("statusCheckRollup"))
    if pr.get("mergeStateStatus") == "BLOCKED" and not failed and not pending:
        return gate("review", "fail", "branch protection blocks the merge", stop=True)
    return gate("review", "pass", "approved" if decision else "no review required")


def current_gate(repo, pr):
    head = pr.get("headRefOid") or ""
    if head != repo.head:
        return gate(
            "current",
            "fail",
            f"local HEAD {short(repo.head)} is not the pull request's head "
            f"{short(head)}: push or pull first",
        )
    if repo.dirty():
        return gate("current", "fail", "tracked files have uncommitted changes")
    return gate("current", "pass", f"head {short(head)}, tracked files clean")


def base_gate(repo, pr):
    base = pr.get("baseRefName") or ""
    ref = f"refs/remotes/{repo.remote}/{base}"
    rc, _, err = repo.try_git("fetch", "-q", repo.remote, f"+refs/heads/{base}:{ref}")
    if rc:
        why = (err.splitlines() or [f"exit {rc}"])[-1]
        return gate("up-to-date", "fail", f"could not fetch {base}: {why}")
    again = f"merge {repo.remote}/{base} into the branch, then test again"
    if pr.get("mergeable") == "CONFLICTING":
        return gate("up-to-date", "fail", f"conflicts with {base}: {again}")
    if repo.try_git("merge-base", "--is-ancestor", ref, "HEAD")[0]:
        n = repo.try_git("rev-list", "--count", f"HEAD..{ref}")[1]
        behind = count(int(n), "commit") if n.isdigit() else "some commits"
        return gate("up-to-date", "fail", f"{behind} behind {base}: {again}")
    return gate("up-to-date", "pass", f"contains the tip of {base}")


def tested_gate(repo, head):
    rounds = load_record(repo.record_file)["rounds"]
    where = repo.record_file.relative_to(repo.root).as_posix()
    if not rounds:
        return gate(
            "tested",
            "fail",
            f"no test record ({where}): run the acceptance test, then ship.py record",
        )
    last, n = rounds[-1], len(rounds)
    if last.get("result") != "pass":
        left = ", ".join(last.get("open") or []) or "not named"
        return gate("tested", "fail", f"round {n} failed, still open: {left}")
    if last.get("commit") != head:
        return gate(
            "tested",
            "fail",
            f"round {n} passed on {short(last.get('commit'))}, the head is now "
            f"{short(head)}: test again",
        )
    tester = last.get("tester") or "agent"
    return gate("tested", "pass", f"round {n} passed on {short(head)} ({tester})")


def ci_gate(pr):
    passed, failed, pending = sort_checks(pr.get("statusCheckRollup"))
    if failed:
        return gate(
            "ci", "fail", f"failed: {check_names(failed)}", hints=log_hints(failed)
        )
    if pending:
        total = len(passed) + len(pending)
        return gate(
            "ci",
            "pending",
            f"{len(pending)} of {total} still running: {check_names(pending)}",
        )
    if not passed:
        return gate("ci", "pass", "no CI checks on this pull request")
    return gate("ci", "pass", f"{count(len(passed), 'check')} finished, none failed")


def evaluate(repo, pr):
    """Every gate for the current branch's pull request; CI as it stands now."""
    first = pr_gate(repo, pr)
    if first["state"] != "pass":
        return [
            first,
            skipped("own"),
            policy_gate(repo),
            skipped("release"),
            skipped("review"),
            skipped("current"),
            skipped("up-to-date"),
            tested_gate(repo, repo.head),
            skipped("ci"),
        ]
    return [
        first,
        own_gate(repo, pr),
        policy_gate(repo),
        release_gate(repo, pr),
        review_gate(pr),
        current_gate(repo, pr),
        base_gate(repo, pr),
        tested_gate(repo, pr.get("headRefOid") or ""),
        ci_gate(pr),
    ]


def verdict(gates):
    """Exit code for a list of gates: 0 all hold, 3 the user's call, 1 otherwise."""
    bad = [g for g in gates if g["state"] != "pass"]
    if not bad:
        return 0
    return EXIT_STOP if any(g["stop"] for g in bad) else EXIT_FAIL


# ---------------------------------------------------------------- output


def render(repo, pr, gates):
    if pr:
        draft = " (draft)" if pr.get("isDraft") else ""
        title = (
            f"Pull request #{pr.get('number')}: {pr.get('headRefName')} -> "
            f"{pr.get('baseRefName')}{draft}"
        )
    else:
        title = f"Branch {repo.branch}: no pull request"
    lines = [title]
    for g in gates:
        lines.append(f"  {WORD[g['state']]:<5} {g['gate']:<11} {g['detail']}")
        lines.extend(f"{'':19}{hint}" for hint in g["hints"])
    bad = [g for g in gates if g["state"] != "pass"]
    if not bad:
        lines.append("Result: ready to merge")
    elif any(g["stop"] for g in bad):
        mine = ", ".join(g["gate"] for g in bad if g["stop"])
        lines.append(f"Result: stop and ask the user ({mine})")
    else:
        lines.append(f"Result: not ready ({', '.join(g['gate'] for g in bad)})")
    return "\n".join(lines)


def report(repo, pr, gates):
    return {
        "schema": SCHEMA,
        "branch": repo.branch,
        "head": repo.head,
        "pr": pr
        and {
            "number": pr.get("number"),
            "url": pr.get("url"),
            "base": pr.get("baseRefName"),
            "draft": bool(pr.get("isDraft")),
        },
        "ready": verdict(gates) == 0,
        "stop": verdict(gates) == EXIT_STOP,
        "gates": [
            {k: g[k] for k in ("gate", "state", "detail", "hints")} for g in gates
        ],
    }


def cmd_status(args, repo):
    pr = repo.pr()
    gates = evaluate(repo, pr)
    if args.json:
        print(json.dumps(report(repo, pr, gates), indent=2))
    else:
        print(render(repo, pr, gates))
    return 0 if args.exit_zero else verdict(gates)


# ---------------------------------------------------------------- CI wait


def grace_seconds(args, repo):
    if args.grace is not None:
        return max(0, args.grace)
    return 90 if repo.has_workflows() else 0


def wait_for_ci(repo, timeout, grace):
    """Poll until every check on the local HEAD has finished.

    Returns (ci gate, pull request). `grace` is how long to wait for the first
    check to show up, and for GitHub to see a push, before judging.
    """
    start = time.monotonic()
    shown = ""
    while True:
        pr = repo.pr()
        if pr is None or pr.get("state") != "OPEN":
            raise ToolError(f"no open pull request for {repo.branch}")
        waited = time.monotonic() - start
        seen = pr.get("headRefOid") == repo.head
        passed, failed, pending = sort_checks(
            pr.get("statusCheckRollup") if seen else []
        )
        if failed:
            return ci_gate(pr), pr
        if seen and not pending and (passed or waited >= grace):
            return ci_gate(pr), pr
        if not seen and waited >= grace:
            detail = (
                f"the pull request's head is {short(pr.get('headRefOid'))}, "
                f"local HEAD is {short(repo.head)}: push first"
            )
            return gate("ci", "fail", detail), pr
        if waited >= timeout:
            names = check_names(pending) or "no check has shown up"
            detail = f"still running after {int(waited)} s: {names}"
            return gate("ci", "pending", detail), pr
        line = f"waiting for CI: {len(passed)} finished, {len(pending)} running"
        if line != shown:
            print(line, file=sys.stderr, flush=True)
            shown = line
        time.sleep(poll_seconds())


def cmd_wait(args, repo):
    ci, _ = wait_for_ci(repo, args.timeout, grace_seconds(args, repo))
    print(f"CI {WORD[ci['state']]}: {ci['detail']}")
    for hint in ci["hints"]:
        print(f"  {hint}")
    return 0 if ci["state"] == "pass" else EXIT_FAIL


# ---------------------------------------------------------------- merge


def merge_plan(repo, pr, args):
    """Merge method and commit subject, following what the base branch does."""
    info = repo.info()
    allowed = [m for m, key in METHODS.items() if info.get(key)] or ["merge"]
    ref = f"refs/remotes/{repo.remote}/{pr.get('baseRefName')}"
    fmt = "--format=%h%x09%P%x09%s"  # the hash keeps the line from starting with a tab
    out = repo.try_git("log", "--first-parent", "-n", "30", fmt, ref)[1]
    rows = [line.split("\t", 2) for line in out.splitlines() if line.count("\t") >= 2]
    subjects = [subject for _, _, subject in rows]
    merges = [subject for _, parents, subject in rows if len(parents.split()) > 1]
    method = args.method
    if not method and "merge" in allowed and (merges or "squash" not in allowed):
        method = "merge"
    if not method:
        method = "squash" if "squash" in allowed else allowed[0]
    subject = args.subject
    sample = merges or subjects
    if not subject and method == "merge" and sample:
        conventional = sum(bool(CONVENTIONAL.match(s)) for s in sample)
        if conventional * 2 > len(sample):
            subject = f"chore: merge {pr.get('headRefName')}"
    return method, subject


def merge_state(repo):
    """mergeStateStatus once GitHub has worked it out (it lags after `ready`)."""
    state = "UNKNOWN"
    for _ in range(8):
        state = (repo.pr() or {}).get("mergeStateStatus") or "UNKNOWN"
        if state not in ("UNKNOWN", "DRAFT"):
            break
        time.sleep(min(poll_seconds(), 3))
    return state


def update_base(repo, base):
    for step in (
        ("fetch", "-q", repo.remote),
        ("checkout", "-q", base),
        ("merge", "-q", "--ff-only", f"{repo.remote}/{base}"),
    ):
        rc, out, err = repo.try_git(*step)
        if rc:
            why = (err or out).splitlines()[-1:] or [f"exit {rc}"]
            print(f"note: git {' '.join(step)} failed: {why[0]}", file=sys.stderr)
            return
    print(f"Now on {base} at {short(repo.git('rev-parse', 'HEAD'))}.")


def cmd_merge(args, repo):
    pr = repo.pr()
    gates = evaluate(repo, pr)
    before_ci = gates[:-1]
    if verdict(before_ci) == 0 and not args.dry_run:
        ci, pr = wait_for_ci(repo, args.timeout, grace_seconds(args, repo))
        gates = [*before_ci, ci]
    print(render(repo, pr, gates))
    code = verdict(gates)
    if code:
        return code
    number, base = str(pr.get("number")), pr.get("baseRefName")
    method, subject = merge_plan(repo, pr, args)
    cmd = ["pr", "merge", number, f"--{method}", "--match-head-commit", repo.head]
    if subject:
        cmd += ["--subject", subject]
    if args.dry_run:
        print("Dry run. Would run: gh " + shlex.join(cmd))
        return 0
    if pr.get("isDraft"):
        rc, out, err = repo.gh("pr", "ready", number)
        if rc:
            raise ToolError(f"gh pr ready: {err or out or f'exit {rc}'}")
    state = merge_state(repo)
    if state == "BLOCKED":
        print(f"STOP: branch protection blocks the merge of #{number}. Ask the user.")
        return EXIT_STOP
    if state in ("BEHIND", "DIRTY"):
        print(
            f"Not merged: #{number} is {state.lower()} against {base}. "
            f"Merge {repo.remote}/{base} into the branch and test again."
        )
        return EXIT_FAIL
    rc, out, err = repo.gh(*cmd, timeout=120)
    if rc:
        print(
            f"ship: gh pr merge failed: {err or out or f'exit {rc}'}", file=sys.stderr
        )
        return EXIT_FAIL
    print(f"Merged #{number} into {base} ({method}) at {short(repo.head)}.")
    if not args.stay:
        update_base(repo, base)
    return 0


# ---------------------------------------------------------------- entry


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ship.py",
        description="Test record, CI wait and gated merge for a pull request "
        "you opened.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    status = sub.add_parser("status", help="show every merge gate")
    status.add_argument("--json", action="store_true", help="machine-readable")
    status.add_argument("--exit-zero", action="store_true", help="always exit 0")
    record = sub.add_parser("record", help="store one round of the acceptance test")
    record.add_argument("--result", required=True, choices=("pass", "fail"))
    record.add_argument(
        "--tester",
        default="agent",
        choices=("agent", "session"),
        help="who tested: a separate agent, or the building session",
    )
    record.add_argument(
        "--open",
        nargs="*",
        default=[],
        metavar="ID",
        help="ids of the blocker and should-fix findings still open",
    )
    record.add_argument("--notes", default="", help="one line about the round")
    wait = sub.add_parser("wait", help="return when CI on the head commit is done")
    merge = sub.add_parser("merge", help="check the gates, wait for CI, merge")
    for cmd in (wait, merge):
        cmd.add_argument(
            "--timeout", type=int, default=1800, metavar="S", help="default 1800"
        )
        cmd.add_argument(
            "--grace",
            type=int,
            default=None,
            metavar="S",
            help="how long to wait for the first check to show up "
            "(default 90 with GitHub workflows in the repository, else 0)",
        )
    merge.add_argument("--method", choices=tuple(METHODS), help="default: as the base")
    merge.add_argument("--subject", default="", help="commit subject of the merge")
    merge.add_argument("--dry-run", action="store_true", help="gates only, no merge")
    merge.add_argument(
        "--stay", action="store_true", help="do not switch to the base afterwards"
    )
    return parser


COMMANDS = {
    "status": cmd_status,
    "record": cmd_record,
    "wait": cmd_wait,
    "merge": cmd_merge,
}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "record" and args.result == "pass" and args.open:
        parser.error("a passed round has no open findings; record it as fail")
    if args.cmd == "record" and args.result == "fail" and not args.open:
        parser.error("name the findings that are still open: --open F1 F2")
    quiet = getattr(args, "exit_zero", False)
    try:
        return COMMANDS[args.cmd](args, Repo())
    except ToolError as exc:
        print(f"ship: {exc}", file=sys.stdout if quiet else sys.stderr)
        return 0 if quiet else EXIT_TOOL


if __name__ == "__main__":
    sys.exit(main())
