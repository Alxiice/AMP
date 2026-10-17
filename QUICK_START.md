# Quick Start Guide

Get AMP running in 5 minutes.

---

## Prerequisites

- Python 3.10+ with `venv` (included in the project)
- Node.js 18+ (for the web frontend)
- Git

---

## 1. Start the Backend

```bash
# From the project root (AMP/)
# Activate the virtual environment (Windows CMD):
activate.bat

# Or PowerShell:
./activate.ps1

# Start the backend server
python amp/backend/main.py
```

The backend starts at **http://localhost:8000**
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

---

## 2. Start the Web Interface

Open a **new terminal** and run:

```bash
cd app
npm install    # First time only
npm run dev
```

The web interface starts at **http://localhost:1420**

---

## 3. Connect YouTube Music

### Option A: Import from Browser (easiest)

If you're already logged into YouTube Music in Firefox:

```bash
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" \
  -d '{"browser": "firefox"}'
```

> Chrome on Windows may be blocked by app-bound encryption. Firefox works best.

### Option B: Sign-in Window (via Tauri)

In the web interface, click **"Connect YouTube Music"**.
This opens a Google sign-in window (requires the Tauri desktop app, which needs Rust build tools on Windows).

### Option C: Web Interface Button

1. Open http://localhost:1420
2. Click **"Connect YouTube Music"**
3. Choose **"Import from Firefox"** or follow the sign-in flow

---

## 4. Verify Auth

```bash
curl http://localhost:8000/api/auth/status
```

Expected response when connected:
```json
{
  "state": "signed_in",
  "account": { "name": "Your Name", "channelId": "..." }
}
```

---

## 5. Get Your Liked Songs

```bash
curl http://localhost:8000/api/user/likes
```

Or view them in the web interface at http://localhost:1420

---

## Running Tests

```bash
# From project root, with venv activated
pytest amp/backend/tests/ -v
```

Expected: **92 tests passing**

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Module not found` | Activate venv: `activate.bat` |
| Port 8000 in use | Kill the process using it, or change port in config |
| `npm install` fails | Make sure Node.js 18+ is installed |
| Auth import fails with Chrome | Use Firefox instead: `{"browser": "firefox"}` |
| Session expired | Re-run the import or sign-in flow |

---

## What's Next?

- **Phase 3 (Core Playback)**: Implement chunk-based audio streaming
- See [ROADMAP.md](ROADMAP.md) for the full plan
- See [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) for detailed auth documentation
