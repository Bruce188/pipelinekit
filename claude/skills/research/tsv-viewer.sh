#!/usr/bin/env bash
# tsv-viewer.sh — One-shot generator: reads docs/research-results.tsv and emits
# a self-contained documentation/research-results.html with a sortable table,
# dynamic status filter checkboxes, light/dark CSS, and a best-effort
# browser-open hook.
#
# Flags:
#   --input  <path>   TSV input (default: docs/research-results.tsv)
#   --output <path>   HTML output (default: documentation/research-results.html)
#   --no-open         Suppress browser-open attempt after writing
#   --help            Print usage and exit 0
#
# Sort axes: iteration (synthesized 1-based row index), metric (col 2),
# memory (col 3). commit/status/description headers are NOT click-sortable.
# Cost is NOT a sort axis — it is not a TSV column. See docs/analysis-v69.md
# "Sort axes" for the design decision.
#
# No remote resources. No CDN. All CSS and JS are inline (F11 contract).
# Tests must always pass --no-open for hermeticity (no browser launched).

set -euo pipefail

INPUT="docs/research-results.tsv"
OUTPUT="documentation/research-results.html"
NO_OPEN=0

usage() {
  cat <<EOF
Usage: tsv-viewer.sh [OPTIONS]

Options:
  --input  <path>   TSV input file (default: docs/research-results.tsv)
  --output <path>   HTML output file (default: documentation/research-results.html)
  --no-open         Suppress browser-open after writing
  --help            Print this help and exit

Sort axes: iteration, metric, memory.
Cost is not a TSV column and is not a sort axis.
No remote resources; all CSS/JS are inline.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      INPUT="${2:?--input requires a path argument}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:?--output requires a path argument}"
      shift 2
      ;;
    --no-open)
      NO_OPEN=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown flag: $1" >&2
      exit 2
      ;;
  esac
done

if [ ! -f "$INPUT" ]; then
  echo "error: input TSV not found: $INPUT" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

python3 - "$INPUT" "$OUTPUT" <<'PYEOF'
import csv
import html
import sys
import os
import datetime

tsv_path = sys.argv[1]
html_path = sys.argv[2]

with open(tsv_path, newline='', encoding='utf-8') as f:
    reader = csv.reader(f, delimiter='\t')
    rows = list(reader)

if not rows:
    header = []
    data_rows = []
else:
    header = rows[0]
    data_rows = rows[1:]

unique_statuses = sorted(set(row[3] for row in data_rows if len(row) > 3))
n_rows = len(data_rows)
status_list = ', '.join(unique_statuses) if unique_statuses else 'none'

now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

# Build filter checkboxes
filter_html = ''
for s in unique_statuses:
    es = html.escape(s)
    filter_html += f'<label><input type="checkbox" checked data-status="{es}"> {es}</label>\n'

# Build table rows
tbody_html = ''
for i, row in enumerate(data_rows, start=1):
    commit_val  = html.escape(row[0]) if len(row) > 0 else ''
    metric_val  = html.escape(row[1]) if len(row) > 1 else ''
    memory_val  = html.escape(row[2]) if len(row) > 2 else ''
    status_val  = html.escape(row[3]) if len(row) > 3 else ''
    desc_val    = html.escape(row[4]) if len(row) > 4 else ''
    tbody_html += (
        f'<tr data-status="{status_val}">'
        f'<td>{i}</td>'
        f'<td>{commit_val}</td>'
        f'<td>{metric_val}</td>'
        f'<td>{memory_val}</td>'
        f'<td>{status_val}</td>'
        f'<td>{desc_val}</td>'
        f'</tr>\n'
    )

if n_rows == 0:
    table_or_empty = '<div class="empty">No iterations recorded yet.</div>'
else:
    table_or_empty = f'''<table id="results">
<thead>
<tr>
  <th data-sort="numeric">iteration ▲▼</th>
  <th>commit</th>
  <th data-sort="numeric">metric ▲▼</th>
  <th data-sort="numeric">memory ▲▼</th>
  <th>status</th>
  <th>description</th>
</tr>
</thead>
<tbody>
{tbody_html}</tbody>
</table>'''

page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>research-results</title>
<style>
:root {{
  --bg: #fff;
  --fg: #111;
  --accent: #0366d6;
  --surface: #f6f8fa;
  --border: #d0d7de;
  --text-muted: #6e7781;
  --link: #0969da;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0d1117;
    --fg: #e6edf3;
    --accent: #58a6ff;
    --surface: #161b22;
    --border: #30363d;
    --text-muted: #8b949e;
    --link: #2f81f7;
  }}
}}
body {{
  font-family: sans-serif;
  background: var(--bg);
  color: var(--fg);
  margin: 1.5rem;
}}
h1 {{ color: var(--accent); }}
p {{ color: var(--text-muted); }}
.filters {{ margin-bottom: 1rem; display: flex; flex-wrap: wrap; gap: 0.75rem; }}
.filters label {{ cursor: pointer; color: var(--fg); }}
table {{
  border-collapse: collapse;
  width: 100%;
}}
th, td {{
  border: 1px solid var(--border);
  padding: 0.4rem 0.6rem;
  text-align: left;
}}
th {{
  background: var(--surface);
  cursor: default;
}}
th[data-sort] {{
  cursor: pointer;
  user-select: none;
}}
th[data-sort]:hover {{ background: var(--border); }}
tr:hover {{ background: var(--surface); }}
.empty {{ color: var(--text-muted); font-style: italic; margin: 2rem 0; }}
footer {{ margin-top: 2rem; font-size: 0.8rem; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 0.5rem; }}
a {{ color: var(--link); }}
</style>
</head>
<body>
<h1>research-results</h1>
<p>{n_rows} iteration{"s" if n_rows != 1 else ""} · statuses: {html.escape(status_list)}</p>
<div class="filters">
{filter_html}</div>
{table_or_empty}
<footer>
  Generated: {now_utc} · Source: {html.escape(tsv_path)} ·
  Cost is not a TSV column; sort axes are iteration, metric, memory.
</footer>
<script>
(function() {{
  // Sort handler
  var table = document.getElementById('results');
  if (table) {{
    var tbody = table.querySelector('tbody');
    table.querySelectorAll('th[data-sort]').forEach(function(th) {{
      th._asc = true;
      th.addEventListener('click', function() {{
        var idx = Array.from(th.parentNode.children).indexOf(th);
        var isNum = th.getAttribute('data-sort') === 'numeric';
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function(a, b) {{
          var av = a.cells[idx] ? a.cells[idx].textContent : '';
          var bv = b.cells[idx] ? b.cells[idx].textContent : '';
          if (av === '') return 1;
          if (bv === '') return -1;
          if (isNum) {{
            var na = Number(av), nb = Number(bv);
            return th._asc ? na - nb : nb - na;
          }}
          return th._asc ? av.localeCompare(bv) : bv.localeCompare(av);
        }});
        th._asc = !th._asc;
        rows.forEach(function(r) {{ tbody.appendChild(r); }});
      }});
    }});
  }}

  // Filter handler
  document.querySelectorAll('.filters input').forEach(function(cb) {{
    cb.addEventListener('change', function() {{
      var enabled = new Set();
      document.querySelectorAll('.filters input:checked').forEach(function(c) {{
        enabled.add(c.getAttribute('data-status'));
      }});
      if (tbody) {{
        tbody.querySelectorAll('tr').forEach(function(row) {{
          row.style.display = enabled.has(row.getAttribute('data-status')) ? '' : 'none';
        }});
      }}
    }});
  }});
}})();
</script>
</body>
</html>
'''

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(page)
PYEOF

echo "wrote: $OUTPUT"

if [ "$NO_OPEN" -eq 0 ]; then
  ( xdg-open "$OUTPUT" || open "$OUTPUT" || cmd /c start "" "$OUTPUT" ) >/dev/null 2>&1 &
fi
