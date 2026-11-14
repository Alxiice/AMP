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

    Downloads, running from source, and building the app.

    [:octicons-arrow-right-24: Install AMP](usage/install.md)

-   :material-play-circle:{ .lg .middle } **Using the app**

    ---

    Search, the queue, the player bar, history, settings and the Developer page.

    [:octicons-arrow-right-24: Read the guide](usage/using-the-app.md)

-   :material-broadcast:{ .lg .middle } **OBS widget**

    ---

    Show the current song on your stream.

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
| **Memory** | About 400 MB in total while playing (measured on Linux) |
| **Account** | Optional: YouTube cookies, used only for liked songs and playlists |
| **Platforms** | Windows (tested), Linux and macOS (built by CI, not tested by hand) |

AMP is free software under the [MIT License](https://github.com/Alxiice/AMP/blob/master/LICENSE),
with no warranty. It isn't affiliated with YouTube or Google. It gets songs the same way
[yt-dlp](https://github.com/yt-dlp/yt-dlp) does, which YouTube's Terms of Service don't allow, so
using it is your call. When YouTube changes something, playback can stop working until yt-dlp is
updated.
