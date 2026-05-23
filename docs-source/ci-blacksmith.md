# CI/CD on Blacksmith

> [INFO] Looking at deployment too? See the [provider chooser](deployment-chooser.html).

Pipelinekit defaults to Blacksmith runners (`runs-on: blacksmith`) for GitHub Actions CI/CD: cost, speed, and per-job pricing characteristics vs `ubuntu-latest`.

<div data-snippet="comparison-tabs"></div>

## 1. Why Blacksmith

Blacksmith provides ephemeral, performant runners for GitHub Actions that are faster and more cost-effective than GitHub-hosted runners for most workloads. Key advantages:

- Faster cache warm-up through persistent runner-local caching via `useblacksmith/cache`
- Reduced per-minute compute cost compared to GitHub-hosted runners at equivalent vCPU tiers
- Drop-in compatibility: most jobs need only one `runs-on:` line change
- Ecosystem-native drop-in actions for common setup tasks (`cache`, `setup-node`, `setup-python`, `setup-go`)

pipelinekit defaults to Blacksmith runners in all generated and templated workflow YAML. The lint rule R5 (in `claude/skills/create-plan/SKILL.md` Step 4.5) enforces this default at plan-creation time.

## 2. Account & runner registration

1.  Sign up at `blacksmith.sh` and create an organisation.
2.  Register an organisation runner via `blacksmith register` in your GitHub organisation settings.
3.  Store the runner authentication token as a GitHub Actions secret named `BLACKSMITH_TOKEN` only if a specific Blacksmith action requires it. Most jobs auto-authenticate via the registered runner — no per-job secret token is required for `useblacksmith/*` actions.
4.  Optionally set the `BLACKSMITH_RUNNER` GitHub Actions variable at the repository or organisation level to select a non-default runner tier (see Section 3).

## 3. The `BLACKSMITH_RUNNER` env-var override

Every `runs-on:` line in pipelinekit-generated workflows uses the fallback expression:

    runs-on: ${{ vars.BLACKSMITH_RUNNER || 'blacksmith-4vcpu-ubuntu-2204' }}

Set the `BLACKSMITH_RUNNER` GitHub Actions variable (repo or org level) to one of the available runner tiers:

- `blacksmith-2vcpu-ubuntu-2204` — small jobs (linting, quick unit tests)
- `blacksmith-4vcpu-ubuntu-2204` — default tier (balanced cost/performance)
- `blacksmith-8vcpu-ubuntu-2204` — heavier builds (multi-module monorepos, Docker builds)
- `blacksmith-16vcpu-ubuntu-2204` — very heavy / parallel matrix jobs

When `BLACKSMITH_RUNNER` is unset, the fallback literal `blacksmith-4vcpu-ubuntu-2204` is used. To switch all jobs in a repository to a larger tier, set the variable once at the repository level — no YAML changes required.

## 4. Drop-in action matrix

Blacksmith publishes optimised drop-in replacements for common GitHub Actions setup steps. Use the drop-ins where available; retain upstream actions and annotate with the gap-comment pattern (see Section 5) where no drop-in exists.

| Upstream action                               | Blacksmith drop-in              | Action          |
|-----------------------------------------------|---------------------------------|-----------------|
| `actions/cache@v3,v4`                         | `useblacksmith/cache@v5`        | swap            |
| `actions/setup-node@v3,v4`                    | `useblacksmith/setup-node@v5`   | swap            |
| `actions/setup-python@v2,v4,v5`               | `useblacksmith/setup-python@v6` | swap            |
| `actions/setup-go@v4,v5`                      | `useblacksmith/setup-go@v6`     | swap            |
| `actions/checkout@v2,v4`                      | (no drop-in needed)             | keep + annotate |
| `actions/upload-artifact@v3,v4`               | (no drop-in published)          | keep + annotate |
| `codecov/codecov-action@v2,v3,v4`             | (no drop-in)                    | keep + annotate |
| `aquasecurity/trivy-action@master`            | (no drop-in)                    | keep + annotate |
| `github/codeql-action/*`                      | (no drop-in)                    | keep + annotate |
| `SonarSource/sonarcloud-github-action@master` | (no drop-in)                    | keep + annotate |
| `snyk/actions/node@master`                    | (no drop-in)                    | keep + annotate |
| `aws-actions/configure-aws-credentials@v2,v4` | (no drop-in)                    | keep + annotate |

## 5. Gap-annotation pattern

When no Blacksmith drop-in exists for an upstream action, retain the upstream action and add a same-line comment using exactly this format (three spaces before `#`, em-dash, action name without the `@vN` pin):

    - uses: codecov/codecov-action@v3   # No Blacksmith drop-in — using upstream codecov/codecov-action

The annotation communicates to reviewers and future maintainers that the upstream action was intentionally retained because no Blacksmith optimised equivalent is available, not because the migration was missed.

## 6. Secrets policy

Never commit Blacksmith account credentials, billing tokens, or runner registration tokens to any YAML, Markdown, or config file in the repository. All secrets must be stored in the GitHub Actions secrets store at the repository or organisation level and referenced via `${{ secrets.<NAME> }}`.

The pipelinekit lint rule R5 does not check for secret exposure — use standard secret-scanning tooling (e.g., `github/codeql-action/init` with secret scanning enabled, or `aquasecurity/trivy-action`) to enforce this policy in CI.

## 7. Lint enforcement (R5)

The pipelinekit plan-mode lint gate (`claude/skills/create-plan/SKILL.md` Step 4.5, rule **R5**) rejects any plan task whose `**Files:**` list creates or modifies a `.github/workflows/*.yml` or `.github/workflows/*.yaml` file with a non-`blacksmith-*` runner, unless the task body documents the gap via a `BLACKSMITH_DOES_NOT_SUPPORT_<reason>:` line in the `**Context:**` field.

The companion smoke test at `tests/test_blacksmith_lint_r5.sh` exercises the R5 rule against six fixture plans covering the violation, compliant, documented-gap, non-workflow-file, yaml-extension, and non-ubuntu-hosted-runner cases.

The `BLACKSMITH_RUNNER` variable name also appears in the R5 remediation hint inside `claude/skills/create-plan/SKILL.md` Step 4.5, and throughout the drop-in matrix examples in this document.

## 8. Documented-gap escape hatch

Use this escape hatch only when the workflow legitimately cannot run on Blacksmith — for example, when the job requires a Windows or macOS host, or custom hardware that Blacksmith does not support. Add a single line to the task's `**Context:**` field:

    BLACKSMITH_DOES_NOT_SUPPORT_HOST_ARCH: windows-2022

R5 reads this as an explicit acknowledgement that the non-Blacksmith runner is intentional, and lets the task pass the lint gate. Choose the `<reason>` suffix to communicate why Blacksmith is not applicable (e.g., `HOST_ARCH`, `GPU_REQUIRED`, `MACOS_KEYCHAIN`).

Do not use this escape hatch for convenience — only for genuine technical incompatibilities. Every use of the escape hatch should be reviewable: a future reader of the plan should be able to understand why Blacksmith was not used for that specific task.

## CI command cheatsheet

Filter by `ci`, `blacksmith`, or `runner` to surface the commands you reach for when wiring or debugging the Blacksmith CI runner.

<div data-snippet="command-cheatsheet"></div>

