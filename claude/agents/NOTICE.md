# Notice

The following agent files in this directory are vendored verbatim from:

**Upstream:** https://github.com/wshobson/agents
**Pinned SHA:** `08ded5e7b0fe57e7f40194775885eba539c3d8e7`
**Upstream paths:**
- plugins/cicd-automation/agents/deployment-engineer.md
- plugins/incident-response/agents/incident-responder.md
- plugins/debugging-toolkit/agents/dx-optimizer.md
- plugins/cicd-automation/agents/terraform-specialist.md
- plugins/cicd-automation/agents/cloud-architect.md
- plugins/cloud-infrastructure/agents/network-engineer.md
- plugins/api-testing-observability/agents/api-documenter.md
- plugins/application-performance/agents/performance-engineer.md
- plugins/backend-development/agents/test-automator.md
- plugins/comprehensive-review/agents/architect-review.md

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
