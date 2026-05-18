---
version: 999
feature: feat/blacksmith-fixture-violation-yaml-ext
created: 2026-05-18
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add CI workflow with yaml extension

**Testable:** no

**Objective:** Add a CI workflow using .yaml extension.

**Files (write):**

- `.github/workflows/bar.yaml`

**Changes.** Create the workflow with:

```yaml
runs-on: ubuntu-latest
```

**Context.** No documented gap.

**Verification:** `bash -n .github/workflows/bar.yaml` exits 0.
