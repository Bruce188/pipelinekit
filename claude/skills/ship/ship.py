#!/usr/bin/env python3
"""Finish a pull request you opened: test record, CI wait, gated merge.

  ship.py status [--json] [--exit-zero]    every merge gate and why it holds or not
  ship.py record --result pass|fail ...    store one round of the acceptance test
  ship.py wait [--timeout S] [--grace S]   return when CI on the head commit is done
  ship.py merge [--dry-run] [--stay]       check the gates, wait for CI, merge

Exit codes: 0 ok; 1 a gate or a check failed; 2 usage or tool error; 3 stop and
ask the user (a review, a release, someone else's pull request, a project that
asks first, or a test loop that does not converge). A passed round says
whether the pull request is a release: `record --result pass --release no`.

Standard library only. Needs git and a signed-in gh.
"""

# ruff: noqa: E402, F403, F405
from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import sys
import time

# Run from the install: no cache file may appear next to it.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ship_behind import behind_refusal, branch_name, conflict_detail, github_behind
from ship_gates import *
from ship_links import after_merge

# ---------------------------------------------------------------- output


def render(repo, pr, gates):
    if pr:
        state = (pr.get("state") or "OPEN").lower()
        note = f" ({state})" if state != "open" else ""
        if not note and pr.get("isDraft"):
            note = " (draft)"
        title = (
            f"Pull request #{pr.get('number')}: {pr.get('headRefName')} -> "
            f"{pr.get('baseRefName')}{note}"
        )
    else:
        title = f"Branch {repo.branch}: no pull request"
    lines = [title]
    for g in gates:
        lines.append(f"  {WORD[g['state']]:<5} {g['gate']:<11} {g['detail']}")
        lines.extend(f"{'':19}{hint}" for hint in g["hints"])
    bad = [g for g in gates if g["state"] in ("fail", "pending")]
    if verdict(gates) == 0:
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
    gates = evaluate(repo, pr, args.allow_no_checks, args.base or "")
    if args.json:
        print(json.dumps(report(repo, pr, gates), indent=2))
    else:
        print(render(repo, pr, gates))
    return 0 if args.exit_zero else verdict(gates)


# ---------------------------------------------------------------- CI wait


def grace_seconds(args, repo):
    if args.grace is not None:
        return args.grace
    return FIRST_CHECK if repo.has_workflows() else 0


def ran_checks(pr):
    """The checks that ran on the pull request; a skipped one did not."""
    return [
        item
        for item in pr.get("statusCheckRollup") or []
        if (item.get("conclusion") or item.get("state") or "").upper() != "SKIPPED"
    ]


def settle_seconds(args, repo, pr):
    """How long a draft has to stay mergeable after it is marked ready.

    A workflow can skip a draft and start when it is marked ready. Where one
    says so, or where no check has really run on the head yet, the first check
    gets as long to show up as it gets in `wait`.
    """
    if args.settle is not None:
        return args.settle
    expected = repo.expects_checks() and not args.allow_no_checks
    if repo.starts_on_ready() or (expected and not ran_checks(pr)):
        return max(SETTLE, grace_seconds(args, repo))
    return SETTLE


def nap(step, waited, *limits):
    """Sleep `step` seconds, or less when one of the limits comes first."""
    left = [limit - waited for limit in limits if limit > waited]
    time.sleep(max(0.01, min([step, *left])))


def wait_for_ci(repo, timeout, grace, no_checks_ok=False):
    """Poll until every check on the local HEAD has finished.

    Returns (ci gate, pull request). `grace` is how long to wait for the first
    check to show up, and for GitHub to see a push, before judging. No check
    at all is a failure when a workflow here runs on pull requests, unless
    the caller says that none of them runs for this change.
    """
    expected = repo.expects_checks() and not no_checks_ok
    start = time.monotonic()
    shown = ""
    while True:
        pr = repo.pr()
        if pr is None or pr.get("state") != "OPEN":
            return gate("ci", "fail", f"no open pull request for {repo.branch}"), pr
        waited = time.monotonic() - start
        seen = pr.get("headRefOid") == repo.head
        passed, failed, pending = sort_checks(
            pr.get("statusCheckRollup") if seen else []
        )
        if failed or (seen and passed and not pending):
            return ci_gate(pr), pr
        if seen and not pending and waited >= grace:
            if expected:
                detail = (
                    f"no check has shown up after {int(waited)} s, and workflows "
                    "here run on pull requests: look at the Actions tab; when "
                    "none of them runs for this change, add --allow-no-checks"
                )
                return gate("ci", "fail", detail), pr
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
        if pending:
            line = f"waiting for CI: {len(passed)} finished, {len(pending)} running"
        elif seen:
            line = "waiting for the first check to show up"
        else:
            line = "waiting for GitHub to show the pushed commit"
        if line != shown:
            print(line, file=sys.stderr, flush=True)
            shown = line
        nap(poll_seconds(), waited, timeout, *(() if pending else (grace,)))


def cmd_wait(args, repo):
    grace = grace_seconds(args, repo)
    ci, _ = wait_for_ci(repo, args.timeout, grace, args.allow_no_checks)
    print(f"CI {WORD[ci['state']]}: {ci['detail']}")
    for hint in ci["hints"]:
        print(f"  {hint}")
    return 0 if ci["state"] == "pass" else EXIT_FAIL


# ---------------------------------------------------------------- merge


def merge_plan(repo, pr, args):
    """Merge method and commit subject, following what the base branch does.

    Returns (method, subject, problem); `problem` says why there is no plan.
    """
    info = repo.info()
    allowed = [m for m, key in METHODS.items() if info.get(key)] or ["merge"]
    if args.method and args.method not in allowed:
        problem = (
            f"this repository does not allow {args.method} merges "
            f"(allowed: {', '.join(allowed)})"
        )
        return "", "", problem
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
    return method, subject, ""


def watch(repo, number, timeout, settle=0, marked=False, expected=False):
    """Read the pull request again until GitHub's view of it has held still.

    Marking a draft ready can start checks, request a review from the code
    owners and bring branch protection in, and none of that shows at once. So
    after `marked` the pull request has to look mergeable for `settle` seconds
    and on two reads at least. With `expected`, a workflow here runs on pull
    requests, so by then a check must have run: one that was skipped on the
    draft does not count. Returns None when it can be merged, else the gate
    that does not hold.
    """
    looks = 2 if marked else 1
    start = time.monotonic()
    calm_from = None
    calm = unknown = 0
    shown = ""
    while True:
        pr = repo.pr()
        state = (pr or {}).get("state") or "CLOSED"
        if state == "MERGED":
            return gate("pr", "fail", f"#{number} is already merged, not by this run")
        if state != "OPEN":
            return gate("pr", "fail", f"#{number} was closed")
        head, base = pr.get("headRefOid") or "", pr.get("baseRefName")
        if head != repo.head:
            detail = (
                f"the head of #{number} is now {short(head)}, the tested commit "
                f"is {short(repo.head)}: pull and test again"
            )
            return gate("current", "fail", detail)
        review = review_gate(pr)
        if review["state"] != "pass":
            return review
        _, failed, pending = sort_checks(pr.get("statusCheckRollup"))
        if failed:
            detail = f"checks failed: {check_names(failed)}"
            return gate("ci", "fail", detail, hints=log_hints(failed))
        merge_state = pr.get("mergeStateStatus") or "UNKNOWN"
        target = f"{repo.remote}/{base}"
        if merge_state == "DIRTY" or pr.get("mergeable") == "CONFLICTING":
            return gate("up-to-date", "fail", conflict_detail(target))
        if merge_state == "BEHIND":
            return gate("up-to-date", "fail", github_behind(repo, target))
        draft = bool(pr.get("isDraft")) or merge_state == "DRAFT"
        if draft and not marked:
            return gate("draft", "fail", f"#{number} was turned into a draft")
        waited = time.monotonic() - start
        step, limit, line = min(poll_seconds(), 3), timeout, shown
        if pending:
            # A check showed up: from here on the usual time to settle is enough.
            calm, calm_from, settle = 0, None, min(settle, SETTLE)
            if waited >= timeout:
                names = check_names(pending)
                detail = f"checks still running after {int(waited)} s: {names}"
                return gate("ci", "pending", detail)
            step = poll_seconds()
            line = f"waiting for CI: {len(pending)} running"
        elif draft or merge_state == "UNKNOWN":
            calm, calm_from = 0, None
            unknown += 1  # counted over the whole watch, so this always ends
            if unknown >= UNKNOWN_LOOKS and draft:
                detail = (
                    f"GitHub still shows #{number} as a draft after it was "
                    "marked ready: run ship.py merge again"
                )
                return gate("draft", "pending", detail)
            if unknown >= UNKNOWN_LOOKS:
                detail = (
                    f"GitHub has not said whether #{number} can be merged: "
                    "run ship.py merge again"
                )
                return gate("mergeable", "pending", detail)
        else:
            calm += 1
            if calm_from is None:
                calm_from = waited
            limit = calm_from + settle
            if calm >= looks and waited >= limit:
                if marked and expected and not ran_checks(pr):
                    detail = (
                        f"no check ran on #{number} in the {int(waited)} s after "
                        "it was marked ready, and workflows here run on pull "
                        "requests: look at the Actions tab; when none of them "
                        "runs for this change, add --allow-no-checks"
                    )
                    return gate("ci", "fail", detail)
                return None
            if settle >= 1:
                line = f"watching #{number} for {settle:g} s before the merge"
        if line != shown:
            print(line, file=sys.stderr, flush=True)
            shown = line
        nap(step, waited, limit)


def update_base(repo, base):
    """Switch to the merged base; one sentence on where that left the checkout."""
    for step in (
        ("fetch", "-q", repo.remote),
        ("checkout", "-q", base),
        ("merge", "-q", "--ff-only", f"{repo.remote}/{base}"),
    ):
        rc, out, err = repo.try_git(*step)
        if rc:
            why = git_said(err or out, rc).rstrip(".")
            failed = f"git {' '.join(step)} failed: {why}"
            now = repo.try_git("branch", "--show-current")[1] or "no branch"
            if now == base:
                return (
                    f"Now on {base}, which could not be brought up to "
                    f"{repo.remote}/{base}: {failed}."
                )
            return f"Still on {now}: {failed}."
    return f"Now on {base} at {short(repo.try_git('rev-parse', 'HEAD')[1])}."


def refusal(gates):
    """The last line when a gate does not hold and nothing was changed."""
    bad = [g for g in gates if g["state"] in ("fail", "pending")] or gates
    first = next((g for g in bad if g["stop"]), bad[0])
    rest = ", ".join(g["gate"] for g in bad if g is not first)
    also = f" Also not holding: {rest}." if rest else ""
    line = f"{first['gate']}: {first['detail'].rstrip('.')}.{also}"
    return f"STOP: {line} Ask the user." if first["stop"] else f"Not merged: {line}"


def finish(args, repo, pr):
    """Every gate holds: mark ready, watch, merge. The outcome is the last line."""
    number, base = str(pr.get("number")), pr.get("baseRefName")
    draft = bool(pr.get("isDraft"))
    method, subject, problem = merge_plan(repo, pr, args)
    if problem:
        print(f"Not merged: {problem}.")
        return EXIT_TOOL
    cmd = ["pr", "merge", number, f"--{method}", "--match-head-commit", repo.head]
    if subject:
        cmd.append(f"--subject={subject}")
    settle = settle_seconds(args, repo, pr) if draft else args.settle or 0
    if args.dry_run:
        first = ""
        if draft:
            first = f"mark #{number} ready, watch it for {settle:g} s, then "
        print(f"Dry run. Would {first}run: gh {shlex.join(cmd)}")
        return 0
    undrafted = ""
    if draft:
        rc, out, err = repo.gh("pr", "ready", number)
        if rc:
            why = said(err or out, rc).rstrip(".")
            print(f"Not merged: gh pr ready failed: {why}.")
            return EXIT_TOOL
        undrafted = f" #{number} is no longer a draft."
    expected = repo.expects_checks() and not args.allow_no_checks
    problem = watch(repo, number, args.timeout, settle, draft, expected)
    if problem:
        for hint in problem["hints"]:
            print(f"  {hint}")
        if problem["gate"] in ("pr", "draft"):
            undrafted = ""
        if problem["stop"]:
            print(f"STOP: {problem['detail']}.{undrafted} Ask the user.")
            return EXIT_STOP
        print(f"Not merged: {problem['detail']}.{undrafted}")
        return EXIT_FAIL
    rc, out, err = repo.gh(*cmd, timeout=120)
    if rc:
        why = said(err or out, rc).rstrip(".")
        print(f"Not merged: gh pr merge failed: {why}.{undrafted}")
        return EXIT_FAIL
    done = f"Merged #{number} into {base} ({method}) at {short(repo.head)}."
    notes = after_merge(repo, pr)
    if not args.stay:
        done = f"{done} {update_base(repo, base)}"
    for line in notes:
        print(line)
    print(done)
    return 0


def cmd_merge(args, repo):
    pr = repo.pr()
    gates = evaluate(repo, pr, args.allow_no_checks)
    before_ci = gates[:-1]
    if verdict(before_ci) == 0 and not args.dry_run:
        grace = grace_seconds(args, repo)
        ci, seen = wait_for_ci(repo, args.timeout, grace, args.allow_no_checks)
        pr = seen or pr
        gates = [*before_ci, ci]
    print(render(repo, pr, gates))
    code = verdict(gates)
    if code:
        print(refusal(gates))
        return code
    return finish(args, repo, pr)


# ---------------------------------------------------------------- entry


def seconds(text):
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds")
    if value < 0:
        raise argparse.ArgumentTypeError("seconds cannot be negative")
    return value


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
    record.add_argument(
        "--release",
        default="",
        choices=("yes", "no"),
        help="with a pass: does this pull request raise the version, add the "
        "notes of one, publish, deploy or move a release branch on?",
    )
    for cmd in (status, record):
        cmd.add_argument(
            "--base",
            type=branch_name,
            default=None,
            metavar="BRANCH",
            help="the branch to compare with while there is no pull request "
            "(default: branch.<name>.gh-merge-base, else the default branch); "
            "a pull request's own base always wins",
        )
    wait = sub.add_parser("wait", help="return when CI on the head commit is done")
    merge = sub.add_parser("merge", help="check the gates, wait for CI, merge")
    for cmd in (wait, merge):
        cmd.add_argument(
            "--timeout", type=seconds, default=1800, metavar="S", help="default 1800"
        )
        cmd.add_argument(
            "--grace",
            type=seconds,
            default=None,
            metavar="S",
            help="how long to wait for the first check to show up "
            f"(default {FIRST_CHECK} with workflows in the repository, else 0)",
        )
    for cmd in (status, wait, merge):
        cmd.add_argument(
            "--allow-no-checks",
            action="store_true",
            help="accept a pull request on which no check shows up, when no "
            "workflow runs for this change",
        )
    merge.add_argument("--method", choices=tuple(METHODS), help="default: as the base")
    merge.add_argument("--subject", default="", help="commit subject of the merge")
    merge.add_argument("--dry-run", action="store_true", help="gates only, no merge")
    merge.add_argument(
        "--stay", action="store_true", help="do not switch to the base afterwards"
    )
    merge.add_argument(
        "--settle",
        type=seconds,
        default=None,
        metavar="S",
        help="how long a draft has to stay mergeable after it is marked ready "
        f"(default {SETTLE}; as --grace where a check is still to come)",
    )
    return parser


def cmd_record_current(args, repo):
    """Record a round; a pass only while the branch contains its base."""
    return cmd_record(args, repo, behind=lambda: behind_refusal(repo, args.base or ""))


COMMANDS = {
    "status": cmd_status,
    "record": cmd_record_current,
    "wait": cmd_wait,
    "merge": cmd_merge,
}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "record":
        args.open = finding_ids(args.open)
        if args.result == "pass" and args.open:
            parser.error("a passed round has no open findings; record it as fail")
        if args.result == "fail" and not args.open:
            parser.error("name the findings that are still open: --open F1 F2")
        if args.result == "pass" and not args.release:
            parser.error(
                "say whether this pull request is a release: --release yes or no"
            )
    quiet = getattr(args, "exit_zero", False)
    try:
        return COMMANDS[args.cmd](args, Repo())
    except ToolError as exc:
        if args.cmd == "merge":
            print(f"Not merged: {str(exc).rstrip('.')}.")
            return EXIT_TOOL
        print(f"ship: {exc}", file=sys.stdout if quiet else sys.stderr)
        return 0 if quiet else EXIT_TOOL


if __name__ == "__main__":
    sys.exit(main())
