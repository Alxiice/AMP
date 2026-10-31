# AMP v2: application

This folder holds the app itself:

| Path | What |
|---|---|
| `backend/` | Python backend (FastAPI): search, YouTube sign-in, segment streaming and cache |
| `frontend/` | React app + `src-tauri/` (the Rust desktop shell) |
| `scripts/build_sidecar.py` | builds the backend executable that Tauri bundles |
| `app.py` | tkinter debug launcher |

To launch the app, see the [root README](../README.md). Everything else is in the documentation:

- Usage: [install](../docs/usage/install.md), [configuration](../docs/usage/configuration.md),
  [debug launcher & manual runs](../docs/usage/debugging.md)
- Code: [architecture](../docs/code/index.md), [backend](../docs/code/backend/index.md),
  [frontend](../docs/code/frontend/index.md), [testing](../docs/code/development/testing.md)

## Common commands (from this folder)

```bash
python -m backend.main --debug                     # backend alone on http://127.0.0.1:8000
python -m pytest -m "not integration"              # unit tests
python -m pytest -m integration                    # integration tests (network)
python scripts/build_sidecar.py --smoke            # rebuild + smoke-test the sidecar
python app.py                                      # debug launcher
```

> Personal prototype, not for distribution.
