---
version: 999
feature: feat/blacksmith-fixture-no-workflow
created: 2026-05-18
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add Python library module

**Testable:** no

**Objective:** Add a Python helper module.

**Files (write):**

- `src/lib/foo.py`

**Changes.** Create the module. Note: some docs mention runs-on: ubuntu-latest
but this task does not touch any .github/workflows/ path.

**Context.** No workflow file involved.

**Verification:** `python3 -c "import src.lib.foo"` exits 0.
