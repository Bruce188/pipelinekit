---
name: security-conventions
description: ASP.NET Core security conventions — anti-forgery, authorization, secret storage, parameterized queries, HTTPS. Loaded when working with controllers, API endpoints, authentication, authorization, or user input handling.
allowed-tools:
  - Read
user-invocable: false
paths:
  - claude/skills/security-conventions/**
  - "**/*.env*"
  - claude/config/never-stage.txt
  - "**/credentials*"
---

# Security Conventions

Security rules for all ASP.NET Core projects. These apply at implementation time, not just during review.

## Anti-Forgery

- `[ValidateAntiForgeryToken]` on every `[HttpPost]`, `[HttpPut]`, `[HttpDelete]` action
- `@Html.AntiForgeryToken()` in every form that posts
- For APIs called from the same site, prefer `[AutoValidateAntiforgeryToken]` globally in `Program.cs`

## Authorization

- `[Authorize]` on controllers that require authentication
- `[Authorize(Roles = "Admin")]` on admin-only controllers and actions
- **Ownership checks before every entity read/write**: `if (entity.UserId != currentUserId) return Forbid();`
- Never trust an ID from the request — always verify the current user owns the resource
- Use policy-based authorization (`[Authorize(Policy = "CanEditOrder")]`) for complex rules

## Secret Storage

- **Never** put API keys, connection strings, or credentials in `appsettings.json` or source files
- Dev: User Secrets — `dotnet user-secrets set "Key" "Value"`
- Prod: environment variables or a secret vault (Azure Key Vault, AWS Secrets Manager)
- Encrypt keys at rest using the Data Protection API (`services.AddDataProtection()`)
- `appsettings.Development.json` may contain non-sensitive defaults only

## Data Access

- EF Core parameterized queries only — LINQ or `FromSqlInterpolated`
- **Never** concatenate strings into SQL
- **Never** use `FromSqlRaw` with untrusted input
- Use migrations, not manual SQL, for schema changes

## Transport Security

- Enforce HTTPS in `Program.cs`: `app.UseHttpsRedirection()` + `app.UseHsts()`
- Cookies: `Secure = true`, `HttpOnly = true`, `SameSite = SameSiteMode.Strict` (or `Lax` for OAuth flows)
- Disable weak TLS versions at the hosting layer

## Input Validation

- Model validation via data annotations (`[Required]`, `[StringLength]`, `[EmailAddress]`, etc.)
- Check `ModelState.IsValid` on every POST — reject invalid requests with `BadRequest(ModelState)` or re-render the view
- Validate file uploads: size, extension, MIME type — and store outside the web root

## Error Handling

- Catch exceptions at the controller boundary (or use `UseExceptionHandler("/Error")` in `Program.cs`)
- **Never** leak stack traces, SQL errors, or internal paths to the client
- Log the full error server-side; return a generic message to the user
- Use `IExceptionHandler` (ASP.NET Core 8+) for centralized handling

## Related

- See `dotnet-conventions` skill for non-security patterns (Clean Architecture, DI, UnitOfWork, ViewModels, testing)
- See `security-auditor` agent for review-time vulnerability assessment
