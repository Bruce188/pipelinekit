---
name: ascii-diagram
description: Generate an ASCII architecture diagram for the current project or a described system
disable-model-invocation: true
paths:
  - claude/skills/ascii-diagram/**
  - docs-source/**
  - documentation/**
---

Generate an ASCII architecture diagram for: $ARGUMENTS

If no arguments provided, analyze the current project structure.

Steps:
1. Read the project's key entry points, config files, and directory structure
2. Identify the main components, their relationships, and data flow
3. Generate a clean ASCII diagram using box-drawing characters

Diagram conventions:
- Use `+--+`, `|`, `---` for boxes and connections
- Use `-->` for data flow direction
- Use `[Component]` for external services
- Group related components visually
- Keep width under 100 characters for terminal readability
- Add a brief legend if symbols aren't self-explanatory

Output the diagram directly. If the user wants it persisted, they'll say where.

---

## Deeper Component Analysis

When the requested diagram covers more than a single module — e.g. service-to-service messaging, plugin lifecycle, multi-process orchestration — surface globbing of imports will not capture the actual edges. In that case, dispatch the `architect` agent with: (a) the user's prompt verbatim, (b) the project's entry-point files, (c) any existing `analysis.md` or PRP from `docs/`. Use the architect's output as the spine of the ASCII diagram.

The surface-glob path (Steps 1-3 above) remains the default for simple intra-module diagrams. Use the architect dispatch only when:
- The user's request mentions "system-level", "service graph", "full architecture", or "deep" analysis, OR
- Surface globbing yields fewer than 3 meaningful edges and the project clearly spans multiple processes or services.

After receiving the architect's `<task-notification>`, incorporate its component diagram and data-flow notes into the final ASCII output using the conventions above.
