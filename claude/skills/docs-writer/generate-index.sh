#!/usr/bin/env bash
set -euo pipefail

# generate-index.sh — crawl documentation/**/*.html (excluding index.html),
# extract <title> and <meta name="description"> from each, emit a landing
# page that lists every page. Output goes to stdout by default; pass --write
# to write directly to documentation/index.html.
#
# nav-from-headings.sh — companion script for in-page table-of-contents.

WRITE_OUT=0
if [ "${1:-}" = "--write" ]; then
  WRITE_OUT=1
fi

DOC_ROOT="documentation"

extract_title() {
  # Capture content between <title> and </title> on a single line; else empty.
  grep -m1 -oE '<title>[^<]*</title>' "$1" 2>/dev/null \
    | sed -E 's|^<title>(.*)</title>$|\1|' || true
}

extract_description() {
  grep -m1 -oE '<meta name="description" content="[^"]*"' "$1" 2>/dev/null \
    | sed -E 's|^<meta name="description" content="(.*)"$|\1|' || true
}

# Collect candidate pages (relative paths).
mapfile -t PAGES < <(find "$DOC_ROOT" -type f -name '*.html' \
  ! -name 'index.html' \
  | sort)

emit() {
  cat <<HEAD
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pipelinekit documentation</title>
  <meta name="description" content="Index of all pipelinekit application documentation pages.">
  <style>
    :root {
      --bg: #ffffff;
      --fg: #111111;
      --muted: #555555;
      --border: #dddddd;
      --link: #0050b3;
      --code-bg: #f5f5f5;
      --header-bg: #fafafa;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #0d1117;
        --fg: #e6edf3;
        --muted: #8b949e;
        --border: #30363d;
        --link: #58a6ff;
        --code-bg: #161b22;
        --header-bg: #161b22;
      }
    }
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.55; background: var(--bg); color: var(--fg); margin: 0 auto; padding: 2rem; max-width: 1200px; }
    h1 { margin-top: 0; font-size: 1.85rem; }
    h2 { margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; background: var(--header-bg); }
    p { margin: 0.7rem 0; }
    a { color: var(--link); }
    ul { padding-left: 1.4rem; }
    li { margin: 0.4rem 0; }
    .desc { color: var(--muted); }
    code { background: var(--code-bg); border: 1px solid var(--border); border-radius: 3px; padding: 0.1rem 0.35rem; font-family: ui-monospace, "Cascadia Code", "Consolas", monospace; }
    @media (max-width: 768px) { body { padding: 1rem; } }
  </style>
</head>
<body>
<h1>pipelinekit documentation</h1>
<p>Generated index of all application documentation pages under <code>documentation/</code>. Workflow files under <code>docs/</code> are intentionally excluded (AI-internal artifacts, never committed).</p>
<h2>Pages</h2>
<ul>
HEAD

  for page in "${PAGES[@]}"; do
    rel="${page#$DOC_ROOT/}"
    title="$(extract_title "$page")"
    desc="$(extract_description "$page")"
    [ -z "$title" ] && title="$rel"
    if [ -n "$desc" ]; then
      printf '  <li><a href="%s">%s</a> &mdash; <span class="desc">%s</span></li>\n' \
        "$rel" "$title" "$desc"
    else
      printf '  <li><a href="%s">%s</a></li>\n' "$rel" "$title"
    fi
  done

  cat <<TAIL
</ul>
</body>
</html>
TAIL
}

if [ "$WRITE_OUT" -eq 1 ]; then
  emit > "$DOC_ROOT/index.html"
  echo "wrote: $DOC_ROOT/index.html ($(wc -l < "$DOC_ROOT/index.html") lines, ${#PAGES[@]} pages listed)"
else
  emit
fi
