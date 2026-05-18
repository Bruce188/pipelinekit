---
version: 999
feature: feat/blacksmith-fixture-violation-ubuntu
created: 2026-05-18
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add CI workflow

**Testable:** no

**Objective:** Add a CI workflow.

**Files (write):**

- `.github/workflows/ci.yml`

**Changes.** Create the workflow with:

```yaml
runs-on: ubuntu-latest
```

**Context.** No documented gap.

**Verification:** `bash -n .github/workflows/ci.yml` exits 0.
