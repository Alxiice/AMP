# Configuration

AMP works without any configuration. This page lists what you can change.

## Where AMP keeps its data

=== "Desktop app"

    | OS | Folder |
    |---|---|
    | Windows | `%APPDATA%\com.amp.v2\` |
    | macOS | `~/Library/Application Support/com.amp.v2/` |
    | Linux | `~/.local/share/com.amp.v2/` |

=== "Manual runs / app.py"

    A backend started by hand (`python -m backend.main`) or by the `app.py` launcher uses the
    checkout:

    - `amp/.amp/` for cache, logs and sign-in,
    - `amp/userdb.sqlite` for the database.

    Pass `--data-dir <folder>` to use another folder (the database then goes inside it too).

Inside the data folder:

| Path | Content |
|---|---|
| `cache/segments/<song id>/` | downloaded audio: `init.bin`, `0000.bin`, `0001.bin`…, plus `layout.json` |
| `cache/ytm_session.json` | your YouTube sign-in, if any |
| `logs/app.log`, `logs/streaming.log` | logs, rotated at 5 MB (3 old files kept) |
| `userdb.sqlite` | segment index and metadata cache |
| `backend.pid` | process ID and port of the running backend, removed when it exits |

Deleting `cache/segments/` is safe: songs download again on next play.

## Settings

Settings are environment variables. For manual runs you can also put them in a `.env` file in
`amp/`. The desktop app passes its own environment to the backend, so variables set before
launching it apply too.

| Variable | Default | Effect |
|---|---|---|
| `CACHE_MAX_SIZE_MB` | `500` | cache size limit. When exceeded, the least recently played segments are removed until the cache is down to 80 % |
| `SEGMENT_BUFFER_AHEAD_SEC` | `30` | how many seconds ahead of the playhead to download |
| `SEGMENT_BEHIND` | `2` | segments kept behind the playhead (for seeking back) |
| `STREAM_FORMAT` | `140` | YouTube format code: `140` = AAC/MP4 (works everywhere), `251` = Opus/WebM |
| `YTDLP_PLAYER_CLIENTS` | `["visionos","default"]` | yt-dlp player clients tried in order, as JSON. `default` = yt-dlp's own choice |
| `DOWNLOAD_WORKERS` | `4` | parallel segment downloads |
| `MAX_RETRIES` | `3` | attempts per segment (with back-off 0.5 / 1 / 2 s) |
| `HTTP_TIMEOUT_CONNECT_S` / `HTTP_TIMEOUT_READ_S` | `5` / `30` | timeouts for YouTube's servers |
| `SEGMENT_SYNC_TIMEOUT_S` | `15` | how long the audio endpoint waits for a segment before giving up |
| `SEGMENT_TARGET_SEC` | `5` | segment length when the song has no index (WebM) |
| `AUTH_TOKEN` | *(none)* | require `Authorization: Bearer <token>` on every API call. Same as `--token` |
| `DEBUG` | `false` | verbose logging and access log. Same as `--debug` |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | manual runs only. The desktop app chooses the port itself |

### Desktop app only

| Variable | Effect |
|---|---|
| `AMP_PORT` | use this port instead of a random free one. Handy to keep a fixed `http://127.0.0.1:<port>/docs` URL. `app.py` reads it too |
| `AMP_PYTHON` | development builds: the Python interpreter that runs the backend, instead of `amp/venv` |

!!! example "Bigger cache, Opus audio"
    === "Windows (PowerShell)"
        ```powershell
        $env:CACHE_MAX_SIZE_MB = "2000"
        $env:STREAM_FORMAT = "251"
        npm run tauri dev
        ```
    === "Linux / macOS"
        ```bash
        CACHE_MAX_SIZE_MB=2000 STREAM_FORMAT=251 npm run tauri dev
        ```

    Opus/WebM songs have no byte index, so their segments are estimated from size and duration:
    seeking is less precise. Prefer the default `140` unless you have a reason.

## Backend command line

For manual runs (`python -m backend.main` from `amp/`):

| Option | Default | Effect |
|---|---|---|
| `--port N` | `8000` | port to listen on; `0` picks a free one |
| `--host H` | `127.0.0.1` | keep the default: the backend must not be reachable from the network |
| `--data-dir DIR` | `amp/.amp/` | data folder (database included) |
| `--token T` | *(none)* | require this Bearer token |
| `--parent-watch` | off | exit when standard input closes. Used by the desktop app |
| `--debug` | off | verbose logging |
