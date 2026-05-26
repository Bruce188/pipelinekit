---
name: caveman-compress
description: Compress a Tier 1 source file (CLAUDE.md* | rules/*.md) per the three-zone contract.
argument-hint: <file> [--in-place]
---

Invoke the `caveman-mode` skill in `compress` mode against `$ARGUMENTS`.

The skill body at `claude/skills/caveman-mode/compress.md` defines the algorithm:
1. Gate the path via `claude/skills/caveman-mode/tier1_allowlist.sh` (exit 2 on reject).
2. Read the file, tokenize into Zone 1 / Zone 2 / Zone 3 per the three-zone contract.
3. Rewrite Zone 2 prose to classical Chinese 文言 and Zone 3 fragments to ultra English; preserve every Zone 1 byte-string verbatim.
4. Write `<file>.compressed` by default, or overwrite source if `--in-place` is present.

See `claude/skills/caveman-mode/compress.md` for the full algorithm and verification gates.
