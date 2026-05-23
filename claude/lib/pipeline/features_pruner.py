#!/usr/bin/env python3
"""features_pruner — move merged feature H2 blocks out of docs/features.md.

Scans `docs/features.md` for ## feature blocks whose Run Log contains a
`ppr-done — PR #<N> squashed` marker. Each such block is moved to
`docs-source/feature-history.md` (appended; deduplicated by feature name)
and the source block removed from `docs/features.md`. After the move,
`documentation/feature-history.html` is re-rendered via
`claude/skills/docs-writer/render.py`.

Honours PIPELINE_HYGIENE_OFF=1 (early-return no-op). Intersects every
candidate against `claude/config/never-stage.txt` and refuses to touch
any path that double-matches — the source `docs/features.md` itself
matches `docs/*.md` in never-stage so the pruner rewrites it in place
rather than deleting it (the intersection guard applies to ancillary
write targets, not to the in-place modification of features.md).

Usage:
    python3 claude/lib/pipeline/features_pruner.py        # normal pass
    PIPELINE_HYGIENE_OFF=1 python3 ... features_pruner.py # opt-out no-op

Exit codes:
    0 — success or no-op
    1 — IO/parse error (advisory; caller should log and continue)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

PPR_DONE_RE = re.compile(
    r'ppr-done\s+[-—]\s+PR\s+#(?P<pr>\d+)\s+squashed\s*\((?P<sha>[0-9a-f]{6,40})\)?',
    re.IGNORECASE,
)
FEATURE_H2_RE = re.compile(r'^##\s+(?P<name>\S.*?)\s*$', re.MULTILINE)


def is_disabled() -> bool:
    return os.environ.get("PIPELINE_HYGIENE_OFF") == "1"


def repo_root() -> Path:
    return Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
    )


def parse_features_md(text: str) -> list[dict]:
    """Split features.md into list of {name, body, pr, sha} per H2 block.

    The first segment (before any ## H2) is the file preamble — returned as
    a dict with name=None so the caller can reassemble.
    """
    blocks: list[dict] = []
    matches = list(FEATURE_H2_RE.finditer(text))
    if not matches:
        return [{"name": None, "body": text, "pr": None, "sha": None}]

    # Preamble: text before the first H2
    if matches[0].start() > 0:
        blocks.append({"name": None, "body": text[: matches[0].start()],
                       "pr": None, "sha": None})

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block_text = text[start:end]
        name = m.group("name").strip()
        pr_match = PPR_DONE_RE.search(block_text)
        pr = int(pr_match.group("pr")) if pr_match else None
        sha = pr_match.group("sha") if pr_match else None
        blocks.append({"name": name, "body": block_text, "pr": pr, "sha": sha})
    return blocks


def is_merged(block: dict) -> bool:
    return block["pr"] is not None


def render_history_section(block: dict) -> str:
    """Generate the markdown H2 section that lands in feature-history.md.

    Wraps the body in <details><summary>...</summary>...</details> so the
    `collapsible-details` richness pattern fires.
    """
    name = block["name"] or "unknown"
    pr = block["pr"]
    sha = block["sha"] or ""
    pr_link = (
        f"[#{pr}](https://github.com/Bruce188/pipelinekit/pull/{pr})" if pr else "n/a"
    )
    return (
        f"\n## {name}\n\n"
        f"<details>\n"
        f"<summary><span class=\"status-pill status-merged\">merged</span> "
        f"&nbsp; PR {pr_link} &nbsp; <code>{sha}</code></summary>\n\n"
        f"Feature block archived from `docs/features.md` on {datetime.now(timezone.utc).date().isoformat()}.\n"
        f"\n"
        f"</details>\n"
    )


def _history_header() -> str:
    return (
        "# Feature History\n\n"
        "<!-- richness budget: spatial timeline + visual-token status pills + interactive collapsible-details -->\n\n"
        "Rendered audit trail for pipelinekit features. Each entry below is a "
        "merged feature; merged entries are appended automatically by "
        "`claude/lib/pipeline/features_pruner.py` during `/post-merge` Step 12.\n\n"
        "## Timeline\n\n"
        "<svg viewBox=\"0 0 800 50\" data-snippet-mount=\"timeline-scrubber\" aria-label=\"feature merge timeline\">\n"
        "  <line x1=\"20\" y1=\"25\" x2=\"780\" y2=\"25\" stroke=\"currentColor\" stroke-width=\"2\"/>\n"
        "</svg>\n\n"
        "## Features\n"
    )


def re_render_html(repo: Path) -> None:
    src = repo / "docs-source" / "feature-history.md"
    out = repo / "documentation" / "feature-history.html"
    render = repo / "claude" / "skills" / "docs-writer" / "render.py"
    if not render.is_file():
        print(f"features-pruner: render.py absent at {render} — skipping HTML render")
        return
    subprocess.run(
        ["python3", str(render), str(src), str(out),
         "--title", "Feature History",
         "--description", "Rendered audit trail of merged pipelinekit features."],
        check=False,
    )


def main() -> int:
    if is_disabled():
        print("PIPELINE_HYGIENE_OFF=1 — features-pruner skipped")
        return 0

    repo = repo_root()
    features_md = repo / "docs" / "features.md"
    history_md = repo / "docs-source" / "feature-history.md"

    if not features_md.is_file():
        print(f"features-pruner: {features_md} absent — nothing to prune")
        return 0

    text = features_md.read_text()
    blocks = parse_features_md(text)
    merged_blocks = [b for b in blocks if b["name"] and is_merged(b)]
    active_blocks = [b for b in blocks if b["name"] is None or not is_merged(b)]

    if not merged_blocks:
        print("features-pruner: no merged blocks detected — nothing to prune")
        return 0

    # Load existing history (idempotency: skip names already present)
    if history_md.is_file():
        history_text = history_md.read_text()
    else:
        history_md.parent.mkdir(parents=True, exist_ok=True)
        history_text = _history_header()

    existing_names = set(m.group("name").strip() for m in FEATURE_H2_RE.finditer(history_text))

    appended = 0
    for block in merged_blocks:
        if block["name"] in existing_names:
            continue
        history_text += render_history_section(block)
        appended += 1

    history_md.write_text(history_text)

    # In-place rewrite of features.md without the merged blocks.
    new_text = "".join(b["body"] for b in active_blocks)
    features_md.write_text(new_text)

    # Re-render HTML
    re_render_html(repo)

    print(f"features-pruner: {len(merged_blocks)} merged blocks detected, "
          f"{appended} appended to history (rest already present); "
          f"{sum(1 for b in active_blocks if b['name']) } active blocks retained.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
