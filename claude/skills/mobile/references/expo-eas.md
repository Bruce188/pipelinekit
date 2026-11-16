# Expo and EAS (reference)

Bruce has no Expo project yet. Use this when one starts, or when the goal is an iOS binary without a Mac.

Versions move fast. Before relying on any number, check `docs.expo.dev/versions/latest` (current SDK, React Native and minimum Node) and `npx eas-cli@latest --help` (commands and flags). Do not install the old global `expo-cli` package; it is deprecated in favour of `npx expo` plus `eas-cli`.

Contents: 1. Project setup · 2. Builds · 3. iOS from Windows · 4. Environment variables · 5. Updates (OTA) · 6. Submit · 7. Push notifications · 8. Old patterns

## 1. Project setup

```bash
npx create-expo-app@latest myapp
npx expo install <package>      # picks the version that matches the SDK
npx expo-doctor                 # dependency and config check; run before every build
npm i -g eas-cli && eas login && eas build:configure   # creates eas.json
```

- **New Architecture only.** Since SDK 55 the Legacy Architecture is gone and `newArchEnabled` is no longer a config option. Every native library must support the New Architecture; check reactnative.directory before adding one.
- **Continuous Native Generation (CNG).** `ios/` and `android/` are generated from `app.json` / `app.config.ts` and config plugins by `npx expo prebuild`. Keep them out of git and change native config through plugins; `npx expo prebuild --clean` regenerates them. "Eject" is not a one-way step any more.
- **Expo Go vs development build.** Expo Go only supports the SDK it ships with and no custom native code. Use a development build (`expo-dev-client`, profile `development`) as soon as you need a native module or push.

## 2. Builds

`eas.json` profiles: `development` (dev client, internal), `preview` (internal distribution), `production` (store).

```bash
eas build -p android --profile preview         # APK/AAB in the cloud
eas build -p ios --profile production          # cloud macOS worker; works from WSL
eas build -p all --profile production --auto-submit
eas build -p android --profile preview --local # runs on this machine: needs Android SDK + JDK, works in WSL
```

- `--local` for iOS needs macOS and Xcode, so it is not an option here.
- `android.buildType` in `eas.json` is `apk` or `app-bundle` (Play needs `app-bundle`).
- `resourceClass` is `medium` or `large`.
- `eas build:dev` reuses or creates a dev-client build for a simulator or emulator. On this setup the only target is an emulator on Windows (see `android-wsl.md`).
- `eas build:inspect -p <platform> -s <archive|pre-build|post-build> -o <dir>` shows what EAS would upload or produce; use it to debug "works locally, fails on EAS".
- CI: EAS Workflows (`.eas/workflows/*.yml`, `eas workflow:run`, `eas workflow:validate`) instead of hand-rolled GitHub Actions.

## 3. iOS from Windows

- Requires a paid Apple Developer account. Let EAS manage certificates and provisioning (`eas credentials`).
- To put a build on a specific iPhone without TestFlight: `eas device:create` (registers the UDID via a link opened on the phone), then build with an internal-distribution profile and open the install link on the phone.
- Otherwise ship through TestFlight: `eas submit -p ios`.
- Nothing here gives you a simulator or Xcode. Test on the phone with a dev build or TestFlight.

## 4. Environment variables

The old `eas secret:*` commands are gone. Variables live in EAS environments (`development`, `preview`, `production`):

```bash
eas env:set --name API_URL --value https://api.example.com --environment production --visibility plaintext
eas env:set --name SENTRY_AUTH_TOKEN --value ... --environment production --visibility secret
eas env:list --environment production
eas env:pull --environment development        # writes .env.local for local dev
eas env:exec production "npx expo export"   # one quoted bash command, run with that environment's variables
```

Visibility: `plaintext`, `sensitive` (masked in logs) or `secret` (never readable after creation, build-time only). Anything prefixed `EXPO_PUBLIC_` is inlined into the JS bundle and readable by anyone with the app, whatever its visibility.

## 5. Updates (OTA)

- An update reaches builds whose `runtimeVersion` matches. Use `"runtimeVersion": { "policy": "fingerprint" }` so a native change produces a new runtime instead of a broken OTA.
- Channels belong to builds (set per profile in `eas.json`); branches hold updates; `eas channel:edit <channel> --branch <branch>` repoints a channel.

```bash
eas update --channel production --environment production --message "fix totals"
eas update --channel production --environment production --rollout-percentage 10 --message "..."
eas update:republish --group <groupId> --destination-channel production   # promote a tested group
eas update:rollback                     # republish the previous group (or the embedded one)
eas update:roll-back-to-embedded
```

`--environment` is required for SDK 55 and later. OTA can only change JS and assets; store policies forbid using it to change the app's purpose.

## 6. Submit

- `eas submit -p ios` uploads to App Store Connect / TestFlight (an App Store Connect API key, which EAS can create).
- `eas submit -p android` needs a Google Play service-account JSON key, and the very first AAB for a new app must be uploaded by hand in Play Console.
- `eas build --auto-submit` chains the two.

## 7. Push notifications

- Remote push does not work in Expo Go on Android (since SDK 53). Use a development build.
- iOS needs the paid developer account (APNs key via `eas credentials`); Android needs FCM v1 credentials (`google-services.json` in the project, the service-account key uploaded to EAS).
- Get the token with `getExpoPushTokenAsync({ projectId })` (the EAS project ID from `app.json` `extra.eas.projectId`).
- In `setNotificationHandler`, use `shouldShowBanner` / `shouldShowList`; `shouldShowAlert` is the old field.
- Test on a physical device; simulators and emulators do not receive real remote push reliably.

## 8. Old patterns (do not use)

`expo-cli` global install · `eas secret:create` · "managed vs bare" / irreversible eject · `newArchEnabled` toggles · `eas update --republish` flag (use `eas update:republish`).
