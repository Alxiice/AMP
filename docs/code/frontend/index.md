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

`App.tsx` then renders the sidebar (navigation, session badge, cache use, backend status), the
routes, the `QueuePanel` and the always-visible `PlayerBar`, and loads the liked songs once signed in.

| Route | Page | Data |
|---|---|---|
| `/` | `Search` | `GET /api/search`, results in `SongList` |
| `/library` | `Library` | `GET /api/user/likes`; `SignInPrompt` when signed out or on 401 |
| `/playlists` | `Playlists` | `GET /api/user/playlists` as cards; same sign-in prompt |
| `/playlists/:id` | `PlaylistDetail` | `GET /api/playlist/{id}` |
| `/queues`, `/queues/:id` | `SavedQueues`, `SavedQueueDetail` | `/api/queues` |
| `/auth` | `Auth` | status, webview sign-in, Advanced (paste, Firefox) |
| `/history` | `History` | `GET /api/history` by period, grouped by day; reloads on the `amp:history` window event |
| `/settings` | `Settings` | `settings.ts` (localStorage, no API) |
| `/logs` | `Logs` | backend output (Tauri events), `/api/stream/logs`, `/api/logs` relay |
| `/developer` | `Developer` | `/api/health`, `/playback-state`, `/now-playing`, `/cache-info`, `/chunks` every 2 s; API tester (`rawRequest`) |

## Modules

| File | Role |
|---|---|
| `api.ts` | typed `fetch` wrapper. Base URL (`setBaseUrl`), optional Bearer token, `ApiError` with HTTP `status` and backend `code`, a hook for 401s from `/api/user/*`. All response types live here |
| `sidecar.ts` | the backend *client* (it never spawns anything): `initBackend()`, health poll every 1 s, `backend-log` / `backend-status` events, the replayed `backend_logs` ring, `restart()` → `restart_backend` |
| `state.ts` | the queue and playback store (below) |
| `authSession.ts` | shared sign-in status: 60 s poll, refresh on 401, badge labels |
| `tauri_auth.ts` | `youtubeLogin()` → Tauri command `youtube_login`; `mightBeTauri()` |
| `player/` | pure helpers covered by vitest: `errors.ts`, `persistence.ts`, `prefetch.ts`, `keyboard.ts` (space bar), `fade.ts` (fade gain), `history.ts` (listening tracker). OS media controls are wired in `PlayerBar.tsx` through `navigator.mediaSession` (metadata, playback state, action handlers calling the player bar's own handlers; position comes from the `<audio>` element) |
| `settings.ts` | theme, accent, fade: `amp.settings.v1` in localStorage, validated by `parseSettings`, applied to `<html>` (`data-theme`, `--accent`, `--on-accent`) when the module loads, so before the first render |
| `likes.ts`, `savedQueues.ts`, `ui.ts` | liked songs store; saved queue list and actions; toasts and dialogs |
| `player/queue.ts` | the pure queue model |
| `components/` | `PlayerBar`, `QueuePanel`, `SongList` (click = play with the list as queue), `SongMenu`, `CollectionHeader`, `Cover`, `Icon`, `LikeButton`, `UiLayer`, `SignInPrompt` |

## State: `state.ts`

!!! note "Fade and history live in the store"
    **Fade**: the element's volume is `volume × fadeGain(position, duration, fadeSec)`, refreshed
    every 50 ms while playing. One audio element: the end of a song fades out, the next fades in;
    they never overlap (the backend session holds one song).
    **History**: `HistoryTracker` gets every `timeupdate`; only forward steps under 2 s count, so
    seeks don't. A new `playToken` ends the play as `skipped`, `ended` as `finished`, Stop or an
    emptied queue as `stopped`. Plays under 5 s are dropped. The play in progress is saved to
    `amp.history.pending.v1` every 5 s and sent as `closed` on the next start.

The **queue belongs to the frontend**; the backend only stores named copies (`/api/queues`).
`player/queue.ts` is a pure model: items with a `uid` (the same song can be queued twice), the
current index, shuffle (reorders `items`, `original` remembers the order to restore) and repeat.
`StateStore` applies it to the audio element and adds playback fields; `useQueueState()` reads it
and components call `store.playList`, `playNext`, `addToQueue`, `moveItem`, `removeItem`, `jumpTo`,
`next`, `previous`... directly.

`playToken` goes up whenever the current song must (re)load, and `PlayerBar` watches it. A restored
queue stays at token 0, so it waits for the play button. Selecting the song already loaded keeps
its position.

- `previous()` restarts the current song after 3 s of play, else goes back one.
- The store owns the `<audio>` element's `ended` listener (→ `next(false)`), and a 2 s timer that
  reads `audio.currentTime` and reports it to `POST /api/stream/position`. The next song is
  prefetched from `timeupdate`.

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
