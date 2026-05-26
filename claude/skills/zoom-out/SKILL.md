<!--
Vendored from mattpocock/skills @ e74f0061bb67222181640effa98c675bdb2fdaa7
Upstream path: skills/engineering/zoom-out/SKILL.md
License: MIT — Copyright (c) 2026 Matt Pocock
Source: https://github.com/mattpocock/skills/blob/e74f0061bb67222181640effa98c675bdb2fdaa7/skills/engineering/zoom-out/SKILL.md
Do not edit in place — re-vendor from upstream and bump the SHA.
-->

---
name: zoom-out
description: Tell the agent to zoom out and give broader context or a higher-level perspective. Use when you're unfamiliar with a section of code or need to understand how it fits into the bigger picture.
allowed-tools:
  - Read
  - Glob
  - Grep
disable-model-invocation: true
paths:
  - claude/skills/zoom-out/**
  - docs/zoom-out*.md
  - documentation/**
---

I don't know this area of code well. Go up a layer of abstraction. Give me a map of all the relevant modules and callers, using the project's domain glossary vocabulary.
