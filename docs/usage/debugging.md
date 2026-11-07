# Manual runs

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

`python app.py` (from `amp/`) opens a small window that starts and stops the backend and the
frontend for you, with logs, an API tester and the segment table: see
[Developer launcher](launcher.md).

## Several backends on one data folder

Each backend writes `backend.pid` in its data folder. At startup, a backend warns in its log if
the one recorded there is still alive. Don't run two backends on the same folder: each would
delete cache files the other is serving.
