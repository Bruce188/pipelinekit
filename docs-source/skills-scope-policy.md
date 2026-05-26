<!--
diataxis: explanation
-->
# Skills scope policy

Authoring policy for the `paths:` frontmatter field on `claude/skills/<name>/SKILL.md`. Every new skill MUST declare `paths:` unless it appears on the global-by-design allowlist below.

## Why scoped skills

The orchestrator builds a **routing slate** at dispatch time — the set of skills it considers for the current active edit target. A skill participates in the slate when at least one of its `paths:` globs matches a file in the target set; it is filtered out otherwise.

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
