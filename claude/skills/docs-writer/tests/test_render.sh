#!/usr/bin/env bash
# Smoke test for the docs-writer skill scripts (render.py, verify_toc.py,
# richness_check.py). Uses only paths relative to this file, so it runs the
# same from the repo checkout and from an installed ~/.claude/skills copy.
#
# Exit 0 if every check passes, 1 otherwise.

set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RENDER="$SKILL_DIR/render.py"

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

python3 "$RENDER" "$TMP/sample.md" "$TMP/sample.html" > /dev/null

# Verify the rendered HTML has the right shape
assert_contains "$TMP/sample.html" '<a href="credits.html">Credits</a>' 'footer credits link present'
# Regression guard: the renderer must NOT inject tooling attribution into output
if grep -qiE 'pipelinekit|name="generator"|pkit-docs-theme' "$TMP/sample.html"; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  output carries tooling attribution (pipelinekit / generator meta / pkit key)")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  no tooling attribution in rendered output")
fi
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

python3 "$RENDER" --from-html "$TMP/source.html" "$TMP/rewrapped.html" > /dev/null

assert_contains "$TMP/rewrapped.html" '<a href="credits.html">Credits</a>' 'rewrap footer credits link present'
assert_contains "$TMP/rewrapped.html" '<title>Existing page' 'rewrap preserves title'
assert_contains "$TMP/rewrapped.html" 'id="section-x"' 'rewrap auto-generates h2 ids'
assert_contains "$TMP/rewrapped.html" 'id="subsection-x-1"' 'rewrap auto-generates h3 ids'
assert_contains "$TMP/rewrapped.html" 'href="#section-x"' 'rewrap ToC entry present'

# ============ Test 3: explicit metadata overrides ============
python3 "$RENDER" \
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

# ============ Test 4: snippet substitution (every shipped snippet) ============
# A placeholder with a JSON child must become the snippet's mount root with the
# child moved inside it, and the placeholder must be gone from the body.
for snip_path in "$SKILL_DIR"/snippets/*.html; do
  name=$(basename "$snip_path" .html)
  cat > "$TMP/snip-$name.md" <<EOF
# Snippet $name

Intro paragraph.

<div data-snippet="$name" data-title="T-$name">
<script type="application/json">{"marker": "DATA-$name"}</script>
</div>

## Section

More text.
EOF
  python3 "$RENDER" "$TMP/snip-$name.md" "$TMP/snip-$name.html" > "$TMP/snip-$name.err" 2>&1 || true
  python3 - "$TMP/snip-$name.html" "$name" > "$TMP/snip-$name.chk" 2>&1 <<'PY' && rc=0 || rc=$?
import re, sys
html, name = open(sys.argv[1]).read(), sys.argv[2]
body = re.sub(r"<!--.*?-->", "", html, flags=re.S)
assert f'<div data-snippet="{name}"' not in body, "placeholder left in body"
m = re.search(r'<[^>]*data-snippet-mount="%s"[^>]*>' % re.escape(name), body)
assert m, "mount root missing"
assert 'data-title="T-%s"' % name in m.group(0), "extra attribute not forwarded to mount root"
after = body[m.end():]
assert after.lstrip().startswith('<script type="application/json">{"marker": "DATA-%s"}' % name), \
    "JSON child not placed first inside the mount root"
PY
  if [ "$rc" -eq 0 ] && grep -q "snippets: $name" "$TMP/snip-$name.err"; then
    PASS=$((PASS + 1)); RESULTS+=("  PASS  snippet $name substituted, child + attrs forwarded")
  else
    FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  snippet $name: $(tail -1 "$TMP/snip-$name.chk") $(tail -1 "$TMP/snip-$name.err")")
  fi
  # No snippet may ship baked-in project data: data comes from the page.
  if grep -qiE 'pipelinekit|/pipeline|charter' "$snip_path"; then
    FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  snippet $name still contains project-specific content")
  fi
done

# before-after-slider: the before/after children must land INSIDE the slider
# root (where its script looks for them), not as stray text after it.
cat > "$TMP/bas.md" <<'EOF'
# Slider

Intro.

<div data-snippet="before-after-slider">
<div data-bas-before><p>OLD-STATE</p></div>
<div data-bas-after><p>NEW-STATE</p></div>
</div>

Trailing paragraph.
EOF
python3 "$RENDER" "$TMP/bas.md" "$TMP/bas.html" > /dev/null 2>&1 || true
if python3 - "$TMP/bas.html" <<'PY'
import re, sys
html = re.sub(r"<!--.*?-->", "", open(sys.argv[1]).read(), flags=re.S)
start = html.index('data-snippet-mount="before-after-slider"')
end = html.index('<script>', start)          # snippet init script follows the root
root = html[start:end]
assert "<div data-bas-before><p>OLD-STATE</p></div>" in root
assert "<div data-bas-after><p>NEW-STATE</p></div>" in root
assert html.count("OLD-STATE") == 1 and html.count("NEW-STATE") == 1
assert "<p>Trailing paragraph.</p>" in html[end:]
PY
then
  PASS=$((PASS + 1)); RESULTS+=("  PASS  before-after-slider children rendered inside the slider root")
else
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  before-after-slider children not inside the slider root")
fi

# Missing snippet -> non-zero exit
cat > "$TMP/missing-snippet.md" <<'EOF'
# Missing snippet test

<div data-snippet="nonexistent-snippet-name"></div>
EOF
if python3 "$RENDER" "$TMP/missing-snippet.md" "$TMP/missing-snippet.html" 2>/dev/null; then
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  missing snippet did not raise (expected non-zero exit)")
else
  PASS=$((PASS + 1)); RESULTS+=("  PASS  missing snippet exits non-zero")
fi

# Missing input file -> clean error, exit 2
python3 "$RENDER" "$TMP/does-not-exist.md" "$TMP/x.html" > /dev/null 2> "$TMP/noinput.err" && rc=0 || rc=$?
if [ "$rc" -eq 2 ] && grep -q '^error: input file not found' "$TMP/noinput.err"; then
  PASS=$((PASS + 1)); RESULTS+=("  PASS  missing input file: clean error, exit 2")
else
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  missing input file: rc=$rc $(head -1 "$TMP/noinput.err")")
fi

# ============ Test 4b: batch mode targets cwd / --root, never the skill dir ============
mkdir -p "$TMP/proj/docs-source"
cp "$TMP/sample.md" "$TMP/proj/docs-source/getting-started.md"
(cd "$TMP/proj" && python3 "$RENDER" > /dev/null 2>&1) || true
if [ -f "$TMP/proj/documentation/getting-started.html" ] && [ -f "$TMP/proj/documentation/search.json" ] \
   && grep -q '"quadrant": "tutorial"' "$TMP/proj/documentation/search.json"; then
  PASS=$((PASS + 1)); RESULTS+=("  PASS  batch mode renders cwd docs-source/ -> documentation/ + search.json")
else
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  batch mode from cwd did not produce documentation/")
fi
rm -rf "$TMP/proj/documentation"
python3 "$RENDER" --root "$TMP/proj" > /dev/null 2>&1 || true
if [ -f "$TMP/proj/documentation/getting-started.html" ]; then
  PASS=$((PASS + 1)); RESULTS+=("  PASS  batch mode honours --root")
else
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  batch mode ignored --root")
fi
if (cd "$TMP/proj/documentation" && python3 "$RENDER" > /dev/null 2>&1); then
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  batch mode without docs-source/ should exit non-zero")
else
  PASS=$((PASS + 1)); RESULTS+=("  PASS  batch mode without docs-source/ exits non-zero")
fi
(cd "$TMP/proj" && python3 "$SKILL_DIR/verify_toc.py" > "$TMP/vt-cwd.txt" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 0 ] && grep -q 'Scanned 1 pages' "$TMP/vt-cwd.txt"; then
  PASS=$((PASS + 1)); RESULTS+=("  PASS  verify_toc.py with no args scans ./documentation")
else
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  verify_toc.py with no args: rc=$rc $(tail -1 "$TMP/vt-cwd.txt")")
fi

# ============ Test 5: richness check linter ============
# A page using one snippet passes, even though the snippet's inline CSS/JS is long
if python3 "$SKILL_DIR/richness_check.py" "$TMP/snip-comparison-tabs.html" > "$TMP/richness-pass.txt" 2>&1; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  richness_check passes on snippet-using page")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  richness_check incorrectly failed on snippet-using page")
fi

# Now write a page that has no rich content (just rendered markdown)
cat > "$TMP/thin.md" <<'EOF'
# Thin page

Just a paragraph.

## Section

Just another paragraph.
EOF
python3 "$RENDER" "$TMP/thin.md" "$TMP/thin.html" > /dev/null

mkdir -p "$TMP/check_dir"
cp "$TMP/thin.html" "$TMP/check_dir/thin-test.html"

if python3 "$SKILL_DIR/richness_check.py" "$TMP/check_dir/thin-test.html" > "$TMP/richness-fail.txt" 2>&1; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  richness_check should have failed on thin page")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  richness_check fails on thin page (rendered markdown only)")
fi

# Exempt marker should let the thin page pass
sed -i 's|</head>|<!-- richness-exempt: test exemption -->\n</head>|' "$TMP/check_dir/thin-test.html"
if python3 "$SKILL_DIR/richness_check.py" "$TMP/check_dir/thin-test.html" > "$TMP/richness-exempt.txt" 2>&1; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  richness_check passes when exempt marker present")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  richness_check ignored exempt marker")
fi

# ============ Test 6: ToC integrity (code-fence headings + duplicate ids) ============
cat > "$TMP/toc-test.md" <<'EOF'
# ToC test page

## Real section A

Some text.

```bash
cat > notes.md <<'CHARTER'
## MVP boundary
- one feature
## Non-goals
- this section heading is INSIDE a code fence
CHARTER
```

## Real section B

### Setup

First setup block.

## Tutorial 2

### Setup

Second setup block.

### Setup

Third setup block.
EOF

python3 "$RENDER" "$TMP/toc-test.md" "$TMP/toc-test.html" > /dev/null

if grep -q 'href="#mvp-boundary"' "$TMP/toc-test.html"; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  ToC includes #mvp-boundary from inside a code fence")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  ToC excludes code-fence headings")
fi

if grep -q '<h2 id="mvp-boundary"' "$TMP/toc-test.html"; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  body parsed code-fence content as a heading")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  body keeps code-fence content as code")
fi

if grep -q 'href="#real-section-a"' "$TMP/toc-test.html"; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  real section in ToC")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  real section missing from ToC")
fi

# Sequence-based dedup: three "Setup" h3s -> setup, setup-2, setup-3
for slug in setup setup-2 setup-3; do
  if grep -q "<h3 id=\"$slug\"" "$TMP/toc-test.html"; then
    PASS=$((PASS + 1))
    RESULTS+=("  PASS  h3 id=\"$slug\" present (sequence dedup)")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  FAIL  h3 id=\"$slug\" missing")
  fi
done

if python3 "$SKILL_DIR/verify_toc.py" "$TMP/toc-test.html" > /dev/null 2>&1; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  verify_toc.py reports 0 broken links on synthetic test page")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  verify_toc.py reported issues on synthetic test page")
fi

# Regression: H4 headings in HTML must NOT shift H2/H3 slug assignments.
# Bug fixed in render.py § fix_heading_ids — pre-fix, an H4 ate a slot from
# the slug sequence and offset every subsequent H2/H3 id by one. Surfaced by
# docs-source/cloud-setup.md where H4 "Path 1: ..." sits between H3 "Bootstrap"
# and H3 "Environment variables".
cat > "$TMP/h4-shift-test.md" <<'EOF'
# H4 shift test

This page mixes H3 and H4 around bash blocks with comment-shaped lines.

## First h2

### Alpha

#### Subitem one

```bash
# Comment-shaped line
# Another comment
```

### Beta

#### Subitem two

```bash
# Third comment
```

### Gamma

## Second h2

### Delta
EOF

python3 "$RENDER" "$TMP/h4-shift-test.md" "$TMP/h4-shift-test.html" > /dev/null 2>&1
for slug_pair in "alpha:Alpha" "beta:Beta" "gamma:Gamma" "delta:Delta" "first-h2:First h2" "second-h2:Second h2"; do
  slug="${slug_pair%:*}"
  expected_text="${slug_pair#*:}"
  if grep -qE "<h[23] id=\"${slug}\">${expected_text}</h" "$TMP/h4-shift-test.html"; then
    PASS=$((PASS + 1))
    RESULTS+=("  PASS  h2/h3 id=\"$slug\" matches heading text \"$expected_text\" (no H4-shift)")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  FAIL  h2/h3 id=\"$slug\" misaligned (expected text: $expected_text)")
  fi
done

# ============ Test 7: widgets really respond in a browser ============
# Headless Chromium drives every snippet and template feature over file://.
# Prints SKIP and exits 0 when playwright is not installed.
if python3 "$SKILL_DIR/tests/test_interactive.py" > "$TMP/interactive.txt" 2>&1; then
  if grep -q '^SKIP' "$TMP/interactive.txt"; then
    RESULTS+=("  SKIP  $(head -1 "$TMP/interactive.txt" | sed 's/^SKIP  //')")
  else
    PASS=$((PASS + 1)); RESULTS+=("  PASS  $(tail -1 "$TMP/interactive.txt")")
  fi
else
  FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  test_interactive.py:" "$(grep FAIL "$TMP/interactive.txt")")
fi

# ============ Summary ============
printf '%s\n' "${RESULTS[@]}"
echo
echo "Total: $PASS pass, $FAIL fail"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
