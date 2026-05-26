# Feature Pipeline — TDD fix

> **TDD red-green-refactor demonstration.** A `fix` feature that runs through the full TDD pairing: `tdd-test-writer` writes failing tests first (red), `tdd-implementer` writes the minimum production change to pass (green), then a small refactor pass. The `tdd-red-phase-gate.sh` hook blocks any commit mixing new tests and new production code in the same change.

## fix/block-push-main-regex

**Description:** The `block-push-main.sh` hook has a known regex bug discovered during F8: it currently passes through `git push origin main` invocations under specific quoting paths because the trailing whitespace match in the branch-name regex is too greedy. Tighten the regex so any `git push` whose ref-spec resolves to `main` or `master` is refused, regardless of how the command line is quoted. This example file describes the work; do NOT actually edit the hook from this example — the orchestrator will plan and execute the fix when this feature is processed.

**Type:** dev

**Constraints:**
- Tests live at `claude/hooks/tests/test-block-push-main.bats` (or `claude/hooks/tests/test_block_push_main.py` if the suite is python).
- Red phase MUST write at least three test cases covering: (a) `git push origin main`, (b) `git push origin HEAD:main`, (c) `git push --tags origin main`.
- Green phase MUST modify only `claude/hooks/block-push-main.sh`. No test edits during green.
- Hook output strings must stay UTF-8. No emoji additions.
- Pre-commit gate: `tdd-red-phase-gate.sh` enforces test-only red commit followed by impl-only green commit.

**Acceptance Criteria:**
1. Running `bash claude/hooks/tests/test-block-push-main.bats` (or the python equivalent) fails before the green-phase commit (red phase verified).
2. Running the same test suite after the green-phase commit produces zero failures.
3. `git log --oneline main..HEAD` shows at least two commits — one `test:` (red) and one `fix:` (green) — in that order.
4. `claude/hooks/block-push-main.sh` returns a non-zero exit code for every case enumerated in Constraints, with a single-line stderr message naming the protected branch.
5. The hook continues to PASS `git push origin feature/anything` (control case).

### Run Log
