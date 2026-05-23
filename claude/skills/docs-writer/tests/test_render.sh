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

# ============ Test 4: snippet substitution ============
cat > "$TMP/snippet-test.md" <<'EOF'
# Snippet substitution test

Body paragraph.

<div data-snippet="pipeline-phase-diagram"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/snippet-test.md" "$TMP/snippet-test.html" > "$TMP/snippet-stderr.txt" 2>&1

assert_contains "$TMP/snippet-test.html" 'data-snippet-mount="pipeline-phase-diagram"' 'snippet placeholder substituted with mount root'
assert_contains "$TMP/snippet-test.html" 'pkit-pipeline-diagram' 'snippet inline CSS class present'
assert_contains "$TMP/snippet-test.html" 'pkit-pd-flow-anim' 'snippet inline animation keyframes present'

# Verify the placeholder is GONE from the page body (the snippet's documentation
# comment contains the same string as an example, so we restrict the check to
# the <div id="page-content"> region only).
PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/snippet-test.html" | grep -c '<div data-snippet="pipeline-phase-diagram"></div>' || true)
if [ "$PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  snippet placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $PLACEHOLDER_HITS placeholder remains in body (substitution failed)")
fi

# Verify stderr logs the snippet name
if grep -q 'snippets: pipeline-phase-diagram' "$TMP/snippet-stderr.txt"; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  snippet name not logged to stderr")
fi

# Missing snippet → error exit
cat > "$TMP/missing-snippet.md" <<'EOF'
# Missing snippet test

<div data-snippet="nonexistent-snippet-name"></div>
EOF

if python3 claude/skills/docs-writer/render.py "$TMP/missing-snippet.md" "$TMP/missing-snippet.html" 2>/dev/null; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  missing snippet did not raise (expected non-zero exit)")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  missing snippet raises (FileNotFoundError)")
fi

# ============ Test 5: richness check linter ============
# Check on the snippet-test output we just produced (should pass — has a snippet)
if python3 claude/skills/docs-writer/richness_check.py "$TMP/snippet-test.html" > "$TMP/richness-pass.txt" 2>&1; then
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
python3 claude/skills/docs-writer/render.py "$TMP/thin.md" "$TMP/thin.html" > /dev/null

# Move thin.html to a path that's NOT in DEFAULT_EXEMPT_FILES so the check fires
mkdir -p "$TMP/check_dir"
cp "$TMP/thin.html" "$TMP/check_dir/thin-test.html"

if python3 claude/skills/docs-writer/richness_check.py "$TMP/check_dir/thin-test.html" > "$TMP/richness-fail.txt" 2>&1; then
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  richness_check should have failed on thin page")
else
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  richness_check fails on thin page (rendered markdown only)")
fi

# Exempt marker should let the thin page pass
sed -i 's|</head>|<!-- richness-exempt: test exemption -->\n</head>|' "$TMP/check_dir/thin-test.html"
if python3 claude/skills/docs-writer/richness_check.py "$TMP/check_dir/thin-test.html" > "$TMP/richness-exempt.txt" 2>&1; then
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
cat > docs/charter.md <<'CHARTER'
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

python3 claude/skills/docs-writer/render.py "$TMP/toc-test.md" "$TMP/toc-test.html" > /dev/null

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

if python3 claude/skills/docs-writer/verify_toc.py "$TMP/toc-test.html" > /dev/null 2>&1; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  verify_toc.py reports 0 broken links on synthetic test page")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  verify_toc.py reported issues on synthetic test page")
fi

if python3 claude/skills/docs-writer/verify_toc.py > "$TMP/verify-real.txt" 2>&1; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  verify_toc.py reports 0 broken links across all documentation/")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  verify_toc.py reported issues in documentation/:")
  cat "$TMP/verify-real.txt" | sed 's/^/    /'
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

python3 claude/skills/docs-writer/render.py "$TMP/h4-shift-test.md" "$TMP/h4-shift-test.html" > /dev/null 2>&1
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

# ============ Test 7: skill-catalog-grid snippet substitution ============
cat > "$TMP/skill-catalog-test.md" <<'EOF'
# Skills catalog

Browse all available skills.

<div data-snippet="skill-catalog-grid"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/skill-catalog-test.md" "$TMP/skill-catalog-test.html" > "$TMP/skill-catalog-stderr.txt" 2>&1

assert_contains "$TMP/skill-catalog-test.html" 'data-snippet-mount="skill-catalog-grid"' 'skill-catalog-grid snippet placeholder substituted with mount root'

SKILL_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/skill-catalog-test.html" | grep -c '<div data-snippet="skill-catalog-grid"></div>' || true)
if [ "$SKILL_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  skill-catalog-grid placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $SKILL_PLACEHOLDER_HITS skill-catalog-grid placeholder remains in body")
fi

if grep -q 'snippets: skill-catalog-grid' "$TMP/skill-catalog-stderr.txt"; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  skill-catalog-grid snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  skill-catalog-grid snippet name not logged to stderr")
fi

# ============ Test 8: agent-catalog-grid snippet substitution ============
cat > "$TMP/agent-catalog-test.md" <<'EOF'
# Agents catalog

Browse all available agents.

<div data-snippet="agent-catalog-grid"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/agent-catalog-test.md" "$TMP/agent-catalog-test.html" > "$TMP/agent-catalog-stderr.txt" 2>&1

assert_contains "$TMP/agent-catalog-test.html" 'data-snippet-mount="agent-catalog-grid"' 'agent-catalog-grid snippet placeholder substituted with mount root'

AGENT_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/agent-catalog-test.html" | grep -c '<div data-snippet="agent-catalog-grid"></div>' || true)
if [ "$AGENT_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  agent-catalog-grid placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $AGENT_PLACEHOLDER_HITS agent-catalog-grid placeholder remains in body")
fi

if grep -q 'snippets: agent-catalog-grid' "$TMP/agent-catalog-stderr.txt"; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  agent-catalog-grid snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  agent-catalog-grid snippet name not logged to stderr")
fi

# ============ Test 9: deployment-provider-quiz snippet substitution ============
cat > "$TMP/deployment-provider-quiz-test.md" <<'EOF'
# Deployment + CI provider chooser

Choose your provider.

<div data-snippet="deployment-provider-quiz"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/deployment-provider-quiz-test.md" "$TMP/deployment-provider-quiz-test.html" > "$TMP/deployment-provider-quiz-stderr.txt" 2>&1 || true

assert_contains "$TMP/deployment-provider-quiz-test.html" 'data-snippet-mount="deployment-provider-quiz"' 'deployment-provider-quiz snippet placeholder substituted with mount root'

DPQ_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/deployment-provider-quiz-test.html" 2>/dev/null | grep -c '<div data-snippet="deployment-provider-quiz"></div>' || true)
if [ "$DPQ_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  deployment-provider-quiz placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $DPQ_PLACEHOLDER_HITS deployment-provider-quiz placeholder remains in body")
fi

if grep -q 'snippets: deployment-provider-quiz' "$TMP/deployment-provider-quiz-stderr.txt" 2>/dev/null; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  deployment-provider-quiz snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  deployment-provider-quiz snippet name not logged to stderr")
fi

# ============ Test 10: path-routing-diagram snippet substitution ============
cat > "$TMP/path-routing-diagram-test.md" <<'EOF'
# Pipeline path routing

Understanding path routing.

<div data-snippet="path-routing-diagram"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/path-routing-diagram-test.md" "$TMP/path-routing-diagram-test.html" > "$TMP/path-routing-diagram-stderr.txt" 2>&1 || true

assert_contains "$TMP/path-routing-diagram-test.html" 'data-snippet-mount="path-routing-diagram"' 'path-routing-diagram snippet placeholder substituted with mount root'

PRD_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/path-routing-diagram-test.html" 2>/dev/null | grep -c '<div data-snippet="path-routing-diagram"></div>' || true)
if [ "$PRD_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  path-routing-diagram placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $PRD_PLACEHOLDER_HITS path-routing-diagram placeholder remains in body")
fi

if grep -q 'snippets: path-routing-diagram' "$TMP/path-routing-diagram-stderr.txt" 2>/dev/null; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  path-routing-diagram snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  path-routing-diagram snippet name not logged to stderr")
fi

# ============ Test 11: command-cheatsheet snippet substitution ============
cat > "$TMP/command-cheatsheet-test.md" <<'EOF'
# Command cheatsheet

Quick reference for all slash commands.

<div data-snippet="command-cheatsheet"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/command-cheatsheet-test.md" "$TMP/command-cheatsheet-test.html" > "$TMP/command-cheatsheet-stderr.txt" 2>&1 || true

assert_contains "$TMP/command-cheatsheet-test.html" 'data-snippet-mount="command-cheatsheet"' 'command-cheatsheet snippet placeholder substituted with mount root'

CMD_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/command-cheatsheet-test.html" 2>/dev/null | grep -c '<div data-snippet="command-cheatsheet"></div>' || true)
if [ "$CMD_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  command-cheatsheet placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $CMD_PLACEHOLDER_HITS command-cheatsheet placeholder remains in body")
fi

if grep -q 'snippets: command-cheatsheet' "$TMP/command-cheatsheet-stderr.txt" 2>/dev/null; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  command-cheatsheet snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  command-cheatsheet snippet name not logged to stderr")
fi

# ============ Test 12: cost-budget-meter snippet substitution ============
cat > "$TMP/cost-budget-meter-test.md" <<'EOF'
# Review cost

Track your pipeline spend.

<div data-snippet="cost-budget-meter" data-spent-usd="3.40" data-max-usd="10" data-spent-turns="220" data-max-turns="500"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/cost-budget-meter-test.md" "$TMP/cost-budget-meter-test.html" > "$TMP/cost-budget-meter-stderr.txt" 2>&1 || true

assert_contains "$TMP/cost-budget-meter-test.html" 'data-snippet-mount="cost-budget-meter"' 'cost-budget-meter snippet placeholder substituted with mount root'

CBM_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/cost-budget-meter-test.html" 2>/dev/null | grep -c '<div data-snippet="cost-budget-meter"' || true)
if [ "$CBM_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  cost-budget-meter placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $CBM_PLACEHOLDER_HITS cost-budget-meter placeholder remains in body")
fi

if grep -q 'snippets: cost-budget-meter' "$TMP/cost-budget-meter-stderr.txt" 2>/dev/null; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  cost-budget-meter snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  cost-budget-meter snippet name not logged to stderr")
fi

# ============ Test 13: before-after-slider snippet substitution ============
cat > "$TMP/before-after-slider-test.md" <<'EOF'
# Before and after

Compare two states.

<div data-snippet="before-after-slider"></div>

## Section

More text.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/before-after-slider-test.md" "$TMP/before-after-slider-test.html" > "$TMP/before-after-slider-stderr.txt" 2>&1 || true

assert_contains "$TMP/before-after-slider-test.html" 'data-snippet-mount="before-after-slider"' 'before-after-slider snippet placeholder substituted with mount root'

BAS_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/before-after-slider-test.html" 2>/dev/null | grep -c '<div data-snippet="before-after-slider"></div>' || true)
if [ "$BAS_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  before-after-slider placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $BAS_PLACEHOLDER_HITS before-after-slider placeholder remains in body")
fi

if grep -q 'snippets: before-after-slider' "$TMP/before-after-slider-stderr.txt" 2>/dev/null; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  before-after-slider snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  before-after-slider snippet name not logged to stderr")
fi

# ============ Test 14: governance-roles-table snippet substitution ============
cat > "$TMP/governance-roles-table-test.md" <<'EOF'
# Governance test

Intro.

<div data-snippet="governance-roles-table"></div>

## Section

More.
EOF

python3 claude/skills/docs-writer/render.py "$TMP/governance-roles-table-test.md" "$TMP/governance-roles-table-test.html" > "$TMP/grt-stderr.txt" 2>&1 || true

assert_contains "$TMP/governance-roles-table-test.html" 'data-snippet-mount="governance-roles-table"' 'governance-roles-table snippet placeholder substituted with mount root'

GRT_PLACEHOLDER_HITS=$(awk '/<div id="page-content">/{flag=1; next} flag && /^<!--/{flag=2} flag==1{print}' "$TMP/governance-roles-table-test.html" 2>/dev/null | grep -c '<div data-snippet="governance-roles-table"></div>' || true)
if [ "$GRT_PLACEHOLDER_HITS" -eq 0 ]; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  governance-roles-table placeholder removed after substitution (in body)")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $GRT_PLACEHOLDER_HITS governance-roles-table placeholder remains in body")
fi

if grep -q 'snippets: governance-roles-table' "$TMP/grt-stderr.txt" 2>/dev/null; then
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  governance-roles-table snippet name logged to stderr")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  governance-roles-table snippet name not logged to stderr")
fi

# ============ Summary ============
printf '%s\n' "${RESULTS[@]}"
echo
echo "Total: $PASS pass, $FAIL fail"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
