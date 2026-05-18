<!-- Adopted from rohitg00/agentmemory @ TBD — MIT (Copyright <YYYY> rohitg00). See claude/lib/agentmemory/NOTICE.md. -->

# Notice — agentmemory

The files in this directory (excluding this `NOTICE.md` and `README.md`) will be
vendored from:

**Upstream:** https://github.com/rohitg00/agentmemory
**Pinned SHA:** TBD
**Upstream paths:** _TBD — upstream file enumeration deferred to follow-up iteration. Today this directory contains only `NOTICE.md` and `README.md`._

AgentMemory is a community project (NOT Anthropic-official). Review upstream
before sandbox use and PIN the version to a specific commit/release for
reproducibility.

## Pipelinekit deltas (documented so re-vendoring stays mechanical)

Vendoring skeleton only — no upstream files copied yet. SHA pinning and the
actual file copy land in a follow-up iteration. When the follow-up runs:

1. **HTML-comment attribution header** prepended to each `.md` file. Pattern:

   ```
   <!-- Adopted from rohitg00/agentmemory @ <short-sha> — MIT (Copyright <YYYY> rohitg00). See claude/lib/agentmemory/NOTICE.md. -->
   ```

2. **Mode-selection wiring** — the follow-up iteration decides whether the
   integration uses "same store" (vector index rebuilt from the markdown
   memory files) or "separate store" (independent vector DB). The choice
   is captured in `.mcp.json.template` `AGENTMEMORY_STORE_MODE` env var.

3. **Plain-markdown inspectability preserved.** Per the
   `claude/lib/agentmemory/README.md` complementarity rules, the flat-file
   `~/.claude/memory/<slug>/` system remains the canonical write path
   regardless of the chosen mode.

## Re-vendor procedure

To re-vendor (e.g., when the follow-up iteration lands the first real pin):

1. Pick a new HEAD SHA:
   ```bash
   gh api repos/rohitg00/agentmemory/commits/HEAD --jq .sha
   ```
2. For each upstream path (enumerated in `**Upstream paths:**` above), fetch
   the file at the new SHA and write it into this directory:
   ```bash
   gh api "repos/rohitg00/agentmemory/contents/${path}?ref=${NEW_SHA}" \
     | python3 -c 'import json,sys,base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)["content"]))' \
     > "claude/lib/agentmemory/${path}"
   ```
3. Re-prepend the HTML-comment attribution header to each `.md` file with the
   new short SHA (first 7 chars).
4. Update this NOTICE.md's `**Pinned SHA:**` line.
5. Commit with `chore: re-vendor rohitg00/agentmemory @ <short-sha>`.

---

## MIT License

Copyright (c) <YYYY> rohitg00

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
