"""session-check.py: silent on a healthy install, one line when it is not."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
START = '{"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"}'
CRASH = "import sys\nprint('pipelinekit check failed: KeyError')\nsys.exit(2)\n"
SHOW_HOME = (
    "import json, os\n"
    "msg = 'home=' + os.environ.get('CLAUDE_HOME', 'unset')\n"
    "print(json.dumps({'results': [{'level': 'fail', 'msg': msg}]}))\n"
)


def checker(*results):
    """A stand-in for check.py that reports the given (level, msg) results."""
    items = [{"section": "install", "level": lv, "msg": msg} for lv, msg in results]
    return (
        "import json, sys\n"
        "assert sys.argv[1:] == ['--quick', '--json'], sys.argv\n"
        f"results = {items!r}\n"
        "fails = [r for r in results if r['level'] == 'fail']\n"
        "print(json.dumps({'healthy': not fails, 'results': results}))\n"
        "sys.exit(1 if fails else 0)\n"
    )


@pytest.fixture
def home(tmp_path):
    """A config directory holding the hook, its log helper and room for check.py."""
    root = tmp_path / "claude"
    (root / "hooks").mkdir(parents=True)
    (root / "skills" / "kit").mkdir(parents=True)
    for name in ("session-check.py", "kitlog.py"):
        shutil.copy(HOOKS / name, root / "hooks" / name)
    return root


def run(home, check=None, stdin=START, **extra):
    if check is not None:
        (home / "skills" / "kit" / "check.py").write_text(check)
    env = dict(os.environ, PIPELINEKIT_STATE_DIR=str(home.parent / "state"))
    for k in ("PIPELINEKIT_SESSION_CHECK", "PIPELINEKIT_LOG", "CLAUDE_HOME"):
        env.pop(k, None)
    env.update(extra)
    p = subprocess.run(
        [sys.executable, str(home / "hooks" / "session-check.py")],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode == 0 and p.stderr == "", p.stderr
    return p.stdout


def said(out):
    assert len(out.splitlines()) == 1, out
    data = json.loads(out)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    return data["systemMessage"], data["hookSpecificOutput"]["additionalContext"]


def logged(home):
    log = home.parent / "state" / "events.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_healthy_install_says_nothing(home):
    out = run(home, checker(("pass", "hook: bash-guard.py"), ("warn", "changed: x")))
    assert out == "" and logged(home) == []


def test_problems_give_one_line_that_names_kit(home):
    out = run(home, checker(("fail", "hook missing: a.py"), ("fail", "second")))
    message, context = said(out)
    assert message == (
        "pipelinekit: 2 problems in this install, first: hook missing: a.py. "
        "Run /kit for the report."
    )
    assert "2 problems" in context and "/kit" in context
    assert "a.py" not in context, "the note for Claude carries no text from the report"
    assert logged(home) == []


def test_one_problem(home):
    message, _ = said(run(home, checker(("warn", "w"), ("fail", "only one"))))
    assert message.startswith(
        "pipelinekit: 1 problem in this install, first: only one."
    )


def test_a_long_or_multi_line_finding_stays_one_short_line(home):
    message, _ = said(run(home, checker(("fail", "line one\nline two " + "x" * 900))))
    assert "line one line two" in message and "\n" not in message
    assert len(message) < 260 and "... Run /kit" in message


def test_missing_checker_points_at_the_installer(home):
    message, context = said(run(home))
    assert "could not run (skills/kit/check.py is missing)" in message
    assert "installer" in message and "Run /kit" not in message
    assert "unknown" in context
    (event,) = logged(home)
    assert (event["hook"], event["kind"], event["rule"]) == (
        "session-check",
        "error",
        "session-check.failed",
    )
    assert event["session"] == "s1"


def test_checker_that_fails_itself(home):
    message, _ = said(run(home, CRASH))
    assert "could not run (check.py gave no report, exit 2)" in message
    assert "Run /kit to see why." in message
    assert [e["rule"] for e in logged(home)] == ["session-check.failed"]


def test_slow_checker_is_dropped_without_a_word(home):
    hook = home / "hooks" / "session-check.py"
    text = hook.read_text()
    assert "TIMEOUT = 4 " in text
    hook.write_text(text.replace("TIMEOUT = 4 ", "TIMEOUT = 0.3 "))
    assert run(home, "import time\ntime.sleep(30)\n") == ""
    (event,) = logged(home)
    assert (event["kind"], event["rule"]) == ("error", "session-check.timeout")


def test_switched_off(home):
    check = checker(("fail", "broken"))
    assert run(home, check, PIPELINEKIT_SESSION_CHECK="0") == ""
    assert run(home, check, PIPELINEKIT_SESSION_CHECK="1") != ""


def test_checks_the_install_it_sits_in(home):
    assert "home=unset." in said(run(home, SHOW_HOME))[0]
    (home / "settings.json").write_text("{}")
    assert f"home={home}." in said(run(home, SHOW_HOME))[0]
    assert "home=/elsewhere." in said(run(home, SHOW_HOME, CLAUDE_HOME="/elsewhere"))[0]


@pytest.mark.parametrize("stdin", ["", "not json", "[1, 2]"])
def test_odd_input_does_not_matter(home, stdin):
    assert run(home, checker(("pass", "ok")), stdin=stdin) == ""
    assert said(run(home, checker(("fail", "broken")), stdin=stdin))


def test_works_without_the_log_helper(home):
    (home / "hooks" / "kitlog.py").unlink()
    assert "could not run" in said(run(home))[0]


def test_leaves_nothing_beside_the_hooks(home):
    run(home)
    run(home, checker(("fail", "broken")))
    names = sorted(f.name for f in (home / "hooks").iterdir())
    assert names == ["kitlog.py", "session-check.py"]
