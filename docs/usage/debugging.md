# Debug launcher & manual runs

The desktop app is the normal way to use AMP. This page covers the other ways to run it, for
development and debugging.

## Backend alone

From `amp/`, with the venv active:

```bash
python -m backend.main --debug
```

The API listens on `http://127.0.0.1:8000`, with its data in `amp/.amp/`. Interactive API docs
are at <http://127.0.0.1:8000/docs>.

```bash
curl http://127.0.0.1:8000/api/health
curl "http://127.0.0.1:8000/api/search?q=daft+punk&limit=5"
curl -X POST http://127.0.0.1:8000/api/stream/BAgTQhR8MLo/play
curl -r 0-1023 -o head.bin http://127.0.0.1:8000/api/stream/BAgTQhR8MLo/audio
```

`curl` works because it sends no `Origin` header. Browsers do, so the backend refuses
state-changing requests from other web pages ([why](../code/backend/api.md#security-middleware)).

## Web app in a browser

```bash
# terminal 1, in amp/
python -m backend.main --debug
# terminal 2, in amp/frontend/
npm run dev
```

Open <http://localhost:1420>. Outside Tauri the frontend talks to `http://127.0.0.1:8000`, so
the backend must be running there. **Sign in with YouTube** isn't available in a browser: use
the [advanced methods](sign-in.md#advanced-methods).

## `app.py` launcher

```bash
python app.py
```

A small tkinter window (standard library only) for working on the full stack:

| Area | What it does |
|---|---|
| **Backend** (top) | Start / Stop / Restart a backend on `:8000` (or `AMP_PORT`) using `amp/.amp/`. **Force Kill** stops the backend recorded in `amp/.amp/backend.pid` (only if it still answers as that process), else whatever listens on the port |
| **Frontend** (top) | *Web app* mode: Vite dev server, opened in the chosen browser, plus the backend. *Desktop app* mode: `npm run tauri dev`; that app starts **its own** backend with its own data folder |
| **Logs** tab | live `app.log` with search and highlighting |
| **API Request** tab | send any request to the backend, with quick buttons for common routes |
| **Chunk Database** tab | segment rows from the SQLite database, refreshed every 2 s, filterable by song |

!!! note
    In *Desktop app* mode you end up with two backends: the one from the launcher (`:8000`,
    `amp/.amp/`) and the one the app started (random port, app data folder). They don't share
    cache or sign-in.

## Several backends on one data folder

Each backend writes `backend.pid` in its data folder. At startup, a backend warns in its log if
the one recorded there is still alive. Don't run two backends on the same folder: each would
delete cache files the other is serving.
