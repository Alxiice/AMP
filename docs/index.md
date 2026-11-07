---
title: AMP
template: home.html
hide:
  - navigation
  - toc
---

# AMP

## Where to next

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Install & launch**

    ---

    Prerequisites, first launch, and building the Windows installers.

    [:octicons-arrow-right-24: Install AMP](usage/install.md)

-   :material-play-circle:{ .lg .middle } **Using the app**

    ---

    Search, the queue, the player bar, history, settings and the Developer page.

    [:octicons-arrow-right-24: Read the guide](usage/using-the-app.md)

-   :material-broadcast:{ .lg .middle } **OBS widget**

    ---

    Show the current song on stream with one Browser source.

    [:octicons-arrow-right-24: Set it up](usage/obs-widget.md)

-   :material-code-braces:{ .lg .middle } **How it's built**

    ---

    Architecture, the streaming pipeline, the backend API and the Tauri shell.

    [:octicons-arrow-right-24: Code reference](code/index.md)

</div>

## At a glance

| | |
|---|---|
| **App** | Tauri desktop window (React + TypeScript) |
| **Backend** | Local FastAPI server (Python), started and stopped by the app |
| **Audio** | AAC 128 kbps (YouTube itag 140), cut into ~10 s segments |
| **Cache** | Segments on disk, 500 MB by default, least recently played songs evicted first |
| **Account** | Optional: YouTube cookies, used only for liked songs and playlists |
| **Platforms** | Windows (tested), Linux (built in CI), macOS (untested) |

!!! warning "Independent project"
    AMP isn't affiliated with YouTube or Google. It fetches streams the way
    [yt-dlp](https://github.com/yt-dlp/yt-dlp) does, which YouTube's Terms of Service don't allow.
    yt-dlp and YouTube change often, so playback can break until yt-dlp is upgraded.
