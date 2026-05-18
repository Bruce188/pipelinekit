---
name: interview-prp
description: [DEPRECATED] Interview the user about a project idea to produce a complete PRP/spec document. Charter Discovery via /pipeline Step 0 is the recommended replacement.
disable-model-invocation: true
allowed-tools: Read, Write, Bash, AskUserQuestion
---

## Migration notice (deprecation)

> **[DEPRECATED]** This skill is in its deprecation window. `/pipeline` Step 0 (Charter Discovery) is the recommended replacement for new-project scoping; it writes `docs/charter.md` and downstream phases (`/analyze`, `/create-plan`, `/implement-plan`, `/review`, `/ppr`) auto-consume the charter.
>
> **PRP-artifact migration path.** If you still want a `docs/prp.md` artifact, continue past this notice — the skill still runs unchanged. To migrate to the modern flow, run `/pipeline` and step through Charter Discovery; it produces `docs/charter.md` covering the same scoping ground, and downstream phases auto-consume it.
>
> This skill will be removed from the default install in the next release.

---

Interview the user to produce a Product Requirements Prompt (PRP) for: $ARGUMENTS

The interview runs in two phases. **Phase 1 is forcing questions** that pressure-test whether the project should exist at all and what the smallest valuable wedge looks like. **Phase 2 is the standard PRP coverage** — stack, architecture, edge cases, etc.

For internal infra / tools / personal scripts where Phase 1 is overkill, the user can say "skip forcing questions" or "skip Phase 1" and you proceed directly to Phase 2.

---

## Phase 0: Persona Preamble

Personas are **advisory only** — they bias question emphasis in Phase 1 / Phase 2 but **never override** explicit user answers. Session-scoped via `docs/active-persona` (gitignored). Default: no persona active (interview proceeds unchanged).

### Process

1. Check for an active persona:

   ```bash
   cat docs/active-persona 2>/dev/null
   ```

2. **If absent or empty:** Use `AskUserQuestion` with the question "Which persona should govern this interview?" and these 5 options:
   - `devops` — infra / operational / deployment emphasis
   - `growth-marketer` — GTM / user-impact / growth-loop emphasis
   - `solo-founder` — scope-creep / opportunity-cost emphasis
   - `startup-cto` — tech-debt vs time-to-market emphasis
   - `no persona` — proceed with default emphasis

   If the user picks a named persona, write the lowercase name to `docs/active-persona`. If `no persona`, do NOT create the file.

3. **If `docs/active-persona` exists or was just written:** Read `claude/agents/personas/<name>.md` and extract 1–2 emphasis bullets relevant to product discovery (e.g., for `solo-founder`: "watch for scope creep in Q4 wedge"; for `startup-cto`: "track tech-debt implications in Q3 desperate specificity"). These bullets bias the depth of follow-up pushes in Phase 1 questions, NOT which questions are asked. Phase 1 still runs the full Q1–Q6 sequence.

4. Append a comment to the eventual PRP header (Phase 2 write step): `<!-- persona: <name> -->`. This is metadata only; do not gate any behavior on it.

5. If the user provides an explicit answer in Phase 1 / Phase 2 that contradicts the persona's emphasis, the explicit answer wins — log the resolution but proceed with the user's answer verbatim.

---

## Phase 1: Forcing Questions

Use the AskUserQuestion tool to ask these **one at a time**, in order. Push on each answer until it is specific, evidence-based, and concrete. If an answer to a later question is already covered by an earlier one (smart-skip), say so and skip it. Do not batch.

If the framing is imprecise, **reframe constructively** — say "Let me try restating what I think you're actually building: [reframe]. Does that capture it better?" Then proceed with the corrected framing.

### Q1 — Demand reality

> "What's the strongest evidence you have that someone actually wants this — not 'is interested,' not 'signed up for a waitlist,' but would be genuinely upset if it disappeared tomorrow?"

**Push until you hear:** A specific person or group, a specific behavior, ideally money/time/effort already spent. **Red flags:** "Everyone has this problem", "I would use it", waitlist sign-ups in lieu of real usage.

### Q2 — Status quo

> "What are your users doing right now to solve this problem — even badly? What does that workaround cost them?"

**Push until you hear:** A concrete current workflow with a measurable cost (time, money, errors). **Red flag:** "Nothing — there's no solution." If truly nothing exists, the problem probably isn't painful enough.

### Q3 — Desperate specificity

> "Name the actual human who needs this most. What's their title? What gets them promoted? What gets them fired? What keeps them up at night?"

**Push until you hear:** A specific human with stakes. The consequence is domain-dependent: B2B → career impact; consumer → daily pain or social moment; hobby/OSS → the weekend project this unblocks. Don't let the answer stay at "users" or "developers."

### Q4 — Narrowest wedge

> "What's the smallest possible version of this that someone would pay real money for — this week, not after you build the platform?"

**Push until you hear:** One feature, one workflow — sometimes as small as a weekly email or a single automation. **Red flag:** "We need to build the full platform before anyone can really use it." That signals attachment to the architecture rather than the value.

**Bonus push:** "What if the user didn't have to do anything at all to get value? No login, no integration, no setup. What would that look like?"

### Q5 — Observation & surprise

> "Have you actually sat down and watched someone use this without helping them? What did they do that surprised you?"

**Push until you hear:** A specific surprise — something that contradicted the founder's assumptions. **Red flags:** "We sent a survey." "We did demo calls." "Nothing surprising." Surveys lie, demos are theater, "as expected" means filtered through existing assumptions. **The gold:** users doing something the product wasn't designed for — that's the real product trying to emerge.

### Q6 — Future-fit

> "If the world looks meaningfully different in 3 years — and it will — does your product become more essential or less?"

**Push until you hear:** A specific claim about how the user's world changes and why that change makes the product more valuable. **Red flags:** "The market is growing 20% per year" (growth rate isn't a vision), "AI keeps getting better so we keep getting better" (rising-tide argument every competitor can make).

---

## Phase 2: PRP Coverage

After Phase 1, conduct a thorough interview using the AskUserQuestion tool. Cover:

1. **Core goal** — What problem does this solve? Who is it for? (Anchor on Phase 1 Q3 / Q1.)
2. **Technical stack** — Language, framework, infrastructure preferences or constraints
3. **Architecture** — Key components, data flow, external integrations

   If the user's architecture answer mentions more than 3 services / processes / plugin surfaces, OR describes integration with external systems beyond a single database, dispatch the `architect` agent with a prompt that captures the answers so far and asks for: (a) component diagram in ASCII, (b) data-flow notes, (c) failure-mode candidates. Use the architect's output to populate the Architecture section of the eventual PRP. Small CLI projects and single-service apps skip this dispatch.
4. **UI/UX** — User-facing behavior, interaction patterns, responsive requirements
5. **Edge cases** — Error handling, failure modes, concurrency, rate limits
6. **Security** — Auth, data validation, secrets management
7. **Tradeoffs** — Performance vs simplicity, scope cuts, MVP vs full vision (anchor on Q4 wedge)
8. **Verification** — How will we know it works? Test strategy, acceptance criteria
9. **Parallelization** — Can the work be broken into independent streams with clear file boundaries? Are there phases requiring architectural exploration or competing approaches? Will streams need to share findings or coordinate during execution?

Guidelines:
- Ask focused, non-obvious questions — skip anything self-evident from the description or already answered in Phase 1
- Dig into the hard parts the user might not have considered
- Group related questions (2-3 per round) to keep the interview efficient
- Keep interviewing until all areas are covered and the user confirms

When the interview is complete, before writing, check if `docs/prp.md` already exists:

```bash
ls docs/prp.md 2>/dev/null
```

If it exists, use AskUserQuestion to ask:
- "docs/prp.md already exists. What should I do?"
- Options: "Overwrite it" / "Save as a new version (docs/prp-vN.md)"

If the user chooses a new version, find the highest existing version number among `docs/prp-v*.md` files and increment. If the user chooses to overwrite, proceed normally.

Write the full PRP to the chosen filename with:
- **Demand reality** (Phase 1 Q1) — specific evidence of want
- **Status quo** (Phase 1 Q2) — concrete current workflow + cost
- **Target user & narrowest wedge** (Phase 1 Q3 + Q4) — the specific human + the smallest valuable version
- **Observations** (Phase 1 Q5) — surprise findings if any
- **Future-fit thesis** (Phase 1 Q6) — why this becomes more essential, not less
- Project overview and goals
- Technical requirements and constraints
- Architecture decisions
- Feature breakdown with acceptance criteria
- Edge cases and error handling
- Parallelization notes per phase: pre-plannable work (subagents + worktree isolation) vs exploratory work requiring mid-flight coordination (agent teams)
- Out of scope / future considerations

If Phase 1 was skipped, omit the five Phase 1 sections.

Then output this block:

```
---

PRP complete → [actual filename written, e.g., docs/prp.md or docs/prp-v2.md]

Review the PRP and confirm it captures everything correctly.

Next:
1. Run /compact to compress context (the PRP is your source of truth now)
2. Then run /create-plan to generate plan + task prompts from the PRP

---
```
