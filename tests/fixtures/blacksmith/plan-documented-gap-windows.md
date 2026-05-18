---
version: 999
feature: feat/blacksmith-fixture-gap-windows
created: 2026-05-18
---

# Plan — fixture

## Phase 1 — fixture

### Task 1.1: Add Windows CI workflow

**Testable:** no

**Objective:** Add a Windows-specific CI workflow.

**Files (write):**

- `.github/workflows/win.yml`

**Changes.** Create the workflow with:

```yaml
runs-on: windows-latest
```

**Context:**

BLACKSMITH_DOES_NOT_SUPPORT_HOST_ARCH: windows-2022

**Verification:** `bash -n .github/workflows/win.yml` exits 0.
