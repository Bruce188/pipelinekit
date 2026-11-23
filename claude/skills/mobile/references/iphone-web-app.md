# iPhone home-screen web app (PWA)

Contents: 1. Bruce's setup · 2. iOS Safari limits · 3. Service worker updates · 4. LAN HTTPS with a private CA · 5. Debugging Safari on the phone without a Mac

## 1. Bruce's setup (`~/Iphonewms`)

- Static app: `index.html`, `style.css`, `manifest.webmanifest`, `sw.js` at the repo root; esbuild bundle at `dist/bundle.js?v=<hash>` (`npm run build`). No app server.
- `scripts/serve.py`: HTTP on 8138 (for the CA download) and HTTPS on 8443, `no-cache` headers, plus a `POST /log` sink that writes client logs to `server.log`.
- `scripts/make-cert.sh [ip] [host]`: makes the cert in `~/.config/iphonewms/certs/` and copies the public part to `wms-ca.crt`. Re-run when the LAN IP changes, then restart the server and reinstall on the phone.
- Tests: `npm test` (`node --test`), Playwright scripts under `scripts/`.

Read `documentation/architecture.md` there before changing boot, caching or the server.

## 2. iOS Safari limits that matter

| Area | Behaviour |
|---|---|
| Install | No install prompt and no `beforeinstallprompt`. The user taps Share → Add to Home Screen. The icon comes from `<link rel="apple-touch-icon">` (180×180). `display: standalone` in the manifest (or `apple-mobile-web-app-capable`) removes the Safari chrome. |
| Separate storage | The installed app has its own storage, cookies and service worker, separate from the same site open in Safari. Logging in or clearing data in one does not affect the other. |
| Service worker | Needs a secure context (HTTPS or `localhost`), so a LAN IP over plain HTTP gets no worker. Scope defaults to the worker's directory; keep `sw.js` at the app root so scope `./` covers everything. |
| Storage eviction | Safari deletes script-writable storage (IndexedDB, localStorage, Cache Storage, SW registrations) for a site after 7 days of Safari use without the user interacting with it. Home-screen apps keep their own day counter, so a used installed app keeps its data. Storage can also be evicted under disk pressure; call `navigator.storage.persist()` and keep the server or another copy as the source of truth. |
| Web Push | iOS/iPadOS 16.4 and later, and only for apps added to the Home Screen; never in a Safari tab. `Notification.requestPermission()` must be called from a user gesture. It needs a push server, which a static app does not have. |
| Viewport | `viewport-fit=cover` lets content draw under the notch and home indicator; pad with `env(safe-area-inset-top|bottom|left|right)`. `apple-mobile-web-app-status-bar-style: black-translucent` puts content under the status bar, so the top inset becomes mandatory. |
| WebAuthn / Face ID | Rejected on IP-literal origins (`https://192.168.x.x`). Needs a hostname, e.g. the `wms.local` mDNS name in `make-cert.sh`. |

## 3. Service worker updates ("the phone shows the old version")

- iOS checks for a new `sw.js` on navigation, but an installed app often resumes from the background without navigating. Call `registration.update()` on `visibilitychange` when the page becomes visible.
- Serve `sw.js` and `index.html` with `Cache-Control: no-cache` (`serve.py` already does).
- Bruce's worker is network-first for the shell and cache-first only for the content-hashed `dist/bundle.js?v=<hash>`. A new build changes the hash in `index.html`, and the stale bundle is pruned. Keep that split: making the shell cache-first pins stale builds.
- Bump the `CACHE` constant in `sw.js` when you change caching strategy, so `activate` deletes old caches.
- Manual reset on the phone: delete the home-screen icon (this drops the installed app's storage), then Settings → Apps → Safari → Advanced → Website Data → remove the host, then add it to the Home Screen again.

## 4. LAN HTTPS with a private CA

Apple's rules for TLS server certs: the name must be in `subjectAltName` (CN is ignored), `extendedKeyUsage` must include `serverAuth`, and validity must be 825 days or less. `make-cert.sh` meets all three (820 days, self-signed with `CA:TRUE`).

Installing on the iPhone:

1. In Safari (not Chrome, which can't install profiles), open `http://<pc-ip>:8138/wms-ca.crt` and allow the download. "Profile Downloaded" appears.
2. Settings → General → VPN & Device Management → the downloaded profile → Install.
3. Settings → General → About → Certificate Trust Settings → turn on full trust for the cert. Without this step the profile is installed but Safari still rejects the site.
4. Open `https://<host-or-ip>:8443`.

After regenerating the cert, remove the old profile (step 2 screen) and repeat. The server's port must be reachable from the phone: with mirrored WSL networking the listener is on the Windows host's IP, but Windows Firewall may still need an inbound rule for 8138/8443.

## 5. Debugging Safari on the phone without a Mac

Safari Web Inspector needs a Mac. Options, cheapest first:

1. **Remote log sink (in use).** The page posts boot progress and `window.onerror` / `unhandledrejection` to `POST /log`; read `server.log`. Good for crashes during startup.
2. **Eruda (in-page console).** Load it only behind a flag, e.g. `?debug=1`, from a vendored copy (`npm i -D eruda`, copy `node_modules/eruda/eruda.js`) so it works offline and never ships by default: `<script src="eruda.js"></script><script>eruda.init()</script>`. It gives console, network, elements and storage panels on the phone.
3. **Playwright WebKit on Linux.** Reproduces WebKit layout and JS bugs with an iPhone device profile (`devices['iPhone 15']`). It is desktop WebKit, not iOS Safari: no home-screen mode, no iOS storage policy.
4. **ios-webkit-debug-proxy on Windows.** Real remote inspection over USB. Install with scoop (`scoop bucket add extras`, `scoop install ios-webkit-debug-proxy`), needs iTunes/Apple device drivers, and Settings → Apps → Safari → Advanced → Web Inspector on the phone. It lists devices on `localhost:9221` and pages from `:9222`. Its README warns that current Chrome DevTools are incompatible with WebKit's protocol, so expect friction; inspect.dev is a paid Windows/Linux app built on the same idea.

Default to 1 and 2. Reach for 4 only for a bug that needs breakpoints on the device.
