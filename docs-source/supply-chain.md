<!--
diataxis: explanation
-->
# Supply-Chain Pin Hardening

pipelinekit's installer fetches code from upstream sources at install time:

- **serena** — semantic-code MCP from `git+https://github.com/oraios/serena`
- **Azure CLI** — Microsoft's `InstallAzureCLIDeb` one-liner
- **Claude CLI** — Anthropic's `https://claude.ai/install.sh` (cloud-bootstrap path)

Each of these is, by default, a `curl | bash`-shaped trust handoff. Prior versions of the installer warned about the lack of pinning but installed anyway. This page documents the three secure-default gates that now fail closed — each gate ships with an explicit opt-out for cases where verification is impractical.

The three gates compose one fail-closed install path: each gate REFUSES (accent, the secure default) and clears to PROCEED (muted) only when a pin or an explicit opt-out flag is supplied.

<svg viewBox="0 0 760 300" role="img" aria-label="Fail-closed flow through the three supply-chain install gates" style="width:100%;height:auto;font-family:var(--sans);">
  <title>serena, Azure CLI, and Claude CLI install gates as a fail-closed flow</title>
  <defs>
    <marker id="sc-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="var(--border-strong)"></path>
    </marker>
    <marker id="sc-arrow-refuse" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="var(--accent)"></path>
    </marker>
  </defs>
  <rect x="14" y="40" width="104" height="48" fill="var(--bg-elev)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
  <text x="66" y="60" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">install /</text>
  <text x="66" y="77" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">bootstrap</text>
  <g>
    <rect x="170" y="36" width="120" height="56" fill="var(--accent-soft)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
    <text x="230" y="58" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">Gate 1</text>
    <text x="230" y="76" text-anchor="middle" fill="var(--fg-muted)" font-size="11">serena ref</text>
  </g>
  <g>
    <rect x="342" y="36" width="120" height="56" fill="var(--accent-soft)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
    <text x="402" y="58" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">Gate 2</text>
    <text x="402" y="76" text-anchor="middle" fill="var(--fg-muted)" font-size="11">Azure .deb</text>
  </g>
  <g>
    <rect x="514" y="36" width="120" height="56" fill="var(--accent-soft)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
    <text x="574" y="58" text-anchor="middle" fill="var(--fg)" font-size="12" font-weight="600">Gate 3</text>
    <text x="574" y="76" text-anchor="middle" fill="var(--fg-muted)" font-size="11">Claude CLI</text>
  </g>
  <rect x="680" y="40" width="68" height="48" fill="var(--bg-elev)" stroke="var(--border-strong)" stroke-width="1.5" rx="6"></rect>
  <text x="714" y="60" text-anchor="middle" fill="var(--fg)" font-size="11" font-weight="600">install</text>
  <text x="714" y="77" text-anchor="middle" fill="var(--fg)" font-size="11" font-weight="600">proceeds</text>
  <g stroke="var(--border-strong)" stroke-width="1.5" fill="none" marker-end="url(#sc-arrow)">
    <line x1="118" y1="64" x2="168" y2="64"></line>
    <line x1="290" y1="64" x2="340" y2="64"></line>
    <line x1="462" y1="64" x2="512" y2="64"></line>
    <line x1="634" y1="64" x2="678" y2="64"></line>
  </g>
  <g fill="var(--fg-subtle)" font-size="10" text-anchor="middle">
    <text x="315" y="56">pass</text>
    <text x="487" y="56">pass</text>
    <text x="657" y="56">pass</text>
  </g>
  <g stroke="var(--accent)" stroke-width="1.5" fill="none" marker-end="url(#sc-arrow-refuse)">
    <line x1="230" y1="92" x2="230" y2="180"></line>
    <line x1="402" y1="92" x2="402" y2="180"></line>
    <line x1="574" y1="92" x2="574" y2="180"></line>
  </g>
  <g>
    <rect x="170" y="184" width="120" height="58" fill="none" stroke="var(--accent)" stroke-width="1.5" rx="6"></rect>
    <text x="230" y="206" text-anchor="middle" fill="var(--accent)" font-size="11" font-weight="600">REFUSE</text>
    <text x="230" y="225" text-anchor="middle" fill="var(--fg-muted)" font-size="10">SERENA_REF=main</text>
  </g>
  <g>
    <rect x="342" y="184" width="120" height="58" fill="none" stroke="var(--accent)" stroke-width="1.5" rx="6"></rect>
    <text x="402" y="206" text-anchor="middle" fill="var(--accent)" font-size="11" font-weight="600">REFUSE</text>
    <text x="402" y="225" text-anchor="middle" fill="var(--fg-muted)" font-size="10">sha256 mismatch</text>
  </g>
  <g>
    <rect x="514" y="184" width="120" height="58" fill="none" stroke="var(--accent)" stroke-width="1.5" rx="6"></rect>
    <text x="574" y="206" text-anchor="middle" fill="var(--accent)" font-size="11" font-weight="600">REFUSE</text>
    <text x="574" y="225" text-anchor="middle" fill="var(--fg-muted)" font-size="10">no sha256 pin</text>
  </g>
  <text x="402" y="272" text-anchor="middle" fill="var(--fg-subtle)" font-size="11" font-style="italic">fail-closed default — clears only with a pin or explicit opt-out</text>
</svg>

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

<details>
<summary>At a glance: each gate's default and opt-out (click to expand)</summary>

| Gate | Default posture | Recommended pin | Acknowledge-and-proceed |
|------|-----------------|-----------------|-------------------------|
| 1 — serena | REFUSE rolling `main` | `SERENA_REF=<sha>` | `SERENA_ALLOW_ROLLING=1` |
| 2 — Azure CLI | proceed over https (no sha) | `INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY=1` + URL + `AZURE_CLI_DEB_SHA256` | (default is already proceed) |
| 3 — Claude CLI | REFUSE without sha256 | `CLAUDE_CLI_SHA256=<sha>` | `CLAUDE_CLI_ALLOW_UNVERIFIED=1` |

Gates 1 and 3 fail closed (refuse unless pinned or explicitly acknowledged); gate 2 is opt-in verification layered over the preserved default path.

</details>

## Reference

- `scripts/install.sh` — gates 1 and 2 (serena, Azure CLI).
- `scripts/cloud/oracle-bootstrap.sh`, `scripts/cloud/hetzner-bootstrap.sh` — gate 3 (Claude CLI).
- `tests/test_install_fail_closed.sh` — automated assertions for refuse/opt-out behaviour.
- `.mcp.json.template` — current serena pin and the `_serena_pin_note` provenance string.
