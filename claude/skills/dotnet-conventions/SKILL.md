---
name: dotnet-conventions
description: C#/.NET conventions for Clean Architecture solutions like FundingRateArb (Domain/Application/Infrastructure/Web, IUnitOfWork, xUnit + Moq + FluentAssertions 7). Covers layering, DI, EF Core migrations, tests, BackgroundService rules, target-framework upgrades and ASP.NET Core security. Use when creating or editing .cs, .csproj, .sln or appsettings files, adding an entity or migration, writing .NET tests, adding a hosted service or controller, or upgrading .NET or EF Core, even if the user names only the feature and not the layer.
user-invocable: false
paths:
  - "**/*.cs"
  - "**/*.csproj"
  - "**/*.sln"
  - "**/*.slnx"
  - "**/Directory.Build.props"
  - "**/appsettings*.json"
---

# .NET conventions

These are defaults for new code. When an existing project does something differently, follow the project, and read its `.claude/CLAUDE.md` first because it is the source of truth for that repo.

Read `references/security.md` before you write controllers, endpoints, auth or Identity code, file uploads, or anything that stores credentials.

## Layers

| Layer | Project | Holds | References |
|---|---|---|---|
| Domain | `*.Domain` | Entities, enums, value objects | nothing |
| Application | `*.Application` | Services, DTOs, interfaces (`IUnitOfWork`, repositories, connectors) | Domain |
| Infrastructure | `*.Infrastructure` | EF Core `DbContext`, migrations, repositories, exchange connectors, hosted services | Application |
| Web | `*.Web` | Controllers, ViewModels, views, `Program.cs` composition root | all |

Application defines interfaces and Infrastructure implements them. Domain and Application never reference Infrastructure.

## Dependency injection and data access

- Inject application services by interface (`AddScoped<IFooService, FooService>()`). Framework types are fine as they are: `ILogger<T>`, `IOptions<T>`, typed `HttpClient`s, `TimeProvider`, `IDbContextFactory<T>`.
- Go through `IUnitOfWork` and the repositories rather than using `DbContext` directly in Application or Web code. Infrastructure owns the EF configuration.
- Views get ViewModels, never entities. MVC forms use Post-Redirect-Get, and on validation failure they re-render the view with the model.

## EF Core migrations

`dotnet ef` is a tool, not part of the SDK. Use the repo's tool manifest:

```bash
dotnet tool restore                      # .config/dotnet-tools.json pins dotnet-ef
# no manifest yet:
dotnet new tool-manifest && dotnet tool install dotnet-ef --version <EF major>.*
```

Keep the `dotnet-ef` major version equal to the EF Core package major version.

```bash
dotnet ef migrations add <Name> \
  --project src/<App>.Infrastructure --startup-project src/<App>.Web
# read the generated Up()/Down(): renames show up as drop+add, which loses data
dotnet ef migrations script --idempotent -o migrate.sql   # review or ship SQL
dotnet ef migrations bundle --self-contained -o efbundle  # or a deployable runner
```

- Never edit a migration that has been applied anywhere else. Add a new migration instead. Use `dotnet ef migrations remove` only on a migration that has not been applied anywhere.
- Do not call `Database.MigrateAsync()` at startup in an environment that can run more than one instance, because replicas and the overlap between revisions will race on the schema. FundingRateArb auto-migrates only in Development; production runs `dotnet ef database update` in the deploy workflow behind a `concurrency` group. Keep it that way, and apply the same pattern in new projects (a pre-deploy step, a migration bundle, or a Container Apps job).

## Tests

- Use xUnit, Moq and FluentAssertions. Name tests `Method_Scenario_ExpectedResult`.
- **Stay on FluentAssertions 7.x** (for example `Version="7.*"` or `[7.0.0,8.0.0)`). Version 8 and later need a paid Xceed licence for commercial use. If a newer API is genuinely needed, suggest AwesomeAssertions or Shouldly, and don't bump the version on your own.
- For database tests, use SQLite in-memory (`Microsoft.EntityFrameworkCore.Sqlite` with `DataSource=:memory:`, keeping the connection open for the whole test). Use Testcontainers SQL Server when you need provider-specific behaviour. Avoid the EF InMemory provider: it has no relational constraints, no transactions and no SQL translation, so tests pass that fail in production. Existing InMemory tests can stay, but write new ones on SQLite.
- Use `WebApplicationFactory<Program>` for integration tests, and swap the `DbContext` registration for SQLite.
- Inject `TimeProvider` and use `FakeTimeProvider` (`Microsoft.Extensions.TimeProvider.Testing`) rather than calling `DateTime.UtcNow`.

## BackgroundService rules

Trading loops run as hosted services, so a mistake here stops trading silently or crashes the host.

- A hosted service is a singleton. To use scoped services, create a scope per iteration: `using var scope = _scopeFactory.CreateScope();` and resolve `IUnitOfWork` from it. Never inject a scoped service into the constructor.
- Pass `stoppingToken` to every await, and end the loop when cancellation is requested. Don't treat `OperationCanceledException` as an error on shutdown.
- Catch and log exceptions inside the loop body. An exception that escapes `ExecuteAsync` stops the whole host by default (`BackgroundServiceExceptionBehavior.StopHost`).
- Use `PeriodicTimer` with the injected `TimeProvider` rather than `Task.Delay` drift loops.
- On shutdown (`StopAsync`), stop opening new positions before you release connections. The host gives you limited time (`HostOptions.ShutdownTimeout`).

## Target framework

- New projects target the current .NET LTS. Pin the SDK in `global.json` with `"rollForward": "latestFeature"`.
- .NET 8 and .NET 9 both reach end of support on 2026-11-10, and .NET 10 is the LTS after them. Check https://dotnet.microsoft.com/platform/support/policy for the current dates before you advise on any upgrade.
- Upgrade in this order:
  1. Install the SDK.
  2. Change the target framework (TFM) in every `.csproj`, or in `Directory.Build.props` if it is set there.
  3. Bump the `Microsoft.*`, EF Core and `dotnet-ef` packages to the matching major version.
  4. Update `DOTNET_VERSION` in CI and the Dockerfile base images.
  5. Build, then test.
  6. Read the breaking-changes notes for ASP.NET Core and EF Core.

## Verify

```bash
dotnet build                     # FundingRateArb sets TreatWarningsAsErrors, so warnings fail
dotnet test --filter "FullyQualifiedName~PositionSizer"
dotnet format --verify-no-changes   # CI runs this
```
