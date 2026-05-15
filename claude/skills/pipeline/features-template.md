# Feature Pipeline

> **Usage:** Feature files are optional. `/pipeline` can auto-generate one from your latest analysis, PRP, or a `--from` description.
>
> ```
> /pipeline                                    # auto-generates from analysis/PRP/deferred items
> /pipeline docs/features.md                   # use an explicit feature file
> /pipeline docs/features.md --dry-run         # preview without executing
> /pipeline docs/features.md --restart-from review  # resume from review step
> /pipeline --renew docs/features.md           # retry failed + include deferred items
> /pipeline --renew                            # renew the default docs/features.md
> /pipeline --from "Add rate limiting to all API endpoints"  # auto-generate from description
> ```
>
> To create a feature file manually, copy this template to your project as `docs/features.md` and replace the examples.

## Format

Each feature is an H2 header: `## <type>/<kebab-case-name>`

Valid types: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `perf/`

Required fields:
- **Description:** What to build or fix. Be specific — this drives the analysis, plan, and implementation.

Optional fields:
- **Constraints:** Areas to preserve, avoid, or treat carefully.
- **Acceptance Criteria:** Numbered list of verifiable conditions that define "done." Each criterion should be testable — either by automated tests or by observable behavior. When present, acceptance criteria are threaded through the workflow: analysis includes them as context, plans map criteria to tasks, review agents verify each criterion is met, and PRs include criteria status.

The `### Run Log` section is populated by the pipeline. Do not edit it manually.

Features are processed top-to-bottom, sequentially. Each gets its own branch, PR, and merge.

---

## feat/example-auth
**Description:** Add JWT-based authentication with login and registration endpoints. Include password hashing with bcrypt, token refresh flow, and middleware for protected routes.
**Constraints:** Do not modify existing public API routes. Use the existing database connection pool.
**Acceptance Criteria:**
1. POST /api/auth/register creates a user and returns a JWT
2. POST /api/auth/login returns a JWT for valid credentials, 401 for invalid
3. Protected routes return 401 without a valid JWT
4. Tokens expire after the configured TTL
5. Refresh endpoint issues a new token from a valid, non-expired token

### Run Log

---

## fix/example-rate-limit
**Description:** API endpoints have no rate limiting, allowing abuse. Add sliding-window rate limiting middleware with configurable per-endpoint limits and proper 429 responses.

### Run Log

---

## refactor/example-error-handling
**Description:** Replace scattered try/catch blocks with a centralized error handling middleware. Normalize error response format across all endpoints to `{ error: string, code: string, details?: object }`.
**Constraints:** Preserve existing HTTP status codes. Do not change error semantics, only response format.

### Run Log

---
