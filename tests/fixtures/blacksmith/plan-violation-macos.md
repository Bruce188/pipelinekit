---
version: 999
feature: feat/blacksmith-fixture-violation-macos
created: 2026-05-18
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add macOS CI workflow

**Testable:** no

**Objective:** Add a CI workflow targeting macOS.

**Files (write):**

- `.github/workflows/mac.yml`

**Changes.** Create the workflow with:

```yaml
runs-on: macos-13
```

**Context.** No documented gap for macOS.

**Verification:** `bash -n .github/workflows/mac.yml` exits 0.
