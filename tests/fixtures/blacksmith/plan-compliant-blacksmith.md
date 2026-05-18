---
version: 999
feature: feat/blacksmith-fixture-compliant
created: 2026-05-18
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add CI workflow

**Testable:** no

**Objective:** Add a CI workflow using Blacksmith runner.

**Files (write):**

- `.github/workflows/ci.yml`

**Changes.** Create the workflow with:

```yaml
runs-on: ${{ vars.BLACKSMITH_RUNNER || 'blacksmith-4vcpu-ubuntu-2204' }}
```

**Context.** Using canonical Blacksmith runner pattern.

**Verification:** `bash -n .github/workflows/ci.yml` exits 0.
