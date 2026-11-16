"""The up-to-date gate: is the branch behind the base its pull request targets?

ship.py never brings a branch up to date itself: no rebase, no merge, no push.
It names the base, how many commits the branch lacks and the next command: a
rebase for a branch that was never pushed, a merge for one that was, and never
a force push.
"""

# ruff: noqa: F403, F405

from __future__ import annotations

import argparse
import re

from ship_base import *

NAME = "up-to-date"
# What git refuses in a branch name (git check-ref-format), and a leading "-".
BAD_NAME = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{|//|^[-/.]|[/.]$|\.lock$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ANOTHER = "another base: ship.py status --base BRANCH"


def branch_name(text):
    """The argparse type of --base: a branch name git would accept."""
    if not text or text == "@" or BAD_NAME.search(text):
        shown = CONTROL.sub("?", text)[:80]
        raise argparse.ArgumentTypeError(
            f"{shown!r} is not a branch name; name the branch the pull request "
            "targets, for example --base main"
        )
    return text


def why(err, rc):
    """A git error on one line, without control characters."""
    return CONTROL.sub("?", git_said(err, rc))


def pick_base(repo, pr, asked):
    """(base, hints, error): the pull request's base first, then --base, then
    the base `gh pr create` would take, then the default branch."""
    if pr:
        base = pr.get("baseRefName") or ""
        if asked and asked != base:
            return (
                base,
                [f"the pull request targets {base}; --base {asked} is not used"],
                "",
            )
        return base, [], ""
    if asked:
        return asked, [f"no pull request yet: compared with {asked}, from --base"], ""
    key = f"branch.{repo.branch}.gh-merge-base"
    rc, out, err = repo.try_git("config", "--get", key)
    if rc not in (0, 1):
        return "", [], f"could not read {key}: {why(err, rc)}"
    if rc == 0 and out and not BAD_NAME.search(out):
        hint = f"no pull request yet: compared with {out}, from {key}; {ANOTHER}"
        return out, [hint], ""
    try:
        base = ((repo.info() or {}).get("defaultBranchRef") or {}).get("name") or ""
    except ToolError as exc:
        base, failed = repo.default_branch(), str(exc)
        if not base:
            return (
                "",
                [],
                (
                    f"could not tell the base branch ({CONTROL.sub('?', failed)}): "
                    "name it with ship.py status --base BRANCH"
                ),
            )
    hint = f"no pull request yet: compared with {base}, the default branch; {ANOTHER}"
    return base, [hint], ""


def pushed(repo, pr):
    """(was the branch pushed, error): a pull request, a remote branch of the
    same name, or an upstream of the same name. An upstream alone is not
    enough: `git switch -c feat origin/main` sets origin/main as the upstream."""
    if pr:
        return True, ""
    rc, _, err = repo.try_git(
        "rev-parse", "--verify", "-q", f"refs/remotes/{repo.remote}/{repo.branch}"
    )
    if rc == 0:
        return True, ""
    if rc != 1:
        return False, why(err, rc)
    rc, out, err = repo.try_git("config", "--get", f"branch.{repo.branch}.merge")
    if rc not in (0, 1):
        return False, why(err, rc)
    return out == f"refs/heads/{repo.branch}", ""


def next_step(target, was_pushed):
    """The command that brings the branch up to date; never a force push."""
    if was_pushed:
        return (
            f"the branch is pushed: git merge {target} (no rebase, no force push), "
            "run the tests again, then push"
        )
    return (
        f"the branch was never pushed: git rebase {target}, "
        "run the tests again, then push"
    )


def base_gate(repo, pr, asked=""):
    base, hints, error = pick_base(repo, pr, asked)
    if error:
        return gate(NAME, "fail", error)
    if base == repo.branch:
        return gate(NAME, "skip", f"{base} is the base branch itself")
    target = f"{repo.remote}/{base}"
    ref = f"refs/remotes/{target}"
    rc, _, err = repo.try_git("fetch", "-q", repo.remote, f"+refs/heads/{base}:{ref}")
    if rc:
        return gate(
            NAME,
            "fail",
            f"could not fetch {base} from {repo.remote}: {why(err, rc)}; check the "
            "base and the remote, then run ship.py status again",
            hints=hints,
        )
    was_pushed, error = pushed(repo, pr)
    if error:
        return gate(
            NAME,
            "fail",
            f"could not tell whether {repo.branch} was pushed: {error}",
            hints=hints,
        )
    state = (pr or {}).get("mergeStateStatus") or ""
    if pr and (pr.get("mergeable") == "CONFLICTING" or state == "DIRTY"):
        return gate(
            NAME,
            "fail",
            f"conflicts with {target}: git merge {target}, resolve the conflicts "
            "and say so in the pull request, run the tests again, then push",
            hints=hints,
        )
    rc, _, err = repo.try_git("merge-base", "--is-ancestor", ref, "HEAD")
    if rc == 1:
        rc, n, err = repo.try_git("rev-list", "--count", f"HEAD..{ref}")
        if rc or not n.isdigit():
            return gate(
                NAME,
                "fail",
                f"behind {target}, could not count the commits: {why(err, rc)}",
                hints=hints,
            )
        behind = count(int(n), "commit")
        detail = f"{behind} behind {target}: {next_step(target, was_pushed)}"
        return gate(NAME, "fail", detail, hints=hints)
    if rc:
        return gate(
            NAME,
            "fail",
            f"could not compare with {target}: {why(err, rc)}",
            hints=hints,
        )
    if state == "BEHIND":
        detail = f"behind {target}, GitHub says: {next_step(target, True)}"
        return gate(NAME, "fail", detail, hints=hints)
    return gate(NAME, "pass", f"contains the tip of {target}", hints=hints)


def behind_refusal(repo, asked=""):
    """Why a pass cannot be recorded: the failed up-to-date gate, or ''."""
    found = base_gate(repo, repo.pr(), asked)
    return found["detail"] if found["state"] == "fail" else ""
