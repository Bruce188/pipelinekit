# Review Agent Prompts

Inline prompt templates for the 4 inline review agents (code-reviewer, security-auditor, test-engineer, performance-tuner). spec-tracer and karpathy-reviewer are self-contained agent files at `~/.claude/agents/spec-tracer.md` and `~/.claude/agents/karpathy-reviewer.md` respectively.

Load only the relevant block when spawning each agent from `SKILL.md` Step 6.

## Tier Selection

SKILL.md Step 4.6 determines which agents to spawn based on diff size:

| Tier | Diff lines | Agents spawned |
|------|-----------|----------------|
| Small | < 500 | Agent 1 (code-reviewer), Agent 5 (spec-tracer) — karpathy-reviewer excluded by design |
| Medium | 500-5,000 | All 6 agents (independent) |
| Large | > 5,000 | All 6 agents (teams mode - collaborative) |

The `--teams` flag (Step 5.5) overrides: if set, small tier upgrades to medium with teams mode and auto-enables `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.

---

## Agent 1 -- code-reviewer

```
Review this diff for correctness, logic errors, and adherence to the stated objective.

Objective: [from plan]
[If REVIEW.md loaded (Step 3a): Project review rules: [REVIEW.md contents]]
[If prior findings loaded (Step 3b): Prior review findings (verify if addressed): [findings summary]]

Read the diff from: [path to $DIFF_FILE]

For each finding, output:
- **File:** path:line
- **Severity:** blocking | non-blocking | nit
- **Issue:** description
- **Suggestion:** fix

Do not suggest refactors or improvements beyond the stated task scope.
If you discover an issue or insight relevant to a DIFFERENT feature than the one being reviewed (e.g., a dependency that another feature should be aware of, a pattern that will conflict with planned work), emit a cross-feature intel section after your findings:

**Cross-Feature Intel:**
- **Target:** [feature name or keyword describing the target area]
- **Keywords:** [2-5 comma-separated keywords that would match the target feature's description]
- **Severity:** blocking | non-blocking | nit
- **Note:** [description of the cross-feature insight]

Only emit this section when you have a genuine cross-feature insight. Omit it entirely if all findings relate to the current feature.
```

---

## Agent 2 -- security-auditor

```
Review this diff for security vulnerabilities. Check for: injection (SQL, command, XSS), auth/authz issues, insecure data handling, hardcoded secrets, OWASP Top 10.

[If REVIEW.md loaded (Step 3a): Project review rules: [REVIEW.md contents]]
[If prior findings loaded (Step 3b): Prior review findings (verify if addressed): [findings summary]]

Read the diff from: [path to $DIFF_FILE]

For each finding, output:
- **File:** path:line
- **Severity:** blocking | non-blocking | nit
- **Issue:** description
- **CWE:** if applicable
- **Suggestion:** fix

Only flag issues introduced or modified in this diff. Do not flag pre-existing issues.
If you discover an issue or insight relevant to a DIFFERENT feature than the one being reviewed (e.g., a dependency that another feature should be aware of, a pattern that will conflict with planned work), emit a cross-feature intel section after your findings:

**Cross-Feature Intel:**
- **Target:** [feature name or keyword describing the target area]
- **Keywords:** [2-5 comma-separated keywords that would match the target feature's description]
- **Severity:** blocking | non-blocking | nit
- **Note:** [description of the cross-feature insight]

Only emit this section when you have a genuine cross-feature insight. Omit it entirely if all findings relate to the current feature.
```

---

## Agent 3 -- test-engineer

```
Review this diff for test quality and coverage gaps.

Check:
- Are new code paths covered by tests?
- Are edge cases handled (null, empty, boundary values)?
- Are error paths tested?
- Do tests actually assert meaningful behavior (not just "runs without error")?
- Are there brittle tests (timing, ordering, external dependencies)?

[If REVIEW.md loaded (Step 3a): Project review rules: [REVIEW.md contents]]
[If prior findings loaded (Step 3b): Prior review findings (verify if addressed): [findings summary]]

Read the diff from: [path to $DIFF_FILE]

For each finding, output:
- **File:** path:line (the source file missing coverage, not the test file)
- **Severity:** blocking | non-blocking | nit
- **Issue:** description
- **Suggestion:** specific test to add

Only flag gaps introduced by this diff. Do not audit pre-existing test debt.
If you discover an issue or insight relevant to a DIFFERENT feature than the one being reviewed (e.g., a dependency that another feature should be aware of, a pattern that will conflict with planned work), emit a cross-feature intel section after your findings:

**Cross-Feature Intel:**
- **Target:** [feature name or keyword describing the target area]
- **Keywords:** [2-5 comma-separated keywords that would match the target feature's description]
- **Severity:** blocking | non-blocking | nit
- **Note:** [description of the cross-feature insight]

Only emit this section when you have a genuine cross-feature insight. Omit it entirely if all findings relate to the current feature.
```

---

## Agent 4 -- performance-tuner

```
Review this diff for performance issues.

Check:
- N+1 queries or unbounded loops
- Memory leaks (unclosed resources, growing caches)
- Blocking I/O in async contexts
- Missing pagination on unbounded queries
- Unnecessary allocations in hot paths

[If REVIEW.md loaded (Step 3a): Project review rules: [REVIEW.md contents]]
[If prior findings loaded (Step 3b): Prior review findings (verify if addressed): [findings summary]]

Read the diff from: [path to $DIFF_FILE]

For each finding, output:
- **File:** path:line
- **Severity:** blocking | non-blocking | nit
- **Issue:** description
- **Suggestion:** fix

Only flag issues introduced or modified in this diff.
If you discover an issue or insight relevant to a DIFFERENT feature than the one being reviewed (e.g., a dependency that another feature should be aware of, a pattern that will conflict with planned work), emit a cross-feature intel section after your findings:

**Cross-Feature Intel:**
- **Target:** [feature name or keyword describing the target area]
- **Keywords:** [2-5 comma-separated keywords that would match the target feature's description]
- **Severity:** blocking | non-blocking | nit
- **Note:** [description of the cross-feature insight]

Only emit this section when you have a genuine cross-feature insight. Omit it entirely if all findings relate to the current feature.
```
