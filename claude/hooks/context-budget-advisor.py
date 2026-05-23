#!/usr/bin/env python3
"""UserPromptSubmit hook: warn when session context approaches a soft cap.

Reads the session transcript jsonl, finds the most recent assistant `usage`
block, computes total context tokens as
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`, and
emits a markdown advisory via the hookSpecificOutput.additionalContext channel
when total exceeds the threshold.

Default soft cap: 200,000 tokens — independent of the model's actual context
window. Models with 1M windows still benefit from a reset around 200K because
attention quality and per-call cost both degrade as context grows.

Re-warns at +20K steps; resets when context drops by 50K (post-compact).
A per-session marker file under ~/.claude/.compact-advisor/ tracks the last
warn level.

Env knobs:
- PIPELINE_NO_CONTEXT_ADVISOR=1  -> skip silently
- PIPELINE_COMPACT_THRESHOLD_TOKENS=<int>  -> override the 200K default

Self-test: `python3 context-budget-advisor.py --selftest`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

THRESHOLD_DEFAULT = 200_000
WARN_STEP = 20_000
RESET_DROP = 50_000
MARKER_DIR = Path.home() / ".claude" / ".compact-advisor"


def latest_total_tokens(transcript_path: str) -> int:
    """Stream the jsonl; return the most recent non-zero usage total."""
    total = 0
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                msg = record.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                t = (
                    (usage.get("input_tokens") or 0)
                    + (usage.get("cache_creation_input_tokens") or 0)
                    + (usage.get("cache_read_input_tokens") or 0)
                )
                if t > 0:
                    total = t
    except Exception:
        return 0
    return total


def read_marker(marker: Path) -> int:
    try:
        return int(marker.read_text().strip())
    except Exception:
        return 0


def write_marker(marker: Path, value: int) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(value))
    except Exception:
        pass


def advise(current: int, threshold: int) -> str:
    pct = int(current / threshold * 100) if threshold else 0
    return (
        "## Context Budget Advisory\n\n"
        f"Session context is at **{current:,} tokens** "
        f"({pct}% of the {threshold:,}-token soft cap).\n\n"
        "Run `/compact` before your next major task, or `/handoff-create` "
        "if you need a fresh session. Even on models with a 1M context "
        "window, attention quality and per-call cost both degrade past "
        "200K — reset around here.\n"
    )


def main() -> int:
    if os.environ.get("PIPELINE_NO_CONTEXT_ADVISOR", "0") == "1":
        return 0

    raw = sys.stdin.read()
    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    transcript_path = envelope.get("transcript_path") or ""
    session_id = envelope.get("session_id") or "unknown"
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    try:
        threshold = int(
            os.environ.get("PIPELINE_COMPACT_THRESHOLD_TOKENS", THRESHOLD_DEFAULT)
        )
    except ValueError:
        threshold = THRESHOLD_DEFAULT
    if threshold <= 0:
        return 0

    current = latest_total_tokens(transcript_path)
    if current < threshold:
        return 0

    marker = MARKER_DIR / f"{session_id}.txt"
    last_warned = read_marker(marker)

    if last_warned >= threshold:
        if current < last_warned - RESET_DROP:
            try:
                marker.unlink()
            except Exception:
                pass
        elif current < last_warned + WARN_STEP:
            return 0

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": advise(current, threshold),
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.write("\n")
    write_marker(marker, current)
    return 0


def selftest() -> int:
    import tempfile

    passes = 0
    fails = 0

    def record(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passes, fails
        if ok:
            print(f"PASS: {name}")
            passes += 1
        else:
            print(f"FAIL: {name} -- {detail}")
            fails += 1

    def make_jsonl(tokens: int) -> str:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": 10,
                        "cache_creation_input_tokens": tokens - 10,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 50,
                    },
                },
            }
        )
        Path(path).write_text(line + "\n")
        return path

    def run(envelope: dict, env: dict | None = None) -> tuple[int, str]:
        import subprocess

        merged_env = os.environ.copy()
        merged_env.setdefault("HOME", str(Path.home()))
        for k, v in (env or {}).items():
            merged_env[k] = v
        proc = subprocess.run(
            [sys.executable, __file__],
            input=json.dumps(envelope),
            capture_output=True,
            text=True,
            env=merged_env,
        )
        return proc.returncode, proc.stdout

    test_marker_dir = Path(tempfile.mkdtemp())
    fake_home = test_marker_dir
    transcript = make_jsonl(150_000)
    envelope = {
        "session_id": "test-below",
        "transcript_path": transcript,
    }
    rc, out = run(envelope, env={"HOME": str(fake_home)})
    record("below_threshold_silent", rc == 0 and out.strip() == "")
    os.unlink(transcript)

    transcript = make_jsonl(210_000)
    envelope["session_id"] = "test-above"
    envelope["transcript_path"] = transcript
    rc, out = run(envelope, env={"HOME": str(fake_home)})
    parsed = None
    try:
        parsed = json.loads(out)
    except Exception:
        pass
    record(
        "above_threshold_emits_advisory",
        rc == 0
        and parsed is not None
        and "additionalContext" in parsed.get("hookSpecificOutput", {})
        and "200,000" in parsed["hookSpecificOutput"]["additionalContext"],
        detail=f"rc={rc} out={out[:120]!r}",
    )

    rc, out = run(envelope, env={"HOME": str(fake_home)})
    record(
        "second_call_below_step_silent",
        rc == 0 and out.strip() == "",
        detail=f"out={out[:120]!r}",
    )
    os.unlink(transcript)

    transcript = make_jsonl(231_000)
    envelope["transcript_path"] = transcript
    rc, out = run(envelope, env={"HOME": str(fake_home)})
    record(
        "above_step_re_emits",
        rc == 0 and out.strip() != "",
        detail=f"out={out[:120]!r}",
    )
    os.unlink(transcript)

    transcript = make_jsonl(60_000)
    envelope["transcript_path"] = transcript
    rc, out = run(envelope, env={"HOME": str(fake_home)})
    record(
        "post_compact_silent_below_threshold",
        rc == 0 and out.strip() == "",
    )
    os.unlink(transcript)

    transcript = make_jsonl(205_000)
    envelope["session_id"] = "test-optout"
    envelope["transcript_path"] = transcript
    rc, out = run(envelope, env={"HOME": str(fake_home), "PIPELINE_NO_CONTEXT_ADVISOR": "1"})
    record("opt_out_env_silent", rc == 0 and out.strip() == "")
    os.unlink(transcript)

    transcript = make_jsonl(110_000)
    envelope["session_id"] = "test-custom"
    envelope["transcript_path"] = transcript
    rc, out = run(
        envelope,
        env={"HOME": str(fake_home), "PIPELINE_COMPACT_THRESHOLD_TOKENS": "100000"},
    )
    record(
        "custom_threshold_via_env",
        rc == 0 and out.strip() != "" and "100,000" in out,
        detail=f"out={out[:120]!r}",
    )
    os.unlink(transcript)

    envelope = {"session_id": "test-missing", "transcript_path": "/nonexistent/x.jsonl"}
    rc, out = run(envelope, env={"HOME": str(fake_home)})
    record("missing_transcript_silent", rc == 0 and out.strip() == "")

    import shutil

    shutil.rmtree(test_marker_dir, ignore_errors=True)

    print(f"\nResults: {passes} PASS / {fails} FAIL")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(selftest())
    sys.exit(main())
