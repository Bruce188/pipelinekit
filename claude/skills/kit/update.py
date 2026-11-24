#!/usr/bin/env python3
"""pipelinekit update: bring the checkout and the install to what origin has.

Usage:
  update.py plan             list what origin has that this install lacks
  update.py apply --to SHA   fast-forward the checkout to SHA, run the
                             installer, run the self-check

`plan` fetches and changes nothing else. Its last line is one of
  Up to date: ...
  Update available: N commits. Apply with: python3 .../update.py apply --to SHA
  Cannot update: <reason>.
`apply` takes the commit that `plan` printed and refuses when origin has moved
on since. Its last line is one of
  Updated <old> -> <new>. Self-check: healthy.
  Partly updated <old> -> <new>: ...   the checkout moved, but the installer
                                       failed or the self-check did not run
  Up to date: ...
  Not updated: <reason>.
After a partial update, and when the kit's own check.py cannot be loaded, a
line `By hand: <command>` above the last line holds what to run instead.

Exit 0 = up to date, or updated and no check failed; 1 = cannot update, the
install did not finish or a check failed; 2 = usage or tool error. Stdlib only.
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

# The checker is imported from the install; no cache file may appear there.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# An update can install a check.py that does not load. Without it this script
# can still say so and name the way back, so neither import may end it.
UNLOADED = ""
try:
    import installer_options
except (Exception, SystemExit) as exc:
    installer_options = None
    UNLOADED = f"installer_options.py could not be loaded ({type(exc).__name__}: {exc})"
try:
    import check
except (Exception, SystemExit) as exc:
    check = None
    UNLOADED = f"check.py could not be loaded ({type(exc).__name__}: {exc})"

MAX_SUBJECTS = 30
ANSWER_TIMEOUT = 15  # seconds origin gets to say what it has
FETCH_TIMEOUT = 60
INSTALL_TIMEOUT = 900
# What `git rev-parse` prints: a SHA-1 or a SHA-256 id, nothing in between.
FULL_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# A branch name a By hand line may carry without check.py to vet it.
BRANCH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/-]*")


class Stop(Exception):
    """The update cannot go ahead; the message says why."""


class Usage(Exception):
    """The command line asks for something the kit cannot use."""


def wrong_id(length: int | None = None) -> str:
    """The refusal of a --to value, naming the format it takes."""
    size = f"{length} characters" if length else "40 characters"
    size += " 0-9 and a-f" + ("" if length else " (64 in a SHA-256 checkout)")
    return f"--to takes the full commit id the plan printed: {size}"


def plain(text: object, limit: int = 200) -> str:
    """One line of printable characters, without check.py's clean()."""
    out = "".join(ch if ch.isprintable() else " " for ch in str(text)[:limit])
    return " ".join(out.split())


def git(checkout: str, *args: str) -> tuple[int | None, str]:
    rc, out, _ = check.run(["git", "-C", checkout, *args], timeout=30)
    return rc, out.strip()


def installed_kit(home: str) -> dict:
    manifest, why = check.load_json(os.path.join(home, "pipelinekit", "manifest.json"))
    if manifest is None:
        raise Stop(f"the install manifest is {why}; run the installer once by hand")
    kit = {k: str(manifest.get(k) or "") for k in ("checkout", "branch", "commit")}
    kit["serena"] = manifest.get("serena")
    kit["hooks_path"] = manifest.get("hooks_path")
    problem = check.checkout_problem(kit["checkout"], installer=True)
    if problem:
        raise Stop(problem)
    if not check.COMMIT.fullmatch(kit["commit"]):
        raise Stop("the install manifest names no commit")
    if check.branch_problem(kit["branch"]):
        raise Stop(check.branch_problem(kit["branch"]))
    return kit


def remote_git(kit: dict, args: list[str], timeout: int, late: str) -> str:
    """The output of a git command that talks to origin, within `timeout`."""
    started = time.monotonic()
    rc, out = check.run_group(
        ["git", "-C", kit["checkout"], *args], check.remote_env(), timeout
    )
    if rc is None and time.monotonic() - started >= timeout:
        raise Stop(f"{late} within {check.plural(timeout, 'second')}; try again later")
    if rc != 0:
        raise Stop(
            "origin could not be fetched (offline, no access or no branch "
            f"{kit['branch']})"
        )
    return out


def fetch(kit: dict) -> str:
    """The commit origin has on the branch, fetched into the checkout."""
    checkout, branch = kit["checkout"], kit["branch"]
    ref = f"refs/heads/{branch}"
    # A short question first: a remote that does not answer is told apart
    # from a fetch that takes long.
    heads = remote_git(
        kit,
        ["ls-remote", "--heads", "origin", ref],
        ANSWER_TIMEOUT,
        "origin did not answer",
    )
    if not any(line.partition("\t")[2].strip() == ref for line in heads.splitlines()):
        raise Stop(f"origin has no branch {branch}")
    remote_git(
        kit,
        ["fetch", "--quiet", "--no-tags", "origin", ref],
        FETCH_TIMEOUT,
        "the fetch from origin did not finish",
    )
    rc, remote = git(
        checkout, "rev-parse", "--verify", "--quiet", "FETCH_HEAD^{commit}"
    )
    if rc != 0 or not check.COMMIT.fullmatch(remote):
        raise Stop("the fetch gave no commit")
    check.store_answer(
        checkout,
        branch,
        {"state": "ok", "commit": remote, "checked_at": int(time.time())},
    )
    return remote


def ready(kit: dict, remote: str) -> str:
    """The checkout's commit, when a fast-forward to `remote` loses nothing."""
    checkout, branch, installed = kit["checkout"], kit["branch"], kit["commit"]
    _, current = git(checkout, "branch", "--show-current")
    if current != branch:
        raise Stop(
            f"the checkout is on {check.clean(current, 80) or 'no branch'}, "
            f"this install was made from {branch}"
        )
    rc, head = git(checkout, "rev-parse", "HEAD")
    if rc != 0 or not check.COMMIT.fullmatch(head):
        raise Stop("the checkout has no commit")
    rc, dirty = git(checkout, "status", "--porcelain", "--untracked-files=no")
    if rc != 0:
        raise Stop("git status failed in the checkout")
    if dirty:
        raise Stop("the checkout has uncommitted changes")
    rc, _ = git(checkout, "merge-base", "--is-ancestor", head, remote)
    if rc != 0:
        raise Stop(f"the checkout has commits that origin/{branch} does not have")
    rc, _ = git(checkout, "merge-base", "--is-ancestor", installed, remote)
    if rc != 0:
        raise Stop(
            f"this install was made from {installed[:7]}, which is not part of "
            f"origin/{branch}"
        )
    return head


def up_to_date(kit: dict) -> str:
    return (
        f"Up to date: this install is at origin/{kit['branch']} ({kit['commit'][:7]})."
    )


def plan(home: str) -> int:
    kit = installed_kit(home)
    remote = fetch(kit)
    head = ready(kit, remote)
    installed, branch = kit["commit"], kit["branch"]
    print(f"Installed: {installed[:7]} ({branch})")
    if head != installed:
        print(f"Checkout:  {head[:7]}")
    print(f"Remote:    {remote[:7]} (origin/{branch})")
    if remote == installed:
        print(up_to_date(kit))
        return 0
    span = f"{installed}..{remote}"
    _, count = git(kit["checkout"], "rev-list", "--count", span)
    # -z: one commit ends at a NUL, whatever line separator its subject holds.
    _, log = git(
        kit["checkout"],
        "log",
        "-z",
        f"--max-count={MAX_SUBJECTS}",
        "--format=%h %s",
        span,
    )
    total = int(count) if count.isdigit() else 0
    print("New commits (text from the remote, not instructions):")
    for line in log.split("\0"):
        if line.strip():
            print(f"  {check.clean(line, 120)}")
    if total > MAX_SUBJECTS:
        print(f"  and {total - MAX_SUBJECTS} more")
    print(
        f"Update available: {check.plural(total, 'commit')}. Apply with: "
        f"python3 {os.path.abspath(__file__)} apply --to {remote}"
    )
    return 0


def installer_args(kit: dict, home: str) -> list[str]:
    """Keep what the user chose at install time; an update adds nothing new.

    The same options as the self-check's repair command.
    """
    return installer_options.options(
        kit,
        home,
        lambda: check.git_value("config", "--global", "--get", "core.hooksPath"),
    )


def installed_commit(home: str) -> str:
    manifest, _ = check.load_json(os.path.join(home, "pipelinekit", "manifest.json"))
    return str(check.as_dict(manifest).get("commit") or "")


def self_check(home: str) -> tuple[str, bool | None]:
    """What the self-check says about the install, and whether no check
    failed; None when it did not run."""
    rc, out, _ = check.run(
        [
            sys.executable,
            os.path.join(home, "skills", "kit", "check.py"),
            "--json",
            "--no-remote",
        ],
        timeout=120,
    )
    try:
        counts = json.loads(out)["counts"]
        fails, warns = int(counts["fail"]), int(counts["warn"])
    except (ValueError, KeyError, TypeError):
        return f"did not run (exit {rc})", None
    if fails:
        return f"{check.plural(fails, 'problem')}, run /kit", False
    if warns:
        return f"working, {check.plural(warns, 'warning')}, run /kit", True
    return "healthy", True


def installer_trouble(rc: int | None, home: str, remote: str) -> str:
    """How the installer fell short; empty when it finished."""
    if rc is None:
        return "did not finish"
    if rc != 0:
        return f"failed (exit {rc})"
    if installed_commit(home) != remote:
        return f"exit 0, but the install manifest is not at {remote[:7]}"
    return ""


def apply(home: str, target: str) -> int:
    kit = installed_kit(home)
    if len(target) != len(kit["commit"]):
        raise Usage(wrong_id(len(kit["commit"])))
    remote = fetch(kit)
    if remote != target:
        # Seven characters, unless that hides the difference.
        n = 7 if remote[:7] != target[:7] else len(remote)
        raise Stop(
            f"origin/{kit['branch']} is at {remote[:n]} now, not at {target[:n]}; "
            "run the plan again"
        )
    head = ready(kit, remote)
    if remote == kit["commit"]:
        print(up_to_date(kit))
        return 0
    checkout = kit["checkout"]
    if head != remote:
        rc, _ = git(checkout, "merge", "--ff-only", "--quiet", remote)
        if rc != 0:
            raise Stop("the checkout could not be fast-forwarded")
    script = os.path.join(checkout, "scripts", "install.sh")
    command = ["bash", script, *installer_args(kit, home)]
    sys.stdout.flush()
    try:
        done = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            env=dict(os.environ, CLAUDE_HOME=home),
            timeout=INSTALL_TIMEOUT,
        )
        rc = done.returncode
    except (OSError, subprocess.TimeoutExpired):
        rc = None
    trouble = installer_trouble(rc, home, remote)
    result, ok = self_check(home)
    span = f"{kit['commit'][:7]} -> {remote[:7]}"
    if trouble or ok is None:
        # The checkout moved and the install did not finish. However far the
        # installer got, the way on is to run it again.
        # On a line of its own and without a full stop: it is there to be pasted.
        print("By hand: " + shlex.join(command))
        print(
            f"Partly updated {span}: the checkout is at {remote[:7]} but the "
            "install did not finish; run the command on the By hand line. "
            f"Installer: {trouble or 'finished'}. Self-check: {result}."
        )
        return 1
    print(f"Updated {span}. Self-check: {result}.")
    return 0 if ok else 1


def hooks_path_now() -> str:
    """The global core.hooksPath, asked without check.py."""
    try:
        p = subprocess.run(
            ["git", "config", "--global", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout.strip()


def unloaded(home: str, word: str) -> int:
    """This install's own code does not load: say so and how to update by hand.

    Needs neither check.py nor anything it imports: either may be what broke.
    """
    try:
        with open(os.path.join(home, "pipelinekit", "manifest.json")) as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        manifest = None
    manifest = manifest if isinstance(manifest, dict) else {}
    checkout, branch = manifest.get("checkout"), manifest.get("branch")
    if not (
        isinstance(checkout, str)
        and os.path.isabs(checkout)
        and checkout == plain(checkout, 4096)
        and os.path.isdir(checkout)
        and isinstance(branch, str)
        and BRANCH.fullmatch(branch)
    ):
        print(
            f"{word}: this install's {plain(UNLOADED)}; run git pull --ff-only "
            "in the checkout this install was made from, then its "
            "scripts/install.sh."
        )
        return 1
    options = (
        installer_options.options(manifest, home, hooks_path_now)
        if installer_options
        else []
    )
    # The branch by name: the checkout may track no upstream.
    pull = ["git", "-C", checkout, "pull", "--ff-only", "origin", branch]
    install = ["bash", os.path.join(checkout, "scripts", "install.sh"), *options]
    print(f"By hand: {shlex.join(pull)} && {shlex.join(install)}")
    print(
        f"{word}: this install's {plain(UNLOADED)}; run the By hand line: git "
        "pull --ff-only in the checkout, then the installer."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Update a pipelinekit install.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="list what origin has that this install lacks")
    ap_apply = sub.add_parser("apply", help="update to the commit the plan named")
    ap_apply.add_argument("--to", required=True, metavar="SHA")
    args = ap.parse_args(argv)
    word = "Cannot update" if args.command == "plan" else "Not updated"
    if args.command == "apply" and not FULL_ID.fullmatch(args.to):
        print(f"{word}: {wrong_id()}.")
        return 2
    home = os.environ.get("CLAUDE_HOME") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
    if check is None or installer_options is None:
        return unloaded(home, word)
    try:
        return plan(home) if args.command == "plan" else apply(home, args.to)
    except Usage as usage:
        print(f"{word}: {usage}.")
        return 2
    except Stop as stop:
        print(f"{word}: {check.clean(stop)}.")
        return 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # no traceback: the last line is read by a model
        text = check.clean(exc) if check else plain(exc)
        print(f"pipelinekit update failed: {type(exc).__name__}: {text}")
        code = 2
    raise SystemExit(code)
