# Review Agent Prompts

Inline prompt templates for the 4 inline review agents (code-reviewer, security-auditor, test-engineer, performance-tuner). spec-tracer and symbol-verifier are self-contained agent files at `~/.claude/agents/spec-tracer.md` and `~/.claude/agents/symbol-verifier.md` respectively.

Load only the relevant block when spawning each agent from `SKILL.md` Step 6.

## Tier Selection

SKILL.md Step 4.6 determines which agents to spawn based on diff size:

| Tier | Diff lines | Agents spawned |
|------|-----------|----------------|
| Small | < 500 | Agent 1 (code-reviewer), Agent 5 (spec-tracer) — symbol-verifier excluded by design |
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
- **Scope:** in | out | adjacent
- **Intent:** correctness | polish | design | unrelated

How to classify (charter-aware):
- **Scope:** `in` = finding touches a charter MVP "In:" item. `out` = touches a Non-Goal or charter "Out (deferred):" item. `adjacent` = near charter scope but not literally in/out.
- **Intent:** `correctness` = logic/bug/security. `polish` = naming/style/docs. `design` = architectural shape. `unrelated` = off-topic relative to the diff's stated objective.
- If unsure of scope, omit the field; the post-aggregation classifier will fill it via token-overlap.
- A `scope=in` tag that contradicts the charter raises a plan-spec error and routes to re-review.

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
- **Scope:** in | out | adjacent
- **Intent:** correctness | polish | design | unrelated

How to classify (charter-aware):
- **Scope:** `in` = finding touches a charter MVP "In:" item. `out` = touches a Non-Goal or charter "Out (deferred):" item. `adjacent` = near charter scope but not literally in/out.
- **Intent:** `correctness` = logic/bug/security. `polish` = naming/style/docs. `design` = architectural shape. `unrelated` = off-topic relative to the diff's stated objective.
- If unsure of scope, omit the field; the post-aggregation classifier will fill it via token-overlap.
- A `scope=in` tag that contradicts the charter raises a plan-spec error and routes to re-review.

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
- **Scope:** in | out | adjacent
- **Intent:** correctness | polish | design | unrelated

How to classify (charter-aware):
- **Scope:** `in` = finding touches a charter MVP "In:" item. `out` = touches a Non-Goal or charter "Out (deferred):" item. `adjacent` = near charter scope but not literally in/out.
- **Intent:** `correctness` = logic/bug/security. `polish` = naming/style/docs. `design` = architectural shape. `unrelated` = off-topic relative to the diff's stated objective.
- If unsure of scope, omit the field; the post-aggregation classifier will fill it via token-overlap.
- A `scope=in` tag that contradicts the charter raises a plan-spec error and routes to re-review.

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
- **Scope:** in | out | adjacent
- **Intent:** correctness | polish | design | unrelated

How to classify (charter-aware):
- **Scope:** `in` = finding touches a charter MVP "In:" item. `out` = touches a Non-Goal or charter "Out (deferred):" item. `adjacent` = near charter scope but not literally in/out.
- **Intent:** `correctness` = logic/bug/security. `polish` = naming/style/docs. `design` = architectural shape. `unrelated` = off-topic relative to the diff's stated objective.
- If unsure of scope, omit the field; the post-aggregation classifier will fill it via token-overlap.
- A `scope=in` tag that contradicts the charter raises a plan-spec error and routes to re-review.

Only flag issues introduced or modified in this diff.
If you discover an issue or insight relevant to a DIFFERENT feature than the one being reviewed (e.g., a dependency that another feature should be aware of, a pattern that will conflict with planned work), emit a cross-feature intel section after your findings:

**Cross-Feature Intel:**
- **Target:** [feature name or keyword describing the target area]
- **Keywords:** [2-5 comma-separated keywords that would match the target feature's description]
- **Severity:** blocking | non-blocking | nit
- **Note:** [description of the cross-feature insight]

Only emit this section when you have a genuine cross-feature insight. Omit it entirely if all findings relate to the current feature.
```

---

## Teams dispatch shape — worked example and anti-patterns

Referenced from `SKILL.md` Step 6. The full teams-mode dispatch detail, the
MANDATORY single-turn contract, the worked example, the three contract
violations, and the F6 background all live here; `SKILL.md` Step 6 carries the
tier-selection summary and the pointer.

**Teams-mode dispatch (when `teams_mode=true`):**

Instead of N independent `Agent` calls, spawn all selected reviewers as named teammates that communicate via SendMessage:

1. Spawn each agent using the Agent tool with a descriptive name ('code-reviewer', 'security-auditor', 'test-engineer', 'performance-tuner', 'spec-tracer', 'symbol-verifier') so they can communicate via SendMessage during execution.
2. Each agent receives the same prompt as the independent path, PLUS this additional instruction at the top:

   > You are part of a review team. As you find issues, share them with your teammates using SendMessage. When you see a teammate's finding that relates to your domain, note the correlation. If a teammate's finding changes your assessment of something, update your analysis.
   >
   > Your teammates: code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer, symbol-verifier.
   > Communicate findings as you go — don't wait until you're done.
   >
   > For each finding, include an additional field:
   > - **Correlated by:** [agent names] (if another teammate flagged a related issue)

3. Each agent prompt still includes: objective, REVIEW.md rules (if loaded), prior findings (if re-review), path to $DIFF_FILE.
4. Agents self-coordinate: if security-auditor finds an auth issue, test-engineer can check coverage for that path.

**MANDATORY single-turn contract:**

When `teams_mode=true`, the lead MUST dispatch the base reviewer set as **exactly N `Agent` tool calls in a single assistant turn**, where N is the count of selected reviewer agents (5 for the base panel, +1 if `symbol-verifier` is included). The base agent types are, verbatim:

- `code-reviewer`
- `security-auditor`
- `test-engineer`
- `performance-tuner`
- `spec-tracer`

Optional additions per Step 6 tier rules: `symbol-verifier` (medium / large tier). When included, it counts toward the bundle and the single-turn rule applies to it too. Serial turns or wrapping-as-one are contract violations.

**Correct shape (worked example, 5-agent base panel):**

```
<one assistant turn>
  Agent(name='code-reviewer',     prompt=…, model=opus)
  Agent(name='security-auditor',  prompt=…, model=opus)
  Agent(name='test-engineer',     prompt=…, model=sonnet)
  Agent(name='performance-tuner', prompt=…, model=sonnet)
  Agent(name='spec-tracer',       prompt=…, model=haiku)
</one assistant turn>
```

All five `Agent` invocations live inside a single assistant message — the harness fans them out concurrently, each in its own context window, each with its own specialist prompt from `agent-prompts.md`. Serial turns or wrapping-as-one are contract violations.

**Contract violations (do NOT do any of these):**

1. **Wrap-as-one-Agent.** Dispatch a SINGLE generic `Agent` (e.g. `Agent(name='F<N> review', prompt='do a 5-perspective review')`) that runs all five perspectives inside one subagent's context. This forfeits parallelism, forfeits per-role specialist prompts, and forfeits inter-agent context isolation. The single subagent runs ~5× the tool calls and produces a flat single-voice review. **This is a contract violation.**
2. **One-per-turn serial dispatch.** Dispatch `code-reviewer` alone in one assistant turn, then `security-auditor` alone in the next turn, then `test-engineer` alone in the next, and so on. Each individual call IS a real specialist dispatch — but the assistant turns are serial, so the harness runs them sequentially instead of concurrently. Total wall time is ~5× the bundled shape. **This is a contract violation.**
3. **Fall-back-to-inline.** When dispatch feels expensive, "just run /pipeline-review quickly to wrap up" by invoking the `Skill: pipeline-review` tool inline OR by reading the diff and emitting findings directly. This skips the entire teams-mode contract: no specialist roles, no parallel execution, no Step 6 dispatch shape at all. **This is a contract violation** (see also `claude/skills/pipeline/SKILL.md` § Phase Mode Precedence — direct `Skill: pipeline-review` invocations are forbidden when Phase Mode is `subagent`).

**Background:** F6 of castellum branch `test/taxii-misp-self-hosted-smoke` (2026-05-26, 560-line diff, teams-on per heuristic) exhibited all three violations sequentially in the same lead session: wrap-as-one → one-per-turn → recovery only on second user nudge. This subsection exists to give the lead a pattern-match surface against those specific failures.

**Cross-reference:** the generic parallelism reminder lives in `~/.claude/rules/agents-worktrees.md` § Subagent Defaults. This subsection is the teams-on review-specific instantiation of that rule.

---

## Default model mapping

Referenced from `SKILL.md` Step 6. Absent a `REVIEW.md` `review-model:` override (see SKILL.md Step 3a), each reviewer runs on the model declared in its agent-file frontmatter. Deep-reasoning reviewers run on opus; pattern-based reviewers drop to sonnet; spec comparison runs on haiku for cost.

| Agent | Default model | Rationale |
|-------|--------------|-----------|
| code-reviewer | opus | Deep reasoning; a single missed issue is expensive |
| security-auditor | opus | Deep reasoning; security misses have high blast radius |
| test-engineer | sonnet | Pattern-based gap-finding that sonnet handles well |
| performance-tuner | sonnet | Pattern-based bottleneck analysis |
| spec-tracer | haiku | Structured diff-vs-objective comparison; ~20× cheaper |
| symbol-verifier | opus | Symbol/API resolution requires deep reasoning; false positives are expensive to triage |

When `review-model:` is set in REVIEW.md it applies uniformly to all six agents and bypasses these per-agent defaults (see SKILL.md Step 3a for override semantics).
