#!/usr/bin/env bash
# Tests for claude/skills/ppr/ppr_research_flag.sh
# Run: bash claude/skills/ppr/tests/test_ppr_research_flag.sh
# Exits non-zero if any scenario fails.
set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/ppr_research_flag.sh"

fails=0

# ---------------------------------------------------------------------------
# Sandbox setup helper
# Creates a temp git repo with a bare-repo origin. Prints the sandbox path.
# ---------------------------------------------------------------------------
setup_sandbox() {
    local tmpdir
    tmpdir="$(mktemp -d)"
    local origin_dir="${tmpdir}/../origin-$(basename "$tmpdir").git"

    (
        cd "$tmpdir"
        git init -q -b main
        git config user.email test@example.com
        git config user.name test
        git commit --allow-empty -qm init
        git init --bare "$origin_dir" -q
        git remote add origin "$origin_dir"
    ) >/dev/null 2>&1

    echo "$tmpdir"
}

# ---------------------------------------------------------------------------
# Scenario (a): Dry-run prints plan, no push
# ---------------------------------------------------------------------------
test_a_dry_run_no_push() {
    local sandbox
    sandbox="$(setup_sandbox)"
    local origin_dir="${sandbox}/../origin-$(basename "$sandbox").git"

    # Create a valid TSV with 2 keep rows and 1 reject row
    mkdir -p "$sandbox/docs"
    printf 'commit\tmetric\tmemory\tstatus\tdescription\n' > "$sandbox/docs/research-results.tsv"
    printf 'abc123\t0.85\t512\tkeep\tgood result one\n' >> "$sandbox/docs/research-results.tsv"
    printf 'def456\t0.72\t480\treject\tbad result\n' >> "$sandbox/docs/research-results.tsv"
    printf 'ghi789\t0.91\t520\tkeep\tgood result two\n' >> "$sandbox/docs/research-results.tsv"

    local stdout stderr exit_code
    stdout="$(cd "$sandbox" && bash "$SCRIPT" --research --dry-run --research-tag demo 2>/tmp/test_a_stderr)"
    exit_code=$?
    stderr="$(cat /tmp/test_a_stderr)"

    local pass=1

    # exit code == 0
    if [ "$exit_code" -ne 0 ]; then
        echo "FAIL: (a) dry-run — expected exit 0 but got $exit_code"
        pass=0
    fi

    # stdout contains DRY-RUN
    if ! echo "$stdout" | grep -q 'DRY-RUN'; then
        echo "FAIL: (a) dry-run — stdout does not contain 'DRY-RUN'"
        pass=0
    fi

    # stdout contains research/demo- (date suffix varies)
    if ! echo "$stdout" | grep -q 'research/demo-'; then
        echo "FAIL: (a) dry-run — stdout does not contain 'research/demo-'"
        pass=0
    fi

    # stdout contains 2 keep (case-insensitive)
    if ! echo "$stdout" | grep -qi '2 keep'; then
        echo "FAIL: (a) dry-run — stdout does not mention '2 keep'"
        pass=0
    fi

    # no research/* branch created
    local branches
    branches="$(cd "$sandbox" && git branch --list 'research/*')"
    if [ -n "$branches" ]; then
        echo "FAIL: (a) dry-run — research/* branch was created unexpectedly: $branches"
        pass=0
    fi

    # nothing pushed to origin
    local push_count
    push_count="$(git --git-dir="$origin_dir" log --all --oneline 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$push_count" -ne 0 ]; then
        echo "FAIL: (a) dry-run — commits were pushed to origin (expected 0, got $push_count)"
        pass=0
    fi

    if [ "$pass" -eq 1 ]; then
        echo "PASS: (a) dry-run prints plan, no push"
    else
        fails=$((fails + 1))
    fi

    rm -rf "$sandbox" "$origin_dir" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Scenario (b): Missing TSV → non-zero exit, clear error
# ---------------------------------------------------------------------------
test_b_missing_tsv() {
    local sandbox
    sandbox="$(setup_sandbox)"
    local origin_dir="${sandbox}/../origin-$(basename "$sandbox").git"

    # Do NOT create docs/research-results.tsv

    local combined exit_code
    combined="$(cd "$sandbox" && bash "$SCRIPT" --research --no-dry-run --research-tag demo 2>&1)"
    exit_code=$?

    local pass=1

    # exit code != 0
    if [ "$exit_code" -eq 0 ]; then
        echo "FAIL: (b) missing TSV — expected non-zero exit but got 0"
        pass=0
    fi

    # combined output contains docs/research-results.tsv
    if ! echo "$combined" | grep -q 'docs/research-results.tsv'; then
        echo "FAIL: (b) missing TSV — output does not mention 'docs/research-results.tsv'"
        pass=0
    fi

    # combined output contains missing or not found (case-insensitive)
    if ! echo "$combined" | grep -qi 'missing\|not found'; then
        echo "FAIL: (b) missing TSV — output does not say 'missing' or 'not found'"
        pass=0
    fi

    if [ "$pass" -eq 1 ]; then
        echo "PASS: (b) missing TSV → non-zero exit, clear error"
    else
        fails=$((fails + 1))
    fi

    rm -rf "$sandbox" "$origin_dir" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Scenario (c): Empty keep-rows → warning, exit 0, no branch
# ---------------------------------------------------------------------------
test_c_no_keep_rows() {
    local sandbox
    sandbox="$(setup_sandbox)"
    local origin_dir="${sandbox}/../origin-$(basename "$sandbox").git"

    # Create a TSV with header + 2 reject rows only
    mkdir -p "$sandbox/docs"
    printf 'commit\tmetric\tmemory\tstatus\tdescription\n' > "$sandbox/docs/research-results.tsv"
    printf 'abc123\t0.85\t512\treject\tbad result one\n' >> "$sandbox/docs/research-results.tsv"
    printf 'def456\t0.72\t480\treject\tbad result two\n' >> "$sandbox/docs/research-results.tsv"

    local combined exit_code
    combined="$(cd "$sandbox" && bash "$SCRIPT" --research --no-dry-run --research-tag demo 2>&1)"
    exit_code=$?

    local pass=1

    # exit code == 0
    if [ "$exit_code" -ne 0 ]; then
        echo "FAIL: (c) no keep rows — expected exit 0 but got $exit_code"
        pass=0
    fi

    # combined output mentions 0 keep or no keep rows (case-insensitive)
    if ! echo "$combined" | grep -qi '0 keep\|no keep rows'; then
        echo "FAIL: (c) no keep rows — output does not warn about 0 keep rows"
        pass=0
    fi

    # no research/* branch created
    local branches
    branches="$(cd "$sandbox" && git branch --list 'research/*')"
    if [ -n "$branches" ]; then
        echo "FAIL: (c) no keep rows — research/* branch was created unexpectedly"
        pass=0
    fi

    # nothing pushed to origin
    local push_count
    push_count="$(git --git-dir="$origin_dir" log --all --oneline 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$push_count" -ne 0 ]; then
        echo "FAIL: (c) no keep rows — commits were pushed to origin (expected 0)"
        pass=0
    fi

    if [ "$pass" -eq 1 ]; then
        echo "PASS: (c) empty keep-rows → warning, exit 0, no branch"
    else
        fails=$((fails + 1))
    fi

    rm -rf "$sandbox" "$origin_dir" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Scenario (d): --no-dry-run without --research-tag → non-zero exit
# ---------------------------------------------------------------------------
test_d_missing_tag() {
    local sandbox
    sandbox="$(setup_sandbox)"
    local origin_dir="${sandbox}/../origin-$(basename "$sandbox").git"

    # Create a minimal valid TSV with 1 keep row
    mkdir -p "$sandbox/docs"
    printf 'commit\tmetric\tmemory\tstatus\tdescription\n' > "$sandbox/docs/research-results.tsv"
    printf 'abc123\t0.85\t512\tkeep\tgood result\n' >> "$sandbox/docs/research-results.tsv"

    local combined exit_code
    combined="$(cd "$sandbox" && bash "$SCRIPT" --research --no-dry-run 2>&1)"
    exit_code=$?

    local pass=1

    # exit code != 0
    if [ "$exit_code" -eq 0 ]; then
        echo "FAIL: (d) missing tag — expected non-zero exit but got 0"
        pass=0
    fi

    # combined output mentions --research-tag
    if ! echo "$combined" | grep -q '\-\-research-tag'; then
        echo "FAIL: (d) missing tag — output does not mention '--research-tag'"
        pass=0
    fi

    if [ "$pass" -eq 1 ]; then
        echo "PASS: (d) --no-dry-run without --research-tag → non-zero exit"
    else
        fails=$((fails + 1))
    fi

    rm -rf "$sandbox" "$origin_dir" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------
test_a_dry_run_no_push
test_b_missing_tsv
test_c_no_keep_rows
test_d_missing_tag

echo "Total fails: $fails"
exit $fails
