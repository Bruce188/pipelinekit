#!/usr/bin/env python3
"""pipelinekit self-check: report what is not working in an installed kit.

Usage:
  check.py [--json] [--quick] [--verbose] [--exit-zero] [--days N] [--session ID]
           [--no-remote]
  check.py --write-manifest REPO_ROOT

Sections: install, changes since install (against the install manifest), a
live probe of every hook (must block, must allow), the environment, whether
the remote has a newer kit (asked once a day, never a failure), and the
activity of the hooks: what they blocked, asked about or failed on in the
last N days (default 7), read from their event log.
`--quick` skips the probes, the update check, the activity and everything slow.

Exit 0 = healthy, 1 = problems found, 2 = the checker itself failed.
Stdlib only. Reads $CLAUDE_HOME (default ~/.claude) and changes nothing in it.
"""

# ruff: noqa: E402, F403, F405
from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import os
import re
import shlex
import shutil
import sys
import time

# Run from the install: no cache file may appear next to it.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from check_core import *
except ImportError as e:  # a module missing or broken in the install
    print(
        f"check.py: cannot load its modules ({e}); install the kit again",
        file=sys.stderr,
    )
    raise SystemExit(0 if "--exit-zero" in sys.argv else 2) from None

# ---------------------------------------------------------------- environment


def is_wsl() -> bool:
    try:
        with open("/proc/sys/kernel/osrelease", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def gh_login_file() -> str:
    base = os.environ.get("GH_CONFIG_DIR") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME")
        or os.path.join(os.path.expanduser("~"), ".config"),
        "gh",
    )
    return os.path.join(base, "hosts.yml")


def read_refused(path: str) -> bool:
    """The file is ours and readable by its mode, and opening it is refused.

    That is what a sandbox around this process does. Nothing is read from it.
    """
    try:
        st = os.stat(path)
        if st.st_uid != os.getuid() or not st.st_mode & 0o400:
            return False
        os.close(os.open(path, os.O_RDONLY))
    except PermissionError:
        return True
    except OSError:
        return False
    return False


def check_sandbox(c: Check) -> None:
    """The kit's deny rule for the gh login also binds gh inside the sandbox."""
    if not shutil.which("gh"):
        return
    settings = as_dict(c.settings)
    box = as_dict(settings.get("sandbox"))
    rules = as_list(as_dict(settings.get("permissions")).get("deny"))
    declared = box.get("enabled") is True and any(
        str(r).startswith("Read(") and "gh/hosts.yml" in str(r) for r in rules
    )
    refused = read_refused(gh_login_file())
    if not (declared or refused):
        return
    fix = (
        'add "gh *" to sandbox.excludedCommands in settings.json, '
        "or run gh outside the sandbox"
    )
    excluded = as_list(box.get("excludedCommands"))
    if any(re.match(r"gh\b", str(x).strip()) for x in excluded):
        c.add(
            "environment",
            "pass",
            "gh is excluded from the Bash sandbox, which denies its login file",
        )
    elif declared:
        c.add(
            "environment",
            "warn",
            "the Bash sandbox is on and applies the deny rule for the gh login "
            "file (hosts.yml) to gh itself: gh fails in sandboxed commands, and "
            "so does git over https when it asks gh for the token",
            fix,
        )
    else:
        c.add(
            "environment",
            "info",
            "this session cannot open the gh login file (hosts.yml), as inside "
            "a Bash sandbox: gh works here only when it is excluded from it",
            fix,
        )


def check_design_plugin(c: Check) -> None:
    """One info line when the user settings enable frontend-design as a plugin
    and the kit's copy is installed (without it there are no two copies).

    A key is repeated only when it reads as a plain name; the rest are counted.
    """
    if not os.path.isfile(c.path(f"skills/{DESIGN_SKILL}/SKILL.md")):
        return
    plugins = as_dict(as_dict(c.settings).get("enabledPlugins"))
    found = [
        key
        for key, on in plugins.items()
        if on is True and DESIGN_PLUGIN_KEY.fullmatch(key)
    ]
    if not found:
        return
    shown = sorted(key for key in found if plain(key, PLAIN_NAME))
    if shown:
        more = len(found) - 1
        tail = f"Plugin: {shown[0]}" + (f" and {more} more" if more else "")
    else:
        tail = f"Plugin entries: {len(found)}"
    c.add("environment", "info", f"{DESIGN_PLUGIN_NOTE} {tail}")


def check_environment(c: Check) -> None:
    v = sys.version_info
    version = f"python3 {v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        c.add("environment", "info", version)
    else:
        c.add("environment", "warn", f"{version}: the kit is tested on 3.10 and newer")
    if is_wsl():
        c.add("environment", "info", WSL_NOTE)
    if os.environ.get("PIPELINEKIT_SESSION_CHECK") == "0":
        c.add(
            "environment",
            "info",
            "the session-start check is switched off (PIPELINEKIT_SESSION_CHECK=0)",
        )
    check_design_plugin(c)
    if c.quick:
        return
    for prog, args, missing in (
        (
            "gitleaks",
            ["version"],
            "gitleaks not installed (secret scan of commits and merges skipped)",
        ),
        (
            "claude",
            ["--version"],
            "claude CLI not on PATH (install: https://claude.ai/install.sh)",
        ),
        (
            "gh",
            ["--version"],
            "gh not installed (the ship skill needs it for pull requests)",
        ),
    ):
        if not shutil.which(prog):
            c.add("environment", "info", missing)
            continue
        _, out, err = run([prog, *args])
        first = ((out or err).strip().splitlines() or ["version unknown"])[0]
        label = "claude CLI" if prog == "claude" else prog
        c.add("environment", "pass", f"{label}: {first.removeprefix('gh version ')}")
    try:
        found = importlib.metadata.version("playwright")
        c.add("environment", "pass", f"playwright: {found} (python3)")
    except importlib.metadata.PackageNotFoundError:
        c.add(
            "environment",
            "info",
            "playwright not installed for python3 "
            "(the ship skill tests web pages with it)",
        )
    check_sandbox(c)
    local = git_value("config", "--local", "--get", "core.hooksPath")
    if local and not same_path(local, c.path("git-hooks")):
        c.add(
            "environment",
            "warn",
            f"this repository sets its own core.hooksPath ({local}): "
            "the kit git hooks do not run here",
        )


# ---------------------------------------------------------------- activity


def check_activity(c: Check) -> None:
    """What the hooks blocked, asked about, let through or failed on."""
    off = os.environ.get("PIPELINEKIT_LOG") == "0"
    if off:
        c.add("activity", "info", "the event log is switched off (PIPELINEKIT_LOG=0)")
    now = time.time()
    since = now - c.days * 86400
    directory = state_dir()
    logs = [os.path.join(directory, n) for n in ("events.jsonl.1", "events.jsonl")]
    # A log that is there and cannot be read is named, not taken for empty.
    lost = [
        p
        for p in logs
        if os.path.lexists(p) and not (os.path.isfile(p) and os.access(p, os.R_OK))
    ]
    if os.path.lexists(directory) and not (
        os.path.isdir(directory) and os.access(directory, os.R_OK | os.X_OK)
    ):
        lost = [directory]
    for path in lost:
        c.add("activity", "info", f"the event log cannot be read: {clean(path)}")
    seen: set[tuple] = set()
    groups: dict[tuple[str, str, str], dict] = {}
    for e in read_events(directory):
        # An event from the future was written by a clock that was wrong.
        if e["when"] < since or e["when"] > now + 300:
            continue
        if c.session and e.get("session") != c.session:
            continue
        key = (e["hook"], e["rule"], e["kind"])
        call = e.get("tool_use_id")
        if isinstance(call, str) and call:
            # One command can trip the same rule once per program in it.
            if (call, *key) in seen:
                continue
            seen.add((call, *key))
        g = groups.setdefault(key, {"count": 0, "last": -1, "reason": ""})
        g["count"] += 1
        if e["when"] >= g["last"]:
            g["last"] = e["when"]
            g["reason"] = clean(e.get("reason") or "", 200)
    if not groups:
        if not off and not lost:
            c.add("activity", "info", f"no blocks, asks or hook errors ({c.window})")
        return
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1]["last"], kv[0]))
    hidden: list[str] = []
    extra = 0
    for n, ((hook, rule, kind), g) in enumerate(ordered):
        when = time.gmtime(g["last"])
        c.activity.append(
            {
                "hook": hook,
                "rule": rule,
                "kind": kind,
                "count": g["count"],
                "last": time.strftime("%Y-%m-%dT%H:%M:%SZ", when),
                "reason": g["reason"],
            }
        )
        if n >= ACTIVITY_LINES:
            # A failed hook is not dropped for newer blocks.
            if kind != "error" or extra >= ACTIVITY_LINES:
                hidden.append(kind)
                continue
            extra += 1
        times = "once" if g["count"] == 1 else f"{g['count']} times"
        msg = (
            f"{rule} ({hook}): {EVENT_KINDS[kind]} {times}, "
            f"last {time.strftime('%Y-%m-%d %H:%M UTC', when)}"
        )
        if g["reason"]:
            msg += f": {g['reason']}"
        c.add("activity", "warn" if kind == "error" else "info", msg)
    if hidden:
        failed = hidden.count("error")
        c.add(
            "activity",
            "warn" if failed else "info",
            f"{plural(len(hidden), 'more rule')} not shown"
            + (f", {failed} of them failed" if failed else "")
            + " (--json lists them all)",
        )


# ---------------------------------------------------------------- report


# ---------------------------------------------------------------- updates


def age(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{round(seconds / 60)} minutes ago"
    return f"{round(seconds / 3600)} hours ago"


def remote_env() -> dict:
    """git may not ask for a password: there is nobody to answer."""
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="true")


def ask_remote(checkout: str, branch: str) -> dict:
    """What origin has on the branch: state ok, gone or unreachable."""
    ref = f"refs/heads/{branch}"
    rc, out = run_group(
        ["git", "-C", checkout, "ls-remote", "--heads", "origin", ref],
        remote_env(),
        UPDATE_TIMEOUT,
    )
    if rc != 0:
        return {"state": "unreachable", "commit": ""}
    for line in out.splitlines():
        commit, _, name = line.partition("\t")
        if name.strip() == ref and COMMIT.fullmatch(commit):
            return {"state": "ok", "commit": commit}
    return {"state": "gone", "commit": ""}


def update_cache() -> str:
    return os.path.join(state_dir(), "update.json")


def cached_answer(checkout: str, branch: str, now: float) -> dict | None:
    data = as_dict(load_json(update_cache())[0])
    state, at = data.get("state"), data.get("checked_at")
    commit = str(data.get("commit") or "")
    if (
        data.get("checkout") != checkout
        or data.get("branch") != branch
        or state not in UPDATE_TTL
        or isinstance(at, bool)
        or not isinstance(at, (int, float))
        or not 0 <= now - at < UPDATE_TTL[state]
        or (state == "ok" and not COMMIT.fullmatch(commit))
    ):
        return None
    return {"state": state, "commit": commit, "checked_at": at}


def store_answer(checkout: str, branch: str, answer: dict) -> None:
    """Best effort: without the file the remote is asked again next time."""
    path = update_cache()
    record = {
        "checked_at": answer["checked_at"],
        "checkout": checkout,
        "branch": branch,
        "state": answer["state"],
        "commit": answer["commit"],
    }
    with contextlib.suppress(OSError):
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f)
        os.replace(path + ".tmp", path)


def check_update(c: Check) -> None:
    """Is the remote ahead of this install? Informs; never a problem."""

    def skip(why: str) -> None:
        c.update = {"state": "unknown"}
        c.add("update", "info", f"not checked: {why}")

    if os.environ.get("PIPELINEKIT_UPDATE_CHECK") == "0":
        c.update = {"state": "off"}
        c.add(
            "update",
            "info",
            "the update check is switched off (PIPELINEKIT_UPDATE_CHECK=0)",
        )
        return
    m = as_dict(c.manifest)
    checkout, branch, installed = (
        str(m.get(k) or "") for k in ("checkout", "branch", "commit")
    )
    there = os.path.isabs(checkout) and os.path.exists(os.path.join(checkout, ".git"))
    if not there:
        return skip("the checkout this install was made from is not there")
    if not COMMIT.fullmatch(installed):
        return skip("the install manifest names no commit")
    head = git_value("-C", checkout, "rev-parse", "HEAD")
    if COMMIT.fullmatch(head) and head != installed:
        c.add(
            "update",
            "info",
            f"the checkout is at {head[:7]}, this install was made from "
            f"{installed[:7]}: the installer brings the install in line",
            repair_hint(c),
        )
    if not BRANCH.fullmatch(branch):
        return skip("the install was made from a checkout that was on no branch")
    now = time.time()
    answer = cached_answer(checkout, branch, now)
    if answer is None:
        if not c.remote:
            c.update = {"state": "unknown"}
            return None
        answer = dict(ask_remote(checkout, branch), checked_at=int(now))
        store_answer(checkout, branch, answer)
    remote = answer["commit"]
    if answer["state"] == "unreachable":
        return skip("origin did not answer (offline, no access or no such remote)")
    if answer["state"] == "gone":
        return skip(f"origin has no branch {branch}")
    when = f"checked {age(now - answer['checked_at'])}"
    c.update = {
        "state": "current",
        "branch": branch,
        "installed": installed,
        "remote": remote,
        "checked_at": int(answer["checked_at"]),
    }
    if remote == installed:
        c.add(
            "update",
            "pass",
            f"up to date with origin/{branch} ({remote[:7]}, {when})",
        )
        return None
    rc, _, _ = run(
        ["git", "-C", checkout, "merge-base", "--is-ancestor", remote, installed],
        timeout=5,
    )
    if rc == 0:
        c.update["state"] = "ahead"
        c.add(
            "update",
            "pass",
            f"ahead of origin/{branch}: this install is from {installed[:7]}, "
            f"the remote is at {remote[:7]} ({when})",
        )
        return None
    c.update["state"] = "available"
    count = git_value("-C", checkout, "rev-list", "--count", f"{installed}..{remote}")
    behind = f", {plural(int(count), 'commit')} ahead" if count.isdigit() else ""
    c.add(
        "update",
        "info",
        f"update available: origin/{branch} is at {remote[:7]}{behind}, "
        f"this install is from {installed[:7]} ({when})",
        "/kit update in a session, or from a shell: "
        f"python3 {c.path('skills/kit/update.py')} plan",
    )
    return None


def repair_hint(c: Check) -> str:
    """The installer, with what the install was made without."""
    m = as_dict(c.manifest)
    checkout = str(m.get("checkout") or "")
    script = os.path.join(checkout, "scripts", "install.sh")
    keep = " --no-serena" if m.get("serena") is False else ""
    shown = clean(checkout) == checkout
    if shown and os.path.isabs(script) and os.path.isfile(script):
        return f"bash {shlex.quote(script)}{keep}"
    return f"bash scripts/install.sh{keep} in your pipelinekit checkout"


def kit_info(c: Check) -> dict:
    m = as_dict(c.manifest)
    names_shown = {
        "version": PLAIN_VERSION,
        "commit": PLAIN_COMMIT,
        "branch": PLAIN_BRANCH,
        "installed_at": PLAIN_TIME,
    }
    info = {k: plain(m.get(k), p) for k, p in names_shown.items()}
    info["checkout"] = clean(m.get("checkout") or "")
    return info


def render_text(c: Check, verbose: bool) -> str:
    kit = {k: clean(v) for k, v in kit_info(c).items()}
    head = " ".join(x for x in ("pipelinekit", kit["version"]) if x)
    ref = ", ".join(x for x in (kit["commit"][:7], kit["branch"]) if x)
    lines = [
        head
        + (f" ({ref})" if ref else "")
        + f" at {c.home}"
        + (" (quick check)" if c.quick else "")
    ]
    for key, title in SECTIONS:
        items = [i for i in c.items if i["section"] == key]
        if not items:
            continue
        lines.append(f"{title} ({c.window})" if key == "activity" else title)
        shown = items if verbose else [i for i in items if i["level"] != "pass"]
        for i in shown:
            lines.append(f"  [{i['level']}] {i['msg']}")
            if "fix" in i:
                lines.append(f"         fix: {i['fix']}")
        hidden = len(items) - len(shown)
        if hidden:
            lines.append(f"  [pass] {plural(hidden, 'check')}")
    fails, warns = c.count("fail"), c.count("warn")
    if fails:
        lines.append(f"Result: {plural(fails, 'problem')}, {plural(warns, 'warning')}")
        lines.append(f"Next: run {repair_hint(c)}, then /kit again.")
    elif warns:
        lines.append(f"Result: working, {plural(warns, 'warning')}")
    else:
        lines.append("Result: healthy")
    return "\n".join(lines)


def render_json(c: Check) -> str:
    return json.dumps(
        {
            "schema": SCHEMA,
            "home": c.home,
            "mode": "quick" if c.quick else "full",
            "kit": kit_info(c),
            "healthy": c.count("fail") == 0,
            "counts": {k: c.count(k) for k in ("fail", "warn", "info", "pass")},
            "repair": repair_hint(c),
            "results": c.items,
            "update": c.update,
            "activity": c.activity,
        },
        indent=2,
    )


def run_checks(
    home: str, quick: bool, days: int = 7, session: str = "", remote: bool = True
) -> Check:
    c = Check(home, quick, days, session)
    c.remote = remote
    check_install(c)
    check_drift(c)
    if not quick:
        probe(c)
    check_environment(c)
    if not quick:
        check_update(c)
        check_activity(c)
    return c


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Report what is not working in a pipelinekit install."
    )
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument(
        "--quick", action="store_true", help="no live probes, no slow checks"
    )
    ap.add_argument(
        "-v", "--verbose", action="store_true", help="list passed checks too"
    )
    ap.add_argument("--exit-zero", action="store_true", help="exit 0 whatever is found")
    ap.add_argument(
        "--days",
        type=int,
        default=7,
        metavar="N",
        help="activity of the last N days (1 to 365, default 7)",
    )
    ap.add_argument(
        "--session",
        default="",
        metavar="ID",
        help="activity of one Claude Code session only",
    )
    ap.add_argument(
        "--no-remote",
        action="store_true",
        help="do not ask the remote for updates; an answer from today is still shown",
    )
    ap.add_argument("--write-manifest", metavar="REPO_ROOT", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if not 1 <= args.days <= 365:
        ap.error("--days takes a whole number from 1 to 365")
    if args.session and not SESSION.fullmatch(args.session):
        ap.error("--session takes a session id (letters, digits, - and _)")
    home = os.environ.get("CLAUDE_HOME") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
    if args.write_manifest:
        write_manifest(args.write_manifest, home)
        return 0
    c = run_checks(home, args.quick, args.days, args.session, not args.no_remote)
    print(render_json(c) if args.json else render_text(c, args.verbose))
    return 0 if args.exit_zero or c.count("fail") == 0 else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        # A character the terminal cannot show must not end the report.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        code = main()
    except Exception as exc:  # the checker must not die with a traceback
        print(f"pipelinekit check failed: {type(exc).__name__}: {clean(exc)}")
        code = 0 if "--exit-zero" in sys.argv else 2
    raise SystemExit(code)
