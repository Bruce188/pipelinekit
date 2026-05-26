# Supply-Chain Pin Hardening

pipelinekit's installer fetches code from upstream sources at install time:

- **serena** — semantic-code MCP from `git+https://github.com/oraios/serena`
- **Azure CLI** — Microsoft's `InstallAzureCLIDeb` one-liner
- **Claude CLI** — Anthropic's `https://claude.ai/install.sh` (cloud-bootstrap path)

Each of these is, by default, a `curl | bash`-shaped trust handoff. Prior versions of the installer warned about the lack of pinning but installed anyway. This page documents the three secure-default gates that now fail closed — each gate ships with an explicit opt-out for cases where verification is impractical.

## Gate 1 — serena rolling-ref refusal

**File:** `scripts/install.sh`
**Trigger:** `SERENA_REF=main` (default) without explicit opt-out.

The serena MCP is loaded at MCP-client startup. Installing from a floating `main` branch means an upstream account takeover (or compromised CI) can execute arbitrary code on your host the next time a client starts.

```text
[install][error] Refusing to install serena from rolling ref 'main'.
```

### Opt-out paths

1. **Pin to a commit SHA (recommended):**

   ```bash
   export SERENA_REF=9b292a6c8b03c8306f117efeabb0ea7afdb0b3c0
   bash scripts/install.sh
   ```

   The current pin is documented under the `serena` entry of `.mcp.json.template`. Refresh it by running `git ls-remote https://github.com/oraios/serena.git main` and replacing the SHA + the `_serena_pin_note` date.

2. **Acknowledge rolling installs (NOT recommended for CI/prod):**

   ```bash
   export SERENA_ALLOW_ROLLING=1
   bash scripts/install.sh
   ```

   The installer still warns and proceeds.

## Gate 2 — Azure CLI sha256 verification (opt-in)

**File:** `scripts/install.sh`
**Default:** unchanged — `curl -sL https://aka.ms/InstallAzureCLIDeb | bash`.

Microsoft does not publish a sha256 alongside the install one-liner, so trust is bound to the https origin. The default path is preserved so existing installer flows keep working.

For verified installs, set:

```bash
export INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY=1
export AZURE_CLI_DEB_URL='https://packages.microsoft.com/repos/azure-cli/pool/main/a/azure-cli/azure-cli_X.Y.Z-1~jammy_all.deb'
export AZURE_CLI_DEB_SHA256='<64-char hex>'
bash scripts/install.sh
```

The installer downloads the `.deb`, runs `sha256sum -c -`, and `dpkg -i`s the package. A mismatch aborts with `Azure CLI .deb sha256 mismatch (expected …)`.

Both URL and sha256 are required when the opt-in flag is set; either missing falls back to the default curl-to-bash path with a warning. The .deb listing lives at <https://packages.microsoft.com/repos/azure-cli/pool/main/a/azure-cli/>.

## Gate 3 — Claude CLI sha256 mandatory

**Files:** `scripts/cloud/oracle-bootstrap.sh`, `scripts/cloud/hetzner-bootstrap.sh`
**Trigger:** `CLAUDE_CLI_SHA256` empty without explicit opt-out.

The cloud-bootstrap scripts install the Claude CLI by downloading `https://claude.ai/install.sh` and piping it through `bash`. Without a sha256 pin, a MITM or upstream-account compromise executes arbitrary code as the bootstrap user.

```text
[bootstrap][error] Refusing to install Claude CLI without a sha256 pin.
```

### Opt-out paths

1. **Pin the installer checksum (recommended):**

   ```bash
   export CLAUDE_CLI_SHA256=<64-char hex>
   bash scripts/cloud/oracle-bootstrap.sh
   ```

   Anthropic publishes release notes at <https://docs.claude.com/en/release-notes/claude-code>; compute the sha256 of the current installer with `curl -fsSL https://claude.ai/install.sh | sha256sum`.

2. **Acknowledge unpinned installs:**

   ```bash
   export CLAUDE_CLI_ALLOW_UNVERIFIED=1
   bash scripts/cloud/oracle-bootstrap.sh
   ```

   The bootstrap still logs an unpinned-install notice.

`scripts/install.sh` itself does not invoke the Claude CLI installer; the gate fires from the cloud-bootstrap entry points only.

## Reference

- `scripts/install.sh` — gates 1 and 2 (serena, Azure CLI).
- `scripts/cloud/oracle-bootstrap.sh`, `scripts/cloud/hetzner-bootstrap.sh` — gate 3 (Claude CLI).
- `tests/test_install_fail_closed.sh` — automated assertions for refuse/opt-out behaviour.
- `.mcp.json.template` — current serena pin and the `_serena_pin_note` provenance string.
