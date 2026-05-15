---
name: dotnet-conventions
description: .NET architecture, DI, data access, and testing conventions. Loaded when working with C#, .NET, controllers, services, entities, repositories, or solution files.
user-invocable: false
paths:
  - "**/*.cs"
  - "**/*.csproj"
  - "**/*.sln"
---

# .NET Conventions

Rules for all C#/.NET projects.

## Clean Architecture

Four layers with strict dependency direction (outer depends on inner, never reverse):

| Layer | Project Suffix | Contains | Depends On |
|-------|---------------|----------|------------|
| Domain | `.Domain` | Entities, enums, value objects | Nothing |
| Application | `.Application` | Services, DTOs, interfaces | Domain |
| Infrastructure | `.Infrastructure` | EF Core, external connectors, background services | Application |
| Web | `.Web` | MVC controllers, views, JS, CSS | All |

Never reference Infrastructure from Domain or Application. Infrastructure implements interfaces defined in Application.

## Dependency Injection

- Register services by interface only: `services.AddScoped<IMyService, MyService>()`
- Never inject concrete classes directly
- Define service interfaces in the Application layer
- Register implementations in Infrastructure (extension methods) or Web (`Program.cs`)

## Data Access

- Use the UnitOfWork pattern via `IUnitOfWork` (defined in Application layer)
- Never use `DbContext` directly outside repository classes
- Repositories implement interfaces defined in Application
- EF Core configuration stays in Infrastructure

## ViewModels

- Always use ViewModels for data passed to views — never expose domain entities directly
- ViewModels live in the Web layer (or Application layer as DTOs)
- Map between entities and ViewModels explicitly

## Web Patterns

- Use POST-Redirect-GET on all form submissions to prevent duplicate submissions
- Return `RedirectToAction()` after successful POST, not a view
- On validation failure, re-render the view with the ViewModel (do NOT redirect — `ModelState` errors must persist)

## Testing

- Framework: xUnit + Moq + FluentAssertions
- Test naming convention: `MethodName_Scenario_ExpectedResult`
  - Example: `Calculate_NegativeInput_ThrowsArgumentException`
- Unit tests: mock dependencies via interfaces
- Integration tests: use `WebApplicationFactory` + InMemory database
