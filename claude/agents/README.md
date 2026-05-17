# Claude Code Specialized Agents

Specialized subagents for software development. Each is defined as a `.md` file with YAML frontmatter.

## Available Agents

### Code Quality & Review
- **@code-reviewer** — Code quality analysis, security, performance, best practices
- **@refactor-expert** — Code refactoring with clean code principles
- **@security-auditor** — Vulnerability detection, OWASP compliance

### Testing & Quality Assurance
- **@test-engineer** — Test creation, validation, coverage analysis
- **@performance-tuner** — Performance optimization and benchmarking

### Documentation & Architecture
- **@docs-writer** — Technical documentation and user guides
- **@architect** — System design and architectural patterns

### Development Support
- **@debugger** — Root cause analysis, systematic debugging
- **@trading-bot-developer** — Automated trading (CEX/DEX), strategies, backtesting
- **@data-pipeline-engineer** — ETL/ELT design, data processing, ML feature pipelines

### Mobile Development
- **@mobile-dev** — iOS (Swift/Xcode), Android (Kotlin), React Native, Expo, Flutter; native modules, mobile CI/CD, App Store / Play Console workflows

## Agent Format

Each agent is a markdown file with YAML frontmatter:

```yaml
---
name: agent-name
description: When to use this agent
tools: Read, Edit, Grep, Glob, Bash
model: inherit  # or sonnet, opus, haiku
maxTurns: 30
---

# Agent instructions follow...
```

## Usage Rules

- Named agents are only invoked when the **task prompt explicitly specifies** them
- Unnamed subagents for research/exploration may be used freely
- When a task prompt specifies a model, pass it via the Agent tool's `model` parameter (overrides frontmatter)
- Opus 4.6 over-spawns agents — prefer direct work for coding; subagents for reading/exploring

## Worktree Isolation

Agents can run in isolated git worktrees with `isolation: "worktree"`. Every worktree agent must commit `wip: [description]` before reporting done (enforced by SubagentStop hook).

See `~/.claude/rules/agents-worktrees.md` for the full merge protocol.
