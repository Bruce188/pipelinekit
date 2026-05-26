#!/usr/bin/env python3
"""Migrate flat-file memory to agentmemory MCP.

Walks `--memory-root` (default: ~/.claude/projects) looking for *.md files
under <root>/**/memory/*.md or directly under <root>/*.md (fixture-style flat
layouts) and emits a `_payload_kind: memory_save` JSON payload on stdout for
each file the harness should ingest into agentmemory.

Contracts (binding):
  - Default mode is --dry-run. Destructive --apply requires explicit opt-in.
  - --dry-run and --apply together is a usage error (exit 2).
  - Dedup by SHA-256 body hash (frontmatter excluded from hash). Log-before-emit
    ordering: the log entry is written BEFORE stdout payload is emitted (Q6).
  - Idempotent: second --apply on the same root skips already-logged body hashes
    with status `skipped-duplicate`.
  - Routing marker: `_payload_kind: memory_save` on every emitted payload line.
    A harness learning to route MCP RPCs can grep this key and dispatch to the
    agentmemory MCP. Current harnesses without that routing see harmless output.
  - PR #117 lesson: no subprocess spawn beyond stdlib. No claude -p. No curl.
    No wget. No agentmemory CLI invocation.

CLI usage:
  # Dry-run (default — safe, no writes):
  python3 scripts/migrate_flatfile_memory_to_agentmemory.py \\
      --memory-root scripts/fixtures/memory-flatfile-sample/

  # Apply (writes .migration.log + emits payload to stdout):
  python3 scripts/migrate_flatfile_memory_to_agentmemory.py --apply \\
      --memory-root scripts/fixtures/memory-flatfile-sample/

Exit codes:
  0 — success (dry-run or apply completed)
  2 — usage error (bad flags or missing/invalid --memory-root)
"""

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys


# ─── Section C — Frontmatter parser ──────────────────────────────────────────

def parse_frontmatter(text: str):
    """Parse YAML-style frontmatter from a markdown file.

    Returns (metadata_dict, body_text).
    Handles two indent levels: top-level keys at indent 0, nested keys under
    the most-recent top-level key at indent 2 (covers the `metadata:` nesting
    in the live memory-file shape).
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text

    meta: dict = {}
    current_top_key: str | None = None
    i = 1
    closed = False

    while i < len(lines):
        raw = lines[i]
        stripped = raw.rstrip("\r\n")

        if stripped == "---":
            i += 1
            closed = True
            break

        # Indent-2 nested key (e.g. "  type: feedback")
        m2 = re.match(r"^  ([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)", stripped)
        if m2 and current_top_key is not None:
            key, val = m2.group(1), m2.group(2)
            val = _strip_quotes(val)
            if current_top_key not in meta or not isinstance(meta[current_top_key], dict):
                meta[current_top_key] = {}
            meta[current_top_key][key] = val
            i += 1
            continue

        # Indent-0 top-level key (e.g. "name: feedback-subagent-first")
        m0 = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)", stripped)
        if m0:
            key, val = m0.group(1), m0.group(2)
            val = _strip_quotes(val)
            # If value is empty, this is the start of a mapping block (e.g. "metadata:")
            if val == "":
                meta[key] = {}
                current_top_key = key
            else:
                meta[key] = val
                current_top_key = key
            i += 1
            continue

        i += 1

    if not closed:
        return {}, text

    # Body is everything after the closing ---
    body_lines = lines[i:]
    # Consume one optional leading blank line
    if body_lines and body_lines[0].strip() == "":
        body_lines = body_lines[1:]
    body = "".join(body_lines)
    return meta, body


def _strip_quotes(val: str) -> str:
    """Strip surrounding double-quotes if the entire value is a single quoted span."""
    if val.startswith('"') and val.endswith('"') and len(val) >= 2:
        inner = val[1:-1]
        # Only strip if no unescaped quotes remain inside (simple check)
        # Replace escaped \" with placeholder, check no remaining "
        if '"' not in inner.replace('\\"', ''):
            return inner.replace('\\"', '"')
    return val


# ─── Section D — Taxonomy mapping ────────────────────────────────────────────

def map_taxonomy(metadata: dict, name_field: str, memory_root: pathlib.Path):
    """Map legacy pipelinekit memory taxonomy to agentmemory tags + category.

    Returns (tags: list[str], category: str).

    Table (analysis § Frontmatter Shape line 102-110):
      user      → tags=[profile],           category=user
      feedback  → tags=[feedback, <tokens>], category=feedback
      project   → tags=[project, <slug>],    category=project
      reference → tags=[reference],          category=reference
      unknown   → tags=[<raw type>],          category=other
    """
    nested_meta = metadata.get("metadata", {})
    if isinstance(nested_meta, dict):
        mem_type = nested_meta.get("type", "")
    else:
        mem_type = ""

    if not mem_type:
        mem_type = metadata.get("type", "unknown")

    if mem_type == "user":
        return ["profile"], "user"

    elif mem_type == "feedback":
        tags = ["feedback"]
        # Derive additional tokens from name_field: strip leading "feedback-" prefix
        if name_field:
            remainder = re.sub(r"^feedback-", "", name_field)
            if remainder and remainder != name_field:
                # Emit the remainder as one token (e.g. "subagent-first")
                tags.append(remainder)
            elif remainder:
                tags.append(remainder)
        return tags, "feedback"

    elif mem_type == "project":
        slug = memory_root.name
        return ["project", slug], "project"

    elif mem_type == "reference":
        return ["reference"], "reference"

    else:
        return [str(mem_type) if mem_type else "unknown"], "other"


# ─── Section E — Hash function ────────────────────────────────────────────────

def body_hash(body: str) -> str:
    """SHA-256 of body text (frontmatter excluded by caller)."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ─── Section F — Log reader ───────────────────────────────────────────────────

def read_log(log_path: pathlib.Path) -> set:
    """Return the set of body hashes already present in .migration.log.

    Tolerates absent file (returns empty set). Skips malformed lines.
    """
    if not log_path.exists():
        return set()
    seen = set()
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 4:
                seen.add(fields[1])  # field index 1 = sha256
    except Exception:
        pass
    return seen


# ─── Section G — Log writer ───────────────────────────────────────────────────

def append_log(log_path: pathlib.Path, body_sha: str, source: str, status: str) -> None:
    """Append one line to .migration.log.

    Line shape (4 tab-separated fields):
      <ISO8601 UTC>\\t<sha256(body)>\\t<source-path>\\t<status>

    Log-before-emit ordering: callers MUST invoke this BEFORE printing stdout payload.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # Fallback for older Python builds
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}\t{body_sha}\t{source}\t{status}\n"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line)


# ─── Section H — Payload builder ─────────────────────────────────────────────

def build_payload(tags, category: str, content: str, body_sha: str, source: str) -> dict:
    """Build the memory_save routing payload dict."""
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "_payload_kind": "memory_save",
        "tags": list(tags),
        "category": category,
        "content": content,
        "body_sha": body_sha,
        "source": source,
        "ts": ts,
    }


# ─── Section I — Walker ───────────────────────────────────────────────────────

def iter_memory_files(memory_root: pathlib.Path):
    """Yield each *.md file to migrate.

    Tries two walk patterns:
      1. <memory_root>/**/memory/*.md  (standard per-project layout)
      2. <memory_root>/*.md            (fixture-style flat layout)

    Skips MEMORY.md (deprecated index — constraint #9).
    Yields in deterministic sorted order.
    """
    found = []

    # Pattern 1: nested memory/ subdirs
    for md in memory_root.rglob("memory/*.md"):
        if md.name == "MEMORY.md":
            continue
        found.append(md)

    # Pattern 2: flat *.md directly in memory_root (fixture-style)
    if not found:
        for md in sorted(memory_root.glob("*.md")):
            if md.name == "MEMORY.md":
                continue
            found.append(md)

    yield from sorted(set(found))


# ─── Section J — Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Migrate flat-file memory to agentmemory MCP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Preview migration without writing anything (default).",
    )
    parser.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        default=False,
        help="Write .migration.log and emit payloads to stdout.",
    )
    parser.add_argument(
        "--memory-root",
        dest="memory_root",
        default="~/.claude/projects",
        help="Root directory to scan. Default: ~/.claude/projects",
    )
    args = parser.parse_args()

    # Validate: both --dry-run and --apply → exit 2
    if args.apply and args.dry_run and not (len(sys.argv) > 1 and "--apply" in sys.argv):
        # dry_run defaults to True; only error when BOTH are explicit
        pass
    if args.apply:
        # When --apply is given, override the default dry_run=True
        args.dry_run = False
    # If neither --apply nor explicit --dry-run, dry_run=True (default is fine)

    # Detect if BOTH were explicitly passed
    explicit_dry = "--dry-run" in sys.argv
    explicit_apply = "--apply" in sys.argv
    if explicit_dry and explicit_apply:
        print("error: --dry-run and --apply are mutually exclusive", file=sys.stderr)
        sys.exit(2)

    memory_root = pathlib.Path(args.memory_root).expanduser()
    if not memory_root.exists() or not memory_root.is_dir():
        print(f"error: --memory-root does not exist or is not a directory: {memory_root}",
              file=sys.stderr)
        sys.exit(2)

    processed = 0
    for file_path in iter_memory_files(memory_root):
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"warning: cannot read {file_path}: {e}", file=sys.stderr)
            continue

        meta, body = parse_frontmatter(text)
        bsha = body_hash(body)

        # Derive log path
        # If file is directly in memory_root (fixture-style flat):
        if file_path.parent == memory_root:
            log_path = memory_root / ".migration.log"
        else:
            # Standard layout: log next to the .md file in its memory/ dir
            log_path = file_path.parent / ".migration.log"

        seen_hashes = read_log(log_path)

        name_field = meta.get("name", "")
        tags, category = map_taxonomy(meta, name_field, memory_root)

        if args.apply:
            if bsha in seen_hashes:
                # Already applied — log skipped-duplicate, no stdout payload
                append_log(log_path, bsha, str(file_path), "skipped-duplicate")
            else:
                # Log-before-emit (Q6)
                append_log(log_path, bsha, str(file_path), "applied")
                payload = build_payload(tags, category, body, bsha, str(file_path))
                print(json.dumps(payload))
        else:
            # Dry-run path
            print(f"dry-run: would save {file_path} tags={tags} category={category}")

        processed += 1

    if args.apply:
        print(f"{processed} file(s) processed", file=sys.stderr)
    else:
        print(f"dry-run: {processed} file(s) would be saved", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
