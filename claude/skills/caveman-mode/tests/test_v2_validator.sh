#!/usr/bin/env bash
# claude/skills/caveman-mode/tests/test_v2_validator.sh
# Smoke test for v2_validator.py — 4 fixtures.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATOR="$SCRIPT_DIR/v2_validator.py"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

PASS=0
FAIL=0

run_check() {
  local name="$1" expected_exit="$2" expected_stderr_substr="$3"
  local pre="$4" post="$5"
  local err rc
  err=$(python3 "$VALIDATOR" "$pre" "$post" 2>&1 >/dev/null); rc=$?
  if [ "$rc" = "$expected_exit" ] && { [ -z "$expected_stderr_substr" ] || echo "$err" | grep -qi "$expected_stderr_substr"; }; then
    echo "PASS: $name"
    PASS=$((PASS+1))
  else
    echo "FAIL: $name (rc=$rc, expected=$expected_exit, stderr=$err)"
    FAIL=$((FAIL+1))
  fi
}

# ---------- Fixture A: PRE (shared baseline) ----------
cat > "$TMPDIR/pre.md" <<'EOF'
# Sample document

This is the introduction. The intro explains the purpose of the document and
its scope. There are several paragraphs of prose here that describe context.
The reader should not assume any prior knowledge. The author does not expect
the audience to know the internals. There are no preconditions and no
required dependencies for understanding this material.
Reference: https://example.com/docs and also https://anthropic.com/api.

## Rules

You MUST follow these rules. NEVER skip them. DO NOT bypass the gate.
There is no exception. The gate is not optional. You should never proceed
when the gate refuses. Do not retry after a refusal; that is not safe.

- First bullet describing thing one
- Second bullet describing thing two
- Third bullet describing thing three
- Fourth bullet describing thing four

```python
def foo():
    return "bar"
```

## More rules

1. Step one of the procedure.
2. Step two of the procedure.
3. Step three of the procedure.

Final paragraph with more prose to bulk up the pre-image so the post can
shrink to a reasonable ratio while still preserving structure. The length
ratio check needs the pre to be substantially larger than the post.
We do not collapse bullets here. We never reorder steps. There is no
shortcut for the procedure; do not invent one. The rules are not flexible.
EOF

# ---------- Fixture 1: PASSING — paraphrased prose, all literals preserved ----------
# Post: ~80% of pre, preserves all URLs/MUSTs/fences/headings/bullets,
# drops some negation-bearing prose to keep density drift under 15%.
cat > "$TMPDIR/post_pass.md" <<'EOF'
# Sample document

Intro. Document purpose plus scope. Several paragraphs describe context.
The reader should not assume prior knowledge. Author does not expect
audience to know internals. No preconditions are required.
Reference: https://example.com/docs and also https://anthropic.com/api.

## Rules

You MUST follow these rules. NEVER skip them. DO NOT bypass the gate.
No exception. Gate is not optional. Should never proceed when refused.
Do not retry after refusal.

- First bullet describing thing one
- Second bullet describing thing two
- Third bullet describing thing three
- Fourth bullet describing thing four

```python
def foo():
    return "bar"
```

## More rules

1. Step one of the procedure.
2. Step two of the procedure.
3. Step three of the procedure.

Final paragraph. Pre-image bulkier; post shorter while preserving structure.
We do not collapse bullets. Order of steps is fixed. No shortcut here;
do not invent one. Rules are not flexible.
EOF

run_check "passing fixture" 0 "" "$TMPDIR/pre.md" "$TMPDIR/post_pass.md"

# ---------- Fixture 2: FAILING-URL — URL removed ----------
cat > "$TMPDIR/post_no_url.md" <<'EOF'
# Sample document

Intro. Document purpose plus scope.
Reference: https://example.com/docs and also see the link.

## Rules

You MUST follow rules. NEVER skip. DO NOT bypass gate.

- First bullet describing thing one
- Second bullet describing thing two
- Third bullet describing thing three
- Fourth bullet describing thing four

```python
def foo():
    return "bar"
```

## More rules

1. Step one of the procedure.
2. Step two of the procedure.
3. Step three of the procedure.

Final paragraph here too.
EOF

run_check "failing-URL fixture" 1 "URL" "$TMPDIR/pre.md" "$TMPDIR/post_no_url.md"

# ---------- Fixture 3: FAILING-MUST — MUST literal removed ----------
cat > "$TMPDIR/post_no_must.md" <<'EOF'
# Sample document

Intro. Document purpose plus scope.
Reference: https://example.com/docs and also https://anthropic.com/api.

## Rules

You should follow rules. NEVER skip. DO NOT bypass gate.

- First bullet describing thing one
- Second bullet describing thing two
- Third bullet describing thing three
- Fourth bullet describing thing four

```python
def foo():
    return "bar"
```

## More rules

1. Step one of the procedure.
2. Step two of the procedure.
3. Step three of the procedure.

Final paragraph.
EOF

run_check "failing-MUST fixture" 1 "MUST" "$TMPDIR/pre.md" "$TMPDIR/post_no_must.md"

# ---------- Fixture 4: FAILING-LENGTH — post is < 40% of pre ----------
cat > "$TMPDIR/post_short.md" <<'EOF'
# Sample document
https://example.com/docs https://anthropic.com/api
MUST. NEVER. DO NOT.
EOF

run_check "failing-length fixture" 1 "length" "$TMPDIR/pre.md" "$TMPDIR/post_short.md"

echo ""
echo "Results: $PASS PASS / $FAIL FAIL"
exit "$FAIL"
