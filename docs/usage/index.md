# Usage

This section is for people who want to run AMP and use it.

| Page | Read it when you want to… |
|---|---|
| [Install & launch](install.md) | set up the prerequisites, run the app, build an installer |
| [Using the app](using-the-app.md) | find your way around: search, the player bar, the queue, logs |
| [Signing in](sign-in.md) | see your liked songs and playlists |
| [Configuration](configuration.md) | change the cache size, the port, the audio format… |
| [Troubleshooting](troubleshooting.md) | fix "Node.js not found", a song that won't play, an expired session… |
| [Debug launcher & manual runs](debugging.md) | run the backend by hand, use the app in a browser, test the API |

## The short version

```bash
cd amp
python -m venv venv
venv/Scripts/activate                  # Unix: source venv/bin/activate
pip install -r requirements.lock
python scripts/build_sidecar.py        # once; Tauri needs this file to exist

cd frontend
npm install
npm run tauri dev                      # opens the app
```

You need Python 3.10+, Node.js and the Rust toolchain. See [Install & launch](install.md) for details.
