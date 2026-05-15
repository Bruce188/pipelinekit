---
name: ascii-diagram
description: Generate an ASCII architecture diagram for the current project or a described system
disable-model-invocation: true
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
