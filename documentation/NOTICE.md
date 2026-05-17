# Notice

The files in this directory under names `SKILL_PIPELINE.md` and `SKILL-AUTHORING-STANDARD.md` are vendored verbatim from:

**Upstream:** https://github.com/alirezarezvani/claude-skills
**Pinned SHA:** `0d477a06589aa730b98e351f46985c5c937de0bf`
**Upstream paths:**
- SKILL_PIPELINE.md
- SKILL-AUTHORING-STANDARD.md

To re-vendor: pick a new HEAD SHA from `gh api repos/alirezarezvani/claude-skills/commits/HEAD`,
re-fetch each upstream path via `gh api repos/alirezarezvani/claude-skills/contents/<path>?ref=<new-SHA>`,
overwrite each local file (keep the HTML-comment attribution header at top, update the SHA),
and commit with `chore: re-vendor claude-skills @ <short-sha>`.

Other files in this directory (`review-cost.md`) are pipelinekit-native and not covered by this notice.

This standard pairs with `claude/skills/write-a-skill/SKILL.md` (vendored from mattpocock/skills) — the two upstreams are distinct.

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
