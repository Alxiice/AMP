# Using the app

The window has a sidebar on the left (pages, backend status, session badge) and the player bar
along the bottom.

## Search

Type in the search box and press ++enter++. The drop-down chooses what to search: `songs`
(default), `videos`, `albums`, `artists` or `playlists`. Only results that can be played are listed.

**Click a result to play it.** The whole result list becomes the queue, so **Next** continues
with the next result.

## The player bar

| Control | What it does |
|---|---|
| ⏮ Previous | restarts the song if more than 3 s have played, else goes to the previous song |
| ▶ / ⏸ | play / pause. A spinner means the stream is still loading |
| ⏹ Stop | stops playback |
| ⏭ Next | next song in the queue. Also happens automatically when a song ends |
| Volume slider | volume, remembered between launches |

### The segment bar

The progress bar is made of one cell per segment of the song (about 10 seconds each). Its colour
shows what's on disk:

| Colour | Meaning |
|---|---|
| :material-square:{ style="color: #1db954" } green | downloaded |
| :material-square:{ style="color: #f0a500" } yellow (pulsing) | downloading |
| :material-square:{ style="color: #333333" } grey | not downloaded yet |
| :material-square:{ style="color: #e74c3c" } red | download failed |

The played part is shaded on top. **Click anywhere on the bar to seek.** Seeking into grey cells
works too: those segments are fetched first.

AMP downloads about 30 seconds ahead of where you are, so the bar fills a little ahead of the
playhead, not all at once. Near the end of a song (last 20 seconds, or past 80 %), the start of
the next song in the queue is downloaded so it starts instantly.

### Cache info

Below the progress bar: how much disk the cache uses, out of its limit (500 MB by default), and
how many songs and segments it holds. When it's full, the songs you haven't played for the
longest are removed first. The song playing is never removed.

### When something goes wrong

Errors appear in red under the song title, in plain words, for example:

| Message | What it means |
|---|---|
| *Sign in required for this track* | YouTube refuses this song without an account (age-gated, for example). [Sign in](sign-in.md) |
| *This track is unavailable* | removed, private or blocked in your country |
| *Node.js not found. Install it and restart.* | see [Troubleshooting](troubleshooting.md#a-song-wont-play) |
| *Couldn't get the audio stream from YouTube* | yt-dlp failed; often fixed by [updating yt-dlp](install.md#updating-yt-dlp) |
| *Backend not reachable* | the backend stopped; see the sidebar status and the **Logs** page |

If the connection drops in the middle of a song, the player reloads once and resumes where it was.

## Queue and restore

The queue, the current song and the volume are saved automatically. When you restart AMP, the
same song is back in the player bar, **paused**: press play to continue.

## Library and Playlists

These two pages need you to [sign in](sign-in.md). When you're signed out they show a
**Sign in** button instead.

- **Library**: your liked songs. Click one to play it; the list becomes the queue.
- **Playlists**: your playlists as cards (name and number of songs). Opening a playlist's tracks
  isn't implemented yet.

## The sidebar

- **Backend: running / starting / stopped / error**: the state of the local backend. When it
  isn't running, a **Restart** button appears next to it; check the **Logs** page for the reason.
- **Session badge**: `Signed in`, `Signed out` or `Session expired — reconnect`. Click it to
  open the Auth page. It is refreshed every minute.

## Logs

Three tabs, useful when something doesn't work:

| Tab | Content |
|---|---|
| **Backend stdout** | everything the backend printed, including startup errors |
| **Streaming** | the backend's recent log lines, read through the API: extractions, segment tables, downloads, retries, errors |
| **API relay** | messages from the player itself (loads, errors, time to first audio). **Clear** empties it |

Log files are also written to disk, in the `logs/` folder of the
[data directory](configuration.md#where-amp-keeps-its-data) (`app.log`, `streaming.log`,
rotated at 5 MB, 3 old files kept).
