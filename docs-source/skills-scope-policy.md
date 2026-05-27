<!--
diataxis: explanation
-->
# Skills scope policy

Authoring policy for the `paths:` frontmatter field on `claude/skills/<name>/SKILL.md`. Every new skill MUST declare `paths:` unless it appears on the global-by-design allowlist below.

## Why scoped skills

The orchestrator builds a **routing slate** at dispatch time — the set of skills it considers for the current active edit target. A skill participates in the slate when at least one of its `paths:` globs matches a file in the target set; it is filtered out otherwise.

The diagram below traces that filter: the loader matches every skill's `paths:` globs against the active edit target, keeping matches in the slate (accent) and dropping the rest (dashed, subtle).

<svg viewBox="0 0 720 320" role="img" aria-label="Routing-slate filter: skills matched against the active edit target by their paths globs" style="width:100%;height:auto;font-family:var(--sans);">
  <title>How the loader filters skills into the routing slate by paths: globs</title>
  <defs>
    <marker id="ssp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="var(--border-strong)"></path>
    </marker>
    <marker id="ssp-arrow-in" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="var(--accent)"></path>
    </marker>
    <marker id="ssp-arrow-out" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="var(--fg-subtle)"></path>
    </marker>
  </defs>
  <rect x="16" y="128" width="150" height="64" fill="var(--bg-elev)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
  <text x="91" y="154" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">active edit target</text>
  <text x="91" y="174" text-anchor="middle" fill="var(--fg-muted)" font-size="11" font-family="var(--mono)">src/auth/login.ts</text>
  <rect x="250" y="120" width="150" height="80" fill="var(--accent-soft)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
  <text x="325" y="148" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">loader</text>
  <text x="325" y="168" text-anchor="middle" fill="var(--fg-muted)" font-size="11">match each skill's</text>
  <text x="325" y="184" text-anchor="middle" fill="var(--fg-muted)" font-size="11" font-family="var(--mono)">paths: globs</text>
  <line x1="166" y1="160" x2="248" y2="160" stroke="var(--border-strong)" stroke-width="1.5" marker-end="url(#ssp-arrow)"></line>
  <rect x="484" y="36" width="220" height="104" fill="none" stroke="var(--accent)" stroke-width="1.5" rx="6"></rect>
  <text x="500" y="62" fill="var(--accent)" font-size="12" font-weight="600">IN slate — glob matches</text>
  <g font-size="11.5" fill="var(--fg)" font-family="var(--mono)">
    <text x="500" y="86">tdd  (**/*.test.ts)</text>
    <text x="500" y="106">code-reviewer  (**)</text>
    <text x="500" y="126">pipeline  (global)</text>
  </g>
  <rect x="484" y="180" width="220" height="104" fill="none" stroke="var(--fg-subtle)" stroke-width="1.5" stroke-dasharray="5 3" rx="6"></rect>
  <text x="500" y="206" fill="var(--fg-subtle)" font-size="12" font-weight="600">filtered OUT — no match</text>
  <g font-size="11.5" fill="var(--fg-muted)" font-family="var(--mono)">
    <text x="500" y="230">vercel-ops  (vercel.json)</text>
    <text x="500" y="250">docs-writer  (docs-source/**)</text>
    <text x="500" y="270">create-plan  (docs/plan*.md)</text>
  </g>
  <path d="M400 146 C 445 116, 455 100, 482 90" fill="none" stroke="var(--accent)" stroke-width="1.5" marker-end="url(#ssp-arrow-in)"></path>
  <path d="M400 174 C 445 204, 455 220, 482 230" fill="none" stroke="var(--fg-subtle)" stroke-width="1.5" stroke-dasharray="5 3" marker-end="url(#ssp-arrow-out)"></path>
</svg>

- **Smaller slate per edit target** — the model spends fewer tokens enumerating irrelevant skills and the dispatch decision is faster and more accurate.
- **Lower cross-talk** — a skill scoped to `docs/plan*.md` does not get pulled in when the user is editing TypeScript tests, even if its description happens to mention "plan" in passing.
- **Explicit surface contract** — the `paths:` field documents the skill's edit territory in machine-readable form. Reviewers can audit scope changes alongside behaviour changes.

Skills that omit `paths:` are treated as **GLOBAL** — they always participate in routing. Use sparingly. The whole-repo skills below are exempted by design; every other skill must declare a surface.

## How to write `paths:`

Use a YAML **block-list** (one entry per indented `- ` line) between `allowed-tools:` and the closing `---` of the frontmatter block. The loader treats inline flow-lists (`paths: ["a", "b"]`) as opaque strings, so the scope check silently passes everything — never use the inline form.

```yaml
---
name: my-skill
description: ...
allowed-tools:
  - Read
  - Edit
paths:
  - claude/skills/my-skill/**
  - docs/my-skill*.md
  - "**/*.config.ts"
---
```

Glob semantics follow `fnmatch`:

- `**` recurses across directory boundaries (`src/**/*.ts` matches any `.ts` under `src/`).
- `*` matches a single path segment (`src/*.ts` does NOT recurse).
- `?` matches one character.

Quote any glob whose value contains a YAML-significant character (`:`, `,`, `{`, `[`) so the parser keeps the string intact.

### Scoping heuristic

Every skill's `paths:` should include `claude/skills/<name>/**` plus the **primary operating surface** the skill touches:

| Surface kind | Example skill | Example path |
|---|---|---|
| Workflow metadata | `create-plan` | `docs/plan*.md`, `docs/prompts*.md` |
| Application source | `tdd` | `**/tests/**`, `**/*.test.ts` |
| Build artifacts | `docs-writer` | `docs-source/**`, `documentation/**` |
| CLI provider docs | `vercel-ops` | `vercel.json`, `documentation/deployment-vercel.html` |
| Repo-state sentinel | `new-branch` | `.git/HEAD` |

When the heuristic feels ambiguous, prefer the narrowest reasonable surface. Never use `**` or `*` as the only entry — that is equivalent to declaring the skill global, but without the explicit allowlist rationale.

<details>
<summary>Worked example: the slate for a <code>docs-source/</code> edit (click to expand)</summary>

Say the active edit target is `docs-source/glossary.md`. The loader walks every skill's `paths:` block and keeps only those with a matching glob:

- **`docs-writer`** survives — its `docs-source/**` glob matches directly.
- **`pipeline`**, **`caveman-mode`**, and the other global-by-design skills survive — they declare no `paths:`, so they match everything.
- **`tdd`** is filtered out — `**/*.test.ts` does not match a `.md` file.
- **`vercel-ops`** is filtered out — `vercel.json` is unrelated to a docs edit.

The result is a slate of two or three skills instead of all 42 — exactly the token-cost and dispatch-accuracy win the policy exists to capture.

</details>

## Global-by-design allowlist

The four skills below intentionally OMIT `paths:`. Their scope is the whole repository; scoping by glob would defeat their purpose.

- `pipeline` — orchestrates every phase across the whole repo; scoping by glob would defeat the purpose.
- `claude-md-enhancer` — operates on any project's `CLAUDE.md` regardless of layout.
- `caveman-mode` — toggles a session-wide verbosity flag; no file surface to scope.
- `write-a-skill` (the meta-skill) — authors NEW skills, so by definition cannot constrain its own surface to existing files.

Adding a new skill to this allowlist requires a charter-level justification — when in doubt, declare `paths:` and let the loader filter the skill out where it does not belong.

## Authoring contract

Every NEW skill in `claude/skills/<name>/SKILL.md` MUST declare `paths:` unless it appears on the allowlist above. A skill that ships without `paths:` and is not on the allowlist is a bug — file an issue or add the field before merging.

The `paths:` block is part of the skill's reviewable contract: bump the skill's version note in the body when you add, remove, or widen a glob, and rerun the skill's tests if it has any.

## See also

- `claude/skills/CLAUDE.md` — the authoring rules root for the `claude/skills/` directory.
- `docs-source/SKILL-AUTHORING-STANDARD.md` — the broader 10-pattern skill DNA template (vendored upstream).
