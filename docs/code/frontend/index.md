# Frontend

A React 18 + TypeScript app built with Vite (`amp/frontend/`), shown in the Tauri window. It also
runs in a normal browser for development (`npm run dev`, port 1420).

| Page | Topic |
|---|---|
| [Player](player.md) | `PlayerBar`, the load sequence, the segment bar, persistence, prefetch, errors |
| [Tauri shell](tauri.md) | the Rust side: backend process, sign-in window, permissions, CSP |

## Startup

```ts
// main.tsx: the backend's port is only known once Tauri answers
initBackend().then(() => {
  ReactDOM.createRoot(root).render(<BrowserRouter><App /></BrowserRouter>);
});
```

`initBackend()` (`sidecar.ts`) calls the Tauri command `backend_info` and sets `api.ts`'s base
URL to `http://127.0.0.1:<port>` **before the first render**, so no component ever calls the
wrong port. Outside Tauri it keeps the default `http://127.0.0.1:8000`.

`App.tsx` then renders the sidebar (navigation, session badge, backend status), the routes and
the always-visible `PlayerBar`.

| Route | Page | Data |
|---|---|---|
| `/` | `Search` | `GET /api/search`, results in `SongList` |
| `/library` | `Library` | `GET /api/user/likes`; `SignInPrompt` when signed out or on 401 |
| `/playlists` | `Playlists` | `GET /api/user/playlists` as cards; same sign-in prompt |
| `/auth` | `Auth` | status, webview sign-in, Advanced (paste, Firefox) |
| `/logs` | `Logs` | backend output (Tauri events), `/api/stream/logs`, `/api/logs` relay |

## Modules

| File | Role |
|---|---|
| `api.ts` | typed `fetch` wrapper. Base URL (`setBaseUrl`), optional Bearer token, `ApiError` with HTTP `status` and backend `code`, a hook for 401s from `/api/user/*`. All response types live here |
| `sidecar.ts` | the backend *client* (it never spawns anything): `initBackend()`, health poll every 1 s, `backend-log` / `backend-status` events, the replayed `backend_logs` ring, `restart()` → `restart_backend` |
| `state.ts` | the queue and playback store (below) |
| `authSession.ts` | shared sign-in status: 60 s poll, refresh on 401, badge labels |
| `tauri_auth.ts` | `youtubeLogin()` → Tauri command `youtube_login`; `mightBeTauri()` |
| `player/` | pure helpers covered by vitest: `errors.ts`, `persistence.ts`, `prefetch.ts` |
| `components/` | `PlayerBar`, `SongList` (click = play with the list as queue), `SignInPrompt` |

## State: `state.ts`

The **queue belongs to the frontend**; the backend has no queue API. `StateStore` is a small
external store read through `useSyncExternalStore`:

```ts
interface QueueState {
  songs: Song[]; currentIndex: number; currentSong: Song | null;
  isPlaying: boolean; positionMs: number; durationMs: number; volume: number;
}
```

`useQueueState()` reads it; `useQueueActions()` exposes `playSong(song, queue?)`, `playQueue`,
`next`, `previous`, `setVolume`, etc.

- `playSong(song, list)` replaces the queue with `list`, positioned on `song`. Without a list,
  the song is appended (or selected if already queued).
- `previous()` restarts the current song after 3 s of play, else goes back one.
- The store owns the `<audio>` element's `ended` listener (→ `next()`), and a 2 s timer that
  reads `audio.currentTime`, reports it to `POST /api/stream/position` and checks whether to
  prefetch the next song.

## Polling rules

Every timer that calls the API has an **in-flight guard**: if the previous call hasn't returned,
the tick is skipped. Otherwise a slow backend accumulates overlapping requests.

| Poll | Interval |
|---|---|
| `/api/health` (sidecar) | 1 s |
| `/api/stream/{id}/chunks` (segment bar) | 500 ms while a song is loaded |
| `/api/stream/cache-info` | 5 s |
| `/api/auth/status` | 60 s |
| `/api/stream/logs`, `/api/logs` (Logs page) | 2 s while the page is open |
| position report | 2 s while playing |

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Vite dev server on :1420 |
| `npm run build` | `tsc` type check + production bundle in `dist/` |
| `npm test` | vitest (pure helpers) |
| `npm run tauri dev` / `npx tauri build` | desktop app / installers ([Tauri shell](tauri.md)) |
