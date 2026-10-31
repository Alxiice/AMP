# Troubleshooting

Start with the **Logs** page: the *Backend stdout* tab shows startup errors, the *Streaming* tab
shows what happened to a song.

## The app doesn't start

??? failure "`Python not found at …: create amp/venv (see README) or set AMP_PYTHON`"
    Development builds run the backend with `amp/venv`. Create it
    ([Install, step 1](install.md#1-set-up-the-backend)) or set `AMP_PYTHON` to your interpreter.

??? failure "Tauri complains about `binaries/amp-backend-…`"
    The sidecar file is missing. Run `python scripts/build_sidecar.py` from `amp/`
    ([Install, step 2](install.md#2-build-the-sidecar-once)). It's needed even for `npm run tauri dev`.

??? failure "Sidebar stays on **Backend: starting** or shows **error**"
    Open **Logs → Backend stdout**. Common causes:

    - a missing Python package: `pip install -r requirements.lock` in the venv;
    - `AMP_PORT` set to a port that is already in use: unset it, or pick another one.

    Then click **Restart** in the sidebar.

??? question "Nothing happens when I start AMP a second time"
    That's intended: AMP runs once, and a second launch focuses the existing window. If you can't
    see it, check the task bar or kill `amp-v2` in the task manager.

## A song won't play

??? failure "Node.js not found. Install it and restart."
    yt-dlp needs Node.js to solve YouTube's JavaScript challenges. Install it from
    [nodejs.org](https://nodejs.org), make sure `node --version` works in a new terminal, then
    restart AMP. The app inherits `PATH` from wherever it was launched.

    `GET /api/health` reports what the backend found under `services.extractor`:
    `{"node": true, "ejs": true, "yt_dlp": "2026.10.26"}`.

??? failure "Couldn't get the audio stream from YouTube"
    yt-dlp couldn't extract this song. Usually YouTube changed something. Try:

    1. [Update yt-dlp](install.md#updating-yt-dlp) (and rebuild the sidecar for the installed app).
    2. Wait a few minutes: after a failure AMP doesn't retry the same song for 5 minutes, to
       avoid hammering YouTube. Restarting the backend clears that.
    3. Look at the *Streaming* log for the yt-dlp error message.

??? failure "This track is unavailable / No audio stream for this track"
    The video is removed, private, or blocked in your country, or it has no audio-only format.
    AMP won't retry an unavailable song for 30 minutes (5 minutes for the other errors).

??? failure "Sign in required for this track"
    YouTube requires an account for this song (age restriction, for example).
    [Sign in](sign-in.md), then play it again.

??? failure "Network error while streaming / playback stops mid-song"
    A download failed even after retries. The player retries once automatically. If it keeps
    happening, check your connection and the *Streaming* log (`403`, `429` or timeouts).

??? question "The first play of a song takes a second or two"
    Expected: AMP first asks YouTube for the stream (about 1 s), then downloads the first
    segment. Songs already in the cache start in a few tens of milliseconds. After restarting
    AMP, the first play of a cached song still needs that 1 s lookup.

## Sign-in problems

??? failure "The sign-in window says the browser isn't supported"
    Google sometimes refuses sign-in from embedded browsers. Use
    [Paste a Cookie header](sign-in.md#advanced-methods) instead.

??? failure "Firefox import: database is locked"
    Close Firefox completely (check the task manager) and try again.

??? failure "Signed in, but Library says to sign in"
    Your session probably expired: the badge shows **Session expired — reconnect**. Sign in again.

??? question "I signed in with `app.py`, but the desktop app says Signed out"
    They use [different data folders](configuration.md#where-amp-keeps-its-data). Sign in once
    in each.

## Cache and disk

??? question "How do I clear the cache?"
    Close AMP and delete `cache/segments/` in the
    [data folder](configuration.md#where-amp-keeps-its-data). Or lower `CACHE_MAX_SIZE_MB`.

??? question "Antivirus flags `amp-backend.exe`"
    The sidecar is a PyInstaller one-file executable, which some antivirus tools flag by mistake.
    Allow it, or run the development build instead.
