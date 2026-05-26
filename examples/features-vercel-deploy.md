# Feature Pipeline — Vercel deploy

> **Charter Topic 10 + `@vercel-deployment-engineer` demo.** A `feat` block that exercises the deployment-target classifier and the Vercel-specific routing. When Topic 10 of the project charter is set to `vercel`, `/pipeline` automatically routes every deployment-shaped task in this feature to the `@vercel-deployment-engineer` agent and the `vercel-ops` skill — no manual agent selection required.

## Prerequisites

- Vercel CLI installed: `npm i -g vercel`. The Vercel skill stops with a guidance message if the CLI is missing — it does not auto-install.
- The project charter at `docs/charter.md` exists and Topic 10 reads `vercel` (verify with `grep '^Topic 10:' docs/charter.md`). If your charter does not yet record Topic 10, run `/pipeline --renew` to revalidate before processing this feature.
- A Vercel project linked via `vercel link` (the deployment-engineer agent verifies linkage as its first step; it does NOT link on your behalf).

## feat/vercel-edge-deploy-rewrite

**Description:** Move the project's `/api/health` endpoint from a Node Vercel serverless function to an Edge Function so it cold-starts in under 50 ms globally. Update `vercel.json` to declare the `runtime: "edge"` directive on `/api/health` only — every other route remains on the Node runtime. Add a `vercel deploy --prod=false` preview-deploy step to the implement phase so a preview URL is produced before the PR opens.

**Type:** dev

**Constraints:**
- Do NOT change runtime for any route other than `/api/health`. The deployment-engineer's charter-aware routing should refuse mixed-runtime edits unless the feature description names the route explicitly.
- Keep the `pages/api/health.ts` (or `app/api/health/route.ts`) handler API surface identical: response body shape, status codes, and headers must round-trip the existing contract.
- The preview deployment URL produced by `vercel deploy --prod=false` must be captured in the PR description by `/ppr` (deployment-engineer attaches it as a step output).
- Secrets MUST flow via Vercel's project env-vars surface — never via `.env` committed to the repo. The `block-stage-sensitive.sh` hook refuses `.env*` paths by default.

**Acceptance Criteria:**
1. `vercel.json` declares `"runtime": "edge"` for the `/api/health` path and NO other path.
2. Running the existing `/api/health` integration tests against the preview deployment URL returns the original response shape unchanged.
3. The PR body contains the preview-deployment URL on its own line (string-match check via `gh pr view`).
4. The `/review` phase test-engineer agent reports a passing `vercel deploy --prebuilt` dry-run as part of its verification log.
5. No `.env*` file appears in `git diff main..HEAD` (defence-in-depth — block-stage-sensitive.sh should already prevent this).

### Run Log
