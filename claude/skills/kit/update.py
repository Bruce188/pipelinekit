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
  Partly updated <old> -> <new>: ...   the installer failed after it had
                                       replaced the files
  Up to date: ...
  Not updated: <reason>.
When the installer fails, a line `By hand: <command>` above the last line holds
the command that runs it again.

Exit 0 = up to date, or updated and no check failed; 1 = cannot update, the
installer failed or a check failed; 2 = usage or tool error. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

# The checker is imported from the install; no cache file may appear there.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check  # noqa: E402

MAX_SUBJECTS = 30
FETCH_TIMEOUT = 60  # seconds
INSTALL_TIMEOUT = 900
# What `git rev-parse` prints: a SHA-1 or a SHA-256 id, nothing in between.
FULL_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class Stop(Exception):
    """The update cannot go ahead; the message says why."""


def git(checkout: str, *args: str) -> tuple[int | None, str]:
    rc, out, _ = check.run(["git", "-C", checkout, *args], timeout=30)
    return rc, out.strip()


def installed_kit(home: str) -> dict:
    manifest, why = check.load_json(os.path.join(home, "pipelinekit", "manifest.json"))
    if manifest is None:
        raise Stop(f"the install manifest is {why}; run the installer once by hand")
    kit = {k: str(manifest.get(k) or "") for k in ("checkout", "branch", "commit")}
    kit["serena"] = manifest.get("serena")
    script = os.path.join(kit["checkout"], "scripts", "install.sh")
    # A path that is not absolute would mean the directory this runs in.
    if not os.path.isabs(script) or not os.path.isfile(script):
        raise Stop("the checkout this install was made from is not there")
    if not check.COMMIT.fullmatch(kit["commit"]):
        raise Stop("the install manifest names no commit")
    if not check.BRANCH.fullmatch(kit["branch"]):
        raise Stop("the install was made from a checkout that was on no branch")
    return kit


def fetch(kit: dict) -> str:
    """The commit origin has on the branch, fetched into the checkout."""
    checkout, branch = kit["checkout"], kit["branch"]
    rc, _ = check.run_group(
        [
            "git",
            "-C",
            checkout,
            "fetch",
            "--quiet",
            "--no-tags",
            "origin",
            f"refs/heads/{branch}",
        ],
        check.remote_env(),
        FETCH_TIMEOUT,
    )
    if rc != 0:
        raise Stop(
            f"origin could not be fetched (offline, no access or no branch {branch})"
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
    """Keep what the user chose at install time; an update adds nothing new."""
    hooks = check.git_value("config", "--global", "--get", "core.hooksPath")
    mine = check.same_path(hooks, os.path.join(home, "git-hooks"))
    args = ["--git-hooks" if mine else "--no-git-hooks"]
    serena = kit["serena"]
    if serena is False or (serena is None and not shutil.which("serena")):
        args.append("--no-serena")
    return args


def installed_commit(home: str) -> str:
    manifest, _ = check.load_json(os.path.join(home, "pipelinekit", "manifest.json"))
    return str(check.as_dict(manifest).get("commit") or "")


def self_check(home: str) -> tuple[str, bool]:
    """What the self-check says about the install, and whether no check failed."""
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
        return f"did not run (exit {rc})", False
    if fails:
        return f"{check.plural(fails, 'problem')}, run /kit", False
    if warns:
        return f"working, {check.plural(warns, 'warning')}, run /kit", True
    return "healthy", True


def apply(home: str, target: str) -> int:
    kit = installed_kit(home)
    remote = fetch(kit)
    if remote != target:
        raise Stop(
            f"origin/{kit['branch']} is at {remote[:7]} now, not at {target[:7]}; "
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
    how = "did not finish" if rc is None else f"failed (exit {rc})"
    if rc != 0:
        # On a line of its own and without a full stop: it is there to be pasted.
        print("By hand: " + " ".join(shlex.quote(part) for part in command))
        if installed_commit(home) != remote:
            raise Stop(
                f"the checkout is at {remote[:7]} but the installer {how} and may "
                "have replaced some files; its command is on the By hand line"
            )
    result, ok = self_check(home)
    span = f"{kit['commit'][:7]} -> {remote[:7]}"
    if rc != 0:
        print(
            f"Partly updated {span}: the installer {how} after it had replaced "
            f"the files; its command is on the By hand line. Self-check: {result}."
        )
        return 1
    print(f"Updated {span}. Self-check: {result}.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Update a pipelinekit install.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="list what origin has that this install lacks")
    ap_apply = sub.add_parser("apply", help="update to the commit the plan named")
    ap_apply.add_argument("--to", required=True, metavar="SHA")
    args = ap.parse_args(argv)
    if args.command == "apply" and not FULL_ID.fullmatch(args.to):
        ap.error("--to takes the full commit id that the plan printed")
    home = os.environ.get("CLAUDE_HOME") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
    try:
        return plan(home) if args.command == "plan" else apply(home, args.to)
    except Stop as stop:
        word = "Cannot update" if args.command == "plan" else "Not updated"
        print(f"{word}: {check.clean(stop)}.")
        return 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # no traceback: the last line is read by a model
        print(f"pipelinekit update failed: {type(exc).__name__}: {check.clean(exc)}")
        code = 2
    raise SystemExit(code)
