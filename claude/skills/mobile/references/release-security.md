# Release and security checklist

Go through the section for the target before a Play upload, an EAS production build, or sharing a PWA beyond the LAN. Report each item as pass, fail or not applicable.

## Secrets

- [ ] No API keys, tokens or passwords in source, `BuildConfig` fields, `gradle.properties` in the repo, `app.json` / `app.config.*` `extra`, `EXPO_PUBLIC_*` variables, or the PWA bundle. All of these ship inside the app and can be extracted. Anything the client must not know stays on a server.
- [ ] Keystores, `local.properties`, `.env*`, service-account JSON and App Store Connect keys are git-ignored and stored outside the repo (Gradle signing values from `~/.gradle/gradle.properties` or env vars; Expo values in EAS environments with `secret` visibility).
- [ ] Runtime secrets (auth tokens, encryption keys) live in Android Keystore / iOS Keychain (Expo: `expo-secure-store`), not SharedPreferences, DataStore, AsyncStorage, localStorage or plain files.

## Android

- [ ] `network_security_config.xml` forbids cleartext in release. Any debug-only trust anchors or cleartext domains sit under `<debug-overrides>` or in the `debug` source set, never in `main`.
- [ ] `android:allowBackup="false"`, or backup rules that exclude databases and key material.
- [ ] Every `exported="true"` activity, service and receiver is intended; intent extras and deep-link parameters are validated.
- [ ] Permissions: only what a shipped feature uses, requested at first use with a rationale.
- [ ] No PII, tokens or device identifiers in logs. Debug logging is stripped in release (`BuildConfig.DEBUG`; Bruce's projects enforce this with the detekt `Log.*` ban).
- [ ] If R8/minify is on: keep rules for reflection/serialization, and the release build was exercised on a physical phone.
- [ ] `versionCode` increased; `versionName` updated.
- [ ] High-value flows that need device attestation use the Play Integrity API, checked server-side. Client-only root detection is bypassable.

## iOS (Expo / EAS)

- [ ] No `NSAllowsArbitraryLoads`. Any `NSExceptionDomains` entry has a written reason.
- [ ] Every `NS*UsageDescription` string names the real use; unused permissions removed (App Review rejects vague or unneeded ones).
- [ ] Build number increases on each upload.
- [ ] Privacy manifest / required-reason APIs declared where libraries need them (`expo-doctor` and EAS warnings flag most).

## PWA

- [ ] Served only over HTTPS; the private CA and its key never leave the dev machine (only the public `.crt` is distributed).
- [ ] The `/log` sink (or any debug endpoint) is LAN-only and does not record credentials or session strings.
- [ ] Eruda or other debug tooling loads only behind an explicit flag.
- [ ] Session material in IndexedDB/localStorage is treated as readable by anyone holding the unlocked phone; sensitive operations re-authenticate (WebAuthn where available).

## Deep links and auth

- [ ] Deep-link and universal-link parameters are validated; OAuth `redirect_uri` and `state` come from the server, not from the link.
- [ ] Certificate pinning only with a rotation plan: a pinned cert change needs a new binary (Expo: a new build, not an OTA update). Pin the public key with a backup pin.

## Before every store release

- [ ] Tested on a physical device: emulators and simulators miss thermal throttling, memory pressure, real push delivery and flaky networks.
- [ ] Dependency audit run (`./gradlew dependencies` review, `npm audit`); high-severity CVEs in direct dependencies block the release.
