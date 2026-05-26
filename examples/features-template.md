# Feature Pipeline

> **Template.** Copy this file to `docs/features.md` in your target repository, then replace the example blocks below with your own. The pipeline orchestrator reads features top-to-bottom, sequentially. Each one gets its own branch, PR, and merge.

## Format

Each feature is an H2 header: `## <type>/<kebab-case-name>`.

Valid types map directly to conventional-commit prefixes: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `perf/`, `style/`, `build/`, `ci/`.

### Fields

- **Description:** *(required)* — what to build or fix. Be specific. This drives analyse, plan, and implement.
- **Type:** *(optional)* — explicit `dev` or `non-dev` override. When omitted, `/pipeline` derives from the conventional-commit prefix (`feat/`, `fix/`, `refactor/`, `perf/`, `test/` → `dev`; everything else → `non-dev`).
- **Constraints:** *(optional)* — areas to preserve, avoid, or treat carefully. The plan reads constraints as guardrails; review verifies they are honoured.
- **Acceptance Criteria:** *(optional but recommended)* — numbered list of verifiable conditions. Each criterion must be testable (automated test or observable behaviour). When present, every phase threads them through: analyse cites them as context, plan maps each criterion to one or more tasks, review verifies each is met, and the PR body lists their pass/fail status.

The `### Run Log` section is populated by `/pipeline` during execution. Do NOT edit it by hand.

## Example block

```markdown
## feat/example-auth

**Description:** Add JWT-based authentication with login and registration
endpoints. Include password hashing with bcrypt, token refresh flow, and
middleware for protected routes.

**Constraints:** Do not modify existing public API routes. Use the existing
database connection pool.

**Acceptance Criteria:**
1. POST /api/auth/register creates a user and returns a JWT
2. POST /api/auth/login returns a JWT for valid credentials, 401 for invalid
3. Protected routes return 401 without a valid JWT
4. Tokens expire after the configured TTL
5. Refresh endpoint issues a new token from a valid, non-expired token

### Run Log
```

## How to invoke

```bash
/pipeline docs/features.md                   # process every feature top-to-bottom
/pipeline docs/features.md --dry-run         # preview only — no edits, no PRs
/pipeline docs/features.md --restart-from review  # resume the in-flight feature from /review
/pipeline --renew docs/features.md           # re-attempt failed + include any deferred items
```

See `/pipeline` for the full flag surface (`--no-charter`, `--no-review`, `--no-ppr`, `--no-tdd`, `--no-docs`, `--max-usd`, `--max-turns`, `--issues`, `--plan`, ...).

---

## chore/example-editorconfig

**Description:** Add an `.editorconfig` at the repository root pinning UTF-8 encoding, LF line endings, two-space indentation for JavaScript/TypeScript and four-space for Python.

**Constraints:** Do not touch existing files. Single new file only.

**Acceptance Criteria:**
1. `.editorconfig` exists at repo root.
2. File contains `root = true` directive.
3. Sections cover `[*]`, `[*.{js,ts,tsx}]`, and `[*.py]` at minimum.

### Run Log
