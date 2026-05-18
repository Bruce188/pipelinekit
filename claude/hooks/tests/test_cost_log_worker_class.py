#!/usr/bin/env python3
"""Tests for cost_log.py --worker-class extension.

Fixtures:
(a) start --worker-class codex -> event JSON contains "worker_class": "codex"
(b) start without --worker-class -> event JSON omits worker_class key entirely
(c) Two events (one with, one without worker_class); report does not crash
"""

import json
import os
import sys
import tempfile

# Locate cost_log module
_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HOOKS_DIR)

import cost_log  # noqa: E402


def _make_tmp_log() -> str:
    """Create a temp log file and set env vars for cost_log to use it."""
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="cost_log_wc_test_")
    os.close(fd)
    os.environ["CLAUDE_COST_LOG_PATH"] = path
    os.environ["CLAUDE_COST_LOG_SELFTEST"] = "1"
    return path


def _cleanup(path: str) -> None:
    os.environ.pop("CLAUDE_COST_LOG_PATH", None)
    os.environ.pop("CLAUDE_COST_LOG_SELFTEST", None)
    try:
        os.unlink(path)
    except OSError:
        pass


def test_fixture_a_worker_class_written():
    """Fixture (a): start --worker-class codex -> event contains worker_class."""
    tmp = _make_tmp_log()
    try:
        rc = cost_log.main(
            ["start", "feat/test", "analyze", "--worker-class", "codex"]
        )
        assert rc == 0, f"cost_log.main returned {rc}"
        with open(tmp) as f:
            events = [json.loads(ln) for ln in f if ln.strip()]
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.get("worker_class") == "codex", (
            f"Expected worker_class='codex', got {ev.get('worker_class')!r}"
        )
    finally:
        _cleanup(tmp)
    print("PASS fixture (a): start --worker-class codex -> worker_class in event")


def test_fixture_b_no_worker_class_omitted():
    """Fixture (b): start without --worker-class -> event omits worker_class key."""
    tmp = _make_tmp_log()
    try:
        rc = cost_log.main(["start", "feat/test", "analyze"])
        assert rc == 0, f"cost_log.main returned {rc}"
        with open(tmp) as f:
            events = [json.loads(ln) for ln in f if ln.strip()]
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert "worker_class" not in ev, (
            f"Expected worker_class to be absent, but found {ev.get('worker_class')!r}"
        )
    finally:
        _cleanup(tmp)
    print("PASS fixture (b): start without --worker-class -> worker_class absent")


def test_fixture_c_report_mixed():
    """Fixture (c): report handles events with and without worker_class."""
    tmp = _make_tmp_log()
    try:
        rc1 = cost_log.main(
            ["start", "feat/test", "analyze", "--worker-class", "codex"]
        )
        assert rc1 == 0, f"first write returned {rc1}"
        rc2 = cost_log.main(["start", "feat/test", "plan"])
        assert rc2 == 0, f"second write returned {rc2}"

        # report should not crash
        rc3 = cost_log.report("feat/test")
        assert rc3 == 0, f"report returned non-zero: {rc3}"
    finally:
        _cleanup(tmp)
    print("PASS fixture (c): report handles mixed worker_class events without crash")


def main():
    failures: list[str] = []
    tests = [
        test_fixture_a_worker_class_written,
        test_fixture_b_no_worker_class_omitted,
        test_fixture_c_report_mixed,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append(str(e))
        except Exception as e:
            failures.append(f"{t.__name__} ERROR: {e}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)

    print("\nAll 3 fixtures passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
