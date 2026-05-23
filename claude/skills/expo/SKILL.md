---
name: expo
description: Expo developer workflow — managed vs. bare workflow, EAS Build, EAS Update (OTA), dev-client, Expo Router, expo-modules-core, push notifications via Expo's APNs/FCM gateway
paths:
  - claude/skills/expo/**
  - "**/app.json"
  - "**/eas.json"
  - apps/**
---

# Expo Developer Workflow

This skill covers the end-to-end Expo developer workflow: choosing between managed and bare workflows, building and distributing apps via EAS Build and EAS Update, writing file-system-routed navigation with Expo Router, managing environment variables and secrets, and wiring push notifications through Expo's APNs/FCM gateway. It focuses on the *workflow and tooling* layer — for canonical Expo SDK API reference, use `context7` MCP (resolve `expo`) or visit `docs.expo.dev`.

## Keywords

Expo, EAS, EAS Build, EAS Update, OTA updates, over-the-air updates, dev-client, Expo Router, expo-modules-core, React Native, managed workflow, bare workflow, Metro bundler, EAS secrets, expo-notifications, APNs, FCM, push notifications, Expo CLI, eas.json, app.json, app.config.js, Expo Go, development build, production build, preview build, runtime version, channel, branch, app signing

## Capabilities

### Managed vs. Bare Workflow

**Managed workflow** — Expo maintains the native layer (iOS and Android project files are hidden). Ideal when:
- Starting a new project and all required native functionality is available in the Expo SDK
- Team lacks iOS/Android native expertise
- Maximum OTA update simplicity is required (only JS changes between builds)

**Bare workflow** — Full native iOS and Android project files are present (`ios/` and `android/` directories). Choose bare when:
- A native library is required that is not available in the managed SDK
- Fine-grained control over build settings, entitlements, or native modules is needed
- Migrating from a plain React Native CLI project

**Ejecting from managed**: Run `npx expo prebuild`. This generates native project files from your `app.json` / `app.config.js` config. After ejecting, manage native dependencies manually and re-run `npx expo prebuild` to sync config changes back to native files. Ejecting is **not reversible** without a fresh project — confirm before proceeding.

**Cost of ejecting**: You gain full native control but lose the simplicity of Expo Go for development and must manage Podfile, Gradle, and native module linking manually. EAS Build still works after ejecting.

### EAS Build

EAS Build provides cloud and local builds for both iOS and Android without requiring a local Xcode or Android Studio installation.

**Build profiles** (defined in `eas.json`):
- `development` — Includes dev-client, JS debugging enabled, internal distribution (TestFlight internal / ad hoc)
- `preview` — Release build without dev-client, internal distribution for QA
- `production` — App Store / Google Play submission build, full signing

**Triggering builds**:
```
# Cloud build
eas build --platform ios --profile production
eas build --platform android --profile preview
eas build --platform all --profile development

# Local build (requires Xcode on macOS or Android Studio on any platform)
eas build --platform ios --profile development --local
```

**App signing**:
- **iOS**: Link your Apple Developer account with `eas credentials`. EAS manages Distribution certificates and provisioning profiles. Credentials are stored in Expo's encrypted credential store.
- **Android**: EAS generates and manages the upload key. Store the keystore backup in a secure vault — losing it makes Play Store updates impossible without account escalation.

**Build caching**: EAS Build caches npm dependencies and CocoaPods by default. Enable Gradle caching in `eas.json` under `android.buildType`. Cache busting is automatic when `package.json` or Podfile changes.

**Platform-specific overrides** in `eas.json`:
```json
{
  "build": {
    "production": {
      "ios": { "resourceClass": "m1-medium" },
      "android": { "buildType": "app-bundle" }
    }
  }
}
```

### EAS Update (OTA)

EAS Update lets you push JavaScript-only bundle changes to users without a new binary release.

**Key concepts**:
- **Runtime version**: A string in `app.json` / `app.config.js` that must match between the binary and the JS bundle. Mismatches cause the update to be rejected. Bump the runtime version with any native module change.
- **Branch**: A named stream of updates (e.g., `main`, `staging`). Point a channel to a branch.
- **Channel**: Corresponds to a build profile. The `production` channel on installed apps pulls from whatever branch the production channel is mapped to.

**Publishing an update**:
```
# Publish to a branch
eas update --branch main --message "Fix login screen crash"

# Preview in Expo Go / dev-client before promoting
eas update --branch staging

# Map production channel to staging branch (gradual rollout pattern)
eas channel:edit production --branch staging
```

**Rollback**:
```
# List recent updates on a branch
eas update:list --branch main

# Roll back by re-publishing a previous build's bundle
eas update --republish --branch main --update-id <previous-id>
```

**Runtime version compatibility**: Do NOT push OTA updates that depend on a new native module that is not present in the installed binary. Always bump `runtimeVersion` in `app.json` when adding or upgrading native modules; this forces users to download a new binary from the store before receiving the JS update.

### Dev-Client

A dev-client is a custom development build that includes your project's native modules, replacing the generic Expo Go sandbox.

**When a dev-client is required**:
- Any native module outside the managed Expo SDK defaults (e.g., `react-native-camera`, custom `expo-modules-core` modules)
- Custom splash screen or notification sounds that require native configuration
- Testing push notification flows end-to-end (Expo Go does not support background notification handlers)

**Building a dev-client**:
```
# Build the dev-client for device
eas build --profile development --platform ios

# Or build locally (macOS required for iOS)
npx expo run:ios --device

# Install on device from EAS build link, then start dev server
npx expo start --dev-client
```

**Install-on-device flow**: After an EAS cloud build completes, EAS sends an install link via email or QR code. Scan from the device to install, then connect to the Metro bundler by opening the Expo Go-like dev-client app and entering the dev server URL.

### Expo Router

Expo Router brings file-system routing to React Native, mirroring the Next.js App Router model.

**File structure** (`app/` directory):
```
app/
  _layout.tsx        # Root layout (navigation container, global providers)
  index.tsx          # / (home route)
  (tabs)/
    _layout.tsx      # Tab bar layout
    feed.tsx         # /feed
    profile.tsx      # /profile
  users/
    [id].tsx         # /users/:id  (dynamic segment)
    [...rest].tsx    # /users/*    (catch-all)
```

**Key patterns**:
- `Link` component for navigation — renders natively on iOS/Android, `<a>` on web
- `useLocalSearchParams()` to access dynamic route params
- `useRouter()` for programmatic navigation (`router.push`, `router.replace`, `router.back`)
- `Stack.Screen` options for per-screen title, header, modal presentation
- `Tabs.Screen` for tab bar customization

**Deep linking**: Expo Router generates a `sitemap.json` and handles universal links / app schemes automatically. Configure in `app.json` under `scheme` (custom URL scheme) and `web.bundler`.

**Type-safe navigation**: Use `expo-router/typed-routes` (experimental) for compile-time checked route paths.

### Environment Variables

**At runtime** (`expo-constants`):
```javascript
import Constants from 'expo-constants';
const apiUrl = Constants.expoConfig?.extra?.apiUrl;
```
Define `extra` in `app.config.js`:
```javascript
export default ({ config }) => ({
  ...config,
  extra: { apiUrl: process.env.API_URL }
});
```

**At build time** (EAS Build environment):
- `EAS_BUILD_PLATFORM` — `ios` or `android`
- `EAS_BUILD_PROFILE` — build profile name (`development`, `preview`, `production`)
- Custom env vars are set in `eas.json` under `build.<profile>.env` (for non-secret values) or via `eas secret` (for secrets)

**Secret management**:
```
# Add a secret to the project (stored encrypted in Expo cloud)
eas secret:create --scope project --name STRIPE_SECRET_KEY --value sk_live_...

# List secrets
eas secret:list

# Secrets are injected as environment variables during EAS Build — never committed to source
```

**What gets bundled vs. injected**:
- `app.config.js` `extra` values → bundled into the JS binary (visible to reverse engineering — do not put secrets here)
- EAS secrets → injected at build time as env vars, never in the bundle

### Push Notifications

Expo provides a push notification gateway that abstracts APNs (iOS) and FCM (Android).

**Setup**:
1. Install: `npx expo install expo-notifications`
2. Configure in `app.json`:
   ```json
   { "expo": { "notification": { "icon": "./assets/notification-icon.png" } } }
   ```
3. For iOS: add `remote-notification` to `UIBackgroundModes` and configure `entitlements.aps-environment` (via `app.json` `ios.entitlements`)

**Registering for a push token**:
```javascript
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

async function registerForPushNotifications() {
  if (!Device.isDevice) return; // simulators cannot receive push notifications
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') return;
  const token = (await Notifications.getExpoPushTokenAsync()).data;
  // Send token to your backend
  return token;
}
```

**Foreground and background handlers**:
```javascript
// Foreground: show notification while app is active
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

// Background: respond to notification tap
Notifications.addNotificationResponseReceivedListener(response => {
  const data = response.notification.request.content.data;
  // navigate to relevant screen
});
```

**Server-side push** via Expo's REST API:
```bash
curl -H "Content-Type: application/json" -X POST https://exp.host/--/api/v2/push/send \
  -d '{ "to": "ExponentPushToken[...]", "title": "Hello", "body": "World" }'
```
Expo's gateway handles APNs and FCM token management. For production volume, use the official `expo-server-sdk-node` or `expo-server-sdk-python` packages.

## How to Use

Natural-language invocations for this skill:

- "Set up EAS Build for an Expo app targeting iOS and Android with three build profiles"
- "Publish an OTA update to the production channel without a new App Store submission"
- "Migrate from managed workflow to bare workflow and add a custom camera native module"
- "Add a custom native module via expo-modules-core in Swift and Kotlin"
- "Configure Expo Router with a tab bar and a modal screen"
- "Set up push notifications with APNs and FCM using expo-notifications"
- "Wire up EAS secrets for a Stripe API key used at build time"
- "Build a dev-client so I can test a third-party BLE library in Expo"
- "Set up a production EAS Build pipeline on GitHub Actions"

## When to Use

- Building a cross-platform mobile app where one codebase targets iOS, Android, and optionally web
- Rapid prototyping — Expo Go or a dev-client enables instant reload without full binary rebuilds
- OTA update requirement — ship JS fixes to users without a store review cycle
- Team lacks native iOS/Android expertise and wants managed SDK abstraction
- Apple Developer Program access is not yet set up — EAS Build handles signing in the cloud
- Migrating from a Create React Native App or vanilla React Native project

## Limitations

### Technical Limitations
- Managed workflow excludes some native APIs (e.g., custom app extensions, PushKit/CallKit without ejecting, Background App Refresh with native code). Check `docs.expo.dev/versions/latest/sdk/` for the current managed SDK surface.
- Bare workflow requires Xcode (macOS) for local iOS builds and Android Studio for local Android builds. Cloud builds (EAS Build) work from any platform.
- OTA updates via EAS Update are JS-bundle-only. Any native code change requires a binary release.
- expo-modules-core native module authoring requires Swift/Kotlin knowledge and a bare workflow.

### Platform Limitations
- iOS local builds require macOS + Xcode. EAS Cloud builds work from Linux/WSL2 for iOS targets.
- Expo Go does not support all native modules — use a dev-client for modules outside the managed SDK.
- Custom push notification actions (notification categories) require native configuration and a bare workflow.

### Cost Limitations
- EAS Build has a free tier with limited monthly build minutes. Large teams or frequent builds may require a paid EAS plan.
- EAS Update free tier limits concurrent channels and update bandwidth. Check current limits at `expo.dev/pricing`.

## When NOT to Use

- Pure native iOS or Android single-platform app where SwiftUI/UIKit or Jetpack Compose performance and platform fidelity are paramount — use `claude/agents/mobile-dev.md` with the native stack directly
- Complex bare-metal performance requirements (audio DSP, real-time video processing, custom GPU shaders) — React Native's JS bridge introduces latency that native code eliminates
- Offline-first apps with heavy local SQLite or realm-based sync that benefit from direct ORM control — React Native with Turbo Modules may be more appropriate than the Expo managed SDK

## Best Practices

- Commit `eas.json`, `app.json` / `app.config.js`, and `.easignore` — but never commit `.env` secrets; use `eas secret` for build-time credentials
- Pin Expo SDK version in `package.json` (`"expo": "~52.0.0"`) and upgrade intentionally with `npx expo install --fix` to align dependent packages
- Always bump `runtimeVersion` in `app.json` when adding or upgrading a native module — mismatched runtime versions silently reject OTA updates
- Use build profiles deliberately: `development` for device testing, `preview` for QA distribution, `production` for store submission. Never submit a `development` build to the App Store.
- Run `eas build:inspect` before the first cloud build to catch signing or config issues without consuming build minutes
- Set `channel` mappings explicitly in `eas.json` — do not rely on EAS channel defaults changing between SDK versions
- Test push notification flows on a physical device in a `development` build, not in Expo Go or the simulator
- Use `expo-crypto` or a platform-native module for any cryptographic operation — do not implement custom crypto in JS

## Installation Requirements

Expo CLI requires Node 18+ (LTS recommended). pipelinekit's installer (`scripts/install.sh`) does NOT install Node — install via your system's package manager or nvm. The `claude/CLAUDE.md.template` already notes Node 20+ recommended.

```bash
# Install Expo CLI globally (optional; npx works without a global install)
npm install -g expo-cli

# Or use npx (no global install needed)
npx create-expo-app my-app
npx expo start
npx eas-cli build --platform ios
```

For EAS CLI specifically:
```bash
npm install -g eas-cli
eas login
```

For canonical Expo SDK API reference and in-session lookups, use `context7` MCP (`resolve-library-id` → `expo`) or visit `https://docs.expo.dev`.
