# MCP LSP Setup

<div data-snippet="terminal-simulator"></div>

Symbol-level Go-to-Definition and Find-References across your pipelinekit checkout, served by an LSP-backed MCP. Ships as `.mcp.json` at the repo root with a `serena` entry (pinned placeholder) and a commented `claude-context` alternative.

## Why LSP-backed MCP

Claude Code's built-in `Grep` does string match across files. That works for tokens you can type literally, but it misses the structural questions that drive most real navigation:

- *"Where is `route_decision` defined?"* — `Grep` returns every comment, log line, and string literal that mentions the name. LSP returns the one definition site.
- *"Who calls `path_b_replan`?"* — `Grep` returns every textual mention. LSP returns the call graph: function calls only, scope-aware, across files.
- *"What does this symbol resolve to?"* — `Grep` can't answer at all without you reading every match by hand. LSP follows imports and reports the canonical binding.

An LSP-backed MCP server gives Claude these scope-aware operations as first-class tools, alongside `Grep` and `Read`. The two are complementary: `Grep` for textual presence, LSP for symbol identity.

`serena` is the LSP MCP shipped in the live `.mcp.json`. It launches a language server per project, indexes symbols, and exposes `find_definition` / `find_references` / `rename` / similar tools through the MCP stdio protocol. Claude Code reads the live `.mcp.json` at session start and connects to any servers listed in the `mcpServers` block.

## What ships

`.mcp.json` at the repo root, with one live entry (`serena`) and one commented alternative (`claude-context`):

- **`serena`** (active in `mcpServers`) — LSP-backed symbol navigation. Default per charter Open Question 3.
- **`claude-context`** (parked in `_mcpServers_alt`) — AST-chunked semantic RAG, complementary to LSP. Move into `mcpServers` and add Milvus / embedding credentials to enable. Both can run together for max-power; neither blocks the other.

Claude Code only reads the `mcpServers` key — anything under `_mcpServers_alt`, `_comment`, or `_security_note` is inert. The sidebar exists so a maintainer can flip the alternative on with one edit.

The `serena` entry's `git+https` URL has an intentional `<PIN-TO-COMMIT-SHA>` placeholder. The `uvx` command will fail until you replace it. This is fail-closed behavior — pipelinekit refuses to execute an unpinned upstream by default.

## How to activate serena

Four steps. First time only.

### 1. Install the `uv` toolchain

`uvx` ships inside the `uv` package. Pick one:

```bash
pip install uv          # any platform with python3 + pip
brew install uv         # macOS / Linuxbrew
```

Verify:

```bash
uvx --version           # expect 0.4.x or newer
```

### 2. Pick a known-good serena commit SHA

Visit [https://github.com/oraios/serena/commits/main](https://github.com/oraios/serena/commits/main) and copy a recent commit hash that you trust. Pin to a specific SHA — never `main`, never a tag you don't control. Pin freshness target: ≤ 30 days; older SHAs work but may lag on language-server bugfixes.

### 3. Edit `.mcp.json` and replace the placeholder

Open `.mcp.json` at the repo root and replace `<PIN-TO-COMMIT-SHA>` with the full 40-character SHA from step 2:

```json
"args": [
  "--from",
  "git+https://github.com/oraios/serena@abcdef0123456789abcdef0123456789abcdef01",
  "serena-mcp-server",
  "--project",
  "."
]
```

### 4. Restart Claude Code

Quit and relaunch — MCP servers are only re-read at session start. Once back in, run `/mcp` (or open the MCP status panel) and confirm `serena` appears as a connected `stdio` MCP server. First connect will take ~30s while `uvx` resolves the pin and bootstraps the language server.

## Verify

Ask Claude to use a serena tool against pipelinekit itself. Examples:

- *"Find the definition of the `path_b_replan` function in the pipeline skill."*
- *"List every caller of `route_decision` across the repo."*
- *"Show me where `block-stage-sensitive.sh` is wired into the hook config."*

If Claude returns scope-aware results (definition line numbers, caller paths, hook wiring sites), serena is live. If you get *"not found"* repeatedly across several queries, two things to check:

1. `uvx --version` returns 0.4.x or newer. Older `uvx` cannot resolve the `--from git+https@...` form.
2. The pinned SHA is recent (≤ 30 days). Re-pin to a fresh commit from step 2 and restart Claude Code again.

## Why pin the SHA

`git+https://github.com/oraios/serena` without a pinned ref defaults to whatever `main` points to right now. If upstream is compromised or a maintainer makes a bad merge, your next `uvx` invocation pulls and executes the new code on your machine, with full filesystem access, before any tool call returns.

Pinning to a commit SHA closes that window. The SHA is content-addressed: a malicious force-push to `main` cannot reach a pinned commit, and any tampered SHA fails the git fetch. This is the same supply-chain control that `requirements.txt`'s `--hash=sha256:` flag and `package-lock.json`'s `integrity:` field provide — applied to the MCP server bootstrap path.

Fail-closed default. The placeholder `<PIN-TO-COMMIT-SHA>` makes `uvx` error out by design. Activate serena by making a deliberate pin decision; never by leaving an unpinned ref in production.

## Alternative: claude-context

`claude-context` is an AST-chunked semantic RAG MCP from Zilliz (the Milvus commercial vendor — NOT Anthropic). It indexes the codebase into a vector store and answers natural-language queries like *"where is rate-limiting handled?"* with semantic matches.

Two modes:

- **Local**: set `EMBEDDING_PROVIDER` to `Ollama` (default in the parked entry) or `Transformers`, supply a local embedding model. No Milvus account needed.
- **Cloud**: set `MILVUS_ADDRESS` and `MILVUS_TOKEN` to Zilliz Cloud credentials.

To enable, move the `claude-context` block from `_mcpServers_alt` into `mcpServers` and fill in the env vars. Restart Claude Code.

claude-context and serena are complementary, not alternatives — they answer different questions:

- **serena** answers *"where exactly is this symbol?"* (symbolic / scope-aware).
- **claude-context** answers *"where is rate-limiting handled in this codebase?"* (semantic / fuzzy).

Run both together when you want both vectors. Neither blocks the other.

## Serena vs claude-context side-by-side

Switch between the two probe surfaces to see the same query routed differently.

<div data-snippet="comparison-tabs"></div>
