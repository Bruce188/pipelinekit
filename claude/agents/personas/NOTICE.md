# Notice

The files in this directory (excluding this NOTICE.md) are vendored from:

**Upstream:** https://github.com/alirezarezvani/claude-skills
**Pinned SHA:** `0d477a06589aa730b98e351f46985c5c937de0bf`
**Upstream paths:**

| Local file                  | Upstream path                                | Note |
|-----------------------------|----------------------------------------------|------|
| `devops.md`                 | `agents/personas/devops-engineer.md`         | Renamed locally (`devops-engineer.md` → `devops.md`) per pipelinekit naming convention; contents byte-exact. |
| `growth-marketer.md`        | `agents/personas/growth-marketer.md`         | Byte-exact. |
| `solo-founder.md`           | `agents/personas/solo-founder.md`            | Byte-exact. |
| `startup-cto.md`            | `agents/personas/startup-cto.md`             | Byte-exact. |

To re-vendor: pick a new HEAD SHA from `gh api repos/alirezarezvani/claude-skills/commits/HEAD`,
re-fetch each upstream path via `gh api repos/alirezarezvani/claude-skills/contents/<path>?ref=<new-SHA>`,
overwrite each local file (preserve the rename mapping above), update the SHA in this NOTICE,
and commit with `chore: re-vendor alirezarezvani/claude-skills @ <short-sha>`.

---

## License

The upstream repository `alirezarezvani/claude-skills` is distributed under the **MIT** license. The full upstream LICENSE text is reproduced below to satisfy attribution requirements.

MIT License

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
