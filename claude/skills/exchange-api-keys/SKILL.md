---
name: exchange-api-keys
description: Rules and runbooks for live crypto-exchange credentials in Bruce's trading bots, CryptoBargain (Python, Lighter) and FundingRateArb (C#, Lighter/Aster/Hyperliquid/Binance/dYdX). Covers where keys load from, keeping them out of logs, chat and commits, testnet vs mainnet and dry vs live, withdrawal-disabled and IP-restricted keys, storage per deploy target, rotation, and what to do after a leak. Use whenever code reads, stores, logs or transmits exchange keys, private keys or signer keys, when adding an exchange connector, when setting up or rotating a key, or when a key may have leaked.
---

# Exchange API keys

These keys control real funds, so a leaked key can mean an empty account within minutes. Everything below follows from that.

## Where the keys live today

| | CryptoBargain | FundingRateArb |
|---|---|---|
| Exchanges | Lighter | Lighter, Aster, Hyperliquid, Binance, dYdX (plus CoinGlass data) |
| Secret | `LIGHTER_API_KEY_PRIVATE` (order-signing key). `ACCOUNT_INDEX`, `API_KEY_INDEX` and `WALLET_ADDRESS` are public. | Operator keys under config `Exchanges:<Venue>:*` (for example `Exchanges:Lighter:SignerPrivateKey`, `Exchanges:Aster:ApiSecret`, `Exchanges:Hyperliquid:PrivateKey`). Per-user keys are in the `UserExchangeCredential.Encrypted*` columns. |
| Loaded by | `live_common.Creds.resolve()`: `.env` (via `load_env` and systemd `EnvironmentFile`), with a fallback to `~/cryptobargain-backup/lighter-creds.json` | `IConfiguration`: user-secrets in development, Azure Key Vault (`KeyVaultName`) in production. Per-user keys are decrypted through `IApiKeyVault` (Data Protection). |
| Non-secret | `.env.example` (the only env file that is tracked) | `appsettings*.json` holds `PLACEHOLDER` values only |

Also secret: `DASH_ADMIN_TOKEN` (CryptoBargain dashboard writes) and `BOT_ALERT_WEBHOOK`.

## Never expose a key

- Don't `cat`, `grep`, `print`, `echo` or `env` a file or variable that holds a key, and don't read `.env`, `.env.*`, `lighter-creds.json` or user-secrets into the conversation. To check that a key is present, test its length or a hash: `python -c 'import os;print(len(os.environ.get("LIGHTER_API_KEY_PRIVATE","")))'`.
- If a user pastes a key into chat, tell them to treat it as leaked and follow "If a key leaks" below.
- Logs and exceptions must never contain key material, signed payloads, signature query strings or auth headers. Mask the value completely: FundingRateArb's `SettingsController` returns `****`. Log the account index or the key index, never the key. A new connector needs a test showing that its error path does not include the key.
- In C#, keep keys in local scope only. Don't store them on a field that gets logged or serialised (`AsterWithdrawClientFactory` shows the pattern). Don't log a whole request or options object in a connector.
- Never commit a key. The `never-stage` hooks block `.env*` and `credentials*`, but a key pasted into `.cs`, `.py`, a test or a doc gets past them. Before you commit, search the diff for `0x[0-9a-fA-F]{64}` and long base64 strings.

## Testnet vs mainnet, dry vs live

- **CryptoBargain:**
  - `live_runner.py --mode dry` is the default and places no orders. `--mode live` is live trading.
  - `LIGHTER_BASE_URL` defaults to mainnet. For testnet, set `https://testnet.zklighter.elliot.ai` (chain ID 300; mainnet is 304) **and** use a key registered on testnet. Keep the base URL and the key together.
  - The systemd unit runs `--mode live` against the real `.env`. Run smoke tests from a worktree with `--mode dry`, because `singleton.py` locks the `state/.bot.lock` relative to the current directory.
- **FundingRateArb:**
  - Mainnet URLs and chain IDs are hardcoded (`LighterSigner.MainnetChainId = 304`, `dydx-mainnet-1`), and there is no testnet switch.
  - Paper trading is `BotConfiguration.DryRunEnabled`.
  - Never point a development environment at production keys. Development uses user-secrets with keys for a separate, small sub-account.
- A new connector should take the network as configuration and refuse to start when the network and the key's environment disagree.

## Scope keys down

| Venue | Withdrawal exposure | IP restriction |
|---|---|---|
| Hyperliquid | Use an **API (agent) wallet**: it can trade but cannot withdraw. Only the master wallet signs withdrawals. | No |
| Aster | Create the API key with trading permission only, and enable its IP restriction. Check the withdrawal settings in Aster's API Management page; the docs I checked don't confirm a per-key withdrawal toggle. | Yes, so whitelist the egress IP |
| Lighter | Its docs don't describe a key scope without withdrawal, so treat an API key as able to move funds. Use a dedicated key index per bot, and keep the account balance at what the strategy needs. | Not documented |
| Binance | Enable reading and futures trading, leave withdrawals off, and restrict the key to trusted IPs. | Yes |

FundingRateArb's capital-transfer code (`Infrastructure/Services/Capital/*WithdrawClientFactory.cs`) needs **master** wallet keys, because it withdraws on Aster and Hyperliquid. That is the only code that should ever hold a key able to withdraw. Keep it behind its own admin-only path, and don't reuse those keys in the trading connectors.

For IP whitelisting, the egress IP must be stable. Azure Container Apps' outbound IP can change unless you put it behind a NAT gateway. On a home host, a residential IP changes too, so check it before you enable the restriction.

## Storage per deploy target

| Target | Store |
|---|---|
| CryptoBargain on its systemd host | `.env` with `chmod 600`, git-ignored, read through `EnvironmentFile`. The backup JSON lives outside the repo, also with `chmod 600`. |
| FundingRateArb on Azure Container Apps | Key Vault secret `Exchanges--<Venue>--<Field>`, read through managed identity. Per-user keys go in the database, encrypted by Data Protection with the key ring persisted to Blob storage. |
| Railway, Render, DigitalOcean, Vercel | The provider's secret env vars. See the `deploy` skill for how to set them without the value appearing in argv. |
| Local .NET development | `dotnet user-secrets set "Exchanges:Aster:ApiKey" ...`, typed by the user |

## Rotation, step by step

1. Create the new key on the exchange with the same restricted scope (trade only, IP list). On Lighter, register a new API key index with `change_api_key`, which is signed by the L1 wallet.
2. The user writes it to the store: `.env`, Key Vault (`az keyvault secret set ... --file`), or the provider's env var. Don't put the value in a command you run.
3. Restart **one** instance:
   - CryptoBargain: restart the systemd unit.
   - FundingRateArb: a new revision, or a restart (`az containerapp revision restart`), so that Key Vault values are read again.
4. Verify:
   - The bot starts.
   - An authenticated read works (balance or open orders).
   - Logs show no auth errors.
5. Revoke the old key on the exchange, then confirm the old key gets an auth error.
6. Delete any backup copies of the old key, such as `.env.*-bak` or old entries in `lighter-creds.json`.

## If a key leaks

Signs of a leak: it was pasted in chat, committed, appeared in a log, or shows up in an unexpected order.

1. **Revoke it on the exchange first**, before cleaning anything. On Lighter, replace the key at that index. Rewriting git history doesn't help if the key has already been pushed.
2. Stop the bot, so it doesn't fight with an attacker or trade on a dead key.
3. Check the account for unexpected orders, positions, transfers or withdrawals. Flatten if needed (CryptoBargain has `flatten.py`).
4. Rotate (above). If a master or wallet private key leaked, move the funds to a new wallet, because a wallet key can't be revoked.
5. Clean up: purge it from logs, and rewrite history if it was committed (`git filter-repo`). Do this only after steps 1 to 4.
6. Tell the user what was exposed, where, and what was done.
