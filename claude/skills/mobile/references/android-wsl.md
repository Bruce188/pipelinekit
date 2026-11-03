# Android from WSL2

Contents: 1. Toolchain · 2. Device access (Windows adb server, wireless, usbipd) · 3. adb recipes · 4. Tests · 5. Kotlin/Compose notes · 6. Release build

Reference projects: `~/hsnotes` and `~/projects/cashregister` (same template). Read their `gradle/libs.versions.toml` for current versions rather than trusting numbers here.

## 1. Toolchain

| Piece | Where / how to check |
|---|---|
| SDK | `~/Android/Sdk` (`build-tools/`, `platforms/`, `platform-tools/`, `cmdline-tools/latest/`). No `emulator/`, no `system-images/`. |
| SDK path for Gradle | `local.properties` → `sdk.dir=/home/bruce/Android/Sdk`. Git-ignored; create it in a fresh clone or export `ANDROID_HOME`. |
| `ANDROID_HOME` | Unset by default. `export ANDROID_HOME=~/Android/Sdk` and put `$ANDROID_HOME/platform-tools` first on `PATH`. |
| Install SDK parts | `$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager "platforms;android-NN" "build-tools;NN.0.0"` (match `compileSdk`). |
| Gradle | Always `./gradlew` (wrapper pins the version in `gradle/wrapper/gradle-wrapper.properties`). `~/android-tools/gradle-*` is only a bootstrap copy. |
| JDK | Projects compile to Java 17 bytecode (`jvmTarget = "17"`); the system JDK (21) runs Gradle fine. If AGP complains, check the AGP/JDK table at developer.android.com/build/releases/gradle-plugin. |
| AGP, Kotlin, compileSdk | Read `libs.versions.toml` (`agp`, `kotlin`, `ksp`, `composeBom`) and `app/build.gradle.kts` (`compileSdk`, `minSdk`, `targetSdk`). Bump `kotlin` and `ksp` together: the KSP version is prefixed with the Kotlin version. |

Build performance: keep the project on the WSL filesystem (`~/...`), never under `/mnt/c`; cross-filesystem I/O makes Gradle many times slower.

## 2. Device access

Pick one adb server. With mirrored networking, WSL and Windows share loopback port 5037, so two servers fight over it.

### Default: Windows adb server, WSL client

Windows has the winget `Google.PlatformTools` adb (same version as the SDK copy in WSL; check both with `adb version` and upgrade the older one if they differ).

```bash
# WSL: stop any WSL-side server first (do this BEFORE setting ADB_SERVER_SOCKET)
~/Android/Sdk/platform-tools/adb kill-server
```

```powershell
# Windows (PowerShell): start the server; USB phones and Windows emulators appear here
adb.exe start-server
adb.exe devices
```

```bash
# WSL: talk to the Windows server
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
adb devices          # same list as Windows
./gradlew installDebug
```

Put the export in the project shell or `~/.bashrc` only once this works. If WSL cannot connect, check that mirrored mode is active (`wsl --shutdown` after editing `.wslconfig`). As a last resort, start the Windows server with `adb.exe -a nodaemon server`; `-a` listens on all interfaces, so the server is also reachable from the LAN. Avoid it on untrusted networks.

Phone over USB: install the OEM USB driver on Windows if `adb.exe devices` shows nothing, and accept the RSA prompt on the phone.

### Wireless debugging (Android 11+)

Phone: Developer options → Wireless debugging → Pair device with pairing code. Mirrored networking puts WSL on the LAN, so this works from either side:

```bash
adb pair <phone-ip>:<pairing-port> <code>     # port/code from the pairing dialog
adb connect <phone-ip>:<debug-port>           # different port, shown on the Wireless debugging screen
```

The debug port changes when wireless debugging restarts; re-run `adb connect`.

### usbipd-win (USB passed into WSL)

`usbipd-win` is installed on Windows. From an admin PowerShell: `usbipd list`, `usbipd bind --busid <id>` (once), then `usbipd attach --wsl --busid <id>`. The phone then belongs to WSL's own adb server and disappears from Windows. Re-attach after every replug (or add `--auto-attach`).

### Emulator

No emulator runs inside WSL. Install Android Studio on Windows, run the AVD there, and use the Windows adb server above. A physical phone is usually faster to set up.

### Failure modes

| Symptom | Cause |
|---|---|
| `device offline`, server restarts in a loop | adb client and server versions differ (Debian 34.x `/usr/bin/adb` vs SDK copy). Use the SDK adb on both sides. |
| `unauthorized` | Accept the RSA prompt on the phone; `adb reconnect offline`. |
| WSL `adb devices` empty, Windows has the device | `ADB_SERVER_SOCKET` unset, or a WSL server grabbed 5037 first. |
| `adb kill-server` in WSL dropped Windows devices | Expected: with `ADB_SERVER_SOCKET` set, it kills the Windows server. |

## 3. adb recipes

```bash
adb shell am start -n <appId>/.MainActivity
adb shell am force-stop <appId>
adb logcat --pid="$(adb shell pidof -s <appId>)"
adb exec-out screencap -p > shot.png                        # binary-safe, unlike `adb shell screencap`
adb shell run-as <appId> ls files databases                 # debug builds only
adb exec-out run-as <appId> cat databases/app.db > app.db   # pull private data from a debug build
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell pm clear <appId>                                  # reset app data
```

`adb root` works only on emulator images without Play Store (userdebug); it fails on retail phones. Use `run-as` instead.

## 4. Tests

| Kind | Command | Needs device |
|---|---|---|
| JVM unit (incl. Robolectric) | `./gradlew :app:testDebugUnitTest` | no |
| Lint + unit + detekt | `./gradlew :app:check` | no |
| Instrumented, Compose UI (`createAndroidComposeRule`) | `./gradlew :app:connectedDebugAndroidTest` | yes |
| Flows across screens | Maestro (`maestro test flow.yaml`), install separately | yes |

Reports: `app/build/reports/tests/` and `app/build/reports/androidTests/connected/`.

## 5. Kotlin and Compose notes (non-obvious only)

- Kotlin 2.x: Compose needs the `org.jetbrains.kotlin.plugin.compose` Gradle plugin (versioned with Kotlin); there is no separate `kotlinCompilerExtensionVersion` any more.
- Compose library versions come from the BOM (`platform(libs.androidx.compose.bom)`); do not add versions to individual `androidx.compose.*` artifacts. Instrumented tests need the BOM again as `androidTestImplementation(platform(...))`.
- Room with KSP: schema changes need a migration or `fallbackToDestructiveMigration`; unit tests do not catch a missing migration, instrumented `MigrationTestHelper` tests do.
- Bruce's projects ban `android.util.Log.*` in production sources via detekt `ForbiddenMethodCall`; use the project's logger.

## 6. Release build

- Signing config reads the keystore path and passwords from `~/.gradle/gradle.properties` or environment variables, never from the repo. Keep the upload keystore and a backup outside the repo.
- `./gradlew :app:bundleRelease` → `app/build/outputs/bundle/release/app-release.aab` for Play. `assembleRelease` gives an APK for sideloading.
- Increase `versionCode` every upload; Play rejects a reused value.
- Test the release build on a physical phone before uploading (R8/minify can strip reflection-only classes once `isMinifyEnabled` is turned on).
- Checklist: `references/release-security.md`.
