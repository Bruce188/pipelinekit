# research/temp-2026-05-19

This is a long-lived demo branch referenced by the `/ppr --research` walk-through
in the [tsv-viewer documentation](https://github.com/Bruce188/pipelinekit/blob/main/documentation/tsv-viewer.html)
and [/ppr --research flag documentation](https://github.com/Bruce188/pipelinekit/blob/main/documentation/ppr-research-flag.html).

When the terminal-simulator on either page plays back its scripted session, it
emits this URL as the "branch published" destination. Clicking that URL lands here.

## What's in this branch

- **`research-keep.tsv`** — the 12 keep-rows that `/ppr --research --no-dry-run --research-tag temp`
  would have filtered out of `docs/research-results.tsv` and committed. Each row carries
  a synthetic commit SHA, a synthetic metric (0.0-1.0 — higher is better), a memory
  proxy (MB), the row's keep/discard status, and a short description.

- **`research-keep.html`** — the same 12 keep-rows passed through `tsv-viewer.sh`,
  rendered as a self-contained HTML page with a sortable table, status filter
  checkboxes, and light/dark CSS. No CDN, no remote assets — open it locally or
  view it via [raw.githack.com](https://raw.githack.com/Bruce188/pipelinekit/research/temp-2026-05-19/research-keep.html).

## Why a branch?

`/ppr --research` is designed to NOT open a PR — research branches stay parked for
per-branch human review. The commit message format and branch slug shape
(`research/<tag>-YYYY-MM-DD`) are part of the contract documented at
[`docs-source/ppr-research-flag.md`](https://github.com/Bruce188/pipelinekit/blob/main/docs-source/ppr-research-flag.md).
