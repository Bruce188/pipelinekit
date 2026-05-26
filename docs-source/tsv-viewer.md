<!--
diataxis: how-to
-->
# TSV Viewer

`tsv-viewer.sh` reads a research-results TSV file and generates a self-contained HTML page with a sortable, filterable table, light/dark CSS, and an optional browser-open hook.

<div data-snippet="terminal-simulator"></div>

---

## Synopsis

```
claude/skills/research/tsv-viewer.sh [OPTIONS]
```

## Options

| Flag | Argument | Default | Description |
|------|----------|---------|-------------|
| `--input` | `<path>` | `docs/research-results.tsv` | TSV file to read |
| `--output` | `<path>` | `documentation/research-results.html` | HTML file to write |
| `--no-open` | — | off | Suppress the browser-open attempt after writing |
| `--help` | — | — | Print usage and exit |

## How to Run

From the repo root:

```bash
# Default — reads docs/research-results.tsv, writes documentation/research-results.html
claude/skills/research/tsv-viewer.sh

# Custom output path, no browser launch
claude/skills/research/tsv-viewer.sh --output /tmp/preview.html --no-open

# Point at a different TSV
claude/skills/research/tsv-viewer.sh --input docs/my-results.tsv
```

The script requires Python 3 on `PATH`. It creates any missing parent directories for the output file automatically.

## TSV Format

The input file must be tab-separated with a header row. Expected columns (0-indexed):

| # | Column | Sortable |
|---|--------|---------|
| 0 | commit | no |
| 1 | metric | yes (numeric) |
| 2 | memory | yes (numeric) |
| 3 | status | filter only |
| 4 | description | no |

A synthesized `iteration` column (1-based row index) is prepended in the HTML output and is also click-sortable.

## Output Description

The generated HTML file is fully self-contained — no CDN or remote assets. It includes:

- A sortable table with click-to-sort headers on `iteration`, `metric`, and `memory` columns. Clicking the same header toggles ascending/descending order.
- Dynamic status filter checkboxes above the table. Each unique value in the `status` column gets its own checkbox; unchecking hides matching rows instantly.
- Light/dark CSS that follows the OS `prefers-color-scheme` media query with no JavaScript required for theming.
- A generation timestamp (UTC) and row count in the page footer.

## Browser Open Behavior

After writing the HTML file the script attempts to open it in the default browser using `xdg-open` (Linux), `open` (macOS), or `start` (Windows/WSL). Pass `--no-open` to suppress this. Tests must always pass `--no-open` to remain hermetic.

## Notes

- `cost` is intentionally absent from the table and is not a sort axis — it is not a TSV column.
- Passing an unknown flag exits with code 2.
- Passing a missing `--input` file exits with code 1.

## Pipelinekit command cheatsheet

Filter by `research`, `ppr`, or `tsv` to surface the commands you reach for when shepherding a research-loop iteration to publish.

<div data-snippet="command-cheatsheet"></div>
