# Changelog

## 1.1.0 — OBS widget settings

**Downloads**

| System | File |
|---|---|
| Windows (x64) | `AMP_1.1.0_x64-setup.exe` or `AMP_1.1.0_x64_en-US.msi` (installers), `AMP-1.1.0-windows-x64.zip` (no install) |
| macOS (Apple Silicon) | `AMP_1.1.0_aarch64.dmg`, `AMP-1.1.0-macos-arm64.tar.gz` (no install) |
| Linux (x64) | `AMP_1.1.0_amd64.deb` (Debian, Ubuntu), `AMP_1.1.0_amd64.AppImage` (most distributions), `AMP-1.1.0-linux-x64.tar.gz` |

Same requirements as 1.0.0: Node.js 18 or newer on your `PATH`, and the builds aren't signed.

**New**

- **Widget page** in the sidebar for the OBS widget: default width and height, border, background,
  progress bar and text colours, and one opacity slider for border and background. The widget
  picks up changes within a second; `?w=` / `?h=` in the OBS URL still override the size.
  **Copy widget URL** at the top of the page.
- **Copy YouTube link** in every song's menu (a `youtube.com/watch` link).

**Fixed**

- The widget's remaining-time line now starts at the knob in OBS too, instead of under the whole bar.
- Windows builds made with the GNU Rust toolchain copy `WebView2Loader.dll` next to `AMP.exe`,
  which wouldn't start without it.

**For developers**

- `AMP-build-and-run.bat` at the repository root (`build_release.py --run`): rebuilds only what
  changed into `build/`, then starts the built app.

## 1.0.0 — first release

The first packaged release of AMP, a desktop player for the YouTube Music library.

**Downloads**

| System | File |
|---|---|
| Windows (x64) | `AMP_1.0.0_x64-setup.exe` or `AMP_1.0.0_x64_en-US.msi` (installers), `AMP-1.0.0-windows-x64.zip` (no install) |
| macOS (Apple Silicon) | `AMP_1.0.0_aarch64.dmg`, `AMP-1.0.0-macos-arm64.tar.gz` (no install) |
| Linux (x64) | `AMP_1.0.0_amd64.deb` (Debian, Ubuntu), `AMP_1.0.0_amd64.AppImage` (most distributions), `AMP-1.0.0-linux-x64.tar.gz` |

**Before you install**

- AMP needs [Node.js](https://nodejs.org) 18 or newer on your `PATH`: yt-dlp uses it to read
  YouTube's player. It isn't bundled.
- The builds aren't signed. Windows SmartScreen shows a warning on first launch ("More info" →
  "Run anyway"). On macOS, right-click the app → Open the first time.
- macOS and Linux builds come from CI and haven't been tested by hand yet.

**What's in it**

Search and play without an account, segment cache on disk, queue with saved queues, liked songs
and playlists after a YouTube sign-in, listening history, crossfade and volume normalization,
light and dark themes, OS media controls, an OBS now-playing widget and a Developer page.
