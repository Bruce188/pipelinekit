<!-- Adopted from alirezarezvani/ClaudeForge @ 6eb741b — MIT (Copyright 2025 Alireza Rezvani). See claude/skills/claude-md-enhancer/NOTICE.md. Content relocated from SKILL.md by pipelinekit for progressive disclosure (verbatim). -->

# CLAUDE.md File Enhancer — Reference

Consulted-but-not-executed reference material for the `claude-md-enhancer` skill.
The skill's executable workflow lives in `SKILL.md`; this file holds the template
catalogue, quality-metric rubric, and advanced-feature catalogue that the skill
reads when generating or scoring output.

## Template Categories

### By Size
- **Minimal** (50 lines) - Solo developers, prototypes, hackathons
- **Core** (100-150 lines) - Small teams, MVPs, standard projects
- **Detailed** (200-300 lines) - Large teams, production systems, enterprise

### By Project Type
- **Web App** - Frontend-focused (React, Vue, Angular)
- **API** - Backend services (REST, GraphQL, microservices)
- **Full-Stack** - Integrated frontend + backend
- **CLI** - Command-line tools and utilities
- **Library** - Reusable packages and frameworks
- **Mobile** - React Native, Flutter, native iOS/Android

### By Tech Stack
- **TypeScript/Node** - Modern JavaScript ecosystem
- **Python** - Django, FastAPI, Flask
- **Go** - Gin, Echo, native services
- **Java/Kotlin** - Spring Boot, enterprise Java
- **Ruby** - Rails, Sinatra

## Quality Metrics

### File Quality Score (0-100)

Calculated based on:
- **Length appropriateness** (25 points) - Not too short or long
- **Section completeness** (25 points) - Required sections present
- **Formatting quality** (20 points) - Proper markdown structure
- **Content specificity** (15 points) - Tailored to project, not generic
- **Modular organization** (15 points) - Uses subdirectory files when appropriate

### Recommendations Priority

- **Critical** - Missing required sections, file too long (>400 lines)
- **High** - Missing important sections, formatting issues
- **Medium** - Could add optional sections, minor improvements
- **Low** - Nice-to-have enhancements, stylistic suggestions

## Advanced Features

### Modular Architecture Support

Automatically generates context-specific files:

```
project-root/
├── CLAUDE.md                 # Root orchestrator (100-150 lines)
├── backend/
│   └── CLAUDE.md            # Backend-specific (150-200 lines)
├── frontend/
│   └── CLAUDE.md            # Frontend-specific (150-200 lines)
├── database/
│   └── CLAUDE.md            # Database operations (100-150 lines)
└── .github/
    └── CLAUDE.md            # CI/CD workflows (100-150 lines)
```

### Tech Stack Detection

Automatically detects technologies from:
- `package.json` (Node.js/TypeScript)
- `requirements.txt` or `pyproject.toml` (Python)
- `go.mod` (Go)
- `Cargo.toml` (Rust)
- `pom.xml` or `build.gradle` (Java)

### Team Size Adaptation

Adjusts detail level:
- **Solo**: Minimal guidelines, focus on efficiency
- **Small (<10)**: Core guidelines, workflow basics
- **Medium (10-50)**: Detailed guidelines, team coordination
- **Large (50+)**: Comprehensive guidelines, process enforcement
