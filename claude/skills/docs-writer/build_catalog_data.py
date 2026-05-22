#!/usr/bin/env python3
"""
build_catalog_data.py — regenerate skill and agent catalog-grid snippet files.

Scans:
  claude/skills/*/SKILL.md         → snippets/skill-catalog-grid.html
  claude/agents/*.md               → snippets/agent-catalog-grid.html

Idempotent: every run produces byte-identical output (deterministic sort, no
timestamps, no random IDs). Safe to re-run at any time; CI uses --check mode.

Usage:
    python3 claude/skills/docs-writer/build_catalog_data.py           # write snippets
    python3 claude/skills/docs-writer/build_catalog_data.py --check   # verify in-place (CI)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

try:
    import yaml as _yaml_mod
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SNIPPETS_DIR = pathlib.Path(__file__).resolve().parent / "snippets"
SKILL_SNIPPET_PATH = SNIPPETS_DIR / "skill-catalog-grid.html"
AGENT_SNIPPET_PATH = SNIPPETS_DIR / "agent-catalog-grid.html"

# ---------------------------------------------------------------------------
# Taxonomy maps — inferred from name-prefix / suffix.
# Unknown names fall through to "misc" so new additions never break the build.
# ---------------------------------------------------------------------------
SKILL_SECTION_MAP: dict[str, str] = {
    # workflow orchestration
    "pipeline": "workflow",
    "analyze": "workflow",
    "create-plan": "workflow",
    "annotate-plan": "workflow",
    "implement-plan": "workflow",
    "review": "workflow",
    "ppr": "workflow",
    "post-merge": "workflow",
    "new-branch": "workflow",
    "document-release": "workflow",
    "handoff-create": "workflow",
    "context-dump": "workflow",
    "landing-report": "workflow",
    "learn": "workflow",
    "zoom-out": "workflow",
    # tdd / dev
    "tdd": "dev",
    "fix-issue": "dev",
    "simplify": "dev",
    "code-health": "dev",
    "research": "dev",
    "financial-data-analyst": "dev",
    "playwright": "dev",
    # ops / cloud
    "azure-ops": "ops",
    "vercel-ops": "ops",
    "railway-ops": "ops",
    "render-ops": "ops",
    "digitalocean-ops": "ops",
    "dependency-auditor": "ops",
    "secret-scanner": "ops",
    "test-hooks": "ops",
    "incident": "ops",
    # mobile
    "ios": "mobile",
    "expo": "mobile",
    # authoring / meta
    "docs-writer": "authoring",
    "write-a-skill": "authoring",
    "commit-conventions": "authoring",
    "security-conventions": "authoring",
    "dotnet-conventions": "authoring",
    "init": "authoring",
    "README": "authoring",
    "build-hook": "authoring",
    "update-config": "authoring",
    "persona": "authoring",
    # ai-tools / assistant
    "caveman-mode": "ai-tools",
    "claude-md-enhancer": "ai-tools",
    "ascii-diagram": "ai-tools",
    "schedule": "ai-tools",
    "loop": "ai-tools",
    "verify": "ai-tools",
    "run": "ai-tools",
}

AGENT_SECTION_MAP: dict[str, str] = {
    # review / quality
    "code-reviewer": "review",
    "security-auditor": "review",
    "test-engineer": "review",
    "performance-tuner": "review",
    "spec-tracer": "review",
    "karpathy-reviewer": "review",
    # tdd
    "tdd-test-writer": "dev",
    "tdd-implementer": "dev",
    "refactor-expert": "dev",
    "debugger": "dev",
    # docs / content
    "docs-writer": "docs",
    # ops / cloud
    "azure-deployment-engineer": "ops",
    "vercel-deployment-engineer": "ops",
    "railway-deployment-engineer": "ops",
    "render-deployment-engineer": "ops",
    "digitalocean-deployment-engineer": "ops",
    "deployment-engineer": "ops",
    "incident-responder": "ops",
    # architecture / data
    "architect": "architecture",
    "data-pipeline-engineer": "data",
    "trading-bot-developer": "data",
    # mobile
    "mobile-dev": "mobile",
    # meta
    "claude-md-guardian": "meta",
}


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

def parse_frontmatter(path: pathlib.Path) -> dict | None:
    """
    Parse YAML frontmatter from a markdown file.
    Prefers PyYAML when available; falls back to a minimal hand-rolled parser.
    Returns None when no frontmatter block is found.

    Tolerates leading HTML comment blocks (e.g. vendored files that start with
    <!-- ... --> before the YAML --- block).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Strip any leading HTML comment blocks before the YAML frontmatter.
    # Some vendored files start with <!-- ... --> then \n---\n.
    stripped = text
    while stripped.lstrip().startswith("<!--"):
        end = stripped.find("-->")
        if end == -1:
            break
        stripped = stripped[end + 3:].lstrip()

    # Find the YAML block between the opening and closing ---
    if not stripped.startswith("---"):
        return None
    lines = stripped.splitlines()
    try:
        end_idx = lines.index("---", 1)
    except ValueError:
        return None

    yaml_block = "\n".join(lines[1:end_idx])

    if _HAVE_YAML:
        try:
            result = _yaml_mod.safe_load(yaml_block)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    # Fallback: hand-rolled key: value parser.
    # Handles simple scalars + block-scalar values (collapses to single line).
    result: dict = {}
    i = 0
    fm_lines = yaml_block.splitlines()
    while i < len(fm_lines):
        line = fm_lines[i]
        m = re.match(r'^([A-Za-z0-9_-]+)\s*:\s*(.*)$', line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val == "|" or val == ">":
                # Block scalar: collect indented continuation lines
                parts: list[str] = []
                i += 1
                while i < len(fm_lines) and fm_lines[i].startswith("  "):
                    parts.append(fm_lines[i].strip())
                    i += 1
                result[key] = " ".join(parts)
                continue
            result[key] = val
        i += 1
    return result or None


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _collapse_description(desc: str) -> str:
    """Normalise a description: strip surrounding quotes, collapse whitespace."""
    desc = desc.strip().strip('"').strip("'")
    desc = re.sub(r'\s+', ' ', desc)
    return desc


def collect_skills() -> list[dict]:
    """
    Scan claude/skills/*/SKILL.md and return a sorted list of skill dicts.
    Keys: name, description, section.
    """
    items: list[dict] = []
    skill_glob = sorted((REPO_ROOT / "claude" / "skills").glob("*/SKILL.md"))
    for path in skill_glob:
        fm = parse_frontmatter(path)
        if not fm or not fm.get("name"):
            continue
        name = str(fm["name"]).strip()
        desc = _collapse_description(str(fm.get("description", "")))
        section = SKILL_SECTION_MAP.get(name, "misc")
        items.append({"name": name, "description": desc, "section": section})
    # Deterministic sort by name
    return sorted(items, key=lambda x: x["name"].lower())


def collect_agents() -> list[dict]:
    """
    Scan claude/agents/*.md and return a sorted list of agent dicts.
    Skips files without a 'name:' frontmatter key (e.g. NOTICE.md, README.md,
    deployment-engineer.md which is a documentation-only base file).
    Keys: name, description, section.
    """
    items: list[dict] = []
    agent_glob = sorted((REPO_ROOT / "claude" / "agents").glob("*.md"))
    for path in agent_glob:
        fm = parse_frontmatter(path)
        if not fm or not fm.get("name"):
            continue
        name = str(fm["name"]).strip()
        desc = _collapse_description(str(fm.get("description", "")))
        section = AGENT_SECTION_MAP.get(name, "misc")
        items.append({"name": name, "description": desc, "section": section})
    return sorted(items, key=lambda x: x["name"].lower())


# ---------------------------------------------------------------------------
# Snippet rendering
# ---------------------------------------------------------------------------

_SKILL_CSS_CLASS = "pkit-skg"
_AGENT_CSS_CLASS = "pkit-akg"
_SKILL_MOUNT = "skill-catalog-grid"
_AGENT_MOUNT = "agent-catalog-grid"


def _html_escape(s: str) -> str:
    """Minimal HTML escaping for text content and attribute values."""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _render_snippet(kind: str, items: list[dict]) -> str:
    """
    Emit the full HTML snippet string for 'skill' or 'agent'.

    Cards are pre-rendered as static HTML (one <div data-X-card> per item) so
    grep-based tests can count them. The IIFE uses show/hide toggling on the
    pre-rendered cards rather than recreating them from the JSON island.
    JSON island is still present for forward-compat (e.g. --check mode, extensions).

    Mirrors tutorial-cards.html grid layout + comparison-tabs.html JSON-island.
    Uses only CSS custom properties from the template (no hex colors).
    """
    is_skill = kind == "skill"
    css_class = _SKILL_CSS_CLASS if is_skill else _AGENT_CSS_CLASS
    mount = _SKILL_MOUNT if is_skill else _AGENT_MOUNT
    card_attr = f"data-{kind}-card"
    label_singular = "Skill" if is_skill else "Agent"
    label_plural = "Skills" if is_skill else "Agents"
    search_placeholder = f"Search {label_plural.lower()}…"
    empty_msg = f"No {label_plural.lower()} match your filter."

    # Collect section names in a deterministic order (alphabetical)
    sections = sorted({item["section"] for item in items})

    json_payload = json.dumps(items, ensure_ascii=False, indent=2)

    lines: list[str] = []
    lines.append(f'<!-- snippet:{mount}')
    lines.append(f'     {label_plural} catalog grid — auto-generated by build_catalog_data.py.')
    lines.append(f'     Re-run that script to refresh this file after adding/removing {label_plural.lower()}.')
    lines.append('')
    lines.append('     Placeholder usage in markdown source:')
    lines.append(f'       <div data-snippet="{mount}"></div>')
    lines.append('-->')
    lines.append(f'<div class="{css_class}" data-snippet-mount="{mount}">')

    # ----- Scoped CSS -----
    lines.append('  <style>')
    lines.append(f'    .{css_class} {{')
    lines.append('      margin: 1.5rem 0;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-toolbar {{')
    lines.append('      display: flex;')
    lines.append('      flex-wrap: wrap;')
    lines.append('      gap: 0.5rem;')
    lines.append('      margin-bottom: 1rem;')
    lines.append('      align-items: center;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-search {{')
    lines.append('      flex: 1;')
    lines.append('      min-width: 180px;')
    lines.append('      padding: 0.4rem 0.7rem;')
    lines.append('      background: var(--bg-elev);')
    lines.append('      border: 1px solid var(--border);')
    lines.append('      border-radius: var(--radius-sm);')
    lines.append('      color: var(--fg);')
    lines.append('      font-family: var(--sans);')
    lines.append('      font-size: 0.88rem;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-search:focus {{')
    lines.append('      outline: none;')
    lines.append('      border-color: var(--accent);')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-chips {{')
    lines.append('      display: flex;')
    lines.append('      flex-wrap: wrap;')
    lines.append('      gap: 0.3rem;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-chip {{')
    lines.append('      padding: 0.25rem 0.6rem;')
    lines.append('      border-radius: 999px;')
    lines.append('      font-size: 0.75rem;')
    lines.append('      font-weight: 600;')
    lines.append('      cursor: pointer;')
    lines.append('      border: 1px solid var(--border);')
    lines.append('      background: var(--bg);')
    lines.append('      color: var(--fg-muted);')
    lines.append('      transition: all 150ms ease;')
    lines.append('      white-space: nowrap;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-chip:hover {{')
    lines.append('      border-color: var(--accent);')
    lines.append('      color: var(--accent);')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-chip.active {{')
    lines.append('      background: var(--accent-soft);')
    lines.append('      border-color: var(--accent);')
    lines.append('      color: var(--accent);')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-grid {{')
    lines.append('      display: grid;')
    lines.append('      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));')
    lines.append('      gap: 1rem;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-card {{')
    lines.append('      background: var(--bg-elev);')
    lines.append('      border: 1px solid var(--border);')
    lines.append('      border-radius: var(--radius);')
    lines.append('      padding: 1rem;')
    lines.append('      display: flex;')
    lines.append('      flex-direction: column;')
    lines.append('      gap: 0.4rem;')
    lines.append('      transition: border-color 150ms ease, transform 150ms ease;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-card:hover {{')
    lines.append('      border-color: var(--accent);')
    lines.append('      transform: translateY(-1px);')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-card[hidden] {{')
    lines.append('      display: none;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-name {{')
    lines.append('      font-size: 0.95rem;')
    lines.append('      font-weight: 700;')
    lines.append('      color: var(--fg);')
    lines.append('      font-family: var(--mono);')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-desc {{')
    lines.append('      font-size: 0.82rem;')
    lines.append('      color: var(--fg-muted);')
    lines.append('      line-height: 1.45;')
    lines.append('      flex: 1;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-section-badge {{')
    lines.append('      font-size: 0.7rem;')
    lines.append('      font-weight: 600;')
    lines.append('      text-transform: uppercase;')
    lines.append('      letter-spacing: 0.05em;')
    lines.append('      color: var(--fg-subtle);')
    lines.append('      border: 1px solid var(--border);')
    lines.append('      border-radius: 999px;')
    lines.append('      padding: 0.1rem 0.45rem;')
    lines.append('      align-self: flex-start;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-empty-msg {{')
    lines.append('      grid-column: 1 / -1;')
    lines.append('      text-align: center;')
    lines.append('      color: var(--fg-subtle);')
    lines.append('      font-size: 0.88rem;')
    lines.append('      padding: 2rem 0;')
    lines.append('      display: none;')
    lines.append('    }')
    lines.append(f'    .{css_class} .{css_class}-count {{')
    lines.append('      font-size: 0.78rem;')
    lines.append('      color: var(--fg-subtle);')
    lines.append('      margin-top: 0.5rem;')
    lines.append('    }')
    lines.append('  </style>')

    # ----- Toolbar (search + filter chips) -----
    lines.append(f'  <div class="{css_class}-toolbar">')
    lines.append(f'    <input class="{css_class}-search" type="search" placeholder="{search_placeholder}" aria-label="{search_placeholder}">')
    lines.append(f'    <div class="{css_class}-chips">')
    lines.append(f'      <button class="{css_class}-chip active" data-section="all">All</button>')
    for section in sections:
        lines.append(f'      <button class="{css_class}-chip" data-section="{section}">{_html_escape(section)}</button>')
    lines.append('    </div>')
    lines.append('  </div>')

    # ----- Card grid — pre-rendered static HTML (one card per item) -----
    lines.append(f'  <div class="{css_class}-grid" role="list" aria-label="{label_plural} catalog">')
    for item in items:
        name_escaped = _html_escape(item["name"])
        desc_escaped = _html_escape(item["description"])
        section_escaped = _html_escape(item["section"])
        lines.append(f'    <div class="{css_class}-card" {card_attr} data-section="{section_escaped}" data-name="{name_escaped}">')
        lines.append(f'      <span class="{css_class}-name">{name_escaped}</span>')
        lines.append(f'      <p class="{css_class}-desc">{desc_escaped}</p>')
        lines.append(f'      <span class="{css_class}-section-badge">{section_escaped}</span>')
        lines.append('    </div>')
    lines.append(f'    <div class="{css_class}-empty-msg">{_html_escape(empty_msg)}</div>')
    lines.append('  </div>')
    lines.append(f'  <p class="{css_class}-count">{len(items)} {label_singular.lower()}s</p>')

    # ----- JSON island (for --check mode + future extensions) -----
    lines.append(f'  <script type="application/json" data-catalog-data>')
    lines.append(json_payload)
    lines.append('  </script>')

    lines.append('</div>')

    # ----- Interactive enhancement IIFE -----
    # Wires up search (debounced 120ms) and filter chips to show/hide pre-rendered cards.
    lines.append('')
    lines.append('<script>')
    lines.append('(function() {')
    lines.append("  'use strict';")
    lines.append(f"  const roots = document.querySelectorAll('.{css_class}[data-snippet-mount=\"{mount}\"]');")
    lines.append("  const root = roots[roots.length - 1];")
    lines.append("  if (!root || root.dataset.pkitInit) return;")
    lines.append("  root.dataset.pkitInit = '1';")
    lines.append('')
    lines.append(f"  const cards = Array.from(root.querySelectorAll('[{card_attr}]'));")
    lines.append(f"  const emptyMsg = root.querySelector('.{css_class}-empty-msg');")
    lines.append(f"  const countEl = root.querySelector('.{css_class}-count');")
    lines.append(f"  const searchEl = root.querySelector('.{css_class}-search');")
    lines.append(f"  const chips = root.querySelectorAll('.{css_class}-chip');")
    lines.append("  let activeSection = 'all';")
    lines.append("  let searchTerm = '';")
    lines.append("  let debounceTimer = null;")
    lines.append('')
    lines.append("  function applyFilters() {")
    lines.append("    const q = searchTerm.toLowerCase();")
    lines.append("    let visible = 0;")
    lines.append("    cards.forEach(card => {")
    lines.append("      const section = card.dataset.section || '';")
    lines.append("      const name = (card.dataset.name || '').toLowerCase();")
    lines.append("      const desc = (card.querySelector('p') || {}).textContent || '';")
    lines.append("      const matchSection = activeSection === 'all' || section === activeSection;")
    lines.append("      const matchSearch = !q || name.includes(q) || desc.toLowerCase().includes(q);")
    lines.append("      const show = matchSection && matchSearch;")
    lines.append("      card.hidden = !show;")
    lines.append("      if (show) visible++;")
    lines.append("    });")
    lines.append(f"    if (emptyMsg) emptyMsg.style.display = visible === 0 ? 'block' : 'none';")
    lines.append(f"    if (countEl) countEl.textContent = visible + ' of ' + cards.length + ' {label_singular.lower()}s shown';")
    lines.append("  }")
    lines.append('')
    lines.append("  chips.forEach(chip => {")
    lines.append("    chip.addEventListener('click', () => {")
    lines.append("      activeSection = chip.dataset.section;")
    lines.append("      chips.forEach(c => c.classList.toggle('active', c.dataset.section === activeSection));")
    lines.append("      applyFilters();")
    lines.append("    });")
    lines.append("  });")
    lines.append('')
    lines.append("  searchEl && searchEl.addEventListener('input', () => {")
    lines.append("    clearTimeout(debounceTimer);")
    lines.append("    debounceTimer = setTimeout(() => {")
    lines.append("      searchTerm = searchEl.value;")
    lines.append("      applyFilters();")
    lines.append("    }, 120);")
    lines.append("  });")
    lines.append('')
    lines.append("  applyFilters();")
    lines.append('})();')
    lines.append('</script>')

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate skill-catalog-grid.html + agent-catalog-grid.html snippets."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="No-write mode: verify existing snippets match what would be generated. Exit 1 if different.",
    )
    args = parser.parse_args()

    skills = collect_skills()
    agents = collect_agents()

    skill_html = _render_snippet("skill", skills)
    agent_html = _render_snippet("agent", agents)

    if args.check:
        ok = True
        for path, content, label in [
            (SKILL_SNIPPET_PATH, skill_html, "skill-catalog-grid.html"),
            (AGENT_SNIPPET_PATH, agent_html, "agent-catalog-grid.html"),
        ]:
            if not path.exists():
                print(f"MISSING: {path}", file=sys.stderr)
                ok = False
            elif path.read_text(encoding="utf-8") != content:
                print(f"STALE: {path} differs from generated output", file=sys.stderr)
                ok = False
            else:
                print(f"OK: {path}")
        return 0 if ok else 1

    # Write mode (default)
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content, label in [
        (SKILL_SNIPPET_PATH, skill_html, "skill-catalog-grid.html"),
        (AGENT_SNIPPET_PATH, agent_html, "agent-catalog-grid.html"),
    ]:
        path.write_text(content, encoding="utf-8")
        print(f"Written: {path}  ({len(skills) if 'skill' in label else len(agents)} items)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
