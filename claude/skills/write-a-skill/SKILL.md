<!--
Vendored from mattpocock/skills @ e74f0061bb67222181640effa98c675bdb2fdaa7
Upstream path: skills/productivity/write-a-skill/SKILL.md
License: MIT — Copyright (c) 2026 Matt Pocock
Source: https://github.com/mattpocock/skills/blob/e74f0061bb67222181640effa98c675bdb2fdaa7/skills/productivity/write-a-skill/SKILL.md
Do not edit in place — re-vendor from upstream and bump the SHA.
-->

---
name: write-a-skill
description: Create new agent skills with proper structure, progressive disclosure, and bundled resources. Use when user wants to create, write, or build a new skill.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# Writing Skills

## Process

1. **Gather requirements** - ask user about:
   - What task/domain does the skill cover?
   - What specific use cases should it handle?
   - Does it need executable scripts or just instructions?
   - Any reference materials to include?

2. **Draft the skill** - create:
   - SKILL.md with concise instructions
   - Additional reference files if content exceeds 500 lines
   - Utility scripts if deterministic operations needed

3. **Review with user** - present draft and ask:
   - Does this cover your use cases?
   - Anything missing or unclear?
   - Should any section be more/less detailed?

## Skill Structure

```
skill-name/
├── SKILL.md           # Main instructions (required)
├── REFERENCE.md       # Detailed docs (if needed)
├── EXAMPLES.md        # Usage examples (if needed)
└── scripts/           # Utility scripts (if needed)
    └── helper.js
```

## SKILL.md Template

```md
---
name: skill-name
description: Brief description of capability. Use when [specific triggers].
---

# Skill Name

## Quick start

[Minimal working example]

## Workflows

[Step-by-step processes with checklists for complex tasks]

## Advanced features

[Link to separate files: See [REFERENCE.md](REFERENCE.md)]
```

## Description Requirements

The description is **the only thing your agent sees** when deciding which skill to load. It's surfaced in the system prompt alongside all other installed skills. Your agent reads these descriptions and picks the relevant skill based on the user's request.

**Goal**: Give your agent just enough info to know:

1. What capability this skill provides
2. When/why to trigger it (specific keywords, contexts, file types)

**Format**:

- Max 1024 chars
- Write in third person
- First sentence: what it does
- Second sentence: "Use when [specific triggers]"

**Good example**:

```
Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when user mentions PDFs, forms, or document extraction.
```

**Bad example**:

```
Helps with documents.
```

The bad example gives your agent no way to distinguish this from other document skills.

## Step 1: Declare paths:

Every NEW skill MUST declare `paths:` in its frontmatter (block-list form, never inline flow-list) unless it appears on the global-by-design allowlist below. Skills that omit `paths:` are treated as GLOBAL — they participate in routing for every edit target, costing the orchestrator tokens and accuracy. The `paths:` field is the skill's reviewable surface contract.

See [`documentation/skills-scope-policy.html`](../../../documentation/skills-scope-policy.html) for the full policy and rationale.

### Scoping heuristic

Every skill's `paths:` should include `claude/skills/<name>/**` plus the primary operating surface the skill touches:

| Surface kind | Example skill | Example path |
|---|---|---|
| Workflow metadata | `create-plan` | `docs/plan*.md`, `docs/prompts*.md` |
| Application source | `tdd` | `**/tests/**`, `**/*.test.ts` |
| Build artifacts | `docs-writer` | `docs-source/**`, `documentation/**` |
| CLI provider docs | `vercel-ops` | `vercel.json`, `documentation/deployment-vercel.html` |
| Repo-state sentinel | `new-branch` | `.git/HEAD` |

When the heuristic feels ambiguous, prefer the narrowest reasonable surface. Never use `**` or `*` as the only entry — that is equivalent to declaring the skill global without the explicit allowlist rationale.

### Global-by-design allowlist

The four skills below intentionally OMIT `paths:`:

- `pipeline` — orchestrates every phase across the whole repo; scoping by glob would defeat the purpose.
- `claude-md-enhancer` — operates on any project's `CLAUDE.md` regardless of layout.
- `caveman-mode` — toggles a session-wide verbosity flag; no file surface to scope.
- `write-a-skill` (the meta-skill) — authors NEW skills, so by definition cannot constrain its own surface to existing files.

Adding a new skill to the allowlist requires a charter-level justification — when in doubt, declare `paths:`.

### Check template

Paste-and-run this snippet against a freshly-authored SKILL.md to verify either `paths:` is declared OR the skill name is on the allowlist:

```bash
python3 - < claude/skills/<your-skill>/SKILL.md <<'PYEOF'
import re, sys
ALLOWLIST = {"pipeline", "claude-md-enhancer", "caveman-mode", "write-a-skill"}
body = sys.stdin.read()
m = re.search(r"^---\s*$(.*?)^---\s*$", body, re.MULTILINE | re.DOTALL)
if not m:
    sys.exit("error: no YAML frontmatter block found")
fm = m.group(1)
name_match = re.search(r"^name:\s*(\S+)\s*$", fm, re.MULTILINE)
name = name_match.group(1) if name_match else None
has_paths = re.search(r"^paths:\s*$", fm, re.MULTILINE) is not None
if has_paths or name in ALLOWLIST:
    print(f"ok: {name} ({'paths declared' if has_paths else 'on allowlist'})")
    sys.exit(0)
sys.exit(f"error: skill '{name}' missing required `paths:` field (and not on allowlist)")
PYEOF
```

Exit code 0 = skill conforms. Exit code != 0 = skill is missing `paths:` and not on the allowlist — add `paths:` before merging.

## When to Add Scripts

Add utility scripts when:

- Operation is deterministic (validation, formatting)
- Same code would be generated repeatedly
- Errors need explicit handling

Scripts save tokens and improve reliability vs generated code.

## When to Split Files

Split into separate files when:

- SKILL.md exceeds 100 lines
- Content has distinct domains (finance vs sales schemas)
- Advanced features are rarely needed

## Review Checklist

After drafting, verify:

- [ ] Description includes triggers ("Use when...")
- [ ] SKILL.md under 100 lines
- [ ] No time-sensitive info
- [ ] Consistent terminology
- [ ] Concrete examples included
- [ ] References one level deep
