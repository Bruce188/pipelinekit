<!--
Vendored from mattpocock/skills @ e74f0061bb67222181640effa98c675bdb2fdaa7
Upstream path: skills/engineering/tdd/refactoring.md
License: MIT — Copyright (c) 2026 Matt Pocock
Source: https://github.com/mattpocock/skills/blob/e74f0061bb67222181640effa98c675bdb2fdaa7/skills/engineering/tdd/refactoring.md
Do not edit in place — re-vendor from upstream and bump the SHA.
-->

# Refactor Candidates

After TDD cycle, look for:

- **Duplication** → Extract function/class
- **Long methods** → Break into private helpers (keep tests on public interface)
- **Shallow modules** → Combine or deepen
- **Feature envy** → Move logic to where data lives
- **Primitive obsession** → Introduce value objects
- **Existing code** the new code reveals as problematic
