"""Friction: how long CI and the project's own commands take, and how often CI fails.

CI runs are read with `gh run list` on the default branch. Local commands are
timed only when the user runs `garden.py time`; the scan shows what was kept.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import stat
import statistics
import subprocess
import time
from datetime import datetime, timezone

from garden_common import SAFE_BRANCH, duration, git, write_new

RUNS = 20
GH_TIMEOUT = 30
FAILED = {"failure", "timed_out", "startup_failure"}
# Runs that never ran to the end: their times say nothing about the build.
NOT_TIMED = {"cancelled", "skipped", "stale"}
SLOW_CI = 600  # seconds: a median above this is a finding
FAILING_CI = 0.2  # a failed share at or above this is a finding
SLOW_COMMAND = 300
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
TIMINGS = "timings.json"
MAX_TIMINGS = 1024 * 1024
KILL_GRACE = 5
# Signals that stop garden.py itself, as when the Bash tool ends a call that ran
# too long: the timed command and all it started are ended first.
STOP_SIGNALS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)
STOP_GRACE = 1


class Stopped(Exception):
    """garden.py got a stop signal while it timed a command."""

    def __init__(self, signum, seconds):
        super().__init__(signum)
        self.signum = signum
        self.seconds = seconds


def github_remote(project):
    rc, out = git(project.root, "config", "--get-regexp", r"^remote\..*\.url$")
    if rc:
        return False
    return any("github" in line.lower() for line in out.splitlines())


def default_branch(project):
    rc, out = git(project.root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out.strip().startswith("origin/"):
        return out.strip()[len("origin/") :]
    try:
        p = subprocess.run(
            [
                "gh",
                "repo",
                "view",
                "--json",
                "defaultBranchRef",
                "-q",
                ".defaultBranchRef.name",
            ],
            cwd=project.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            env=gh_env(),
        )
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    for name in ("main", "master"):
        if (
            git(project.root, "rev-parse", "--verify", "-q", f"refs/heads/{name}")[0]
            == 0
        ):
            return name
    return None


def gh_env():
    return dict(
        os.environ, GH_PROMPT_DISABLED="1", NO_COLOR="1", GH_NO_UPDATE_NOTIFIER="1"
    )


def when(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def ci_runs(project):
    """What the last finished CI runs on the default branch say, or why unknown."""
    if not project.in_git:
        reason = project.git_problem or "not a git repository"
        return {"measured": False, "reason": reason}
    if not github_remote(project):
        return {"measured": False, "reason": "no GitHub remote"}
    if not shutil.which("gh"):
        return {"measured": False, "reason": "gh is not installed"}
    branch = default_branch(project)
    if not branch or not SAFE_BRANCH.fullmatch(branch):
        return {"measured": False, "reason": "the default branch is not known"}
    try:
        p = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--branch",
                branch,
                "--status",
                "completed",
                "--limit",
                str(RUNS),
                "--json",
                "conclusion,createdAt,startedAt,updatedAt",
            ],
            cwd=project.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GH_TIMEOUT,
            env=gh_env(),
        )
    except subprocess.TimeoutExpired:
        return {
            "measured": False,
            "reason": f"gh gave no answer within {GH_TIMEOUT} seconds",
        }
    except OSError:
        return {"measured": False, "reason": "gh did not start"}
    if p.returncode:
        return {
            "measured": False,
            "reason": f"gh could not read the runs (exit {p.returncode})",
        }
    try:
        runs = json.loads(p.stdout or "[]")
        if not isinstance(runs, list):
            raise ValueError
    except (ValueError, RecursionError):
        return {
            "measured": False,
            "reason": "gh gave an answer that is not a list of runs",
        }
    seconds, failed, untimed = [], 0, 0
    for run in runs[:RUNS]:
        if not isinstance(run, dict):
            continue
        conclusion = str(run.get("conclusion", "")).lower()
        if conclusion in FAILED:
            failed += 1
        if conclusion in NOT_TIMED:
            untimed += 1
            continue
        start = when(run.get("startedAt")) or when(run.get("createdAt"))
        end = when(run.get("updatedAt"))
        if start and end and end >= start:
            seconds.append((end - start).total_seconds())
    counted = len([r for r in runs[:RUNS] if isinstance(r, dict)])
    if not counted:
        return {"measured": True, "branch": branch, "runs": 0}
    return {
        "measured": True,
        "branch": branch,
        "runs": counted,
        "median": statistics.median(seconds) if seconds else None,
        "longest": max(seconds) if seconds else None,
        "failed": failed,
        "untimed": untimed,
    }


def load_timings(project):
    """The kept timings; None when the file is there but cannot be read."""
    path = project.garden / TIMINGS
    try:
        st = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return {}
    except OSError:
        return None
    try:
        if stat.S_ISLNK(st.st_mode) or st.st_size > MAX_TIMINGS:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    kept = {}
    for label, t in data.items():
        if not (
            isinstance(label, str) and LABEL.fullmatch(label) and isinstance(t, dict)
        ):
            continue
        secs, code = t.get("seconds"), t.get("exit")
        if not isinstance(secs, (int, float)) or isinstance(secs, bool) or secs < 0:
            continue
        if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
            continue
        date = (
            t.get("date")
            if isinstance(t.get("date"), str) and when(t.get("date"))
            else None
        )
        kept[label] = {
            "seconds": float(secs),
            "exit": code,
            "timed_out": t.get("timed_out") is True,
            "date": date,
        }
    return kept


def save_timing(project, label, seconds, code, timed_out, now):
    """Keep one timing; a damaged timings file is replaced. OSError on failure."""
    data = load_timings(project) or {}
    data[label] = {
        "seconds": round(seconds, 3),
        "exit": code,
        "timed_out": timed_out,
        "date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_new(
        project.garden / TIMINGS, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )


def end_group(p, grace=KILL_GRACE):
    """End the command and everything it started: TERM, then KILL after a grace."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2)):
        try:
            os.killpg(p.pid, sig)
        except OSError:
            with contextlib.suppress(OSError):
                p.send_signal(sig)
        try:
            p.wait(timeout=wait)
            if sig == signal.SIGTERM:
                # The leader is gone; children that ignored TERM still get KILL.
                with contextlib.suppress(OSError):
                    os.killpg(p.pid, signal.SIGKILL)
            return
        except subprocess.TimeoutExpired:
            continue


def run_timed(command, timeout, cwd):
    """(seconds, exit code or None, timed out) for one run of `command`.

    Raises Stopped when garden.py gets TERM or HUP, after ending the command.
    """
    start = time.monotonic()

    def stop(signum, _frame):
        raise Stopped(signum, time.monotonic() - start)

    before = {sig: signal.signal(sig, stop) for sig in STOP_SIGNALS}
    p = None
    try:
        p = subprocess.Popen(command, cwd=cwd, start_new_session=True)
        code = p.wait(timeout=timeout)
        return time.monotonic() - start, code, False
    except subprocess.TimeoutExpired:
        end_group(p)
        return time.monotonic() - start, None, True
    except Stopped:
        for sig in STOP_SIGNALS:
            signal.signal(sig, signal.SIG_IGN)
        if p is not None:
            end_group(p, STOP_GRACE)
        raise
    except KeyboardInterrupt:
        if p is not None:
            end_group(p)
        raise
    finally:
        for sig, handler in before.items():
            signal.signal(sig, handler)


def friction_findings(friction):
    out = []
    ci = friction["ci"]
    if ci.get("measured") and ci.get("runs"):
        if ci.get("median") is not None and ci["median"] > SLOW_CI:
            out.append(
                {
                    "key": "friction.ci-slow",
                    "area": "Friction",
                    "title": "CI is slow",
                    "evidence": f"median {duration(ci['median'])}, "
                    f"longest {duration(ci['longest'])} "
                    f"over the last {ci['runs']} runs",
                    "change": "Cache dependencies, split the slowest job, "
                    "and run the fast checks first",
                    "size": "M",
                    "weight": 75,
                }
            )
        share = ci["failed"] / ci["runs"]
        if share >= FAILING_CI:
            out.append(
                {
                    "key": "friction.ci-failing",
                    "area": "Friction",
                    "title": "CI fails often on the default branch",
                    "evidence": f"{ci['failed']} of the last {ci['runs']} runs failed "
                    f"({round(share * 100)}%)",
                    "change": "Read the failed runs, fix the flaky or broken step, "
                    "and add a check that catches it before the merge",
                    "size": "M",
                    "weight": 85,
                }
            )
    for label, t in sorted((friction["timings"] or {}).items()):
        if t["timed_out"]:
            evidence, title = (
                f"{label}: timed out after {duration(t['seconds'])}",
                f"{label} did not finish",
            )
        elif t["exit"]:
            evidence, title = (
                f"{label}: exit {t['exit']} after {duration(t['seconds'])}",
                f"{label} fails",
            )
        elif t["seconds"] > SLOW_COMMAND:
            evidence, title = (
                f"{label}: {duration(t['seconds'])}, exit 0",
                f"{label} is slow",
            )
        else:
            continue
        out.append(
            {
                "key": f"friction.command.{label}",
                "area": "Friction",
                "title": title,
                "evidence": evidence,
                "change": f"Find what makes {label} slow or failing and fix it, "
                "so it can run on every change",
                "size": "M",
                "weight": 70,
            }
        )
    return out
