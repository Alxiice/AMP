# AMP v2

**Another Music Player**: a desktop app that plays music from the YouTube Music library.

AMP downloads each song in small pieces (*segments*) and keeps them on disk. Playback starts as
soon as the first piece arrives, you can seek inside a song that is only partly downloaded, and
songs you have played before start immediately.

You don't need an account to search and play. Signing in with your YouTube account adds your
liked songs and playlists.

<div class="grid cards" markdown>

- :material-play-circle: **[Usage](usage/index.md)**

    Install AMP, launch it, sign in, change settings, fix common problems.

- :material-code-braces: **[Code](code/index.md)**

    How the app is built: architecture, backend services, the streaming pipeline, the frontend
    and the Tauri shell.

</div>

## At a glance

| | |
|---|---|
| **App** | Tauri v2 desktop window (React + TypeScript) |
| **Backend** | Local FastAPI server (Python), started and stopped by the app |
| **Audio** | AAC 128 kbps (YouTube itag 140), cut into ~10 s segments |
| **Cache** | Segments on disk, 500 MB by default, least recently used songs evicted first |
| **Account** | Optional: YouTube cookies, used only for liked songs and playlists |
| **Platforms** | Windows (tested), Linux (built in CI), macOS (untested) |

!!! warning "Personal prototype"
    AMP is a personal project, not for distribution. Fetching YouTube streams this way goes
    against YouTube's Terms of Service. yt-dlp and YouTube change often, so playback can
    break until yt-dlp is upgraded.
