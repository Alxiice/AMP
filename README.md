<div align="center">
  <img src="./icon/logo-square.svg" width="200"/>
  <h1>
    AMP <br/>
  </h1>
  <i>Another Music Player : a local music player based on Youtube Music library.</i>
  <br/>
  <br/>
  <div>
    <a href="https://github.com/Alxiice/AMP/actions/workflows/python-ci.yml"><img src="https://github.com/Alxiice/AMP/actions/workflows/python-ci.yml/badge.svg" alt="Python CI" /></a>
    <a href="https://codecov.io/gh/Alxiice/AMP"><img src="https://img.shields.io/codecov/c/github/Alxiice/AMP/master?logo=codecov" alt="Code Coverage" /></a>
    <a href="https://github.com/Alxiice/AMP/actions/workflows/tauri-build.yml"><img src="https://github.com/Alxiice/AMP/actions/workflows/tauri-build.yml/badge.svg" alt="Tauri Build" /></a>
  </div>
</div>

---

AMP v2 is a desktop app (Tauri + React) with a local FastAPI backend. It streams
YouTube Music audio as cached byte-range segments, so playback starts fast and
seeking works on partially downloaded songs. Search, browse and play work
without an account; signing in with YouTube cookies (optional) unlocks liked
songs and playlists.

## Quick start

```bash
cd amp
python -m venv venv
venv/Scripts/activate          # Unix: source venv/bin/activate
pip install -r requirements.lock

python -m backend.main --debug  # backend on http://127.0.0.1:8000

cd frontend && npm install
npm run tauri dev               # desktop app (needs the Rust toolchain)
```

Node.js must be on `PATH`: yt-dlp uses it to solve YouTube's JS challenges.
Full setup, configuration and API reference: [amp/README.md](amp/README.md).

## Quality checks

The same checks run in CI on every push ([Python CI](.github/workflows/python-ci.yml),
[Tauri Build](.github/workflows/tauri-build.yml)):

```bash
ruff check amp/backend/                                     # from the repo root
cd amp && python -m pytest -m "not integration" --cov=backend   # unit tests + coverage
```

Integration tests hit the real network and are run manually:
`python -m pytest backend/tests/test_integration_download.py -m integration -v -s`.

## Documentation

| Document | Contents |
|---|---|
| [DESIGN_DOC_2.md](DESIGN_DOC_2.md) | Architecture and design (authoritative spec) |
| [AGENTS.md](AGENTS.md) | Progress tracker: revisions, decisions, known issues |
| [improvement-plan/](improvement-plan/README.md) | Refactoring plan, phases 0–6 |
| [amp/README.md](amp/README.md) | Setup, configuration, API reference |
