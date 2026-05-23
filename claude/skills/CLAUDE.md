# claude/skills

Authoring rules for pipelinekit skills. A skill is one directory containing a `SKILL.md` (the contract) plus any supporting files (snippets, templates, helper Python, tests). One skill = one verb in the agent's vocabulary.

## Frontmatter Shape

Every `SKILL.md` opens with a YAML frontmatter block. Required keys first, optional keys after.

```yaml
---
name: my-skill
description: One sentence summary the orchestrator reads when deciding whether to dispatch this skill. Include trigger keywords here so the routing layer can match it.
# Optional but RECOMMENDED for routing precision (omit only for prose-only doctrine skills):
# Optional below this line:
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
paths:
  - "src/**/*.ts"
  - "tests/**/*.spec.ts"
model: opus
effort: high
argument-hint: ([--scope <id>] [--dry-run])
disable-model-invocation: false
---
```

Field rules:

- `name` must match the directory name exactly (`claude/skills/my-skill/SKILL.md` → `name: my-skill`).
- `description` is the routing surface — orchestrator dispatch decisions read this string, not the body. Lead with the verb and a trigger noun.
- `allowed-tools` is a BLOCK-LIST (one tool per indented `- ` line). Inline flow-list form (`[Read, Write]`) is tolerated but the block form is canonical.
- `paths` is a BLOCK-LIST of glob patterns scoping which files the skill is intended to touch. One entry per indented `- ` line. NEVER use the inline flow-list form (`paths: ["a", "b"]`) — the loader treats inline flow-lists as opaque strings and the scope check silently passes everything.
- `model` accepts `opus | sonnet | haiku | inherit`. Treat as a hint — the orchestrator may override at dispatch time.
- `effort` accepts `low | medium | high | max`. Drives reasoning budget.
- `disable-model-invocation: true` removes the skill from automatic routing (still invocable by slash command).

## Authoring Conventions

Body shape after the frontmatter block:

1. **One H1** matching the skill's display name (typically `# <name> — <one-line role>`). Never multiple H1s.
2. **Process H2s** in the order the skill executes them (`## Step 1: Survey`, `## Step 2: Plan`, `## Step 3: Apply`). Numbered H2s are easier for the orchestrator to resume mid-skill on `--restart-from`.
3. **Reference appendix** at the end (`## Reference`, `## See Also`) for material the skill consults but does not execute.

Tool allowlist precision:

- List the EXACT tools the skill touches. A skill that only reads files declares `allowed-tools: [Read, Glob, Grep]` — not `*`, not a copy-paste of the full toolbox.
- Wildcard (`*`) is reserved for general-purpose dispatch surfaces (the `pipeline` skill, `claude-md-enhancer`). New skills should always enumerate.
- Adding a tool to `allowed-tools` is a contract change — bump the skill's version note in the body and rerun any skill-specific tests.

Tests for a skill live at `claude/skills/<name>/tests/`. Run them via `bash claude/skills/<name>/tests/run.sh` (bash skills) or `python3 -m pytest claude/skills/<name>/tests/` (python skills). New skills that ship behaviour-bearing code (renderers, validators, parsers) MUST include a tests directory.

## Path Scoping

The `paths:` field tells the loader which files the skill is meant to touch. When the active edit target falls outside every declared glob, the skill is filtered out of the routing slate. Two consequences worth knowing:

- Missing `paths:` means GLOBAL — the skill participates in routing for every edit. Use sparingly; see the allowlist below.
- Patterns use `fnmatch` semantics (`**` recurses, `*` matches a single segment, `?` matches one char). Quote glob values to keep YAML happy.

## When to Extend vs Add New

1. **Same goal, different surface** → extend the existing skill. Example: `azure-ops` covering a new `az` subcommand stays inside `azure-ops`. Add a new `## Capability` H2 or a new `## Process` step; do not fork.
2. **Same goal, different platform** → fork. `vercel-ops`, `railway-ops`, `render-ops`, `digitalocean-ops`, `azure-ops` are siblings, not branches of one skill, because their CLI surfaces and auth posture diverge enough to make a shared skill fragile.
3. **Different goal entirely** → new skill. A skill that "writes commit messages" is a different verb from one that "renders documentation". Each verb gets its own directory.
4. **Cross-cutting concern (a check, a sanitizer)** → new skill IF it can be invoked stand-alone. A hook captures the same surface when the concern is gate-shaped (run before/after a tool call) — see `claude/hooks/CLAUDE.md` for the hook decision.

## Global-by-Design Allowlist

Skills below intentionally OMIT `paths:` because their scope is the whole repository:

- `pipeline` — orchestrates every phase across the whole repo; scoping by glob would defeat the purpose.
- `claude-md-enhancer` — operates on any project's `CLAUDE.md` regardless of layout.
- `caveman-mode` — toggles a session-wide verbosity flag; no file surface to scope.
- `write-a-skill` (the meta-skill) — authors NEW skills, so by definition cannot constrain its own surface to existing files.

Any other skill that ships without `paths:` is a bug — file an issue or add the field.

## See Also

- Root rules: `../../CLAUDE.md` (project-level conventions, never-stage list pointer, base-branch detection).
- Sibling subdir rules: `../agents/CLAUDE.md`, `../hooks/CLAUDE.md`.
- Skill index lives in the orchestrator dispatch slate — see the `pipeline` skill body for the routing surface.
