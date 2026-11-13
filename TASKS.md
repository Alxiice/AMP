# AMP — Tasks

Open work, in no particular order. Tick a box when it is done and note the revision in `AGENTS.md`.
Items marked **decide** need a choice before implementation.

## Requested

### Playback

- [x] **Space bar toggles play/pause** anywhere in the app, except while typing in a text field
  (Revision 19). Media keys / Windows media overlay: still open, see proposal P3.

### Settings page

- [x] New `/settings` page, values stored locally (`localStorage`) (Revision 19).
  - [x] **Theme**: dark / light / system and an **accent colour** (8 presets + custom).
  - [x] **Fade between songs**: slider 0–10 s (0 = off). Done as fade-out + fade-in on one audio
    element: the songs don't overlap. Manual skips are not faded.
  - [x] **True crossfade** (Revision 22): two `<audio>` elements; the next song takes the backend
    session at the start of the overlap and the fading one finishes over its open `/audio` request
    (no backend change).
  - [x] **Volume normalization** from YouTube's `loudnessDb` (Revision 22).

### Listening history

- [x] Record each play: song, start time, **time actually listened (seeks excluded), percentage**,
  how it ended (finished / skipped / stopped / app closed). Table `listening_history`, one `POST`
  from the player per play (Revision 19).
- [x] History page: by day, percentage per play, 7 days / 30 days / all time, remove / clear.
- [ ] History export (CSV/JSON) and stats (top songs / artists): not started.

### UI rework

- [ ] Rework the main UI. **decide**: direction to define together through canvas mockups first
  (layout, player bar, queue panel, colours), then implement page by page.

### Recommendations

- [ ] Recommendations page. **decide** the source:
  - **YouTube Music** (`ytmusicapi`: home feed, "watch playlist"/radio from a song): good results at
    once, works signed out for radio; depends on YouTube and gives no control.
  - **Own system from listening history**: e.g. score artists/songs by plays × completion %, then
    expand with YouTube's "related" for the top ones. Needs the history above first; weak at the
    start (cold start).
  - Suggested: start with YouTube radio seeded by your most-completed songs from the history: simple,
    and it uses your own data from day one.

### Local music

- [ ] Play local files: pick folders in the settings, scan them (tags via `mutagen`, already a
  yt-dlp dependency), serve them through the backend with Range support like streamed songs.
- [ ] Local library page (artists / albums / songs, search).
- [ ] **Mixed queues**: queue items are either a YouTube song or a local file. The queue model
  (`player/queue.ts`) and saved queues need a `source` field; IDs can no longer be assumed to be
  11-character YouTube IDs (validation in `persistence.ts` and the backend).

### Developer tools inside the app

- [x] Bring the launcher's tools into the native app: **Developer page** (Revision 19).
  - Embedding the app in the tkinter launcher would need a browser engine; tkinter has none (the
    pure-Python options can't run a React app), and adding pywebview/CEF breaks the "stdlib only"
    launcher.
  - Done as a **Developer page** in the app: backend status + restart, widget, cache, current
    song's segments, API tester. Always in the sidebar (not hidden behind a setting).
  - `app.py` stays for full-stack work where the app itself can't build or run.

## Proposals (to review)

My suggestions, not yet agreed. Keep, drop or reword.

- [ ] **P1 — Detect a stale sidecar.** The release app bundles the PyInstaller backend from
  `binaries/`, which isn't rebuilt automatically: after a backend change (e.g. the OBS widget) an
  old sidecar silently ships old code. `build.rs` now fails clearly when the sidecar is *missing*;
  it could also warn when `amp/backend/**` is newer than the sidecar.
- [ ] **P2 — Play cached songs without re-extracting after a restart** (known issue): serve from
  `layout.json` + the cached segments and extract only when an uncached segment is needed. Cached
  songs would start instantly after a restart (~1 s today).
- [ ] **P3 — Media keys and Windows media overlay** via `navigator.mediaSession` (title, artist,
  cover, play/pause/next/previous handlers). Small, pairs with the space bar task.
- [ ] **P4 — Pre-warm yt-dlp at sidecar startup** (known issue: first extraction in a fresh sidecar
  takes ~3 s, later ones ~1.4 s): import it in a background thread at startup.
- [ ] **P5 — Search albums, artists and playlists** (known issue): result tabs + album/artist pages,
  reusing `CollectionHeader` and the playlist page.
- [ ] **P6 — Volume normalization**: YouTube reports a loudness value per video; scaling the volume
  by it avoids loud/quiet jumps between songs. To check: whether yt-dlp exposes it for our clients.
- [ ] **P7 — Pin songs for offline use**: mark songs/playlists to keep in the cache (excluded from
  LRU eviction) and fully download them in the background. Fits with local music.
- [ ] **P8 — Widget options**: `?theme=dark`, `?accent=`, hide the cover or the progress bar, via the
  URL, so streamers can match their overlay without editing `widget.html`.
- [ ] **P9 — Per-launch API token** (refactor plan 5.6, still open): random token from Rust, passed
  to the backend and the frontend, so other local programs can't drive the API.
- [ ] **P10 — Ship-ready installers**: code signing (SmartScreen warning) and a one-folder
  PyInstaller build if antivirus tools flag the one-file sidecar.
