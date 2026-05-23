# Feature History

<!-- richness budget: spatial timeline + visual-token status pills + interactive collapsible-details (≥ 2 target) -->

Rendered audit trail for pipelinekit features. Each merged feature appears
below as its own H2 with a `<details>` collapsible body. The pipeline appends
new entries automatically via `claude/lib/pipeline/features_pruner.py` during
`/post-merge` Step 12.

## Timeline

Spatial overview of recent feature merges (left to right). Built as inline SVG
so it renders standalone without any client dependencies.

<svg viewBox="0 0 800 200" data-snippet-mount="timeline-scrubber" aria-label="feature merge timeline" style="width:100%;max-width:800px;height:auto;">
  <line x1="20" y1="100" x2="780" y2="100" stroke="currentColor" stroke-width="2" />
  <g fill="currentColor" font-size="10" text-anchor="middle">
    <circle cx="80"  cy="100" r="4"/><text x="80"  y="120">F1</text>
    <circle cx="150" cy="100" r="4"/><text x="150" y="120">F2</text>
    <circle cx="220" cy="100" r="4"/><text x="220" y="120">F3</text>
    <circle cx="290" cy="100" r="4"/><text x="290" y="120">F4</text>
    <circle cx="360" cy="100" r="4"/><text x="360" y="120">F5</text>
    <circle cx="430" cy="100" r="4"/><text x="430" y="120">F6</text>
    <circle cx="500" cy="100" r="4"/><text x="500" y="120">F7</text>
    <circle cx="570" cy="100" r="4"/><text x="570" y="120">F8</text>
    <circle cx="640" cy="100" r="4"/><text x="640" y="120">F9</text>
    <circle cx="710" cy="100" r="4"/><text x="710" y="120">F10</text>
    <circle cx="770" cy="100" r="4"/><text x="770" y="120">F11</text>
  </g>
</svg>

## Status legend

<span class="status-pill status-merged">merged</span>
&nbsp; <span class="status-pill status-in-progress">in-progress</span>
&nbsp; <span class="status-pill status-blocked">blocked</span>

## Features

Per-feature sections (backfilled and ongoing) follow. Each H2 wraps its body
in `<details><summary>` so the page stays scannable as the audit trail grows.

<details>
<summary><span class="status-pill status-merged">scaffold</span> &nbsp; about this page</summary>

This page is auto-maintained by `claude/lib/pipeline/features_pruner.py`. New
merged-feature blocks land here as the pipeline runs `/post-merge` Step 12.
The skeleton ships with zero per-feature entries; Task 2.1 of the
fix/docs-workflow-hygiene plan backfills the F1-F11 history below.

</details>

<!-- Per-feature H2 sections injected by Task 2.1 backfill below this comment. -->
