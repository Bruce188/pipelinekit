---
name: mobile
description: >-
  Builds, runs and debugs phone apps from Windows + WSL2 with no Mac: native
  Android (Kotlin, Jetpack Compose, Gradle, adb to a phone or Windows
  emulator), iPhone home-screen web apps (PWA install, service worker,
  LAN HTTPS with a private CA, debugging Safari on the phone), and
  Expo/React Native with EAS cloud builds for iOS. Use when the user
  mentions gradlew, assembleDebug, installDebug, adb, APK/AAB, an Android
  device, emulator or build error, Compose UI tests, getting an app onto a
  phone, a PWA on iPhone or iOS Safari, Expo, EAS, OTA updates, or
  shipping to Google Play or the App Store. Not for desktop web layout,
  backend/server Kotlin, or APIs a mobile app merely calls.
paths:
  - "**/build.gradle"
  - "**/build.gradle.kts"
  - "**/settings.gradle"
  - "**/settings.gradle.kts"
  - "**/gradle/libs.versions.toml"
  - "**/AndroidManifest.xml"
  - "**/app.json"
  - "**/app.config.js"
  - "**/app.config.ts"
  - "**/eas.json"
  - "**/manifest.webmanifest"
  - "**/*.webmanifest"
  - "**/sw.js"
  - "**/service-worker.js"
---

# Mobile from WSL2

## Environment facts

- Host: Windows 11 + WSL2 with `networkingMode=mirrored`, so `127.0.0.1` in WSL reaches listeners bound to Windows loopback. No Mac, so no Xcode, no iOS Simulator, no Safari Web Inspector.
- Android SDK: `~/Android/Sdk` (build-tools, platforms, platform-tools, cmdline-tools; no emulator or system images). Projects point at it through the git-ignored `local.properties` (`sdk.dir=...`). `ANDROID_HOME` is not set; export it before running `sdkmanager` or anything outside Gradle.
- `adb` on PATH is Debian's 34.x at `/usr/bin/adb`. Use `$ANDROID_HOME/platform-tools/adb` instead; it matches the Windows winget copy, and a client/server version mismatch is the usual cause of "device offline" and restart loops.
- Device access goes through Windows: a physical phone or an emulator running on Windows. Nothing runs an emulator inside WSL.

## Pick the reference

| Task | Read |
|---|---|
| Gradle build, adb, getting a device visible from WSL, Compose tests, signing an AAB | `references/android-wsl.md` |
| iPhone web app: install, service worker updates, LAN HTTPS + CA, debugging Safari on the phone | `references/iphone-web-app.md` |
| Expo/React Native, EAS Build/Update/Submit, an iOS binary without a Mac | `references/expo-eas.md` |
| Pre-release or security review of any of the above | `references/release-security.md` |

Read only the row that matches; they are independent.

## Daily Android loop

```bash
export ANDROID_HOME=~/Android/Sdk; export PATH="$ANDROID_HOME/platform-tools:$PATH"
./gradlew assembleDebug                 # compile
./gradlew installDebug                  # needs `adb devices` to show a device
adb shell am start -n <applicationId>/<activity>   # e.g. com.notes.hsnotes/.MainActivity
adb logcat --pid="$(adb shell pidof -s <applicationId>)"
```

Before calling Android work done, run `./gradlew :app:check` (lint, unit tests and, in Bruce's projects, the type-resolved `detektDebug`). Plain `:app:detekt` is the name-only pass and misses the `android.util.Log` ban. Instrumented tests (`:app:connectedDebugAndroidTest`) need a device attached.

## Getting a device visible from WSL

Default: run the adb server on Windows and point WSL's client at it (`ADB_SERVER_SOCKET=tcp:127.0.0.1:5037`). Escape hatches: wireless debugging (`adb pair` / `adb connect`) or `usbipd attach --wsl`. Steps and failure modes are in `references/android-wsl.md`.

## iOS without a Mac

Two realistic routes: a home-screen web app in Safari (`references/iphone-web-app.md`), or an Expo app built in EAS's cloud and sent with `eas submit` (`references/expo-eas.md`). Say plainly when a request needs Xcode or a simulator; those are unavailable here.

## Gotchas

- `adb kill-server` run in WSL with `ADB_SERVER_SOCKET` set kills the Windows server, because it talks to the same socket.
- Never commit `local.properties`, keystores, `google-services.json` with secrets, or `.env` files.
- `versionCode` must increase on every Play upload; Play rejects a reused or lower value.
- iPhone origins: WebAuthn/Face ID refuses IP-literal origins; use a hostname (Bruce uses `wms.local` over mDNS).
