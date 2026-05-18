#!/usr/bin/env bash
set -euo pipefail

# nav-from-headings.sh — reads markdown body from stdin, emits a <nav> block
# with one <a href="#<slug>"> entry per H2 (^## ) or H3 (^### ) heading.
#
# Slug rule: lowercase the heading text, replace non-alphanumeric runs with
# a single hyphen, strip leading and trailing hyphens.
#
# Empty input emits an empty <nav><ul></ul></nav> shell.

emit_slug() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-//; s/-$//'
}

printf '<nav>\n  <ul>\n'

while IFS= read -r line; do
  case "$line" in
    "## "*)
      text="${line#"## "}"
      slug="$(emit_slug "$text")"
      printf '    <li><a href="#%s">%s</a></li>\n' "$slug" "$text"
      ;;
    "### "*)
      text="${line#"### "}"
      slug="$(emit_slug "$text")"
      printf '    <li><a href="#%s">%s</a></li>\n' "$slug" "$text"
      ;;
  esac
done

printf '  </ul>\n</nav>\n'
