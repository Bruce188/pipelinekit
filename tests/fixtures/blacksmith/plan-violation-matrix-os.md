---
version: 999
feature: feat/matrix-ci-workflow
created: 2026-05-19
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add matrix-OS CI workflow

**Testable:** no

**Objective:** Add a CI workflow targeting multiple OS via matrix strategy.

**Files (write):**

- `.github/workflows/matrix.yml`

**Changes.** Create the workflow with:

```yaml
runs-on: ${{ matrix.os }}
```

**Context.** No documented gap.

**Verification:** `bash -n .github/workflows/matrix.yml` exits 0.
