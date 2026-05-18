#!/usr/bin/env bash
set -euo pipefail

# migrate-md-to-html.sh — convert allowlisted project-native .md files under
# documentation/ to .html in place, archive-first. Accepts one or more basename
# arguments. Refuses to operate on vendored filenames and refuses anything
# outside the hard 2-file allowlist.
#
# Companion: nav-from-headings.sh for in-page navigation.

ALLOWLIST=( "github-issues-integration.md" "review-cost.md" )
DENYLIST=( "NOTICE.md" "SKILL-AUTHORING-STANDARD.md" "SKILL_PIPELINE.md" )

DOC_ROOT="documentation"
ARCHIVE="$DOC_ROOT/_md_archive"
mkdir -p "$ARCHIVE"

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

# Minimal markdown-to-HTML converter. Body content stays inside <pre> for
# fidelity-by-default (avoids loss of tables, code fences, links). The
# emitted page wraps the verbatim source in a styled HTML shell.
emit_html() {
  local md_path="$1"
  local title="$2"
  local body
  body="$(cat "$md_path")"

  cat <<HEAD
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>$title</title>
  <meta name="description" content="$title — pipelinekit application documentation.">
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
    pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: 3px; padding: 1rem; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; font-family: ui-monospace, "Cascadia Code", "Consolas", monospace; }
    @media (max-width: 768px) { body { padding: 1rem; } }
  </style>
</head>
<body>
<h1>$title</h1>
<pre>
HEAD

  # HTML-escape the body content. The whole markdown body lives inside <pre>
  # so original formatting is preserved verbatim.
  printf '%s' "$body" \
    | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'

  cat <<TAIL

</pre>
</body>
</html>
TAIL
}

migrate_one() {
  local name="$1"

  if contains "$name" "${DENYLIST[@]}"; then
    echo "error: $name is on the vendored-NOTICE list, refusing to migrate" >&2
    return 1
  fi

  if ! contains "$name" "${ALLOWLIST[@]}"; then
    echo "error: $name is not on the migration allowlist (allowed: ${ALLOWLIST[*]})" >&2
    return 1
  fi

  local stem="${name%.md}"
  local src="$DOC_ROOT/$name"
  local dst_html="$DOC_ROOT/$stem.html"
  local dst_archive="$ARCHIVE/$name"

  # Idempotence: both target and archive already present => skip.
  if [ -f "$dst_html" ] && [ -f "$dst_archive" ]; then
    echo "already migrated: $name (skipping)"
    return 0
  fi

  if [ ! -f "$src" ]; then
    echo "error: source $src not found" >&2
    return 1
  fi

  # Archive-first: copy source to _md_archive/ before any generation.
  cp -p "$src" "$dst_archive"

  # Generate the HTML. On failure, leave source in place (don't rm).
  local title
  # Use the first H1 if present, otherwise fall back to the stem.
  title="$(grep -m1 -E '^# ' "$src" | sed -E 's/^# +//' || true)"
  [ -z "$title" ] && title="$stem"

  if ! emit_html "$src" "$title" > "$dst_html"; then
    echo "error: HTML generation failed for $name; source preserved at $src" >&2
    rm -f "$dst_html"
    return 1
  fi

  # Only delete the source after both archive and html are in place.
  rm "$src"

  echo "migrated: $name -> $dst_html (archive: $dst_archive)"
}

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <basename.md> [<basename.md> ...]" >&2
  exit 2
fi

for arg in "$@"; do
  migrate_one "$arg"
done
