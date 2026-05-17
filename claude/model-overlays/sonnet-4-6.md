---
model: sonnet-4-6
family: sonnet
token_budget_hint: 200000
thinking_budget_hint: medium
max_turns_hint: 40
---

## Reasoning tips
- Sonnet 4.6 is the implement-phase workhorse — fast enough for tight TDD loops.
- Prefer focused file reads over wide exploration.

## Token budget guidance
Aim for 200K input / 8K output. ~10% headroom.

## Thinking budget guidance
Extended thinking OFF for implement. ON only when task asks for design judgment.
