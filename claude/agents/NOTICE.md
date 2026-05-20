# Notice

The following agent files in this directory are vendored verbatim from:

**Upstream:** https://github.com/wshobson/agents
**Pinned SHA:** `08ded5e7b0fe57e7f40194775885eba539c3d8e7`
**Upstream paths:**
- plugins/cicd-automation/agents/deployment-engineer.md
- plugins/incident-response/agents/incident-responder.md

To re-vendor: pick a new HEAD SHA from `gh api repos/wshobson/agents/commits/HEAD`,
re-fetch each upstream path via `gh api repos/wshobson/agents/contents/<path>?ref=<new-SHA>`,
overwrite each local file (keep the HTML-comment attribution header at top, update the SHA),
and commit with `chore: re-vendor wshobson/agents @ <short-sha>`.

---

## MIT License

Copyright (c) 2024 Seth Hobson

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

---

# Additional vendor — alirezarezvani/ClaudeForge

`claude-md-guardian.md` in this directory is vendored from:

**Upstream:** https://github.com/alirezarezvani/ClaudeForge
**Pinned SHA:** `6eb741b46cd8dcdb444be6f004b481a0b589a18d`
**Upstream path:** `agent/claude-md-guardian.md`
**License:** MIT — Copyright (c) 2025 Alireza Rezvani.

The full MIT License text and the related skill-level notice are in
`claude/skills/claude-md-enhancer/NOTICE.md`.

## Pipelinekit deltas (so re-vendoring stays mechanical)

1. **HTML-comment attribution header** prepended:
   `<!-- Adopted from alirezarezvani/ClaudeForge @ 6eb741b — MIT (Copyright 2025 Alireza Rezvani). See claude/agents/NOTICE.md. -->`
2. **Frontmatter rewrite:** upstream's `permissions:` block, `hooks:` block,
   and the fields `color`, `field`, `expertise`, `fork_safe` are dropped.
   `model: haiku` is upgraded to `model: sonnet`. New `tools: Read, Grep,
   Glob, Bash` line is added. `description:` is tightened to "drift detection
   and best-practices audit" framing.
3. **Pipelinekit integration section** `## Pipelinekit Integration — /review`
   appended to the END of the agent body. Documents the pipelinekit review
   schema and the `## CLAUDE.md Audit` filing convention.

## Re-vendor procedure

To re-vendor (e.g., when upstream ships a guardian improvement):

1. Pick a new HEAD SHA: `gh api repos/alirezarezvani/ClaudeForge/commits/HEAD --jq .sha`
2. Fetch the upstream body:
   ```bash
   gh api "repos/alirezarezvani/ClaudeForge/contents/agent/claude-md-guardian.md?ref=${NEW_SHA}" \
     | python3 -c 'import json,sys,base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)["content"]))' \
     > /tmp/upstream-guardian.md
   ```
3. Manually re-apply the frontmatter rewrite (drop `permissions`, `hooks`,
   `color`, `field`, `expertise`, `fork_safe`; ensure `model: sonnet` and
   `tools: ...`).
4. Re-prepend the HTML-comment attribution header (update the short SHA).
5. Re-append the `## Pipelinekit Integration — /review` section
   (sentinel header — find it at the end of the previous version's file).
6. Update this NOTICE.md's `**Pinned SHA:**` line.
7. Commit with `chore: re-vendor alirezarezvani/ClaudeForge guardian @ <short-sha>`.
