# Notice — claude-md-enhancer

The files in this directory (excluding this `NOTICE.md` and the pipelinekit
overlay sections at the bottom of `SKILL.md`) are vendored from:

**Upstream:** https://github.com/alirezarezvani/ClaudeForge
**Pinned SHA:** `6eb741b46cd8dcdb444be6f004b481a0b589a18d`
**Upstream paths (15 files byte-exact):**
- skill/SKILL.md
- skill/HOW_TO_USE.md
- skill/README.md
- skill/analyzer.py
- skill/generator.py
- skill/template_selector.py
- skill/validator.py
- skill/workflow.py
- skill/sample_input.json
- skill/expected_output.json
- skill/examples/README.md
- skill/examples/minimal-solo-CLAUDE.md
- skill/examples/core-small-team-CLAUDE.md
- skill/examples/python-api-CLAUDE.md
- skill/examples/modular-root-CLAUDE.md
- skill/examples/modular-backend-CLAUDE.md
- skill/examples/modular-frontend-CLAUDE.md

The related guardian agent (`claude/agents/claude-md-guardian.md`) is also
vendored from this upstream (`agent/claude-md-guardian.md`) — see
`claude/agents/NOTICE.md` for the agent-level notice.

## Pipelinekit deltas (documented so re-vendoring stays mechanical)

1. **HTML-comment attribution header** prepended to each `.md` file (Python
   and JSON files are byte-exact, no header). Pattern:

   ```
   <!-- Adopted from alirezarezvani/ClaudeForge @ 6eb741b — MIT (Copyright 2025 Alireza Rezvani). See claude/skills/claude-md-enhancer/NOTICE.md. -->
   ```

2. **SKILL.md frontmatter swap:** upstream's `permissions:` block is replaced
   with pipelinekit's `allowed-tools: Read, Write, Edit, Bash, Glob, Grep,
   AskUserQuestion` line. `disable-model-invocation: false` is ensured present.
   The body below the closing `---` is byte-identical to upstream.

3. **Pipelinekit overlay sections** appended to the END of `SKILL.md`:
   - `## Pipelinekit Overlay — Diff/Accept Flow` — documents the
     `.CLAUDE.md.proposed` write-and-diff-and-prompt workflow.
   - `## Pipelinekit Overlay — Step 4 Validation` — shells out to
     `python3 ~/.claude/hooks/claude-md-guard.py` after generation.
   - `## Installation` — opt-in `settings.json` snippet for the hook.

4. **Hook is clean-room, NOT vendored.** `claude/hooks/claude-md-guard.py`
   is pipelinekit-native. It enforces 8 rules (CM001–CM008) — see the hook
   file's docstring. The upstream's `validator.py` is a thorough audit;
   the hook is a fast gate. The two rule-sets may legitimately diverge.

## Re-vendor procedure

To re-vendor (e.g., when upstream ships a quality improvement):

1. Pick a new HEAD SHA:
   ```bash
   gh api repos/alirezarezvani/ClaudeForge/commits/HEAD --jq .sha
   ```
2. For each of the 17 destination paths, fetch the corresponding upstream
   `skill/<path>` at the new SHA and overwrite the local file:
   ```bash
   gh api "repos/alirezarezvani/ClaudeForge/contents/skill/${path}?ref=${NEW_SHA}" \
     | python3 -c 'import json,sys,base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)["content"]))' \
     > "claude/skills/claude-md-enhancer/${path}"
   ```
3. Re-prepend the HTML-comment attribution header to each `.md` file with the
   new short SHA (first 7 chars).
4. Re-apply the SKILL.md frontmatter swap (`permissions:` → `allowed-tools:`).
5. Re-append the three pipelinekit overlay sections to SKILL.md
   (look for the `## Pipelinekit Overlay — ` sentinel — they sit at the end).
6. Update this NOTICE.md's `**Pinned SHA:**` line.
7. Commit with `chore: re-vendor alirezarezvani/ClaudeForge @ <short-sha>`.

---

## MIT License

Copyright (c) 2025 Alireza Rezvani

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
