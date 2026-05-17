---
model: claude
family: claude
token_budget_hint: default
thinking_budget_hint: default
max_turns_hint: default
---

## Reasoning tips
- Prefer concise tool I/O over verbose narration.
- Reserve ~15% headroom in token budgets.
- For multi-step tasks, decompose explicitly before invoking tools.

## Token budget guidance
No model-specific override. Defer to Anthropic API defaults.

## Thinking budget guidance
No model-specific override. Defer to Claude Code defaults.
