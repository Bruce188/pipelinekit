#!/usr/bin/env bash
# scan-secrets-staged.sh -- pre-commit gitleaks gate.
#
# Invokes `gitleaks detect --staged --redact --no-banner --report-format json
# --report-path /dev/null` on the current staged content. Exits 2 on any
# finding so git aborts the commit; --redact masks any secret values that
# might otherwise reach the JSON report.
#
# ACs:
#   1. PIPELINEKIT_ALLOW_SECRET=1 opts out (exit 0 + stderr notice).
#   2. gitleaks not on PATH -> graceful degrade (exit 0 + stderr notice).
#   3. No staged files -> exit 0.
#   4. Clean staged content -> exit 0.
#   5. Secret detected -> exit 2 with redacted advisory.
#
# Designed to run as `.git/hooks/pre-commit` (cwd = repo root by git contract)
# or as a unit test against a sandbox git repo.

set -uo pipefail

# AC-1: opt-out env (highest precedence; never reaches gitleaks).
if [[ "${PIPELINEKIT_ALLOW_SECRET:-}" == "1" ]]; then
  printf 'scan-secrets-staged: PIPELINEKIT_ALLOW_SECRET=1 opt-out -- secret scan skipped\n' >&2
  exit 0
fi

# AC-2: gitleaks optional (graceful degrade when binary absent).
if ! command -v gitleaks >/dev/null 2>&1; then
  printf 'scan-secrets-staged: gitleaks not on PATH -- skipping (install via https://github.com/gitleaks/gitleaks)\n' >&2
  exit 0
fi

# AC-3: no staged files -> nothing to scan.
if [[ -z "$(git diff --cached --name-only 2>/dev/null)" ]]; then
  exit 0
fi

# AC-4/5: run gitleaks with --redact mandatory (never log raw secret content).
GITLEAKS_EXIT=0
gitleaks detect --staged --redact --no-banner --report-format json --report-path /dev/null >/dev/null 2>&1 || GITLEAKS_EXIT=$?

if [[ "$GITLEAKS_EXIT" -eq 0 ]]; then
  exit 0
fi

# Finding detected (gitleaks exits non-zero on detection).
printf 'error: secret-scanner: gitleaks found potential secret(s) in staged content -- run `gitleaks detect --staged --verbose` locally to inspect (values redacted); set PIPELINEKIT_ALLOW_SECRET=1 to override one commit\n' >&2
exit 2
