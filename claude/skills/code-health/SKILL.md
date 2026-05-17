---
name: code-health
description: Comprehensive codebase health assessment with quality metrics, test coverage, documentation, and maintainability analysis. Use for quality gates, pre-release checks, or periodic health monitoring.
argument-hint: [--scope quality,tests,docs,all] [--quick] [--threshold N]
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

# Codebase Health Assessment

---

## Overview

The `/code-health` command performs comprehensive codebase health assessment across multiple quality dimensions - code quality, test coverage, documentation completeness, and maintainability. It provides a 0-10 health score with actionable improvement recommendations.

---

## Key Features

- ✅ **Multi-Dimensional Assessment** - Quality, tests, docs, maintainability
- ✅ **Health Score (0-10)** - Overall codebase health rating
- ✅ **Intelligent Analysis** - Auto-detects languages and frameworks
- ✅ **Actionable Recommendations** - Prioritized by impact
- ✅ **Trend Tracking** - Compare health over time
- ✅ **Best Practices Compliance** - Language/framework conventions

---

## Quick Start

```bash
# Full health assessment
/code-health

# Specific scope
/code-health --scope quality,tests
/code-health --scope documentation

# Quick assessment (skip deep analysis)
/code-health --quick
```

---

## What Gets Assessed

### 1. Code Quality (Weight: 30%)
- Cyclomatic complexity (target: < 10 per function)
- Code duplication (target: < 5%)
- Code smells (long functions, god classes)
- Naming conventions
- File organization

### 2. Test Coverage (Weight: 30%)
- Unit test coverage (target: ≥ 80%)
- Integration test coverage
- E2E test coverage (if applicable)
- Files without tests
- Test quality (assertions, edge cases)

### 3. Documentation (Weight: 20%)
- Code comments (target: 50% of functions)
- API documentation completeness
- README quality
- Inline documentation
- Architecture diagrams

### 4. Maintainability (Weight: 20%)
- File length (target: < 300 lines per file)
- Function length (target: < 50 lines per function)
- Dependency count
- Coupling/cohesion
- SOLID principles adherence

---

## Example Output

```
Code Health Assessment Complete!

Overall Health Score: 7.3/10 (GOOD)

Breakdown:
- Code Quality: 7.5/10 [PASS]
- Test Coverage: 8.2/10 [PASS]
- Documentation: 6.5/10 [WARN]
- Maintainability: 7.2/10 [PASS]

Top Issues:
1. 15 files without tests
2. 3 files > 500 lines (god classes)
3. 45% of functions lack documentation
4. 12 complex functions (complexity > 15)

Quick Wins (16 hours):
- Add tests for critical files (8h)
- Refactor 3 god classes (8h)

Expected Improvement: 7.3 -> 8.5 (+1.2 points)
```

---

## Integration with Workflow

After assessment, consider:
- Use `/review` for deep-dive into specific issues found
- Update `docs/progress.md` (AI workflow tracking) with health score and improvement tasks
- When the health report flags refactor candidates (cyclomatic complexity, large files, duplicated blocks), dispatch the `refactor-expert` agent with a prompt that includes: (a) the file path and offending region, (b) the desired refactor pattern, (c) the existing test coverage for the region. Refactor-expert returns either a patch plan or a "needs more tests first" verdict. Create the resulting tasks in the prompts file (follow the `**Prompts:**` pointer in `docs/progress.md`).
- Note: `docs/` = AI workflow files. `documentation/` = application docs. Documentation quality metrics should assess `documentation/`, not `docs/`.

---

## Command Options

### `--scope`
```bash
/code-health --scope quality        # Code quality only
/code-health --scope tests          # Test coverage only
/code-health --scope docs           # Documentation only
/code-health --scope all            # All dimensions (default)
```

### `--threshold`
```bash
/code-health --threshold 8.0   # Stricter threshold (default: 7.0)
/code-health --threshold 6.0   # More lenient threshold
```

### `--quick`
```bash
/code-health --quick
# Fast assessment (15-20 min):
# - Surface-level metrics
# - Skip deep analysis
# - Suitable for CI/CD
```

---

## Recommended Frequency

- **Weekly:** Quick health check (`--quick`)
- **Monthly:** Full assessment (default)
- **Before releases:** Full assessment with high threshold
- **After major refactors:** Verify improvements

---

## FAQ

### Q: What's a good health score?

**A:**
- **9.0-10.0:** Excellent (production-ready, well-maintained)
- **7.0-8.9:** Good (acceptable, minor improvements needed)
- **5.0-6.9:** Fair (needs attention, plan improvements)
- **< 5.0:** Poor (urgent refactoring needed)

### Q: How do I improve my health score?

**A:** Focus on quick wins first:
1. Add missing tests (highest impact)
2. Refactor god classes (split into modules)
3. Document public APIs
4. Reduce cyclomatic complexity

Use `/review --health` to prioritize by ROI.

---

## See Also

- **[/review](../review/)** - Multi-agent code review and quality gate
- **[/analyze](../analyze/)** - Codebase analysis and architecture assessment

---

**Version:** 2.7.0
**Last Updated:** November 19, 2025
**Category:** Quality
**License:** MIT
**Author:** Alireza Rezvani

---

## Authoring Reference

This skill is a reference implementation of pipelinekit's skill authoring conventions.
For the full standard, see:

- `documentation/SKILL-AUTHORING-STANDARD.md` — the 10-pattern skill DNA template
- `documentation/SKILL_PIPELINE.md` — the Intent → ... → Verify lifecycle

Both are vendored from `alirezarezvani/claude-skills` (MIT). The standard is **advisory** for v1
of pipelinekit — no skills are required to conform. `/code-health` is offered as the worked example
because (a) it's pipelinekit-native (no vendor boundary), (b) it has the right shape (frontmatter
with `name`, `description`, `argument-hint`, `disable-model-invocation`, `allowed-tools`), and
(c) its body uses the action-oriented patterns the standard recommends.
