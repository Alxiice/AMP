# Phase 5 — Auth simplification & local API hardening

**Goal**: one sign-in path that works on Windows, plus a manual fallback. Only YouTube cookies are stored, including in files written before this fix. Other web pages can't trigger state-changing calls on the local API. The app keeps working "out of the box" with no setup.

**Effort**: 1 day · **Depends on**: Phase 0 (hotfix 0.8). Can run alongside Phases 2–4. · **Branch**: `fix/phase-5-auth-security`

---

## 1. Problems addressed

| # | Problem | Where |
|---|---|---|
| F12 | Cookie files written before Phase 0 can hold **every site's cookies**, flattened by name (collisions such as another site's `SID`). They're sent as a `Cookie` header to YouTube and googlevideo. | `.amp/cache/ytm_session.json`, `auth.py:load_from_store` |
| — | Four sign-in flows on one page: Tauri webview, browser polling, browser import, manual paste. Browser polling reads **Chrome** cookies by default while opening the **default** browser. Chrome/Edge cookie decryption by yt-dlp is generally broken on Windows (app-bound encryption), so polling and import mostly fail there. | `Auth.tsx`, `signin_flow.py:165` |
| — | `SignInFlow.start()` reads browser cookies synchronously inside the request, so the request is slow and can 500. Finished flows are never cleaned up. | `signin_flow.py:87`, `SignInFlowManager` |
| F15 | Open mode plus a Host check doesn't stop **cross-site requests**: any web page open in the user's browser can POST to `127.0.0.1:8000`. CORS only blocks reading the response. Requests with no body or only query parameters run: `/auth/logout`, `/auth/import-browser`, `/auth/open-signin`, `/stream/seek`, `/stream/stop`, `DELETE /logs`. | `server.py:43-65` |
| — | The Host check splits on `:`, so `[::1]:8000` becomes `[` and IPv6 loopback is rejected | `server.py:53` |
| — | Session expiry isn't visible outside the Auth page | `App.tsx` |

---

## 2. Tasks

### 5.1 Cookie storage v2 with domains

File: `amp/backend/services/auth.py`

- New on-disk format (atomic write and `0600` unchanged):
  ```json
  { "version": 2, "cookies": [ {"name": "SID", "value": "…", "domain": ".youtube.com"} ] }
  ```
- `AuthService` keeps `list[Cookie]` internally. `get_cookie_header()` and `write_netscape_cookie_file()` use the real domain instead of writing every cookie for both `.youtube.com` and `.music.youtube.com`.
- All entry points (`set_cookies_from_header`, Tauri cookies, browser import) go through `filter_youtube_cookies` (Phase 0). For a pasted `Cookie:` header with no domain, assume `.youtube.com`.

### 5.2 Migrate existing v1 files

- On `load_from_store`, if the file has no `"version"` key (v1, flat name→value):
  - Keep only names in an allowlist of YouTube/Google session cookies: `SID HSID SSID APISID SAPISID __Secure-1PSID __Secure-3PSID __Secure-1PAPISID __Secure-3PAPISID __Secure-1PSIDTS __Secure-3PSIDTS __Secure-1PSIDCC __Secure-3PSIDCC SIDCC LOGIN_INFO PREF VISITOR_INFO1_LIVE VISITOR_PRIVACY_METADATA YSC`. Domain `.youtube.com`.
  - Rewrite the file as v2 immediately. Log `Migrated credential store v1→v2: kept N of M cookies` (counts only, P24).
  - If M was much larger than N (say M > 3·N), also log a WARNING suggesting the user sign in again, and surface `migrated_from_full_jar: true` in `/api/auth/status` for one session.

### 5.3 One primary sign-in path

- **Primary**: Tauri webview login (`youtube_login.rs` → `POST /api/auth/tauri-cookies`). Keep it as is, plus:
  - read cookies for both `https://music.youtube.com/` and `https://www.youtube.com/`, merged by (name, domain)
  - keep the incognito window and the 10-minute timeout
- **Fallback**: manual "paste Cookie header", in a collapsed "Advanced" section.
- **Remove** the browser-polling flow: `services/signin_flow.py`, `test_signin_flow.py`, the `/start-signin-flow`, `/signin-status/{id}` and `/cancel-signin-flow/{id}` routes, the related `api.ts` methods and types, and the Auth.tsx section.
- **Browser import**: keep it under "Advanced" for **Firefox only**, with the "close Firefox first" hint, or remove it. Recommendation: keep Firefox-only. It's the one browser where it still works reliably on Windows.
- **Remove** `/api/auth/open-signin`. The webview flow replaces it.

### 5.4 Session state everywhere

- Sidebar badge next to the backend status: `Signed in` / `Signed out` / `Session expired — reconnect`. Clicking it navigates to `/auth`.
- Poll `/api/auth/status` every 60 s (with an in-flight guard, P12), and after any 401 from `/api/user/*`.
- When `/api/user/likes` or `/playlists` return 401, Library and Playlists show "Sign in to see your library" with a button, instead of a raw error.

### 5.5 Block cross-site state changes (F15)

File: `amp/backend/api/server.py`

- In the middleware, for methods other than `GET`, `HEAD` and `OPTIONS`:
  - If an `Origin` header is present and **not** in `ALLOWED_ORIGINS`, return 403 `{"detail": {"code": "forbidden_origin"}}`.
  - If `Origin` is absent, allow the request. Non-browser clients such as `app.py`'s API tab and curl don't send it, while browsers always send `Origin` on cross-origin POST, PUT and DELETE.
- Also reject `GET` requests whose `Sec-Fetch-Site` is `cross-site` on `/api/auth/*`, so another site can't trigger `status?verify=true`. Keep `/stream/*/audio` open for the app's `<audio>` element. That element is same-site from the webview, but check it in WebView2 before tightening further.
- Fix the Host parsing: handle `[::1]:8000` (split on the last `:` only if the host isn't bracketed).
- Keep CORS as is. Never use `*` with credentials.

### 5.6 (Optional) automatic per-launch token

This is compatible with "no setup", because the user never sees the token.

- Phase 6 has the Rust side generate a random token and pass `--token` to the backend. The frontend reads it through a Tauri command and `api.ts` attaches `Authorization: Bearer`.
- `<audio>` can't send headers, so `/stream/{id}/audio` also accepts `?t=<token>`, compared in constant time with `hmac.compare_digest`.
- The control panel, curl and dev mode without Tauri keep using open mode, because no token is configured when the backend is started by hand.
- Do this only after Phase 6 has landed.

---

## 3. Tests to add

| Test | Asserts |
|---|---|
| `test_store_v2_roundtrip` | save then load preserves name, value and domain; file perms `0600` on POSIX |
| `test_migrate_v1_keeps_allowlist_only` | v1 file with 300 cookies incl. `SAPISID` and `bank_session` → v2 file with only allowlisted names; warning logged; no values in the log |
| `test_netscape_file_uses_real_domains` | each cookie appears once, with its own domain |
| `test_tauri_cookies_filters_domains` | `.google.com` and third-party cookies dropped |
| `test_cross_origin_post_forbidden` | `POST /api/auth/logout` with `Origin: https://evil.example` → 403 |
| `test_allowed_origin_post_ok` | same with `Origin: http://tauri.localhost` → 200 |
| `test_post_without_origin_ok` | no Origin header → 200 (control panel / curl) |
| `test_ipv6_loopback_host_accepted` | `Host: [::1]:8000` → not 403 |
| `test_signin_flow_routes_removed` | `/api/auth/start-signin-flow` → 404 |

---

## 4. Acceptance criteria

- [x] Unit suite green. `signin_flow.py` and its tests deleted. (357 pass, Revision 13)
- [ ] *(not run yet)* Manual (Windows): Auth page → "Sign in with YouTube" → Google login in the webview → Library shows liked songs.
- [x] Manual: start with a pre-Phase-0 `ytm_session.json` (keep a copy) → startup log reports the migration; the file now only has allowlisted cookies. (Synthetic 246-cookie v1 file; the real store was already v2.)
- [x] Manual: from a page served at another origin (e.g. `python -m http.server 9999` with a page that does `fetch("http://127.0.0.1:8000/api/auth/logout", {method: "POST"})`) → 403, still signed in. (Headless Edge, from `localhost:9999` and `127.0.0.1:9999`.)
- [x] Auth page shows at most three things: status, "Sign in with YouTube", and the "Advanced" section.

## 5. Risks and notes

- **Google may block sign-in from embedded webviews.** The custom user agent in `youtube_login.rs` helps today. If it starts failing, the manual paste fallback still works. Keep the user agent's Chrome version roughly current.
- **Migration is lossy on purpose.** Cookies outside the allowlist are dropped. If YouTube features break after migrating, signing in again rebuilds a complete v2 store.
