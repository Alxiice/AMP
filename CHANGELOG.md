# Changelog

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
