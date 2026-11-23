"""garden.py: CI friction from gh and the `time` command (criteria 4 and 5)."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest
from garden_testkit import HELPER, Sandbox, findings, section

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def run(seconds, conclusion="success", n=0):
    start = T0 + timedelta(hours=n)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return {
        "conclusion": conclusion,
        "createdAt": (start - timedelta(seconds=5)).strftime(fmt),
        "startedAt": start.strftime(fmt),
        "updatedAt": (start + timedelta(seconds=seconds)).strftime(fmt),
    }


@pytest.fixture
def sb(tmp_path):
    s = Sandbox(tmp_path)
    s.write("go.mod", "module x\n")
    s.git("remote", "add", "origin", "https://github.com/example/sample.git")
    return s


def ci(sb):
    return sb.scan_json()["friction"]["ci"]


def test_median_longest_and_failed_share_of_the_last_20_runs(sb):
    secs = [100] * 10 + [200] * 9 + [900]
    runs = [run(s, "failure" if i < 3 else "success", i) for i, s in enumerate(secs)]
    sb.gh(default="main", runs=runs)
    text = sb.scan()
    friction = section(text, "## Friction")
    assert (
        "- CI runs on main: last 20 finished, median 2 min 30 s, longest 15 min 0 s, "
        "3 of 20 failed (15%)"
    ) in friction
    calls = sb.gh_calls()
    listing = [c for c in calls if c[:2] == ["run", "list"]]
    assert len(listing) == 1
    args = listing[0]
    assert args[args.index("--branch") + 1] == "main"
    assert args[args.index("--limit") + 1] == "20"
    assert args[args.index("--status") + 1] == "completed"
    keys = {f["key"] for f in sb.scan_json()["findings"]}
    assert "friction.ci-slow" not in keys
    assert "friction.ci-failing" not in keys


def test_the_default_branch_comes_from_origin_head_first(sb):
    sb.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    sb.gh(default="main", runs=[run(60)])
    assert ci(sb)["branch"] == "trunk"
    assert not any(c[:2] == ["repo", "view"] for c in sb.gh_calls())


def test_cancelled_runs_are_counted_but_not_timed(sb):
    runs = [run(120, n=i) for i in range(4)] + [run(86400, "cancelled", 5)]
    sb.gh(default="main", runs=runs)
    data = ci(sb)
    assert data["runs"] == 5
    assert data["median"] == 120
    assert data["longest"] == 120
    assert data["untimed"] == 1
    assert "1 cancelled or skipped (not timed)" in section(sb.scan(), "## Friction")


def test_only_cancelled_runs(sb):
    sb.gh(default="main", runs=[run(50, "cancelled", i) for i in range(3)])
    assert "no run that ran to the end to time" in section(sb.scan(), "## Friction")


def test_slow_and_failing_ci_are_findings(sb):
    runs = [run(700, "failure" if i < 5 else "success", i) for i in range(20)]
    sb.gh(default="main", runs=runs)
    text = sb.scan()
    titles = [f[3] for f in findings(text)]
    assert "CI is slow" in titles
    assert "CI fails often on the default branch" in titles
    assert titles.index("CI fails often on the default branch") < titles.index(
        "CI is slow"
    )


def test_no_finished_run_yet(sb):
    sb.gh(default="main", runs=[])
    assert "- CI runs on main: no finished run yet" in sb.scan()


@pytest.mark.parametrize(
    "state, reason",
    [
        ({"default": "main", "runs_exit": 1}, "gh could not read the runs (exit 1)"),
        (
            {"default": "main", "runs_raw": "not json"},
            "gh gave an answer that is not a list of runs",
        ),
        (
            {"default": "main", "runs_raw": '{"a": 1}'},
            "gh gave an answer that is not a list of runs",
        ),
        ({"default": "bad branch;rm"}, "the default branch is not known"),
    ],
)
def test_when_gh_fails_the_scan_says_why_and_exits_0(sb, state, reason):
    sb.gh(**state)
    assert f"- CI runs: not measured ({reason})" in sb.scan()


def test_without_gh(sb):
    assert "- CI runs: not measured (gh is not installed)" in sb.scan()


def test_without_a_github_remote(sb):
    sb.git("remote", "set-url", "origin", "https://gitlab.example.com/x.git")
    sb.gh(default="main", runs=[run(60)])
    assert "- CI runs: not measured (no GitHub remote)" in sb.scan()
    assert sb.gh_calls() == []


def test_without_git_at_all(tmp_path):
    sb = Sandbox(tmp_path, git=False)
    sb.write("go.mod", "module x\n")
    (sb.bin / "git").unlink()
    text = sb.scan()
    assert "- CI runs: not measured (git is not installed)" in text
    assert "## Checks" in text


# ---------------------------------------------------------------- time


def test_time_keeps_the_duration_and_exit_code_not_the_output(sb):
    p = sb.garden(
        "time",
        "--label",
        "tests",
        "--",
        "python3",
        "-c",
        "import sys; print('OUTPUT-OF-THE-COMMAND'); sys.exit(3)",
    )
    assert p.returncode == 3
    assert "OUTPUT-OF-THE-COMMAND" in p.stdout
    assert p.stdout.splitlines()[-1].startswith("tests: ")
    assert p.stdout.splitlines()[-1].endswith(", exit 3")
    stored = (sb.root / "docs" / "garden" / "timings.json").read_text()
    assert "OUTPUT-OF-THE-COMMAND" not in stored
    assert "sys.exit" not in stored
    assert set(json.loads(stored)["tests"]) <= {"seconds", "exit", "timed_out", "date"}
    assert "docs" not in sb.status()
    text = sb.scan()
    line = [
        x
        for x in section(text, "## Friction").splitlines()
        if x.startswith("- tests: ")
    ]
    assert line and ", exit 3, measured " in line[0]
    assert "tests fails" in [f[3] for f in findings(text)]


def test_time_a_passing_command(sb):
    p = sb.garden("time", "--label", "build", "--", "python3", "-c", "pass")
    assert p.returncode == 0
    assert p.stdout.strip().endswith(", exit 0")
    assert "build" not in [f[3].split()[0] for f in findings(sb.scan())]


def test_time_ends_the_whole_process_tree_on_timeout(sb):
    pidfile = sb.tmp / "child.pid"
    script = (
        "import subprocess, sys, time\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(c.pid))\n"
        "time.sleep(120)\n"
    )
    start = time.monotonic()
    p = sb.garden(
        "time", "--label", "slow", "--timeout", "1", "--", "python3", "-c", script
    )
    took = time.monotonic() - start
    assert p.returncode == 124
    assert "timed out" in p.stdout
    assert took < 20
    child = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
            with open(f"/proc/{child}/stat") as f:
                stat = f.read()
            if stat.split(") ", 1)[1].startswith("Z"):
                break
        except (ProcessLookupError, FileNotFoundError):
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        pytest.fail("the child of the timed command is still running")
    stored = json.loads((sb.root / "docs" / "garden" / "timings.json").read_text())
    assert stored["slow"]["timed_out"] is True
    assert "slow did not finish" in [f[3] for f in findings(sb.scan())]


NEEDS_PROC = pytest.mark.skipif(
    not os.path.isdir("/proc"), reason="tells a zombie from a running process by /proc"
)


def gone_within(pid, seconds):
    """True once `pid` has ended (a zombie counts as ended)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            with open(f"/proc/{pid}/stat") as f:
                if f.read().split(") ", 1)[1].startswith("Z"):
                    return True
        except (ProcessLookupError, FileNotFoundError):
            return True
        time.sleep(0.1)
    return False


@NEEDS_PROC
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
def test_time_stopped_by_a_signal_ends_the_tree_and_keeps_the_run(sb, sig):
    pidfile = sb.tmp / "child.pid"
    script = (
        "import subprocess, sys, time\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(pidfile)!r} + '.tmp', 'w').write(str(c.pid))\n"
        f"__import__('os').rename({str(pidfile)!r} + '.tmp', {str(pidfile)!r})\n"
        "time.sleep(120)\n"
    )
    p = subprocess.Popen(
        [sys.executable, str(HELPER), "time", "--label", "suite", "--", "python3"]
        + ["-c", script],
        cwd=sb.root,
        env=sb.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child = int(pidfile.read_text())
        p.send_signal(sig)
        out, err = p.communicate(timeout=15)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 128 + sig, err
    assert out.splitlines()[-1].startswith("suite: stopped after ")
    assert out.splitlines()[-1].endswith(
        " before it finished; the command and what it started were ended"
    )
    if not gone_within(child, 5):
        os.kill(child, 9)
        pytest.fail("the child of the timed command is still running")
    stored = json.loads((sb.root / "docs" / "garden" / "timings.json").read_text())
    assert stored["suite"]["timed_out"] is True
    assert stored["suite"]["exit"] is None


def test_the_skill_gives_the_bash_call_a_timeout_above_the_commands():
    skill = (HELPER.parent / "SKILL.md").read_text(encoding="utf-8")
    assert "`--timeout 580` with a Bash timeout of 600000 ms" in skill
    assert "in the background" in skill


def test_time_default_timeout_is_600_seconds():
    assert "\nDEFAULT_TIMEOUT = 600\n" in HELPER.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "args",
    [
        ("time", "--label", "bad label", "--", "python3", "-c", "pass"),
        ("time", "--label", "x/../y", "--", "python3", "-c", "pass"),
        ("time", "--label", "tests"),
        ("time", "--label", "tests", "--"),
        ("time", "--label", "tests", "--timeout", "0", "--", "python3", "-c", "pass"),
        ("time", "--", "python3", "-c", "pass"),
    ],
)
def test_time_wrong_use_exits_2_and_runs_nothing(sb, args):
    p = sb.garden(*args)
    assert p.returncode == 2
    assert not (sb.root / "docs").exists()


def test_time_a_command_that_cannot_start(sb):
    p = sb.garden("time", "--label", "tests", "--", "/no/such/command")
    assert p.returncode == 127
    assert "could not start" in p.stderr


def test_a_label_with_dots_survives_a_record(sb):
    p = sb.garden(
        "time",
        "--label",
        "unit.fast.tests",
        "--",
        "python3",
        "-c",
        "raise SystemExit(1)",
    )
    assert p.returncode == 1
    assert sb.garden("record").returncode == 0
    guidance = section(sb.scan(), "## Guidance")
    assert "unit.fast.tests fails" in guidance


def test_broken_timings_are_ignored(sb):
    sb.write(
        "docs/garden/timings.json",
        json.dumps(
            {
                "tests": {"seconds": "x"},
                "ok": {"seconds": 2, "exit": 0},
                "bad label": {"seconds": 1, "exit": 0},
            }
        ),
    )
    friction = section(sb.scan(), "## Friction")
    assert "- ok: 2.0 s, exit 0" in friction
    assert "tests" not in friction
    assert "bad label" not in friction


LABEL_MSG = (
    "time: --label takes letters, digits and ._- (at most 40), as in: --label tests\n"
)
COMMAND_MSG = (
    "time: give the command after --, as in: garden.py time --label tests -- pytest\n"
)
TIMEOUT_MSG = (
    "time: --timeout takes seconds above 0 and at most 86400, as in: --timeout 900\n"
)
RUN = ("--", "python3", "-c", "pass")


@pytest.mark.parametrize(
    "args, message",
    [
        (("--label", "bad label", *RUN), LABEL_MSG),
        (("--label", "x/../y", *RUN), LABEL_MSG),
        (("--label", "tests"), COMMAND_MSG),
        (("--label", "tests", "--"), COMMAND_MSG),
        (("--label", "tests", "--timeout", "0", *RUN), TIMEOUT_MSG),
        (("--label", "tests", "--timeout", "nan", *RUN), TIMEOUT_MSG),
        (("--label", "tests", "--timeout", "inf", *RUN), TIMEOUT_MSG),
        (("--label", "tests", "--timeout", "86401", *RUN), TIMEOUT_MSG),
    ],
)
def test_time_wrong_use_is_said_in_one_line(sb, args, message):
    p = sb.garden("time", *args)
    assert (p.returncode, p.stdout, p.stderr) == (2, "", message)


def test_time_a_command_that_cannot_start_is_said_in_one_line(sb):
    p = sb.garden("time", "--label", "tests", "--", "/no/such/command")
    assert p.stderr == (
        "time: the command could not start (No such file or directory); "
        "check its name and run time again\n"
    )


@pytest.mark.parametrize(
    "args, words",
    [
        (("scan",), ["the same facts as JSON"]),
        (("record",), ["the findings the user picked"]),
        (
            ("time",),
            [
                "a name for the command: letters, digits and ._- (at most 40)",
                "(default 600)",
                "the command, after --",
            ],
        ),
    ],
)
def test_every_option_has_help(sb, args, words):
    p = sb.garden(*args, "--help")
    assert p.returncode == 0
    text = " ".join(p.stdout.split())
    for w in words:
        assert w in text, w


@pytest.mark.parametrize("text", ["{", "[]", "x" * 10])
def test_an_unreadable_timings_file_is_said_and_replaced(sb, text):
    sb.write("docs/garden/timings.json", text)
    friction = section(sb.scan(), "## Friction")
    assert (
        "- Local commands: docs/garden/timings.json could not be read; "
        "delete it and time the commands again\n"
    ) in friction
    assert sb.garden("time", "--label", "t", *RUN).returncode == 0
    assert "- t: " in section(sb.scan(), "## Friction")


def test_a_timings_file_that_is_a_link_is_not_read(sb, tmp_path):
    outside = tmp_path / "t.json"
    outside.write_text(json.dumps({"ok": {"seconds": 2, "exit": 0}}))
    (sb.root / "docs" / "garden").mkdir(parents=True)
    (sb.root / "docs" / "garden" / "timings.json").symlink_to(outside)
    assert "timings.json could not be read" in section(sb.scan(), "## Friction")
    assert sb.garden("time", "--label", "t", *RUN).returncode == 0
    assert json.loads(outside.read_text()) == {"ok": {"seconds": 2, "exit": 0}}


@pytest.mark.parametrize("git", [True, False])
def test_record_and_time_work_where_git_is_missing(tmp_path, git):
    sb = Sandbox(tmp_path, git=git)
    (sb.bin / "git").unlink()
    p = sb.garden("time", "--label", "t", "--", "python3", "-c", "pass")
    assert (p.returncode, p.stderr) == (0, "")
    assert sb.garden("record").returncode == 0
    assert "- t: " in section(sb.scan(), "## Friction")
    assert (sb.root / "docs" / "garden" / "last.json").is_file()
