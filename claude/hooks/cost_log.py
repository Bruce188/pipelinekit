#!/usr/bin/env python3
"""Lightweight pipeline cost logger.

Claude Code's own cost tracker (cost-tracker.ts per NETMIND Part 4 §3)
is internal and not exposed to hooks or skills at the current API
surface. This helper is the manual fallback — the user's /pipeline
skill writes phase-boundary events and /cost-report reads them back.

Log location: ~/.claude/logs/cost-events.jsonl
               (override with CLAUDE_COST_LOG_PATH env var — used by --self-test)
Entry shape:
  {"feature": "...", "phase": "...", "event": "start"|"end",
   "ts": epoch, "input_tokens": N, "output_tokens": N,
   "cache_reads": N, "estimated_usd": F,
   "dispatch_mode": "inline"|"subagent"|"subprocess",
   "agent_id": "..." (optional — only when dispatch_mode=subagent or subprocess)}

Modes:
  start <feature> <phase> [--input N --output N --cache N --usd F
                           --dispatch-mode MODE --agent-id ID]
                              -- write a start event
  end <feature> <phase>       -- write an end event (same flags accepted)
  report [feature]            -- table: feature, phase, in, out, cache, USD
  report-current              -- read current feature from pipeline-state.md
  --self-test                 -- run inline self-test; prints OK on success

Backwards compatible: existing 2-arg invocations like
    cost_log.py start feat/foo pipeline
continue to work unchanged (dispatch_mode defaults to "inline").
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

LOG_DIR = os.path.expanduser("~/.claude/logs")
PIPELINE_STATE = "docs/pipeline-state.md"


def _log_path() -> str:
    """Resolve log path from env at call time (self-test sets the var).

    Hardening (review-v21 NB5): the parent-directory realpath MUST live
    under LOG_DIR. The self-test sets CLAUDE_COST_LOG_SELFTEST=1 to
    temporarily waive this allowlist check so its /tmp file path is
    accepted. We return the ORIGINAL path (not the realpath) so a
    subsequent ``os.open(..., O_NOFOLLOW)`` still sees any symlink at
    the final path component and can reject it.
    """
    raw = os.environ.get(
        "CLAUDE_COST_LOG_PATH", os.path.join(LOG_DIR, "cost-events.jsonl")
    )
    parent = os.path.dirname(raw) or "."
    # Resolve the parent directory only — don't dereference a symlink
    # at the final file path, so O_NOFOLLOW can still fire on open.
    parent_real = os.path.realpath(parent)
    if os.environ.get("CLAUDE_COST_LOG_SELFTEST") == "1":
        return raw
    log_dir_real = os.path.realpath(LOG_DIR)
    if not (
        parent_real == log_dir_real
        or parent_real.startswith(log_dir_real + os.sep)
    ):
        raise ValueError("CLAUDE_COST_LOG_PATH must resolve under LOG_DIR")
    return raw


def _ensure_log_dir(path: str) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass


def write_event(
    feature: str,
    phase: str,
    event: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_reads: int = 0,
    estimated_usd: float = 0.0,
    dispatch_mode: str = "inline",
    agent_id: str | None = None,
    worker_class: str | None = None,
) -> int:
    try:
        path = _log_path()
    except ValueError as exc:
        print(f"cost_log: {exc}", file=sys.stderr)
        return 2
    _ensure_log_dir(path)
    entry = {
        "feature": feature,
        "phase": phase,
        "event": event,
        "ts": int(time.time()),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_reads": cache_reads,
        "estimated_usd": round(estimated_usd, 4),
        "dispatch_mode": dispatch_mode,
    }
    if agent_id is not None:
        entry["agent_id"] = agent_id
    if worker_class is not None:
        entry["worker_class"] = worker_class
    try:
        # O_NOFOLLOW rejects symlinks at open time — review-v21 NB5.
        fd = os.open(
            path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"cost_log: {exc}", file=sys.stderr)
        return 2
    return 0


def read_events() -> list[dict]:
    try:
        path = _log_path()
    except ValueError:
        return []
    if not os.path.isfile(path):
        return []
    out: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def report(feature_filter: str | None = None) -> int:
    events = read_events()
    if feature_filter:
        events = [e for e in events if e.get("feature") == feature_filter]
    if not events:
        print("no cost events logged")
        return 0

    # Aggregate by (feature, phase). end events overwrite start events.
    agg: dict[tuple[str, str], dict] = {}
    for e in events:
        key = (e.get("feature", "?"), e.get("phase", "?"))
        if key not in agg:
            agg[key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_reads": 0,
                "estimated_usd": 0.0,
            }
        agg[key]["input_tokens"] += int(e.get("input_tokens") or 0)
        agg[key]["output_tokens"] += int(e.get("output_tokens") or 0)
        agg[key]["cache_reads"] += int(e.get("cache_reads") or 0)
        agg[key]["estimated_usd"] += float(e.get("estimated_usd") or 0.0)

    print(
        f"{'feature':30s}  {'phase':15s}  {'input':>10s}  {'output':>10s}  "
        f"{'cache':>10s}  {'usd':>8s}"
    )
    print("-" * 92)
    total_usd = 0.0
    for (feat, phase), v in sorted(agg.items()):
        total_usd += v["estimated_usd"]
        print(
            f"{feat[:30]:30s}  {phase[:15]:15s}  {v['input_tokens']:>10d}  "
            f"{v['output_tokens']:>10d}  {v['cache_reads']:>10d}  "
            f"${v['estimated_usd']:>7.4f}"
        )
    print("-" * 92)
    print(f"{'total':30s}  {'':15s}  {'':>10s}  {'':>10s}  {'':>10s}  ${total_usd:>7.4f}")
    return 0


def current_feature_from_state() -> str | None:
    if not os.path.isfile(PIPELINE_STATE):
        return None
    try:
        with open(PIPELINE_STATE) as f:
            text = f.read()
    except OSError:
        return None
    import re  # lazy import — hot-path latency (review-v21 NB7)
    m = re.search(r"^\*\*Name:\*\*\s*(.+)$", text, re.M)
    if m:
        return m.group(1).strip()
    return None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cost_log.py",
        add_help=False,
        description="Pipeline cost event logger.",
    )
    p.add_argument("--self-test", action="store_true", help="Run inline self-test.")
    p.add_argument("--help", "-h", action="store_true")
    sub = p.add_subparsers(dest="command")

    def add_event_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("feature")
        sp.add_argument("phase")
        sp.add_argument("--input", dest="input_tokens", type=int, default=0)
        sp.add_argument("--output", dest="output_tokens", type=int, default=0)
        sp.add_argument("--cache", dest="cache_reads", type=int, default=0)
        sp.add_argument("--usd", dest="estimated_usd", type=float, default=0.0)
        sp.add_argument(
            "--dispatch-mode",
            dest="dispatch_mode",
            choices=("inline", "subagent", "subprocess"),
            default="inline",
            help=(
                "Phase dispatch mode: "
                "inline \u2014 phase ran in the main pipeline context; "
                "subagent \u2014 phase ran via the Agent tool (use returned subagent ID as --agent-id); "
                "subprocess \u2014 phase ran in a child process (e.g. cost_log.py parse-json forwarding claude -p JSON output)."
            ),
        )
        sp.add_argument(
            "--agent-id",
            dest="agent_id",
            default=None,
            type=lambda s: s[:128] if s else None,
        )
        sp.add_argument(
            "--worker-class",
            dest="worker_class",
            default=None,
            help="Worker class that handled this phase (e.g. claude, codex). Omit to leave field absent.",
        )

    add_event_args(sub.add_parser("start", add_help=False))
    add_event_args(sub.add_parser("end", add_help=False))

    rp = sub.add_parser("report", add_help=False)
    rp.add_argument("feature", nargs="?", default=None)

    sub.add_parser("report-current", add_help=False)

    pj = sub.add_parser("parse-json", add_help=False)
    pj.add_argument("path", help="JSON file path, or '-' for stdin")
    pj.add_argument("feature")
    pj.add_argument("phase")
    pj.add_argument("--agent-id", dest="agent_id", default=None,
                    type=lambda s: s[:128] if s else None)

    return p


def _usage() -> None:
    print(
        "usage: cost_log.py <start|end|report|report-current|parse-json> [args...]\n"
        "       cost_log.py --self-test\n"
        "\n"
        "event args (start/end):\n"
        "  feature phase [--input N] [--output N] [--cache N] [--usd F]\n"
        "                [--dispatch-mode {inline,subagent,subprocess}]\n"
        "                [--agent-id ID]\n"
        "\n"
        "parse-json args:\n"
        "  <path|-> feature phase [--agent-id ID]\n"
        "  reads JSON from path (or stdin if '-'), extracts cost_usd / usage.input_tokens\n"
        "  / usage.output_tokens, writes an 'end' event with dispatch_mode=subprocess.\n"
        "\n"
        "--dispatch-mode values:\n"
        "  inline     -- phase ran in the main pipeline context\n"
        "  subagent   -- phase ran via the Agent tool (use returned subagent ID as --agent-id)\n"
        "  subprocess -- phase ran in a child process (e.g. claude -p --output-format json via parse-json)",
        file=sys.stderr,
    )


def _safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def parse_json_event(path: str, feature: str, phase: str, agent_id: str | None = None) -> int:
    """Read JSON from <path> ('-' for stdin), extract cost_usd + token usage, forward to write_event."""
    try:
        if path == "-":
            text = sys.stdin.read()
        else:
            with open(path, "r") as fh:
                text = fh.read()
    except OSError as e:
        print(f"parse-json: cannot read {path!r}: {e}", file=sys.stderr)
        return 2
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"parse-json: invalid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("parse-json: JSON root must be an object", file=sys.stderr)
        return 2
    cost = _safe_float(data.get("cost_usd"))
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    in_tok = _safe_int(usage.get("input_tokens"))
    out_tok = _safe_int(usage.get("output_tokens"))
    return write_event(
        feature, phase, "end",
        input_tokens=in_tok,
        output_tokens=out_tok,
        estimated_usd=cost,
        dispatch_mode="subprocess",
        agent_id=agent_id,
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        _usage()
        return 2

    # --self-test is a top-level flag (handle before subcommand dispatch)
    if argv[0] == "--self-test":
        return _self_test()

    if argv[0] in ("-h", "--help"):
        _usage()
        return 0

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse writes its own error; surface a consistent exit code.
        return int(e.code) if isinstance(e.code, int) else 2

    cmd = args.command
    if cmd in ("start", "end"):
        return write_event(
            args.feature,
            args.phase,
            cmd,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            cache_reads=args.cache_reads,
            estimated_usd=args.estimated_usd,
            dispatch_mode=args.dispatch_mode,
            agent_id=args.agent_id,
            worker_class=args.worker_class,
        )

    if cmd == "report":
        return report(args.feature)

    if cmd == "report-current":
        feat = current_feature_from_state()
        if not feat:
            print("no current feature in pipeline-state.md", file=sys.stderr)
            return 1
        return report(feat)

    if cmd == "parse-json":
        return parse_json_event(args.path, args.feature, args.phase, agent_id=args.agent_id)

    _usage()
    return 2


def _self_test() -> int:
    """Inline self-test. Exits 0 on success with 'OK', 1 on failure."""
    import tempfile  # lazy import — hot-path latency (review-v21 NB7)
    # Capture original env values so we can restore them — review-v21 NB6.
    _orig_log_path = os.environ.get("CLAUDE_COST_LOG_PATH")
    _orig_selftest = os.environ.get("CLAUDE_COST_LOG_SELFTEST")
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, prefix="cost_log_selftest_"
    )
    tmp_path = tmp.name
    tmp.close()
    os.environ["CLAUDE_COST_LOG_PATH"] = tmp_path
    # Permit the /tmp selftest path to bypass the LOG_DIR allowlist.
    os.environ["CLAUDE_COST_LOG_SELFTEST"] = "1"
    failures: list[str] = []
    try:
        # Case 1: start with no dispatch_mode → default "inline", no agent_id
        rc = main(["start", "feat/selftest", "phase-a"])
        if rc != 0:
            failures.append(f"case1: write_event returned {rc}")

        # Case 2: start with --dispatch-mode subagent --agent-id abc123
        rc = main(
            [
                "start",
                "feat/selftest",
                "phase-b",
                "--dispatch-mode",
                "subagent",
                "--agent-id",
                "abc123",
            ]
        )
        if rc != 0:
            failures.append(f"case2: write_event returned {rc}")

        # Case 3: legacy 2-arg form end
        rc = main(["end", "feat/selftest", "phase-a"])
        if rc != 0:
            failures.append(f"case3: write_event returned {rc}")

        # Case 4: subprocess dispatch_mode (added by F2 plan-v28 Task 1.2)
        rc = main([
            "start", "feat/selftest", "phase-d",
            "--dispatch-mode", "subprocess",
            "--agent-id", "pid12345",
        ])
        if rc != 0:
            failures.append(f"case4: write_event returned {rc}")

        # Read back and verify shapes
        with open(tmp_path) as f:
            lines = [json.loads(ln) for ln in f if ln.strip()]

        if len(lines) != 4:
            failures.append(f"expected 4 log lines, got {len(lines)}")
        else:
            e1, e2, e3, e4 = lines
            if e1.get("dispatch_mode") != "inline":
                failures.append(
                    f"case1: dispatch_mode={e1.get('dispatch_mode')!r}, expected 'inline'"
                )
            if "agent_id" in e1:
                failures.append(
                    f"case1: agent_id unexpectedly present: {e1.get('agent_id')!r}"
                )
            if e1.get("feature") != "feat/selftest" or e1.get("phase") != "phase-a":
                failures.append("case1: feature/phase fields missing or wrong")

            if e2.get("dispatch_mode") != "subagent":
                failures.append(
                    f"case2: dispatch_mode={e2.get('dispatch_mode')!r}, expected 'subagent'"
                )
            if e2.get("agent_id") != "abc123":
                failures.append(
                    f"case2: agent_id={e2.get('agent_id')!r}, expected 'abc123'"
                )

            if e3.get("dispatch_mode") != "inline":
                failures.append(
                    f"case3 (legacy): dispatch_mode={e3.get('dispatch_mode')!r}, expected 'inline'"
                )
            if e3.get("event") != "end":
                failures.append(f"case3: event={e3.get('event')!r}, expected 'end'")

            if e4.get("dispatch_mode") != "subprocess":
                failures.append(
                    f"case4: dispatch_mode={e4.get('dispatch_mode')!r}, expected 'subprocess'"
                )
            if e4.get("agent_id") != "pid12345":
                failures.append(
                    f"case4: agent_id={e4.get('agent_id')!r}, expected 'pid12345'"
                )
            if e4.get("feature") != "feat/selftest" or e4.get("phase") != "phase-d":
                failures.append("case4: feature/phase fields missing or wrong")
            # Preserved fields
            for e in lines:
                for key in ("feature", "phase", "event", "ts", "estimated_usd"):
                    if key not in e:
                        failures.append(f"missing legacy field {key!r}")
                        break
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        # Restore original env values instead of unconditionally popping — review-v21 NB6.
        if _orig_log_path is not None:
            os.environ["CLAUDE_COST_LOG_PATH"] = _orig_log_path
        else:
            os.environ.pop("CLAUDE_COST_LOG_PATH", None)
        if _orig_selftest is not None:
            os.environ["CLAUDE_COST_LOG_SELFTEST"] = _orig_selftest
        else:
            os.environ.pop("CLAUDE_COST_LOG_SELFTEST", None)

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
