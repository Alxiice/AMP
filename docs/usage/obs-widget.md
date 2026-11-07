# OBS now-playing widget

While AMP runs, a small page shows the current song (cover, title, artist, progress) for a stream overlay.

![The widget at 420 × 96](../assets/screenshots/widget.png){ width="420" }

The wave on the progress bar moves while the song plays and freezes on pause.

## Add it to OBS

1. **Sources → + → Browser**.
2. URL: `http://127.0.0.1:8001/?w=320&h=72`
3. Set the source's **Width** / **Height** to the same `w` and `h` (or a little larger).

`w` and `h` are the card size in pixels. Text, cover and progress bar scale with `h`, so a short card stays readable.
Without them the card is 320 × 72.

The card fades in when a song starts and hides when playback stops or AMP closes.
The wave on the progress bar moves while the song plays and freezes on pause.

## Details

- The page polls `GET /now.json` every second: `{song_id, title, artist, cover_url, duration_ms, position_ms, is_playing}`, or `{"song_id": null}` when nothing plays.
- The player sends title, artist and cover with `POST /api/stream/{id}/play`; the position comes from the usual position reports (every 2 s, and on pause). The page fills the gaps itself.
- Port: `8001` by default, `WIDGET_PORT` or `--widget-port` to change it, `0` to turn it off. If the port is taken (for example a second backend started by `app.py`), the backend logs a warning and runs without the widget.
- The server is read-only, listens on `127.0.0.1` only and refuses other `Host` names. The page itself is `amp/backend/widget.html`: edit it freely, then refresh the OBS source.
- Covers come from Google's image servers; a song without a cover shows its YouTube thumbnail.
