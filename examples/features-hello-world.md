# Feature Pipeline — hello-world

> **Self-contained dry-run-friendly example.** A trivial `chore` feature you can run end-to-end to confirm `/pipeline` is wired correctly without touching real production code. Total runtime: under five minutes.

## chore/hello-world-greeting

**Description:** Append a one-line `# Hello, world!` ASCII greeting block to the top of `README.md` (or `documentation/getting-started.html` if you'd rather keep README untouched) so a brand-new clone shows it visibly. The line must read literally `# Hello, world! Welcome to <project>.`, substituting `<project>` for the repository's actual name.

**Type:** non-dev

**Constraints:**
- Single-file edit, append-only.
- Do NOT rewrite or remove existing README content.
- No new dependencies. No new files. No CI hook changes.
- AI-attribution scrubber must pass — no `Co-Authored-By`, no `Generated with`.

**Acceptance Criteria:**
1. The first line of the target file reads `# Hello, world! Welcome to <project>.` after the change.
2. `git diff main..HEAD --stat` reports exactly one file changed.
3. `git log --oneline -1` produces a `chore:` prefixed commit message ≤ 72 chars.
4. `python3 claude/skills/docs-writer/render.py` (when `documentation/getting-started.html` is the target) re-emits the file with no parse errors.

### Run Log
