# AMP — Tasks

Open work, in no particular order. When an item is done, remove it here. Items marked **decide**
need a choice before implementation.

## Requested

### Listening history

- [ ] History export (CSV/JSON) and stats (top songs / artists).

### UI rework

- [ ] Rework the main UI. **decide**: direction to define together through canvas mockups first
  (layout, player bar, queue panel, colours), then implement page by page.

### Recommendations

- [ ] Recommendations page. **decide** the source:
  - **YouTube Music** (`ytmusicapi`: home feed, "watch playlist"/radio from a song): good results at
    once, works signed out for radio; depends on YouTube and gives no control.
  - **Own system from listening history**: e.g. score artists/songs by plays × completion %, then
    expand with YouTube's "related" for the top ones. Weak at the start (cold start).
  - Suggested: start with YouTube radio seeded by your most-completed songs from the history: simple,
    and it uses your own data from day one.

### Local music

- [ ] Play local files: pick folders in the settings, scan them (tags via `mutagen`, already a
  yt-dlp dependency), serve them through the backend with Range support like streamed songs.
- [ ] Local library page (artists / albums / songs, search).
- [ ] **Mixed queues**: queue items are either a YouTube song or a local file. The queue model
  (`player/queue.ts`) and saved queues need a `source` field; IDs can no longer be assumed to be
  11-character YouTube IDs (validation in `persistence.ts` and the backend).

## Proposals (to review)

Suggestions, not yet agreed. Keep, drop or reword.

- [ ] **P1 — Detect a stale sidecar.** The release app bundles the PyInstaller backend from
  `binaries/`, which isn't rebuilt automatically: after a backend change an old sidecar silently
  ships old code. `build.rs` fails clearly when the sidecar is *missing*; it could also warn when
  `amp/backend/**` is newer than the sidecar.
- [ ] **P2 — Play cached songs without re-extracting after a restart** (known issue): serve from
  `layout.json` + the cached segments and extract only when an uncached segment is needed. Cached
  songs would start instantly after a restart (~1 s today).
- [ ] **P4 — Pre-warm yt-dlp at sidecar startup** (known issue: first extraction in a fresh sidecar
  takes ~3 s, later ones ~1.4 s): import it in a background thread at startup.
- [ ] **P5 — Search albums, artists and playlists** (known issue): result tabs in Search. The album
  page exists; artist pages and the search tabs don't.
- [ ] **P7 — Pin songs for offline use**: mark songs/playlists to keep in the cache (excluded from
  LRU eviction) and fully download them in the background. Fits with local music.
- [ ] **P8 — Widget options**: `?theme=dark`, `?accent=`, hide the cover or the progress bar, via the
  URL, so streamers can match their overlay without editing `widget.html`.
- [ ] **P9 — Per-launch API token** (refactor plan 5.6): random token from Rust, passed to the
  backend and the frontend, so other local programs can't drive the API.
- [ ] **P10 — Ship-ready installers**: code signing (SmartScreen warning) and a one-folder
  PyInstaller build if antivirus tools flag the one-file sidecar.

## Known issues

- [ ] Liked state of songs beyond the first 2000 likes is unknown (hearts show empty).
- [ ] Listened time of a crossfading song's last seconds isn't counted in the history.
- [ ] `youtube_login.rs` user agent still says Chrome 125.
- [ ] `CODECOV_TOKEN` repository secret needed for the coverage badge.
- [ ] MSE upgrade (DESIGN_DOC §8.4), optional.

Not tested by hand yet: installers on Linux/macOS, the Release workflow, webview sign-in with a
real Google account, crossfade edge cases (pause during the overlap, uncached next song), media
keys, the widget inside OBS.
