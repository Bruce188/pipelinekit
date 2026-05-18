---
version: 3
created: 2026-05-01
---

# Analysis

## 1. Objective

Enable /pipeline to auto-extract a draft charter from prior workflow artifacts when no charter exists yet. This removes the need to run the full 9-topic discovery loop for projects that already have analysis and plan documents.

## 2. Constraints

**PRESERVE:**
- Existing skip-condition ladder for Step 0 must remain intact
- No behavior change for --no-charter users
- Pure stdlib only; no LLM calls in extraction

**AVOID:**
- Overwriting an existing docs/charter.md
- Auto-extraction from docs/review*.md or docs/progress.md (feedback-loop risk)
- LLM-based charter refinement in the extractor

## Prior Art

- charter_revalidate.py already implements a generic H2-bounded body slicer

## 3. Project Structure

Standard pipelinekit layout: claude/lib/pipeline/ for Python modules, claude/skills/pipeline/ for SKILL.md and reference.md.
