---
name: persona
description: Set the active session persona (devops, growth-marketer, solo-founder, startup-cto, or none).
allowed-tools: Read, Write, Bash, AskUserQuestion
argument-hint: <name>
---

# /persona — Switch the active session persona

Personas are **advisory only** — they bias emphasis in `/analyze` and in `/pipeline` Step 0 Charter Discovery. Explicit user instructions always override persona emphasis. Session-scoped via `docs/active-persona` (cleared via `/persona none`). Default: no persona active (skills proceed unchanged).

## Available personas

- `devops` — Infra / operational / deployment / observability emphasis
- `growth-marketer` — GTM / user-impact / instrumentation / growth-loop emphasis
- `solo-founder` — Scope-creep / opportunity-cost / "smallest valuable version" emphasis
- `startup-cto` — Tech-debt vs time-to-market / hiring / scaling emphasis

Persona content lives in `claude/agents/personas/<name>.md`.

## Argument modes

- `/persona <name>` — Write `<name>` (lowercase) to `docs/active-persona`. Print the first 2 lines of `claude/agents/personas/<name>.md` as a confirmation summary.
- `/persona none` — Remove `docs/active-persona`. Print `Persona cleared — default emphasis active.`
- `/persona` (no argument) — Use `AskUserQuestion` to offer the 4 valid persona names plus `none`. Then proceed as above.

## Process

1. Parse the argument from `$ARGUMENTS`.

2. If the argument is empty:
   - Use `AskUserQuestion` with the question "Which persona should govern this session?" and the 5 options: `devops`, `growth-marketer`, `solo-founder`, `startup-cto`, `none`.

3. Validate the chosen name. Must be one of: `devops`, `growth-marketer`, `solo-founder`, `startup-cto`, `none`. Any other value: print `Unknown persona: <name>. Valid values: devops, growth-marketer, solo-founder, startup-cto, none.` and exit.

4. If `none`:
   ```bash
   rm -f docs/active-persona
   echo "Persona cleared — default emphasis active."
   ```

5. Otherwise:
   ```bash
   mkdir -p docs
   echo "<name>" > docs/active-persona
   echo "Active persona set to: <name>"
   echo "---"
   head -2 claude/agents/personas/<name>.md
   ```

6. Remind the user (one line): `Personas are advisory — explicit user instructions override persona emphasis.`

## Constraints

- `docs/active-persona` is gitignored via `.git/info/exclude` and never-staged via `claude/config/never-stage.txt`.
- Do not validate the persona file content — only the filename match.
- Do not modify any other file outside `docs/active-persona`.
