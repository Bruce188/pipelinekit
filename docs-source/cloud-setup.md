# Cloud Setup

This file covers two distinct topics:

<div data-snippet="chooser-quiz" data-set="cloud-provider" data-question-set="deploy"></div>

1. **VM bootstrap** — provisioning a development VM (Oracle Cloud Free Tier ARM A1 or Hetzner CX22) where you run pipelinekit itself.
2. **Cloud deployment providers** — configuring Railway, Render, DigitalOcean, Azure, or Vercel as the deployment target for your projects.

---

## Cloud deployment providers

pipelinekit ships five first-class deployment-provider integrations. Charter Topic 10 selects the active provider; `/pipeline` routes all deployment-shaped tasks to the matching agent and ops skill automatically.

| Provider | Agent | Skill | CLI install |
|----------|-------|-------|-------------|
| Azure | `@azure-deployment-engineer` | `azure-ops` | Auto-installed by `scripts/install.sh` on Debian/Ubuntu |
| Vercel | `@vercel-deployment-engineer` | `vercel-ops` | `npm i -g vercel` |
| Railway | `@railway-deployment-engineer` | `railway-ops` | `npm i -g @railway/cli` |
| Render | `@render-deployment-engineer` | `render-ops` | See [render.com/docs/cli](https://render.com/docs/cli) |
| DigitalOcean | `@digitalocean-deployment-engineer` | `digitalocean-ops` | `snap install doctl` or [github.com/digitalocean/doctl](https://github.com/digitalocean/doctl) |

Each ops skill stops and prompts if its CLI is not authenticated — never auto-authenticates.

Provider-specific setup guides:
- `documentation/deployment-railway.html` — Railway account setup, project link, auth posture
- `documentation/deployment-render.html` — Render account setup, service link, render.yaml Blueprint
- `documentation/deployment-digitalocean.html` — DigitalOcean account setup, app link, App Spec (.do/app.yaml)

Azure and Vercel mode overlays are documented in `claude/CLAUDE.md.template` under `## Azure Mode` and `## Vercel Workflows`.

---

## VM bootstrap

Provision pipelinekit on a fresh Oracle Cloud Free Tier ARM A1 instance or a fresh Hetzner CX22 instance. Each section covers image selection, SSH, firewall, swap, bootstrap (two paths), and verification.

---

## Oracle Cloud Free Tier (ARM Ampere A1)

Oracle Free Tier includes Always Free Ampere A1 instances: up to 4 OCPU and 24 GB RAM total (combinable across up to 4 VMs). All A1 instances run on aarch64.

### Image

Select **Ubuntu 22.04** or **Ubuntu 24.04 LTS** (Canonical image). Choose the ARM64 variant. Minimum recommended shape: **VM.Standard.A1.Flex** with 1 OCPU / 6 GB RAM; the bootstrap works on any A1 shape.

### SSH

Upload your public key when creating the instance (Compute → Instances → Create Instance → Add SSH keys). The default login user is `ubuntu`.

For key generation, see [GitHub's SSH key guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent).

### Firewall

Oracle's default Security List allows inbound port 22 only. The bootstrap does not require additional inbound ports. If you plan to expose services later, add ingress rules in **Networking → Virtual Cloud Networks → your VCN → Security Lists**.

Note: Oracle also has OS-level iptables rules on Ubuntu images. If port 22 is unreachable after instance creation, check `sudo iptables -L INPUT -n` and flush or adjust.

### Swap

A1 has 24 GB RAM — swap is not required. The bootstrap skips swap by default. To enable a 4 GB swapfile (useful if you run memory-intensive workloads alongside pipelinekit):

```bash
# Pass --with-swap to oracle-bootstrap.sh
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh \
  | bash -s -- --with-swap
```

### Bootstrap

Two equivalent paths — pick one.

#### Path 1: Cloud-init at instance creation (fully unattended)

1. Copy the contents of [`scripts/cloud/oracle-cloud-init.yaml`](../scripts/cloud/oracle-cloud-init.yaml).
2. In Oracle Cloud Console → Create Instance → Advanced options → Management tab → paste the YAML into the **Cloud-init script** field.
3. Click **Create**. The bootstrap runs automatically at first boot (typically 3–8 minutes).
4. To inject env vars without typing them in the terminal, uncomment and fill the `write_files` block in the YAML before pasting.

Trade-offs: cloud-init is fully unattended (no SSH needed), but output is only visible via `sudo cat /var/log/pipelinekit-cloud-init.log` after the instance is up. Harder to debug mid-run.

#### Path 2: Post-boot via SSH (interactive)

```bash
ssh ubuntu@<your-oracle-ip>
# Optional: set env vars before running the bootstrap
# export USER_EMAIL="you@example.com"
# export USER_NAME="Your Name"
# export CLAUDE_CLI_SHA256=""          # set for a pinned install
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh \
  | bash
```

Trade-off: you see the output in real time and can interrupt if something goes wrong. Requires an SSH session.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_EMAIL` | (none — warned) | Substituted into `CLAUDE.md` |
| `USER_NAME` | (none — warned) | Substituted into `CLAUDE.md` |
| `CLAUDE_INSTALL_OPTIONALS` | `tresor,lsp,mcp` | Comma list of install.sh optional components |
| `CLAUDE_CLI_SHA256` | (none — warned) | SHA256 of `claude.ai/install.sh` for pinned installs |
| `PIPELINEKIT_DIR` | `$HOME/pipelinekit` | Repo clone target directory |
| `GH_TOKEN` | (none — warned) | GitHub token (only needed for private forks) |
| `ANTHROPIC_API_KEY` | (none — warned) | Set later via `claude login` |

Set them in the shell before `curl | bash`, or uncomment the `write_files` block in the cloud-init YAML.

### Verify

```bash
cd $HOME/pipelinekit
bash scripts/verify.sh
```

On ARM, you may see a `LSP_FAILURES` line listing `csharp-ls` — this is expected and benign (see Troubleshooting below).

---

## Hetzner Cloud CX22 (x86_64)

CX22 is a shared-vCPU server: 2 vCPU, 4 GB RAM, 40 GB SSD, running Ubuntu. It is x86_64. The 4 GB RAM ceiling requires a swapfile before npm install — the bootstrap handles this automatically.

### Image

Select **Ubuntu 22.04** or **Ubuntu 24.04 LTS** from the Hetzner image list. The default login user is `root`.

### SSH

Add your public SSH key in Hetzner Cloud Console → SSH Keys before creating the server, or paste it during creation. The key is injected automatically into `/root/.ssh/authorized_keys`.

### Firewall

Hetzner servers have no firewall by default (all ports reachable). If you create a firewall rule set, allow inbound TCP 22. The bootstrap does not require additional inbound ports.

### Swap

**Mandatory.** CX22 has only 4 GB RAM. Without swap, `npm install` for `typescript-language-server` can OOM and fail. The bootstrap creates a 2 GB swapfile by default before running apt-get.

To skip swap (not recommended):

```bash
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/hetzner-bootstrap.sh \
  | bash -s -- --no-swap
```

The script guards against duplicate swapfile creation: if `/swapfile` is already active in `swapon --show`, it skips creation.

### Bootstrap

Two equivalent paths — pick one.

#### Path 1: Cloud-init at server creation (fully unattended)

1. Copy the contents of [`scripts/cloud/hetzner-cloud-init.yaml`](../scripts/cloud/hetzner-cloud-init.yaml).
2. In Hetzner Cloud Console → Create Server → (bottom of page) → **User data** field, paste the YAML.
3. Click **Create & Buy now**. The bootstrap runs at first boot (typically 4–10 minutes, including swap setup and apt operations).
4. To inject env vars without typing them in the terminal, uncomment and fill the `write_files` block in the YAML before pasting.

#### Path 2: Post-boot via SSH (interactive)

```bash
ssh root@<your-hetzner-ip>
# Optional: set env vars
# export USER_EMAIL="you@example.com"
# export USER_NAME="Your Name"
# export CLAUDE_CLI_SHA256=""
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/hetzner-bootstrap.sh \
  | bash
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_EMAIL` | (none — warned) | Substituted into `CLAUDE.md` |
| `USER_NAME` | (none — warned) | Substituted into `CLAUDE.md` |
| `CLAUDE_INSTALL_OPTIONALS` | `tresor,lsp,mcp` | Comma list of install.sh optional components |
| `CLAUDE_CLI_SHA256` | (none — warned) | SHA256 of `claude.ai/install.sh` for pinned installs |
| `PIPELINEKIT_DIR` | `$HOME/pipelinekit` | Repo clone target directory |
| `GH_TOKEN` | (none — warned) | GitHub token (only needed for private forks) |
| `ANTHROPIC_API_KEY` | (none — warned) | Set later via `claude login` |

### Verify

```bash
cd $HOME/pipelinekit
bash scripts/verify.sh
```

On x86_64, all LSP tools should install cleanly. If you see `LSP_FAILURES`, check `~/.cache/pipelinekit-install.log`.

---

## Troubleshooting

### `uname -m` mismatch

Each bootstrap asserts the target architecture and exits immediately on mismatch:

- `oracle-bootstrap.sh` exits with an error if `uname -m` is not `aarch64`.
- `hetzner-bootstrap.sh` exits with an error if `uname -m` is not `x86_64`.

If you see this error, you are running the wrong script for your instance type.

### `claude: command not found` after bootstrap

The Claude CLI is installed to a path that may not be in your shell's `PATH` yet. Run:

```bash
source ~/.bashrc   # or ~/.profile, or start a new shell session
claude --version
```

If `claude` is still not found, the CLI install may have failed. Check the bootstrap log:

```bash
# Cloud-init path:
sudo cat /var/log/pipelinekit-cloud-init.log
# SSH path:
cat ~/.cache/pipelinekit-bootstrap.log
```

Then re-run `claude login`.

### npm OOM during install.sh

Symptom: install.sh fails during `npm install -g typescript-language-server` or similar, with a killed/OOM message.

Fix: ensure swap is active. Check with `swapon --show`. If no swap is listed:

```bash
# Hetzner — re-run bootstrap (idempotent, will create swap):
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/hetzner-bootstrap.sh | bash

# Oracle — re-run with explicit swap flag:
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh | bash -s -- --with-swap
```

Then re-run `scripts/install.sh` from inside the `pipelinekit` directory.

### `LSP_FAILURES` warning on ARM (Oracle A1)

`scripts/verify.sh` may print `LSP_FAILURES: csharp-ls` on aarch64. This is expected: the `csharp-ls` binary distribution does not ship an ARM64 native binary. All other LSP tools (pyright, typescript-language-server, gopls, rust-analyzer) install correctly on ARM64.

The warning is non-blocking: `install.sh` continues and `verify.sh` exits 0 for this case. Logs at `~/.cache/pipelinekit-install.log`.

### Re-running the bootstrap to recover from a partial install

All bootstrap scripts are idempotent: re-running on a partially-provisioned instance converges cleanly. Every step is guarded:

- `dpkg -s <pkg>` before apt installs
- `command -v node` before NodeSource setup
- `command -v claude` before CLI install
- `git -C <dir> pull` instead of re-cloning if the repo directory exists
- `swapon --show` before swapfile creation

Simply re-run the same `curl | bash` command you used the first time.

## Pipelinekit command cheatsheet

Filter the slash-command table below by `pipeline`, `install`, `analyze`, or any other keyword to surface the commands you will reach for during initial cloud bootstrap.

<div data-snippet="command-cheatsheet"></div>
