#!/usr/bin/env python3
"""Audit the ground a project is built on: friction, checks, pruning, guidance.

  garden.py scan [--json]                        the four sections, the ranked findings
  garden.py time --label L [--timeout N] -- CMD  run CMD, keep duration and exit code
  garden.py record [--scan ID --picked G1 G3]    save this run under docs/garden/

The scan reads files and asks git and gh; it runs nothing from the project and
changes no file. Its output holds file names, counts, durations and dates only.
`time` runs the one command it is given and keeps neither its output nor its
arguments. `record` and `time` write to docs/garden/ only, which they add to
.git/info/exclude. The scan's id names its list of findings; `record` takes
it with the picked ids and refuses when the findings changed since.

Exit codes: scan 0; record 0, 1 when docs/garden/ cannot be written, 2 on
wrong use; time gives the command's own exit code, 124 when it timed out, 127
when it could not start, 128 plus the signal when garden.py was stopped
(the command is ended first), and 2 on wrong use or when docs/garden/ cannot
be written (then nothing runs). An unexpected error is one line, "internal
error (<class>, line <n>)", never a traceback: scan still exits 0, record and
time exit 2.

Standard library only, Python 3.10 or later.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone

sys.dont_write_bytecode = True  # leave no __pycache__ in the installed skill
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from garden_checks import KIND_NAMES, MARKERS, STACK_NAMES, check_findings, scan_checks
from garden_common import (
    GARDEN_DIR,
    Project,
    duration,
    garden_problem,
    git,
    plural,
    write_new,
)
from garden_friction import (
    LABEL,
    TIMINGS,
    Stopped,
    ci_runs,
    friction_findings,
    load_timings,
    run_timed,
    save_timing,
    when,
)
from garden_prune import prune_findings, scan_pruning

SCHEMA = 1
LAST = "last.json"
LONG_GUIDE_LINES = 300
LONG_GUIDE_BYTES = 40000
FINDING_ID = re.compile(r"G[1-9][0-9]{0,3}")
SCAN_ID = re.compile(r"[0-9a-f]{8}")
# The last part may hold dots: a label of `garden.py time` such as unit.fast.
KEY = re.compile(r"[a-z]+(?:\.[A-Za-z0-9_-]+){1,2}(?:\.[A-Za-z0-9._-]{1,40})?")
STATES = ("open", "picked")
# A wrong id the refusal may repeat.
SAFE_ARG = re.compile(r"[A-Za-z0-9_-]{1,20}")
DEFAULT_TIMEOUT = 600
MAX_TIMEOUT = 86400
HERE = os.path.dirname(os.path.abspath(__file__))
UNAVAILABLE = "not checked, file list not available"


def now_utc():
    return datetime.now(timezone.utc)


def stamp(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ----- guidance ------------------------------------------------------------


def guide_file(project):
    for name in ("CLAUDE.md", ".claude/CLAUDE.md"):
        path = project.root / name
        try:
            if path.is_file():
                data = path.read_bytes()
                return {
                    "file": name,
                    "lines": data.count(b"\n")
                    + (0 if data.endswith(b"\n") or not data else 1),
                    "bytes": len(data),
                }
        except OSError:
            continue
    return None


def previous_run(project):
    """{date, findings} from docs/garden/last.json; {'broken': True} when unreadable."""
    path = project.garden / LAST
    try:
        size = path.stat().st_size
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        # Inside the try: on Python 3.10 to 3.13 exists() raises when the
        # folder cannot be searched.
        return {"broken": True}
    try:
        if size > 1024 * 1024:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
        date = when(data.get("date"))
        if (
            not isinstance(data, dict)
            or date is None
            or not isinstance(data.get("findings"), list)
        ):
            raise ValueError
    except (OSError, ValueError, RecursionError, AttributeError):
        return {"broken": True}
    findings = []
    for f in data["findings"]:
        if not isinstance(f, dict):
            continue
        fid, key, state = f.get("id"), f.get("key"), f.get("state")
        if (
            isinstance(fid, str)
            and FINDING_ID.fullmatch(fid)
            and isinstance(key, str)
            and KEY.fullmatch(key)
            and state in STATES
        ):
            findings.append({"id": fid, "key": key, "state": state})
    return {"date": date, "findings": findings}


def scan_guidance(project, findings, previous, now):
    guide = guide_file(project)
    out = {"claude_md": guide, "previous": None}
    if previous and previous.get("broken"):
        out["previous"] = {"broken": True}
    elif previous:
        current = {f["key"]: f for f in findings}
        still = [
            {
                "was": p["id"],
                "now": current[p["key"]]["id"],
                "title": current[p["key"]]["title"],
                "state": p["state"],
            }
            for p in previous["findings"]
            if p["key"] in current
        ]
        out["previous"] = {
            "date": previous["date"].strftime("%Y-%m-%d"),
            "days": max(0, (now - previous["date"]).days),
            "findings": len(previous["findings"]),
            "still_open": still,
        }
    return out


def guidance_findings(guide):
    if guide is None:
        return [
            {
                "key": "guidance.no-claude-md",
                "area": "Guidance",
                "title": "No CLAUDE.md",
                "evidence": "0 guidance files found (CLAUDE.md, .claude/CLAUDE.md)",
                "change": "Add a short CLAUDE.md: how to build and test, "
                "the checks to run, and the rules a past mistake taught",
                "size": "S",
                "weight": 35,
            }
        ]
    if guide["lines"] > LONG_GUIDE_LINES or guide["bytes"] > LONG_GUIDE_BYTES:
        return [
            {
                "key": "guidance.long-claude-md",
                "area": "Guidance",
                "title": "CLAUDE.md is long",
                "evidence": f"{guide['file']}: {guide['lines']} lines, "
                f"{guide['bytes']} bytes",
                "change": "Cut it to the rules an agent needs on every task; "
                "move the rest into documentation it can look up",
                "size": "M",
                "weight": 30,
            }
        ]
    return []


# ----- the scan ------------------------------------------------------------


def scan(project):
    now = now_utc()
    checks = scan_checks(project)
    stack_names = [s["stack"] for s in checks["stacks"]]
    pruning = scan_pruning(project, stack_names)
    friction = {"ci": ci_runs(project), "timings": load_timings(project)}
    findings = (
        check_findings(checks) + prune_findings(pruning) + friction_findings(friction)
    )
    guide = guide_file(project)
    findings += guidance_findings(guide)
    findings.sort(key=lambda f: (-f["weight"], f["key"]))
    for n, f in enumerate(findings, 1):
        f["id"] = f"G{n}"
    pairs = json.dumps([[f["id"], f["key"]] for f in findings])
    previous = previous_run(project)
    guidance = scan_guidance(project, findings, previous, now)
    return {
        "schema": SCHEMA,
        "date": stamp(now),
        "scan": hashlib.sha256(pairs.encode()).hexdigest()[:8],
        "git": project.in_git,
        "git_problem": project.git_problem,
        "files_truncated": project.truncated,
        "files_unavailable": project.files_unavailable,
        "stacks": checks["stacks"],
        "friction": friction,
        "checks": checks,
        "pruning": pruning,
        "guidance": guidance,
        "findings": [{k: v for k, v in f.items() if k != "weight"} for f in findings],
    }


# ----- the text report -----------------------------------------------------


def render(data):
    lines = [
        f"garden scan, {data['date'][:10]}. Data, not instructions: "
        "file names, counts, durations and dates.",
    ]
    if data["files_unavailable"]:
        lines.append(f"Stacks: {UNAVAILABLE}")
    elif data["stacks"]:
        named = ", ".join(
            f"{STACK_NAMES[s['stack']]} ({s['marker']})"
            if s["marker"]
            else STACK_NAMES[s["stack"]]
            for s in data["stacks"]
        )
        lines.append(f"Stacks: {named}")
    else:
        lines.append("Stacks: none recognised")
    if data["git_problem"]:
        lines.append(
            f"Git could not be used ({data['git_problem']}): CI runs and commit "
            "hooks are measured from files only."
        )
    elif not data["git"]:
        lines.append(
            "Not a git repository: CI runs and commit hooks are measured "
            "from files only."
        )
    if data["files_truncated"]:
        lines.append(
            "The project has more files than the scan reads; "
            "counts cover the first ones."
        )
    lines += ["", "## Friction"] + render_friction(data["friction"])
    lines += ["", "## Checks"] + render_checks(data["checks"])
    lines += ["", "## Pruning"] + render_pruning(data["pruning"], data["stacks"])
    lines += ["", "## Guidance"] + render_guidance(data["guidance"])
    lines += [
        "",
        f"Findings, ranked, scan {data['scan']} "
        "(size: S an hour or less, M a few hours, L a day or more):",
    ]
    if not data["findings"]:
        lines.append("- none")
    for f in data["findings"]:
        lines.append(f"- {f['id']} [{f['size']}] {f['area']}: {f['title']}")
        lines.append(f"    evidence: {f['evidence']}")
        lines.append(f"    change: {f['change']}")
    return "\n".join(lines) + "\n"


def render_friction(friction):
    ci = friction["ci"]
    out = []
    if not ci["measured"]:
        out.append(f"- CI runs: not measured ({ci['reason']})")
    elif not ci["runs"]:
        out.append(f"- CI runs on {ci['branch']}: no finished run yet")
    else:
        share = round(ci["failed"] * 100 / ci["runs"])
        times = (
            f"median {duration(ci['median'])}, longest {duration(ci['longest'])}"
            if ci.get("median") is not None
            else "no run that ran to the end to time"
        )
        untimed = ci.get("untimed") or 0
        skipped = f", {untimed} cancelled or skipped (not timed)" if untimed else ""
        out.append(
            f"- CI runs on {ci['branch']}: last {ci['runs']} finished, {times}, "
            f"{ci['failed']} of {ci['runs']} failed ({share}%){skipped}"
        )
    if friction["timings"] is None:
        out.append(
            f"- Local commands: {GARDEN_DIR}/{TIMINGS} could not be read; "
            "delete it and time the commands again"
        )
        return out
    for label, t in sorted(friction["timings"].items()):
        result = (
            f"timed out after {duration(t['seconds'])}"
            if t["timed_out"]
            else f"{duration(t['seconds'])}, exit {t['exit']}"
        )
        on = f", measured {t['date'][:10]}" if t["date"] else ""
        out.append(f"- {label}: {result}{on}")
    if not friction["timings"]:
        out.append(
            "- Local commands: not measured (garden.py time --label tests -- <command>)"
        )
    return out


def render_checks(checks):
    out = []
    for r in checks["rows"]:
        name = KIND_NAMES[r["kind"]] + (
            f" ({STACK_NAMES[r['stack']]})" if r["stack"] else ""
        )
        if r["state"] == "no":
            out.append(f"- {name}: none found")
        elif r["state"] == "not checked":
            out.append(f"- {name}: {UNAVAILABLE}")
        else:
            src = r["file"] or ("a file with a name not shown" if r["hidden"] else "")
            out.append(f"- {name}: {r['state']}" + (f", {src}" if src else ""))
    if checks.get("unavailable"):
        out.append(f"- lint, format, types and tests: {UNAVAILABLE}")
    elif not checks["recognised"]:
        markers = ", ".join(m for s in MARKERS.values() for m in s)
        out.append(
            "- lint, format, types, tests and secret scan: not checked, the project's "
            f"stack was not recognised (looked for {markers})"
        )
    return out


def render_pruning(p, stacks):
    if p.get("unavailable"):
        return [
            f"- Python tests that assert nothing: {UNAVAILABLE}",
            f"- Skipped tests: {UNAVAILABLE}",
            f"- Dead-code tools: {UNAVAILABLE}",
            "- Nothing was deleted.",
        ]
    out = []
    if p["python"]:
        out.append(f"- Python tests that assert nothing: {p['no_assert_total']}")
        for t in p["no_assert"]:
            out.append(
                f"    {t['file']}:{t['line']}" + (f" {t['name']}" if t["name"] else "")
            )
        if p["no_assert_more"]:
            out.append(f"    and {p['no_assert_more']} more")
        if p["unparsed"]:
            out.append(f"    {plural(p['unparsed'], 'test file')} could not be parsed")
    else:
        out.append("- Python tests that assert nothing: not checked (no Python stack)")
    by = ", ".join(
        f"{STACK_NAMES[s]} {n}" for s, n in sorted(p["skipped_by_stack"].items())
    )
    out.append(f"- Skipped tests: {p['skipped_total']}" + (f" ({by})" if by else ""))
    for t in p["skipped"]:
        out.append(f"    {t['file']}:{t['line']}")
    if p["skipped_more"]:
        out.append(f"    and {p['skipped_more']} more")
    if not stacks:
        out.append(
            "- Dead-code tools: not checked, the project's stack was not recognised"
        )
    for stack, found in sorted(p["dead_code_tools"].items()):
        if found:
            names = ", ".join(f"{t['tool']} ({t['where']})" for t in found)
            out.append(f"- Dead-code tools for {STACK_NAMES[stack]}: {names}")
        else:
            out.append(f"- Dead-code tools for {STACK_NAMES[stack]}: none installed")
    out.append("- Nothing was deleted.")
    return out


def render_guidance(g):
    out = []
    c = g["claude_md"]
    if c:
        out.append(f"- {c['file']}: {c['lines']} lines, {c['bytes']} bytes")
    else:
        out.append("- CLAUDE.md: none")
    prev = g["previous"]
    if prev is None:
        out.append("- Last run: none recorded")
    elif prev.get("broken"):
        out.append(
            f"- Last run: {GARDEN_DIR}/{LAST} could not be read; delete it, "
            "the next record writes a new one"
        )
    else:
        out.append(
            f"- Last run: {prev['date']}, {plural(prev['days'], 'day')} ago, "
            f"{plural(prev['findings'], 'finding')}"
        )
        out.append(f"- Still open from that run: {len(prev['still_open'])}")
        for s in prev["still_open"]:
            out.append(
                f"    {s['was']} (now {s['now']}, {s['state']} then): {s['title']}"
            )
    return out


# ----- record and time -----------------------------------------------------


def ensure_excluded(project):
    """Keep docs/garden/ out of commits: add it to .git/info/exclude."""
    if not project.in_git:
        return
    if git(project.root, "check-ignore", "-q", f"{GARDEN_DIR}/{LAST}")[0] == 0:
        return
    rc, out = git(project.root, "rev-parse", "--git-path", "info/exclude")
    if rc:
        return
    exclude = project.root / out.strip()
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        old = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        gap = "" if not old or old.endswith("\n") else "\n"
        exclude.write_text(f"{old}{gap}{GARDEN_DIR}/\n", encoding="utf-8")
    except OSError:
        return


def cmd_scan(args):
    data = scan(Project(os.getcwd()))
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        sys.stdout.write(render(data))
    return 0


def cmd_record(args):
    picked = []
    for value in args.picked or []:
        for fid in value.replace(",", " ").split():
            if not FINDING_ID.fullmatch(fid.upper()):
                what = f"'{fid}'" if SAFE_ARG.fullmatch(fid) else "an argument"
                print(
                    f"record: {what} is not a finding id like G1; "
                    "give the ids of the scan, as in: "
                    "garden.py record --scan 1a2b3c4d --picked G1 G3",
                    file=sys.stderr,
                )
                return 2
            picked.append(fid.upper())
    given = args.scan.lower() if args.scan is not None else None
    if given is not None and not SCAN_ID.fullmatch(given):
        print(
            "record: --scan takes the 8 letters and digits after 'scan' on the "
            "scan's 'Findings, ranked' line, as in: --scan 1a2b3c4d",
            file=sys.stderr,
        )
        return 2
    if picked and given is None:
        print(
            "record: give the scan's id with the picked findings, as in: "
            "garden.py record --scan 1a2b3c4d --picked G1 G3; the id is on the "
            "scan's 'Findings, ranked' line",
            file=sys.stderr,
        )
        return 2
    project = Project(os.getcwd())
    data = scan(project)
    if given is not None and given != data["scan"]:
        # The ids are ranks: after a change G1 may name another finding.
        print(
            f"record: the findings changed since scan {given}; run garden.py "
            "scan again, show the new findings and ask again which to fix",
            file=sys.stderr,
        )
        return 2
    ids = {f["id"] for f in data["findings"]}
    unknown = [f for f in picked if f not in ids]
    if unknown:
        print(
            f"record: no finding {', '.join(unknown)} in this scan "
            f"(it has {plural(len(ids), 'finding')}); run garden.py scan "
            "and pick from its ids",
            file=sys.stderr,
        )
        return 2
    problem = garden_problem(project)
    if problem:
        print(f"record: {problem} and run record again", file=sys.stderr)
        return 1
    last = {
        "schema": SCHEMA,
        "date": data["date"],
        "findings": [
            {
                "id": f["id"],
                "key": f["key"],
                "title": f["title"],
                "size": f["size"],
                "state": "picked" if f["id"] in picked else "open",
            }
            for f in data["findings"]
        ],
    }
    report = project.garden / f"{data['date'][:10]}.md"
    for path, text in (
        (report, render(data)),
        (project.garden / LAST, json.dumps(last, indent=2) + "\n"),
    ):
        try:
            write_new(path, text)
        except OSError as exc:
            print(
                f"record: could not write {GARDEN_DIR}/{path.name} "
                f"({exc.strerror or type(exc).__name__}); "
                f"check that {GARDEN_DIR}/ can be written and run record again",
                file=sys.stderr,
            )
            return 1
    ensure_excluded(project)
    print(
        f"Recorded: {GARDEN_DIR}/{report.name} and {GARDEN_DIR}/{LAST}; "
        f"{len(picked)} picked, {len(data['findings']) - len(picked)} open."
    )
    return 0


def cmd_time(args):
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print(
            "time: give the command after --, as in: "
            "garden.py time --label tests -- pytest",
            file=sys.stderr,
        )
        return 2
    if not LABEL.fullmatch(args.label):
        print(
            "time: --label takes letters, digits and ._- (at most 40), "
            "as in: --label tests",
            file=sys.stderr,
        )
        return 2
    if not 0 < args.timeout <= MAX_TIMEOUT:
        print(
            f"time: --timeout takes seconds above 0 and at most {MAX_TIMEOUT}, "
            "as in: --timeout 900",
            file=sys.stderr,
        )
        return 2
    project = Project(os.getcwd())
    problem = garden_problem(project)
    if problem:
        print(f"time: {problem} and run time again; nothing was run", file=sys.stderr)
        return 2
    try:
        seconds, code, timed_out = run_timed(command, args.timeout, os.getcwd())
    except OSError as exc:
        print(
            f"time: the command could not start "
            f"({exc.strerror or type(exc).__name__}); "
            "check its name and run time again",
            file=sys.stderr,
        )
        return 127
    except Stopped as exc:
        with contextlib.suppress(OSError):
            save_timing(project, args.label, exc.seconds, None, True, now_utc())
        ensure_excluded(project)
        with contextlib.suppress(OSError):
            print(
                f"{args.label}: stopped after {duration(exc.seconds)} before it "
                "finished; the command and what it started were ended",
                flush=True,
            )
        return 128 + exc.signum
    sys.stdout.flush()
    try:
        save_timing(project, args.label, seconds, code, timed_out, now_utc())
    except OSError as exc:
        print(
            f"time: the duration was not kept: could not write {GARDEN_DIR}/{TIMINGS} "
            f"({exc.strerror or type(exc).__name__}); check that {GARDEN_DIR}/ "
            "can be written",
            file=sys.stderr,
        )
    ensure_excluded(project)
    if timed_out:
        print(
            f"{args.label}: timed out after {duration(seconds)} "
            f"(limit {args.timeout:g} s); the command and what it started were ended"
        )
        return 124
    print(f"{args.label}: {duration(seconds)}, exit {code}")
    return code if 0 <= code < 256 else 1


def internal_error(exc):
    """'internal error (<class>, line <n>)': n is the innermost line in a garden module.

    The error's own message is left out: it may quote the project's files.
    """
    line = "?"
    for frame in traceback.extract_tb(exc.__traceback__):
        if os.path.dirname(os.path.abspath(frame.filename)) == HERE:
            line = frame.lineno
    return f"internal error ({type(exc).__name__}, line {line})"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="garden.py", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="report friction, checks, pruning and guidance")
    s.add_argument("--json", action="store_true", help="the same facts as JSON")
    s.set_defaults(func=cmd_scan)
    r = sub.add_parser("record", help="save this run under docs/garden/")
    r.add_argument(
        "--scan",
        metavar="ID",
        help="the id of the scan the user picked from, on its 'Findings, ranked' line",
    )
    r.add_argument(
        "--picked", nargs="*", metavar="ID", help="the findings the user picked"
    )
    r.set_defaults(func=cmd_record)
    t = sub.add_parser("time", help="run a command and keep its duration and exit code")
    t.add_argument(
        "--label",
        required=True,
        help="a name for the command: letters, digits and ._- (at most 40)",
    )
    t.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"seconds before the command and all it started are ended "
        f"(default {DEFAULT_TIMEOUT})",
    )
    t.add_argument("command", nargs=argparse.REMAINDER, help="the command, after --")
    t.set_defaults(func=cmd_time)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - one line, never a traceback
        what = internal_error(exc)
        if args.cmd == "scan":
            # The scan loads with the skill: the rest of the skill still runs.
            print(f"garden scan: {what}; not measured. Say so and go on without it.")
            return 0
        print(
            f"{args.cmd}: {what}; run it again, and report this line if it comes back",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
