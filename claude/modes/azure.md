## Azure Mode

Azure 部署專案工作流疊加層。適用專案部署至 Azure (App Service, Container Apps, Function Apps, Azure DB)。部署相關工作透過 `@azure-deployment-engineer` 與 `azure-ops` 技能路由；非部署階段沿用預設管道代理。

| Phase | Agents / Skills | Notes |
|-------|-----------------|-------|
| analyze | default `/analyze` | No Azure-specific gating at analyze-time. |
| plan | default `/create-plan` | If plan touches Azure deploy config, include explicit `@azure-deployment-engineer` task per resource. |
| implement | `@azure-deployment-engineer` for ARM / Bicep / `az` CLI / pipeline YAML tasks; default agents otherwise | Use the `azure-ops` skill for day-to-day ops against an already-authenticated context. |
| review | default `/review` + `@azure-deployment-engineer` consulted on Azure-touching diffs | Security-auditor remains primary on auth / secret / RBAC changes. |
| merge | default `/ppr` | No Azure-specific merge gate. |

**Gotchas:**
- `azure-ops` STOPS and prompts if `az account show` fails — never auto-authenticates. Run `az login` (or the CI service-principal equivalent) before invoking deploy commands.
- Azure CLI auto-install runs at `scripts/install.sh` time on Debian / Ubuntu only. On macOS / RHEL / Arch hosts the installer prints the Homebrew / Microsoft-docs link and continues; install the CLI manually before first use.
- Secrets (connection strings, SAS tokens, service-principal JSON) NEVER go in committed files. Use Key Vault references in App Settings, or store under names matched by `~/.claude/config/never-stage.txt` so `block-stage-sensitive.sh` refuses to stage them.
- App Service / Container Apps deploys are not idempotent across regions — confirm the target `--resource-group` + `--name` before re-running a deploy command.
