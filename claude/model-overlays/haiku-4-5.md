---
model: haiku-4-5
family: haiku
token_budget_hint: 100000
thinking_budget_hint: low
max_turns_hint: 20
---

## Reasoning tips
- Haiku 4.5 is the smallest/fastest tier — use for utility tasks (docs writeups, status checks).
- Avoid multi-hop reasoning; decompose into smaller sub-tasks first.

## Token budget guidance
Aim for 100K input / 4K output. Keep prompts compact.

## Thinking budget guidance
Extended thinking OFF by default. Enable only for narrow analytical sub-tasks.
