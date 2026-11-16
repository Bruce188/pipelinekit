"""The up-to-date gate: is the branch behind the base its pull request targets?

ship.py never brings a branch up to date itself: no rebase, no merge, no push.
It names the base, how many commits the branch lacks and the next command: a
rebase for a branch that was never pushed, a merge for one that counts as
pushed, and never a force push.
"""

# ruff: noqa: F403, F405

from __future__ import annotations

import argparse
import json
import re

from ship_base import *
from ship_judged import COMMIT, MAX_STATE, linked, read_plain

NAME = "up-to-date"
# What git refuses in a branch name (git check-ref-format), and a leading "-".
BAD_NAME = re.compile(
    r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{|//|^[-/.]|[/.]$|/\.|\.lock$|\.lock/"
)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ANOTHER = "another base: ship.py status --base BRANCH"
PUSHED = "the branch is pushed"
JUDGED = "the branch has a judge record, whose results cite its commits"


def is_branch_name(text):
    return bool(text) and text != "@" and not BAD_NAME.search(text)


def shown(text):
    """A name as it may be printed: control characters replaced, at most 80."""
    return repr(CONTROL.sub("?", text)[:80])


def branch_name(text):
    """The argparse type of --base: a branch name git would accept."""
    if not is_branch_name(text):
        raise argparse.ArgumentTypeError(
            f"{shown(text)} is not a branch name; name the branch the pull request "
            "targets, for example --base main"
        )
    return text


def why(err, rc):
    """A git error on one line, without control characters."""
    return CONTROL.sub("?", git_said(err, rc))


def default_base(repo):
    """(the default branch, why it could not be told)."""
    failed = "gh repo view names no default branch"
    try:
        info = repo.info() or {}
        ref = info.get("defaultBranchRef") if isinstance(info, dict) else None
        base = ref.get("name") if isinstance(ref, dict) else ""
    except ToolError as exc:
        base, failed = "", CONTROL.sub("?", str(exc))
    if not isinstance(base, str) or not is_branch_name(base):
        base = repo.default_branch()
    return base, ("" if base else failed)


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
    hints = []
    if rc == 0 and is_branch_name(out):
        hint = f"no pull request yet: compared with {out}, from {key}; {ANOTHER}"
        return out, [hint], ""
    if rc == 0:
        hints.append(f"{key} holds {shown(out)}, not a branch name: ignored")
    base, failed = default_base(repo)
    if not base:
        return (
            "",
            hints,
            f"could not tell the base branch ({failed}): "
            "name it with ship.py status --base BRANCH",
        )
    hints.append(
        f"no pull request yet: compared with {base}, the default branch; {ANOTHER}"
    )
    return base, hints, ""


def judge_record(repo):
    """True when the branch's build loop record names a commit of the branch.

    The judge results cite that commit, so a rebase would void them."""
    name = slug(repo.branch)
    if linked(repo.root, name):
        return False
    path = repo.root / "docs" / "loops" / name / "build" / "state.json"
    data = read_plain(path, MAX_STATE)
    if not data:
        return False
    try:
        st = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return False
    if not isinstance(st, dict) or st.get("kind") != "build":
        return False
    if st.get("branch") != repo.branch:
        return False
    rounds = st.get("rounds") if isinstance(st.get("rounds"), list) else []
    pending = st.get("pending") if isinstance(st.get("pending"), dict) else {}
    cited = [st.get("commit"), pending.get("commit")]
    cited += [rnd.get("commit") for rnd in rounds if isinstance(rnd, dict)]
    shas = [c for c in cited if isinstance(c, str) and COMMIT.fullmatch(c)]
    return any(
        repo.try_git("merge-base", "--is-ancestor", sha, "HEAD")[0] == 0
        for sha in dict.fromkeys(shas)
    )


def pushed(repo, pr):
    """(why the branch counts as pushed, '' when it was never pushed; error).

    It counts as pushed with a pull request, a remote branch of the same name
    (fetched here or only on the remote), an upstream of the same name, or a
    judge record on the branch. An upstream on another branch is not enough:
    `git switch -c feat origin/main` sets origin/main as the upstream."""
    if pr:
        return PUSHED, ""
    rc, _, err = repo.try_git(
        "rev-parse", "--verify", "-q", f"refs/remotes/{repo.remote}/{repo.branch}"
    )
    if rc == 0:
        return PUSHED, ""
    if rc != 1:
        return "", why(err, rc)
    rc, out, err = repo.try_git("config", "--get", f"branch.{repo.branch}.merge")
    if rc not in (0, 1):
        return "", why(err, rc)
    if rc == 0 and out == f"refs/heads/{repo.branch}":
        return PUSHED, ""
    if judge_record(repo):
        return JUDGED, ""
    ref = f"refs/heads/{repo.branch}"
    rc, out, err = repo.try_git("ls-remote", "--heads", repo.remote, ref)
    if rc:
        return "", f"git ls-remote {repo.remote}: {why(err, rc)}"
    found = any(row.split("\t", 1)[-1] == ref for row in out.splitlines())
    return (PUSHED if found else ""), ""


def next_step(repo, target, was_pushed):
    """The command that brings the branch up to date; never a force push.

    `was_pushed`: why the branch counts as pushed, or '' when it never was."""
    if was_pushed:
        return (
            f"{was_pushed}: git merge {target} (no rebase, no force push), "
            "run the tests again, then push"
        )
    return (
        f"the branch was never pushed: git rebase {target}, run the tests again, "
        f"then git push -u {repo.remote} {repo.branch}"
    )


def conflict_detail(target):
    return (
        f"conflicts with {target}: git merge {target}, resolve the conflicts "
        "and say so in the pull request, run the tests again, then push"
    )


def github_behind(repo, target):
    return f"behind {target}, GitHub says: {next_step(repo, target, PUSHED)}"


def check_base(repo, pr, asked=""):
    """(the up-to-date gate, True when it failed because the branch is behind
    or in conflict; False when it passed or the base could not be checked)."""
    base, hints, error = pick_base(repo, pr, asked)
    if error:
        return gate(NAME, "fail", error, hints=hints), False
    if base == repo.branch:
        return gate(NAME, "skip", f"{base} is the base branch itself"), False
    target = f"{repo.remote}/{base}"
    ref = f"refs/remotes/{target}"

    def failed(detail, behind=False):
        return gate(NAME, "fail", detail, hints=hints), behind

    rc, _, err = repo.try_git("fetch", "-q", repo.remote, f"+refs/heads/{base}:{ref}")
    if rc:
        return failed(
            f"could not fetch {base} from {repo.remote}: {why(err, rc)}; check the "
            "base and the remote, then run ship.py status again"
        )
    was_pushed, error = pushed(repo, pr)
    if error:
        return failed(f"could not tell whether {repo.branch} was pushed: {error}")
    state = (pr or {}).get("mergeStateStatus") or ""
    if pr and (pr.get("mergeable") == "CONFLICTING" or state == "DIRTY"):
        return failed(conflict_detail(target), True)
    rc, _, err = repo.try_git("merge-base", "--is-ancestor", ref, "HEAD")
    if rc == 1:
        rc, n, err = repo.try_git("rev-list", "--count", f"HEAD..{ref}")
        if rc or not n.isdigit():
            detail = f"behind {target}, could not count the commits: {why(err, rc)}"
            return failed(detail, True)
        behind = count(int(n), "commit")
        step = next_step(repo, target, was_pushed)
        return failed(f"{behind} behind {target}: {step}", True)
    if rc:
        return failed(f"could not compare with {target}: {why(err, rc)}")
    if state == "BEHIND":
        return failed(github_behind(repo, target), True)
    return gate(NAME, "pass", f"contains the tip of {target}", hints=hints), False


def base_gate(repo, pr, asked=""):
    return check_base(repo, pr, asked)[0]


def behind_refusal(repo, asked=""):
    """Why a pass cannot be recorded, or ''. Behind or in conflict: the test
    runs again after the update. The base could not be checked: the test still
    counts, and record runs again once the base can be checked."""
    found, behind = check_base(repo, repo.pr(), asked)
    if found["state"] != "fail":
        return ""
    if behind:
        return f"{found['detail']}; after that, run the acceptance test again"
    return (
        f"the base could not be checked: {found['detail']}; once it can, "
        "run record again (the test still counts)"
    )
