# /caveman-compress — Tier 1 compression algorithm

## Invocation
- Single-file: `/caveman-compress <path>` or `/caveman-compress <path> --in-place`.
- Default mode writes `<path>.compressed` sidecar (non-destructive).
- `--in-place` overwrites the source file via Write tool.
- Multi-file batching is NOT supported — caller loops if multiple files needed.

## Allowlist gate
Deterministic regex gate enforced by `claude/skills/caveman-mode/tier1_allowlist.sh`:
- Accept: `(^|/)CLAUDE\.md(\.template)?$` OR `(^|/)rules/[^/]+\.md$`.
- Reject: anything else (including `agents/*.md`, `skills/*/SKILL.md`, `commands/*.md`, arbitrary paths).
- Exit codes: 0 = accept; 2 = reject (with stderr refusal naming the rejected path).
- Algorithm step 1 runs `bash tier1_allowlist.sh <path>` and aborts on non-zero exit.

## Zone contract
The three-zone contract is sourced from `claude/snippets/caveman-subagent.md` (READ-ONLY here).
- **Zone 1** — code fences (triple-backtick blocks), inline backticks (`` `…` ``), URLs (`http(s)://…`), filesystem paths (`/foo`, `claude/...`, `~/.claude/...`, `docs/...`), command names with flags (`/caveman wenyan-ultra`, `git push --force`). PRESERVED byte-exact.
- **Zone 2** — narrative prose paragraphs. Rewritten to classical Chinese 文言 (Han characters U+4E00–U+9FFF mandatory).
- **Zone 3** — fragments, bullet items, status lines, table cells where prose-shaped. Rewritten to ultra English (drop articles, filler, hedging).

## Algorithm
1. Run `bash claude/skills/caveman-mode/tier1_allowlist.sh <path>`. On exit != 0, abort and propagate the rejection message.
2. Read the file via the Read tool (full file into memory).
3. Tokenize the file into zones:
   - YAML frontmatter (`---` … `---` at top) — pass through byte-identical.
   - Triple-fenced code blocks (`` ``` `` … `` ``` ``) — pass through byte-identical including fence-language tag.
   - Markdown headings (`# `, `## `, `### `) — pass through byte-identical (anchor preservation).
   - Inline backtick spans (`` `foo` ``) — pass through byte-identical.
   - URLs (`http(s)://…`) — pass through byte-identical.
   - Filesystem paths and command-with-flags tokens — pass through byte-identical.
   - Narrative prose paragraphs — classify as Zone 2 → rewrite to 文言.
   - Bullets, status lines, fragment paragraphs — classify as Zone 3 → rewrite to ultra English.
4. Compose the output by emitting tokens in order with Zone 1 byte-strings spliced verbatim.
5. Write the output:
   - Default (no flag): write to `<path>.compressed` via Write tool.
   - `--in-place`: overwrite `<path>` via Write tool.

## Verification
After rewrite, run these assertions:
- File shrank: `wc -c <path>.post` < `wc -c <path>.pre`.
- Zone 1 byte-identity (Python):
  ```python
  import re
  pre = open('/tmp/pre').read()
  post = open('<path>').read()
  for pat in [r'```[\s\S]*?```', r'`[^`]*`', r'https?://\S+']:
      for span in re.findall(pat, post):
          assert span in pre, f'Zone 1 violation: {span[:80]}'
  ```
- Anchor preservation: `diff <(grep -E '^#{1,3} ' /tmp/pre) <(grep -E '^#{1,3} ' <path>)` exits 0.

## Exit codes
- 0: compression complete and verified.
- 2: path rejected by Tier 1 allowlist.
- 1: any other failure (read error, write error, verification failure).
