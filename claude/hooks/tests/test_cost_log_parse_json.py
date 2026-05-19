#!/usr/bin/env python3
"""Tests for cost_log.py parse-json subcommand.

Fixtures:
(a) parse-json from stdin writes correct event with all cost/usage fields
(b) parse-json from file path writes correct event (no --agent-id path)
(c) missing optional fields (cost_usd, usage) default to 0 — no crash
(d) malformed JSON returns non-zero exit code and writes nothing to log
"""

import contextlib
import io
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
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="cost_log_pj_test_")
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


def test_fixture_a_parse_json_from_stdin_writes_event():
    """Fixture (a): parse-json from stdin writes correct event."""
    tmp = _make_tmp_log()
    json_text = '{"cost_usd": 0.05, "usage": {"input_tokens": 100, "output_tokens": 50}, "result": "ok"}'
    _orig_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(json_text)
        rc = cost_log.main(["parse-json", "-", "research/test", "iter-1", "--agent-id", "agent-x"])
        assert rc == 0, f"cost_log.main returned {rc}"
        with open(tmp) as f:
            events = [json.loads(ln) for ln in f if ln.strip()]
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.get("event") == "end", f"Expected event='end', got {ev.get('event')!r}"
        assert ev.get("feature") == "research/test", f"feature mismatch: {ev.get('feature')!r}"
        assert ev.get("phase") == "iter-1", f"phase mismatch: {ev.get('phase')!r}"
        assert ev.get("estimated_usd") == 0.05, f"estimated_usd mismatch: {ev.get('estimated_usd')!r}"
        assert ev.get("input_tokens") == 100, f"input_tokens mismatch: {ev.get('input_tokens')!r}"
        assert ev.get("output_tokens") == 50, f"output_tokens mismatch: {ev.get('output_tokens')!r}"
        assert ev.get("dispatch_mode") == "subprocess", f"dispatch_mode mismatch: {ev.get('dispatch_mode')!r}"
        assert ev.get("agent_id") == "agent-x", f"agent_id mismatch: {ev.get('agent_id')!r}"
    finally:
        sys.stdin = _orig_stdin
        _cleanup(tmp)
    print("PASS fixture (a): parse-json from stdin writes correct event")


def test_fixture_b_parse_json_from_file_path_writes_event():
    """Fixture (b): parse-json from file path writes correct event (no --agent-id)."""
    tmp = _make_tmp_log()
    json_text = '{"cost_usd": 0.05, "usage": {"input_tokens": 100, "output_tokens": 50}, "result": "ok"}'
    json_file = None
    try:
        tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
        tf.write(json_text)
        tf.flush()
        tf.close()
        json_file = tf.name
        rc = cost_log.main(["parse-json", json_file, "research/test", "iter-2"])
        assert rc == 0, f"cost_log.main returned {rc}"
        with open(tmp) as f:
            events = [json.loads(ln) for ln in f if ln.strip()]
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.get("estimated_usd") == 0.05, f"estimated_usd mismatch: {ev.get('estimated_usd')!r}"
        assert ev.get("input_tokens") == 100, f"input_tokens mismatch: {ev.get('input_tokens')!r}"
        assert ev.get("output_tokens") == 50, f"output_tokens mismatch: {ev.get('output_tokens')!r}"
        assert ev.get("dispatch_mode") == "subprocess", f"dispatch_mode mismatch: {ev.get('dispatch_mode')!r}"
        # agent_id should be absent or None when not supplied
        assert "agent_id" not in ev or ev["agent_id"] is None, (
            f"Expected agent_id absent or None, got {ev.get('agent_id')!r}"
        )
    finally:
        if json_file:
            try:
                os.unlink(json_file)
            except OSError:
                pass
        _cleanup(tmp)
    print("PASS fixture (b): parse-json from file path writes correct event")


def test_fixture_c_parse_json_missing_optional_fields_defaults_to_zero():
    """Fixture (c): missing cost_usd and usage default to 0 — no crash."""
    tmp = _make_tmp_log()
    json_text = '{"result": "no cost"}'
    _orig_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(json_text)
        rc = cost_log.main(["parse-json", "-", "research/test", "iter-3"])
        assert rc == 0, f"cost_log.main returned {rc}"
        with open(tmp) as f:
            events = [json.loads(ln) for ln in f if ln.strip()]
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.get("estimated_usd") == 0.0, f"estimated_usd mismatch: {ev.get('estimated_usd')!r}"
        assert ev.get("input_tokens") == 0, f"input_tokens mismatch: {ev.get('input_tokens')!r}"
        assert ev.get("output_tokens") == 0, f"output_tokens mismatch: {ev.get('output_tokens')!r}"
    finally:
        sys.stdin = _orig_stdin
        _cleanup(tmp)
    print("PASS fixture (c): missing optional fields default to 0")


def test_fixture_d_parse_json_malformed_returns_nonzero():
    """Fixture (d): malformed JSON returns non-zero, writes nothing to log."""
    tmp = _make_tmp_log()
    json_text = "this is not json"
    _orig_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(json_text)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cost_log.main(["parse-json", "-", "research/test", "iter-4"])
        assert rc != 0, f"Expected non-zero exit, got {rc}"
        assert rc == 2, f"Expected rc==2 per _usage() convention, got {rc}"
        # No event should be written
        with open(tmp) as f:
            content = f.read().strip()
        assert content == "", f"Expected empty log, got: {content!r}"
    finally:
        sys.stdin = _orig_stdin
        _cleanup(tmp)
    print("PASS fixture (d): malformed JSON returns non-zero and writes nothing")


def main():
    failures: list[str] = []
    tests = [
        test_fixture_a_parse_json_from_stdin_writes_event,
        test_fixture_b_parse_json_from_file_path_writes_event,
        test_fixture_c_parse_json_missing_optional_fields_defaults_to_zero,
        test_fixture_d_parse_json_malformed_returns_nonzero,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append(f"{t.__name__}: {e}")
        except Exception as e:
            failures.append(f"{t.__name__} ERROR: {e}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)

    print("\nAll 4 fixtures passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
