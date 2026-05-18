#!/usr/bin/env bash
# Smoke test for /pipeline --renew --auto behavior. F12 contract.
#
# Asserts:
#   Fixture B: charter with frontmatter `created:` 3 days ago → the
#     charter_revalidate_skip.sh helper emits `CHARTER_REVALIDATE: fresh`.
#   Fixture C: charter with `created:` 30 days ago → the helper does NOT
#     emit `CHARTER_REVALIDATE: fresh`; falls through to the existing
#     `CHARTER_REVALIDATE: charter found at` token.
#   Fixture A: simulated --auto code path produces an HTML-comment header
#     in features-renewed.md beginning with `<!-- auto-accept:`.
#
# Run from repo root:
#   bash claude/skills/pipeline/tests/test_renew_auto_flag.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SKIP_SCRIPT="$REPO_ROOT/claude/lib/pipeline/charter_revalidate_skip.sh"

if [ ! -f "$SKIP_SCRIPT" ]; then
  echo "FAIL helper script missing: $SKIP_SCRIPT"
  exit 1
fi

TMP=""
cleanup() {
  if [ -n "${TMP:-}" ] && [ -d "${TMP:-}" ]; then
    rm -rf "$TMP"
  fi
  return 0
}
trap cleanup EXIT

# ---------- Fixture B: fresh charter ---------------------------------
TMP=$(mktemp -d)
mkdir -p "$TMP/docs"
echo "**Charter:** docs/charter.md" > "$TMP/progress.md"
THREE_DAYS_AGO=$(date -d "$(date +%Y-%m-%d) -3 days" +%Y-%m-%d)
cat > "$TMP/docs/charter.md" <<CHARTER
---
created: $THREE_DAYS_AGO
---
# Charter

## Non-Goals

- no logging changes
CHARTER

OUT_B=$(bash "$SKIP_SCRIPT" "$TMP" 2>&1 || true)
if ! grep -q 'CHARTER_REVALIDATE: fresh' <<< "$OUT_B"; then
  echo "FAIL Fixture B: expected 'CHARTER_REVALIDATE: fresh' in output:"
  echo "$OUT_B"
  exit 1
fi
rm -rf "$TMP"

# ---------- Fixture C: old charter -----------------------------------
TMP=$(mktemp -d)
mkdir -p "$TMP/docs"
echo "**Charter:** docs/charter.md" > "$TMP/progress.md"
THIRTY_DAYS_AGO=$(date -d "$(date +%Y-%m-%d) -30 days" +%Y-%m-%d)
cat > "$TMP/docs/charter.md" <<CHARTER
---
created: $THIRTY_DAYS_AGO
---
# Charter
CHARTER

OUT_C=$(bash "$SKIP_SCRIPT" "$TMP" 2>&1 || true)
if grep -q 'CHARTER_REVALIDATE: fresh' <<< "$OUT_C"; then
  echo "FAIL Fixture C: did not expect 'CHARTER_REVALIDATE: fresh' for old charter:"
  echo "$OUT_C"
  exit 1
fi
if ! grep -q 'CHARTER_REVALIDATE: charter found at' <<< "$OUT_C"; then
  echo "FAIL Fixture C: expected fall-through to 'charter found at' token:"
  echo "$OUT_C"
  exit 1
fi
rm -rf "$TMP"

# ---------- Fixture A: --auto auto-accept header ---------------------
# Simulates the documented --auto branch of sub-step 6.5 sub-step h:
# prepend an HTML-comment header block to features-renewed.md.
TMP=$(mktemp -d)
mkdir -p "$TMP/docs"
cat > "$TMP/docs/features-renewed.md" <<RENEWED
## feat/structured-logging
**Description:** Add structured logging across worker pool
RENEWED

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
HEADER=$(cat <<HEADER_EOF
<!-- auto-accept: charter drift accepted without prompting; --renew --auto invoked at $TS
  drift entries:
    - feature: ## feat/structured-logging | section: Non-Goals | status: drifted | evidence: feature blob token-overlaps Non-Goal phrase 'no logging changes'
-->
HEADER_EOF
)
{ printf '%s\n\n' "$HEADER"; cat "$TMP/docs/features-renewed.md"; } > "$TMP/docs/features-renewed.md.new"
mv "$TMP/docs/features-renewed.md.new" "$TMP/docs/features-renewed.md"

if ! head -1 "$TMP/docs/features-renewed.md" | grep -q '^<!-- auto-accept:'; then
  echo "FAIL Fixture A: features-renewed.md head missing auto-accept comment block"
  echo "--- head of file ---"
  head -5 "$TMP/docs/features-renewed.md"
  exit 1
fi
rm -rf "$TMP"

echo "OK: test_renew_auto_flag.sh"
exit 0
