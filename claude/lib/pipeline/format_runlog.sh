#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

# format_runlog.sh — single source of truth for the canonical Run Log entry
# format defined in docs/analysis-v35.md § 3.1 and codified by
# docs/plan-v36.md (F5 of features-v2.md).
#
# Contract (see docs/analysis-v35.md § 3.1, § 3.2, § 4.2, § 4.3, § 4.4):
#
#   $1 = subcommand. One of:
#     validate <line>   — exit 0 if <line> matches RUNLOG_RE, exit 1 otherwise.
#                         On failure, writes "RUNLOG_FORMAT_INVALID: <reason>" to stderr.
#     format <flags>    — assemble a canonical Run Log line from 18 named flags
#                         (--date --time --status --pr --sha --class --av --pv
#                         --ppv --rv --path-b --inline --b --nb --nit --files
#                         --add --del --summary), self-validate the result, and
#                         emit it on stdout. Exit 0 on success, exit 2 on
#                         self-consistency failure (formatter bug).
#     selftest          — run 8 built-in assertions (3 should-match, 4 should-NOT-
#                         match, 1 format round-trip). Exit 0 with "selftest: 8/8 PASS"
#                         on stdout iff all assertions pass; exit 1 on any failure.
#
# Exit codes:
#   0 — operation succeeded (validate match, format produced, selftest all-PASS)
#   1 — validate failed to match, or selftest assertion failed
#   2 — formatter self-consistency failure, or unknown subcommand / bad args
#
# POSIX-only invariants (plan-v36.md AC13): the helper uses only bash
# builtins, printf, grep -E, tr, cut. No external scripting interpreters
# or JSON parsers are invoked.

# RUNLOG_RE: the canonical regex (POSIX-extended), copied verbatim from
# docs/analysis-v35.md § 4.2. This is the ONLY definition of the regex in the
# repository. SKILL.md and reference.md reference this helper for runtime
# enforcement; reference.md additionally embeds the human-readable pattern
# as a reference card.
#
# Em-dash `—` is the literal UTF-8 byte sequence E2 80 94 — required by the
# canonical format and matched byte-wise under LC_ALL=C.
RUNLOG_RE='^- [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}: (SUCCESS|FAILED|PARTIAL|BLOCKED) — PR #([0-9]+|N/A) merged as ([0-9a-f]{7}|N/A)\. (dev|non-dev) feature\. analysis-v[0-9]+ / plan-v[0-9]+ / prompts-v[0-9]+ / review-v[0-9]+\. [0-9]+ Path B cycles, [0-9]+ inline cycles\. [0-9]+ blocking, [0-9]+ non-blocking, [0-9]+ nits\. [0-9]+ files, \+[0-9]+/-[0-9]+\. .{1,200}\.$'

usage() {
  cat >&2 <<'USAGE'
usage: format_runlog.sh <subcommand> [args...]
  validate <line>   exit 0 if <line> matches the canonical Run Log regex
  format <flags>    assemble a canonical line from 18 named flags
  selftest          run built-in assertions
See docs/analysis-v35.md § 3.1 and claude/skills/pipeline/reference.md
"Run Log Canonical Format" for the contract.
USAGE
}

cmd_validate() {
  if [[ $# -lt 1 ]]; then
    printf 'RUNLOG_FORMAT_INVALID: validate requires a single string argument\n' >&2
    return 2
  fi
  local line="$1"
  if printf '%s' "$line" | grep -qE -- "$RUNLOG_RE"; then
    return 0
  fi
  printf 'RUNLOG_FORMAT_INVALID: line does not match canonical regex\n' >&2
  return 1
}

cmd_format() {
  local DATE="" TIME_="" STATUS="" PR="" SHA="" CLASS=""
  local AV="" PV="" PPV="" RV=""
  local PATH_B="" INLINE="" B="" NB="" NIT=""
  local FILES="" ADD="" DEL="" SUMMARY=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --date)    DATE="$2"; shift 2 ;;
      --time)    TIME_="$2"; shift 2 ;;
      --status)  STATUS="$2"; shift 2 ;;
      --pr)      PR="$2"; shift 2 ;;
      --sha)     SHA="$2"; shift 2 ;;
      --class)   CLASS="$2"; shift 2 ;;
      --av)      AV="$2"; shift 2 ;;
      --pv)      PV="$2"; shift 2 ;;
      --ppv)     PPV="$2"; shift 2 ;;
      --rv)      RV="$2"; shift 2 ;;
      --path-b)  PATH_B="$2"; shift 2 ;;
      --inline)  INLINE="$2"; shift 2 ;;
      --b)       B="$2"; shift 2 ;;
      --nb)      NB="$2"; shift 2 ;;
      --nit)     NIT="$2"; shift 2 ;;
      --files)   FILES="$2"; shift 2 ;;
      --add)     ADD="$2"; shift 2 ;;
      --del)     DEL="$2"; shift 2 ;;
      --summary) SUMMARY="$2"; shift 2 ;;
      *)
        printf 'RUNLOG_FORMAT_INVALID: unknown flag: %s\n' "$1" >&2
        return 2
        ;;
    esac
  done

  # Strip \n \r \t from summary, then cap at 200 chars (with trailing ... if truncated).
  SUMMARY=$(printf '%s' "$SUMMARY" | tr -d '\n\r\t')
  local orig_len=${#SUMMARY}
  if [[ $orig_len -gt 200 ]]; then
    SUMMARY=$(printf '%s' "$SUMMARY" | cut -c1-197)
    SUMMARY="${SUMMARY}..."
  fi

  # If summary already ends with a period, the canonical line still appends a
  # trailing period from the template — but the regex anchors `\.$` once. To
  # keep the output unambiguous and matching the regex's `.{1,200}\.$` tail
  # (i.e. 1..200 chars then a final period), strip any user-supplied trailing
  # period so the template's final `.` is the only one.
  while [[ "${SUMMARY: -1}" == "." ]]; do
    SUMMARY="${SUMMARY%.}"
  done

  # Assemble the canonical line. Em-dash is the literal UTF-8 char.
  local LINE
  LINE=$(printf -- '- %s %s: %s — PR #%s merged as %s. %s feature. analysis-v%s / plan-v%s / prompts-v%s / review-v%s. %s Path B cycles, %s inline cycles. %s blocking, %s non-blocking, %s nits. %s files, +%s/-%s. %s.' \
    "$DATE" "$TIME_" "$STATUS" "$PR" "$SHA" "$CLASS" \
    "$AV" "$PV" "$PPV" "$RV" \
    "$PATH_B" "$INLINE" "$B" "$NB" "$NIT" \
    "$FILES" "$ADD" "$DEL" "$SUMMARY")

  # Self-consistency gate: the formatter's output must pass validate.
  if ! printf '%s' "$LINE" | grep -qE -- "$RUNLOG_RE"; then
    printf 'RUNLOG_FORMAT_INVALID: formatter produced invalid line — internal bug\n' >&2
    return 2
  fi

  printf '%s\n' "$LINE"
  return 0
}

cmd_selftest() {
  local pass=0 fail=0 total=0

  # Should-match examples (analysis-v35 § 4.3 examples 1, 2, 3).
  local match1='- 2026-05-18 14:22: SUCCESS — PR #33 merged as a1b2c3d. non-dev feature. analysis-v35 / plan-v36 / prompts-v36 / review-v33. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 3 files, +145/-2. Unified Run Log format with helper script and validation regex.'
  local match2='- 2026-05-18 02:10: FAILED — PR #N/A merged as N/A. dev feature. analysis-v40 / plan-v41 / prompts-v41 / review-v38. 5 Path B cycles, 0 inline cycles. 2 blocking, 3 non-blocking, 1 nits. 12 files, +0/-0. Max review cycles exceeded; surviving blockers in NB1+NB2.'
  local match3='- 2026-05-18 09:01: PARTIAL — PR #34 merged as fedcba9. dev feature. analysis-v36 / plan-v37 / prompts-v37 / review-v34. 1 Path B cycles, 2 inline cycles. 0 blocking, 0 non-blocking, 2 nits. 5 files, +88/-3. Inline mini-fix landed; 2 cosmetic nits survived sanity-gate revert.'

  # Should-NOT-match examples (analysis-v35 § 4.4 examples 1-4).
  local nomatch1='**Completed [2026-05-18 00:35]:** SUCCESS | Review cycles: 1 | PR: ...'
  local nomatch2='- 2026-05-18: PR #25 merged. analysis-v23 / plan-v24 / prompts-v24 / review-v21. 0 blocking + 0 non-blocking + 0 nits; PASS.'
  local nomatch3='- 2026-05-18 14:22: success — PR #33 merged as a1b2c3d. non-dev feature. analysis-v35 / plan-v36 / prompts-v36 / review-v33. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 3 files, +145/-2. Lowercase status fails.'
  local nomatch4='- 2026-05-18 14:22: SUCCESS - PR #33 merged as a1b2c3d. non-dev feature. analysis-v35 / plan-v36 / prompts-v36 / review-v33. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 3 files, +145/-2. ASCII hyphen fails.'

  assert_match() {
    local label="$1" line="$2"
    total=$((total + 1))
    if printf '%s' "$line" | grep -qE -- "$RUNLOG_RE"; then
      pass=$((pass + 1))
    else
      fail=$((fail + 1))
      printf 'selftest FAIL [%s]: expected match but regex did not match\n  line: %s\n' "$label" "$line" >&2
    fi
  }

  assert_nomatch() {
    local label="$1" line="$2"
    total=$((total + 1))
    if printf '%s' "$line" | grep -qE -- "$RUNLOG_RE"; then
      fail=$((fail + 1))
      printf 'selftest FAIL [%s]: expected NO match but regex matched\n  line: %s\n' "$label" "$line" >&2
    else
      pass=$((pass + 1))
    fi
  }

  assert_match "match1 (success)" "$match1"
  assert_match "match2 (failed)"  "$match2"
  assert_match "match3 (partial)" "$match3"
  assert_nomatch "nomatch1 (legacy Format 1)" "$nomatch1"
  assert_nomatch "nomatch2 (Format 2)"        "$nomatch2"
  assert_nomatch "nomatch3 (lowercase)"       "$nomatch3"
  assert_nomatch "nomatch4 (ascii hyphen)"    "$nomatch4"

  # Round-trip: format + validate the AC7 inputs.
  total=$((total + 1))
  local rt_out
  if rt_out=$(cmd_format \
    --date 2026-05-18 --time 14:22 --status SUCCESS --pr 33 --sha a1b2c3d \
    --class non-dev --av 35 --pv 36 --ppv 36 --rv 33 \
    --path-b 0 --inline 0 --b 0 --nb 0 --nit 0 \
    --files 3 --add 145 --del 2 \
    --summary "Unified Run Log format with helper script and validation regex.") \
    && printf '%s' "$rt_out" | grep -qE -- "$RUNLOG_RE"
  then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    printf 'selftest FAIL [round-trip]: format/validate round-trip did not green-path\n  out: %s\n' "$rt_out" >&2
  fi

  if [[ $fail -eq 0 ]]; then
    printf 'selftest: %d/%d PASS\n' "$pass" "$total"
    return 0
  fi
  printf 'selftest: %d/%d PASS, %d FAIL\n' "$pass" "$total" "$fail" >&2
  return 1
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    return 2
  fi
  local sub="$1"; shift
  case "$sub" in
    validate) cmd_validate "$@" ;;
    format)   cmd_format "$@" ;;
    selftest) cmd_selftest ;;
    -h|--help|help) usage; return 0 ;;
    *)
      printf 'usage: unknown subcommand: %s\n' "$sub" >&2
      usage
      return 2
      ;;
  esac
}

main "$@"
