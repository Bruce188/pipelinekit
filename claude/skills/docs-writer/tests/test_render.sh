#!/usr/bin/env bash
# Smoke test for claude/skills/docs-writer/render.py
# Tests: markdown render mode, --from-html rewrap mode, template signature,
# generator meta tag, ToC generation, syntax highlight, table rendering.
#
# Exit 0 on all pass, exit 1 on first failure.

set -euo pipefail
cd "$(dirname "$0")/../../../.."

PASS=0
FAIL=0
RESULTS=()

assert_contains() {
  local file=$1 needle=$2 label=$3
  if grep -qF -- "$needle" "$file"; then
    PASS=$((PASS + 1))
    RESULTS+=("  PASS  $label")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  FAIL  $label (missing in $file: $needle)")
  fi
}

assert_count() {
  local file=$1 pattern=$2 expected=$3 label=$4
  local actual
  actual=$(grep -cE "$pattern" "$file" || true)
  if [ "$actual" -ge "$expected" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("  PASS  $label ($actual ≥ $expected)")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  FAIL  $label ($actual < $expected)")
  fi
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ============ Test 1: markdown render mode ============
cat > "$TMP/sample.md" <<'EOF'
# Sample page

A description paragraph for the page header.

## Section A

Some text with `inline code` and **bold**.

```python
def hello():
    print("world")
```

## Section B

| Column | Value |
|--------|-------|
| foo    | 1     |
| bar    | 2     |

> [INFO] This is a callout.

### Subsection B.1

More content.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/sample.md" "$TMP/sample.html" > /dev/null

# Verify the rendered HTML has the right shape
assert_contains "$TMP/sample.html" 'docs-writer/2 — rich-template' 'generator meta tag present'
assert_contains "$TMP/sample.html" '<title>Sample page' 'title in <title>'
assert_contains "$TMP/sample.html" '<h1>Sample page</h1>' 'h1 in page-header'
assert_contains "$TMP/sample.html" 'class="description">A description' 'description in header'
assert_contains "$TMP/sample.html" 'id="section-a"' 'h2 has slug id'
assert_contains "$TMP/sample.html" 'id="subsection-b-1"' 'h3 has slug id'
assert_contains "$TMP/sample.html" 'href="#section-a"' 'ToC links to section-a'
assert_contains "$TMP/sample.html" 'href="#subsection-b-1"' 'ToC links to subsection-b-1'
assert_contains "$TMP/sample.html" 'class="codehilite"' 'codehilite wrapper present (Pygments active)'
assert_contains "$TMP/sample.html" '<table>' 'table rendered as semantic HTML'
assert_contains "$TMP/sample.html" '<th>Column' 'table header rendered'

# Verify description dedup: the lead paragraph should NOT appear in the body
# (#page-content). It SHOULD appear in <meta> and .page-header .description.
# Count only occurrences inside the <div id="page-content"> block.
BODY_HITS=$(awk '/<div id="page-content">/{flag=1; next} /<\/div>/{flag=0} flag' "$TMP/sample.html" | grep -c 'A description paragraph for the page header' || true)
if [ "$BODY_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  description stripped from body (still present in <meta> + .page-header)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  description leaked into body $BODY_HITS times (expected 0)")
fi

# Verify interactivity: JS for theme toggle, scrollspy, copy-button must be present
assert_contains "$TMP/sample.html" 'theme-toggle' 'theme toggle script present'
assert_contains "$TMP/sample.html" 'copy-btn' 'copy-button script present'
assert_contains "$TMP/sample.html" 'IntersectionObserver' 'scrollspy uses IntersectionObserver'
assert_contains "$TMP/sample.html" 'page-search' 'in-page search input present'

# Self-contained: no remote refs
# (use a literal substring check rather than regex to keep this simple)
if grep -qE 'href="https?://[^"]+\.(css|js)"|src="https?://[^"]+\.js"' "$TMP/sample.html"; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  output references remote CSS or JS asset")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  no remote CSS/JS references (self-contained)")
fi

# ============ Test 2: --from-html rewrap mode ============
cat > "$TMP/source.html" <<'EOF'
<!DOCTYPE html>
<html><head><title>Existing page</title><meta name="description" content="An existing HTML page."></head>
<body>
<h1>Existing page</h1>
<p>Some lead paragraph.</p>
<h2>Section X</h2>
<p>Body content.</p>
<h3>Subsection X.1</h3>
<ul><li>Item one</li><li>Item two</li></ul>
</body></html>
EOF

python3 claude/skills/docs-writer/render.py --from-html "$TMP/source.html" "$TMP/rewrapped.html" > /dev/null

assert_contains "$TMP/rewrapped.html" 'docs-writer/2 — rich-template' 'rewrap output has generator tag'
assert_contains "$TMP/rewrapped.html" '<title>Existing page' 'rewrap preserves title'
assert_contains "$TMP/rewrapped.html" 'id="section-x"' 'rewrap auto-generates h2 ids'
assert_contains "$TMP/rewrapped.html" 'id="subsection-x-1"' 'rewrap auto-generates h3 ids'
assert_contains "$TMP/rewrapped.html" 'href="#section-x"' 'rewrap ToC entry present'

# ============ Test 3: explicit metadata overrides ============
python3 claude/skills/docs-writer/render.py \
  "$TMP/sample.md" "$TMP/explicit.html" \
  --title "Custom Title" \
  --description "Custom description that overrides derivation" \
  --source-link "https://example.com/source" \
  --meta "Section: testing" > /dev/null

assert_contains "$TMP/explicit.html" '<h1>Custom Title</h1>' 'explicit --title respected'
assert_contains "$TMP/explicit.html" 'Custom description that overrides' 'explicit --description respected'
assert_contains "$TMP/explicit.html" 'https://example.com/source' 'source link in meta'
assert_contains "$TMP/explicit.html" 'Section:' 'meta item rendered'

# When --description is explicit, the body lead paragraph should NOT be stripped
LEAD_COUNT=$(grep -c 'A description paragraph for the page header' "$TMP/explicit.html" || true)
if [ "$LEAD_COUNT" -ge 1 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  with explicit --description, body lead paragraph preserved")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  body lead paragraph stripped despite explicit --description")
fi

# ============ Summary ============
printf '%s\n' "${RESULTS[@]}"
echo
echo "Total: $PASS pass, $FAIL fail"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
