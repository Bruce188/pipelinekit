---
name: ios
description: Xcode 26.3 + Anthropic Claude Agent SDK integration — project setup, in-editor usage, Agent SDK API surface, simulator integration, code signing & TestFlight workflows
---

# iOS Development with Xcode 26.3 + Claude Agent SDK

This skill covers the integration between Xcode 26.3 and Anthropic's Claude Agent SDK. It documents project setup, in-editor usage patterns, the Agent SDK API surface for Swift, iOS Simulator integration via the optional `ios-simulator-mcp` MCP, and code signing/TestFlight workflows as they relate to the SDK. Based on the Feb-2026 baseline; see `docs/xcode-sdk-verification.md` for the most-recent verification.

## Keywords

Xcode 26.3, Claude Agent SDK, Anthropic Agent SDK, Claude Code, Swift, SwiftUI, UIKit, iOS development, agentic coding, code signing, TestFlight, App Store Connect, ios-simulator-mcp, XcodeBuildMCP, autonomous coding, visual verification, MCP Xcode, in-editor AI, project-wide reasoning

## Capabilities

### Xcode 26.3 Integration Overview

Xcode 26.3 ships with a native integration of the Claude Agent SDK — the same foundation that powers Claude Code, now available directly inside the IDE. Key capabilities:

- **Autonomous task execution**: Claude accepts high-level goals ("Refactor the authentication module to use async/await throughout"), breaks them into steps, modifies multiple files, and iterates until the goal is achieved or user input is required.
- **Visual verification**: Claude can capture Xcode Previews to see the SwiftUI interface it is building, identify visual issues, and iterate from the preview result. This is particularly powerful for UI-heavy SwiftUI development where visual feedback accelerates iteration.
- **Project-wide reasoning**: Claude understands the complete app architecture — SwiftUI views, UIKit controllers, Swift Data models, SPM dependencies, build settings, and their relationships — before making modifications. This reduces incorrect imports and broken symbol references compared to single-file AI completions.
- **MCP exposure**: Xcode 26.3 exposes its capabilities through the Model Context Protocol. Claude Code users running the CLI can connect to Xcode over MCP to trigger builds, capture previews, and read diagnostics without leaving the terminal.
- **Subagents, background tasks, and plugins**: The Xcode integration supports the full Claude Agent SDK feature set, including spawning subagents for focused subtasks, running tasks in the background while the developer continues editing, and extending behaviour via plugins.

Verification status: use Feb-2026 baseline; APIs unchanged — confirmed 2026-05-17. See `docs/xcode-sdk-verification.md`.

### Project Setup

How to enable the Claude integration in an Xcode project:

1. **Install Xcode 26.3** from the Mac App Store or the Apple Developer Portal. Xcode 26.3 is required — earlier versions do not include the Claude Agent SDK integration layer.
2. **Open the target project** in Xcode 26.3. The Claude Agent SDK integration is project-aware by default; no per-project configuration file is required.
3. **Sign in with your Anthropic account or API key**: navigate to Xcode → Settings → Claude → authenticate with your Anthropic account (uses your claude.ai subscription) or paste an `ANTHROPIC_API_KEY` for API-key billing.
4. **Invoke Claude**: use the keyboard shortcut or the Claude panel in the Xcode toolbar. Claude has immediate access to the open project's full source tree, build settings, and Swift Package dependencies.
5. **Framework and SPM targets**: the integration works across App targets, Framework targets, and Swift Package targets within the same workspace. Claude understands the dependency graph between targets.

For projects that use the Claude Agent SDK programmatically (i.e., Swift code that calls into the SDK to build AI-powered features), add the SDK as a Swift Package dependency:
```
https://github.com/anthropics/claude-agent-sdk-swift
```
<!-- verify at implement time: confirm the canonical Swift SPM URL for claude-agent-sdk-swift -->

### In-Editor Usage

Invoking Claude from Xcode's source editor:

- **Keyboard shortcut**: the canonical binding for opening the Claude panel is set during initial setup in Xcode → Settings → Key Bindings → Claude. <!-- verify at implement time: confirm default keybinding once Xcode 26.3 GA ships -->
- **Context provided to Claude**: when invoked from a source file, Claude sees the current file, the selected text (if any), the project structure (file tree), and recent build errors from the issue navigator.
- **Inline completions**: Claude can suggest multi-line code completions directly in the source editor, styled similarly to Xcode's native code completion but with full project context rather than type-inference-only context.
- **Panel mode**: for longer conversations or multi-file tasks, the Claude panel (sidebar or bottom sheet) provides a persistent session that survives file switches.
- **Preview integration**: in SwiftUI files, Claude can trigger a preview build and receive the visual result as part of its context, allowing it to iterate on layout, colors, and spacing with visual feedback in the loop.

### Agent SDK API Surface

The Claude Agent SDK exposes a set of public APIs for Swift code that calls the SDK to build AI-powered features in an iOS/macOS app. All signatures below reflect the Feb-2026 baseline.

<!-- verify at implement time: SDK API signatures — use the canonical Swift SDK docs at code.claude.com/docs/en/agent-sdk -->

**Core query function** (Python/TypeScript SDK pattern, Swift equivalent):
```swift
// Example pattern — verify exact Swift API at implement time
import ClaudeAgentSDK

let stream = try await ClaudeAgent.query(
    prompt: "Analyze the auth module",
    options: ClaudeAgentOptions(allowedTools: ["Read", "Glob", "Grep"])
)
for try await message in stream {
    print(message)
}
```

**Built-in tools available to Swift-hosted agents**: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Monitor, AskUserQuestion — the same tool set as Claude Code.

**Subagents**: the SDK supports spawning subagents from Swift with custom instructions and tool sets via `AgentDefinition`. <!-- verify at implement time: Swift-specific AgentDefinition API -->

**Sessions**: session IDs can be captured from the `SystemMessage` init event and used to resume or fork sessions. <!-- verify at implement time: Swift session resume API -->

**Hooks**: lifecycle callbacks at `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`. Hooks can log, validate, block tool use, or transform agent behaviour.

**MCP servers**: the SDK accepts `mcpServers` configuration to connect agents to external tools. In Xcode this is how the IDE exposes build/preview capabilities to a Claude Code CLI session.

For authoritative API reference, use `context7` MCP (`resolve-library-id` → `claude-agent-sdk`) or visit `https://code.claude.com/docs/en/agent-sdk`.

### macOS Host Requirement

Xcode is macOS-only. The Claude Agent SDK's Xcode integration is therefore macOS-only as well.

**For Linux/WSL2 developers:**
- **XcodeBuildMCP** (optional MCP, advisory entry in `.mcp.json.template` under `_mobile_mcpServers`): provides remote Xcode build capabilities — trigger builds, run tests, capture diagnostics from a Linux/WSL2 host by connecting to a macOS build host over SSH. This is the recommended path for teams with Linux CI and macOS build machines.
- **ios-simulator-mcp** (optional MCP, advisory entry in `.mcp.json.template` under `_mobile_mcpServers`): programmatic iOS Simulator control. Requires a macOS host with Xcode installed; does not function on Linux/WSL2 natively.
- **macOS CI runners**: Codemagic, Bitrise, and GitHub Actions (`macos-latest`) provide hosted macOS runners with Xcode pre-installed for iOS build and test automation without a dedicated macOS machine.

**For macOS developers:** Xcode 26.3 is available from the Mac App Store and the Apple Developer Portal. Ensure Xcode Command Line Tools are installed (`xcode-select --install`) for `xcrun` and `xcodebuild` CLI access.

### iOS Simulator Integration

The optional `ios-simulator-mcp` MCP provides programmatic control of the iOS Simulator:

- Launch and terminate specific simulator devices
- Install and uninstall app builds
- Capture screenshots and screen recordings
- Send simulated push notifications
- Control device state (rotate, shake, lock, change network conditions)

**Prerequisites:** macOS host with Xcode 26.3 installed. The `ios-simulator-mcp` MCP is activated by moving the `ios-simulator-mcp` entry from `_mobile_mcpServers` into `mcpServers` in your project's `.mcp.json`.

**PIN the git+https ref**: the `ios-simulator-mcp` entry in `.mcp.json.template` uses `@main` as the ref. Before sandbox use, replace `@main` with a pinned commit SHA (as instructed in `.mcp.json.template`'s `_mobile_instructions` comment).

### Code Signing and TestFlight

The Claude Agent SDK is a developer-time tool — it runs in the Xcode IDE and in the `claude` CLI during development and CI. It does NOT interact with code signing, provisioning profiles, or TestFlight workflows at runtime.

- **Code signing is unaffected** by enabling or disabling the Claude integration. The SDK does not inject entitlements, modify the binary, or require special provisioning.
- **TestFlight and App Store Connect submissions** proceed identically whether or not the project uses the Claude Agent SDK during development. The SDK is not linked into the app binary.
- **Privacy manifest**: the Claude Agent SDK (as a development tool) does not add `PrivacyInfo.xcprivacy` requirements to your app. If your Swift code calls the SDK at runtime (to build AI-powered features in your app), review the SDK's privacy manifest requirements for required-reason API usage at that point.

## How to Use

Natural-language invocations for this skill:

- "Set up the Claude Agent SDK integration in a new Xcode 26.3 project"
- "Enable the Claude panel in Xcode and start a project-wide refactoring session"
- "Use visual verification to iterate on a SwiftUI layout with Claude watching the preview"
- "Connect Claude Code CLI to Xcode over MCP to trigger a build and capture diagnostics"
- "Configure XcodeBuildMCP in .mcp.json for remote iOS builds from a Linux host"
- "Set up ios-simulator-mcp to programmatically control the iOS Simulator during testing"
- "Review code signing requirements — does the Claude Agent SDK affect provisioning?"

## When to Use

- Native iOS app development with AI assistance — Xcode 26.3 + Claude Agent SDK is the canonical path for Apple platform agentic coding
- SwiftUI-heavy projects where visual preview feedback accelerates UI iteration
- Multi-file refactoring tasks that benefit from Claude's project-wide context (rename symbols, change API signatures, update all call sites)
- CLI-based Claude Code workflows that need to trigger Xcode builds, run tests, or capture previews without switching to the IDE (via XcodeBuildMCP MCP)
- Teams evaluating AI-assisted development on the Apple platform who want the tightest IDE integration available

## Limitations

### Technical Limitations
- Xcode 26.3 is macOS-only. No Linux or Windows support. For Linux/WSL2 hosts, use `XcodeBuildMCP` for remote builds.
- The Claude Agent SDK's visual preview integration requires Xcode Previews to be functional for the target file (SwiftUI or UIKit preview providers). UIKit-only projects without preview providers cannot use visual verification.
- The SDK requires network access to Anthropic's API endpoints. Air-gapped development environments cannot use the Xcode integration directly; however, Bedrock and Vertex AI routing is available as an alternative (`CLAUDE_CODE_USE_BEDROCK=1`, `CLAUDE_CODE_USE_VERTEX=1`).

### API Stability
APIs documented here reflect the Feb-2026 baseline; see `docs/xcode-sdk-verification.md` for drift. Billing changes effective June 15, 2026: Agent SDK usage on subscription plans moves to a separate monthly Agent SDK credit. This does not affect the Xcode integration's feature set. Model deprecations (Sonnet 4, Opus 4 retired June 15, 2026) may affect SDK model selection options — verify current model IDs at `code.claude.com/docs/en/agent-sdk`.

### Tool Integration
- No Linux/WSL2 native Xcode support; remote build via `XcodeBuildMCP` is the only path.
- `ios-simulator-mcp` requires a macOS host — it does not support remote simulator tunneling.
- The Xcode integration does not (currently) support watchOS, tvOS, or visionOS preview capture — iOS and macOS are the primary targets.

## When NOT to Use

- Cross-platform mobile development targeting Android in addition to iOS — use `claude/agents/mobile-dev.md` with the appropriate platform stack (Kotlin, React Native, Expo, Flutter)
- Web development — use the native pipelinekit skills for backend and consumer web work
- Android-only development — use Kotlin + Android Studio; this skill is Xcode-specific

## Cross-references

- `claude/agents/mobile-dev.md` — the `@mobile-dev` agent that orchestrates iOS (and multi-platform) mobile work. Invoke explicitly when implementing iOS features.
- `claude/skills/expo/SKILL.md` — the JS-side mobile workflow for Expo and React Native projects, including EAS Build, EAS Update, and Expo Router.
- Optional MCPs (advisory entries in `.mcp.json.template` under `_mobile_mcpServers`):
  - **XcodeBuildMCP** — remote iOS build automation for Linux/WSL2 hosts
  - **ios-simulator-mcp** — programmatic iOS Simulator control (requires macOS + Xcode)

## Installation Requirements

- macOS 14+ (Sonoma or later recommended for Xcode 26.3)
- Xcode 26.3+ (available from the Mac App Store or Apple Developer Portal)
- Apple Developer account (free for simulator development; paid for TestFlight and App Store submission)
- Anthropic account or API key for the Claude Agent SDK integration (configured in Xcode → Settings → Claude)
- For XcodeBuildMCP / ios-simulator-mcp: copy the `_mobile_mcpServers` block from `.mcp.json.template` into your project's `.mcp.json` and uncomment the entries you need
