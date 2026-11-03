# ASP.NET Core security defaults

These defaults apply when you write code. For a review of a finished diff, use `/security-review` instead. For the handling of exchange API keys, see the `exchange-api-keys` skill.

## Antiforgery

- In MVC, add `AutoValidateAntiforgeryTokenAttribute` once as a global filter (FundingRateArb does this in `Program.cs`). Don't also put `[ValidateAntiForgeryToken]` on each action.
- With minimal APIs, `app.UseAntiforgery()` validates form-bound endpoints automatically.
- **Exempt token-authenticated APIs.** Endpoints authenticated by a bearer token, JWT or API-key header are not exposed to CSRF, because the browser does not attach the credential automatically. Antiforgery on them only breaks non-browser clients. Use `[IgnoreAntiforgeryToken]` on those controllers.

## Authorization

- Prefer a global fallback policy to remembering `[Authorize]` on each controller:
  `options.FallbackPolicy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build();`
  Then opt out with `[AllowAnonymous]`.
- Check ownership on every read and write of a user-owned entity: `if (entity.UserId != currentUserId) return Forbid();`. Never trust an ID that comes from the route or the body. In FundingRateArb this matters most for `UserExchangeCredential` and positions.
- Put admin-only code in the `Admin` area with role or policy authorization.

## Secrets and Data Protection

- Exchange keys and connection strings never go in `appsettings*.json`. In development, use `dotnet user-secrets set "Exchanges:Aster:ApiKey" ...`. In production, use Azure Key Vault, loaded through `AddAzureKeyVault`. Key Vault secret names use `--` where configuration keys use `:` (for example `Exchanges--Aster--ApiKey`).
- Per-user credentials are encrypted at rest through `IApiKeyVault`, implemented in `Infrastructure/Services/ApiKeyVault.cs` on top of the Data Protection API. Reuse it; don't write new encryption code.
- **Persist the Data Protection key ring outside the container** (`PersistKeysToAzureBlobStorage`, or a mounted volume). Otherwise every restart makes the stored keys impossible to decrypt and logs users out.
- Keep `SetApplicationName("FundingRateArb")` constant. It is the key-ring discriminator, and changing it orphans every encrypted credential.
- Never return decrypted secrets to a view. Show `****` (`SettingsController` already does this) and never show the first or last characters either.

## Cookies

- Use `SameSite=Lax` by default. `Strict` breaks the external-login and OAuth return flows (Google and GitHub sign-in), because the browser withholds the cookie on the cross-site redirect. Reserve `Strict` for cookies that are only used by admins.
- Set `HttpOnly` and `SecurePolicy = Always` outside Development.

## Abuse limits

- Put `AddRateLimiter` policies on login, register, password reset and the endpoints that save credentials.
- Validate file uploads (size, extension and content sniffing), and store them outside `wwwroot`.

## Raw SQL

- Use `FromSql`/`FromSqlInterpolated` with interpolated parameters. Pass `FromSqlRaw` and `ExecuteSqlRaw` constant SQL only, never request data.
