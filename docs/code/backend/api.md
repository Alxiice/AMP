# HTTP API

Defined in `api/server.py` (app, middleware, health), `api/endpoints.py` (library, streaming,
logs) and `api/auth_routes.py` (`/api/auth/*`). The running backend serves interactive docs at
`/docs` (Swagger) and the schema at `/openapi.json`.

The TypeScript client in `frontend/src/api.ts` defines matching types. There is no translation
layer: if you change a response shape, change `api.ts` too.

## Routes

!!! tip "Route order matters"
    FastAPI matches in declaration order. Specific routes (`/stream/logs`,
    `/stream/playback-state`, `/stream/cache-info`) are declared **before** parameterised ones
    (`/stream/{song_id}/…`). Keep it that way when adding routes.

=== "Library"

    | Method | Path | Returns |
    |---|---|---|
    | GET | `/` | `{app, version, status}` |
    | GET | `/api/health` | `{status, app: "AMP v2", pid, services: {auth, streaming, database, extractor: {node, ejs, yt_dlp}}}` |
    | GET | `/api/search?q=&type=songs&limit=20` | list of songs (`limit` 1–50; `type` = songs, videos, albums, artists, playlists) |
    | GET | `/api/song/{id}` | song metadata |
    | GET | `/api/artist/{id}`, `/api/album/{id}`, `/api/playlist/{id}` | metadata dicts |
    | GET | `/api/user/likes` | liked songs (**401** when signed out) |
    | GET | `/api/user/playlists` | the user's playlists (**401** when signed out) |

=== "Streaming"

    | Method | Path | Returns |
    |---|---|---|
    | POST | `/api/stream/{id}/play` | resolves the stream (blocks for the extraction), starts the session and buffer-ahead → `{song_id, duration_ms, mime_type, segment_count, is_dash, epoch, cached_ahead, message}`. `message: "superseded"` if a newer `/play` arrived meanwhile |
    | GET | `/api/stream/{id}/audio` | the song as one file, with full Range support ([serving](serving.md)) |
    | GET | `/api/stream/{id}/chunks` | per-segment status for the segment bar (`pending`, `downloading`, `downloaded`, `error`), from memory |
    | GET | `/api/stream/info/{id}` | segment table summary, incl. `method` (`sidx` / `proportional`), `itag`, `layout_id` |
    | POST | `/api/stream/buffer/{id}?mode=current\|prefetch` | `current`: re-run buffer-ahead. `prefetch`: resolve and queue init + 2 segments at LOW, session untouched |
    | POST | `/api/stream/pause`, `/resume`, `/stop` | `{message}` |
    | POST | `/api/stream/position?position_ms=` | playhead report (every 2 s) |
    | POST | `/api/stream/seek?position_ms=` | bump epoch, buffer from the new segment |
    | GET | `/api/stream/playback-state` | the in-memory `PlaybackInfo` |
    | GET | `/api/stream/cache-info` | `{total_bytes, total_mb, max_mb, usage_pct, file_count, song_count, songs[]}` |
    | GET | `/api/stream/logs?n=200` | last lines of the in-memory log ring (all backend INFO+ lines, 1000 kept) |

=== "Auth"

    | Method | Path | Body / returns |
    |---|---|---|
    | GET | `/api/auth/status?verify=false` | `{state, is_authenticated, account, migrated_from_full_jar}`. `verify=true` checks the session against YouTube |
    | POST | `/api/auth/tauri-cookies` | `{cookies: [{name, value, domain}]}` from the sign-in webview. 400 if none is a youtube.com cookie |
    | POST | `/api/auth/cookies`, `/api/auth/cookie-header` | `{cookie_header}` pasted from DevTools |
    | POST | `/api/auth/import-browser?browser=firefox` | Firefox only (400 for others, 404 if no YouTube cookie, hint if the DB is locked) |
    | POST | `/api/auth/logout` | deletes the stored session |

=== "Logs"

    | Method | Path | Use |
    |---|---|---|
    | GET | `/api/logs?n=500` | frontend log relay (last 500 lines) |
    | POST | `/api/logs` | append a line from the frontend |
    | DELETE | `/api/logs` | clear the relay |

## Security middleware

The API runs on loopback with no login, so it relies on the checks in `AuthMiddleware`
(`server.py`). They apply to every request except `OPTIONS` and the public paths
(`/`, `/api/health`, `/docs`, `/redoc`, `/openapi.json`):

1. **Host check, always.** The `Host` header (port stripped, `[::1]` kept whole) must be
   `127.0.0.1`, `localhost` or `[::1]`. This blocks DNS-rebinding attacks.
2. **Cross-site check, always.** `cross_site_rejection()` refuses with
   `403 {"detail": {"code": "forbidden_origin"}}`:
    - any non-GET/HEAD/OPTIONS request with an `Origin` not in `ALLOWED_ORIGINS`;
    - a GET on `/api/auth/*` with `Sec-Fetch-Site: cross-site` and no allowed `Origin`.

    Requests **without** `Origin` (curl, `app.py`, scripts) are allowed: browsers always send
    `Origin` on cross-origin POSTs, so a missing one means "not a web page".
3. **Bearer token, only if configured** (`--token` / `AUTH_TOKEN`). Off by default.

`ALLOWED_ORIGINS` is the Tauri origins (`tauri://localhost`, `http(s)://tauri.localhost`) and
the Vite dev server (`http://localhost:1420`, `http://127.0.0.1:1420`). CORS uses the same list
(never `*`) and exposes `Content-Range`, `Content-Length`, `Accept-Ranges`.

??? question "Why is CORS not enough?"
    CORS only stops a page from *reading* a response. A cross-site
    `fetch(url, {method: "POST"})` with no body is a "simple request": the browser sends it
    without a preflight, and the backend would act on it (log you out, stop playback…). The
    `Origin` check refuses it before any handler runs.

## Error model

Streaming routes return one shape, built in `api/errors.py`:

```json
{"detail": {"code": "auth_required", "message": "Sign in required for this video."}}
```

| `code` | HTTP | Raised when |
|---|---|---|
| `invalid_id` | 400 | the song ID doesn't match `^[A-Za-z0-9_-]{11}$` (`InvalidSongId`) |
| `unavailable` | 404 | video removed, private or region-blocked |
| `no_audio` | 404 | no audio-only format |
| `auth_required` | 401 | age-gated / members-only and signed out |
| `node_missing` | 503 | Node.js not on `PATH` |
| `extract_failed` | 502 | any other extraction failure |
| `segment_unavailable` | 502 | the first segment of an `/audio` response couldn't be fetched |
| `forbidden_origin` | 403 | cross-site request (middleware) |

`ExtractionError` and `InvalidSongId` raised anywhere in a handler are converted by exception
handlers, so routes don't need try/except. Library routes still raise `HTTPException` with a
string `detail`; `api.ts` accepts both shapes and exposes the code as `ApiError.code`, which
`player/errors.ts` turns into text.

The song ID is validated before it's used in any file path: it ends up in
`segments/<song_id>/`, so an unchecked value would allow path traversal.
