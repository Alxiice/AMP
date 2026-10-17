# AMP Desktop App

A Tauri-based desktop application for AMP (Another Music Player).

## Overview

This is the frontend desktop application for AMP, built with:
- **Tauri** - Cross-platform desktop framework
- **React** - UI framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Build tool

The app connects to the AMP backend (FastAPI) to provide a full music player experience with YouTube Music integration.

## Features

- One-click authentication with YouTube Music via browser
- Browse and play your liked songs
- Clean, modern UI
- Cross-platform (Windows, macOS, Linux)

## Project Structure

```
app/
├── src/                 # React/TypeScript source files
│   ├── App.tsx         # Main application component
│   ├── main.tsx       # Application entry point
│   └── index.css      # Global styles
├── public/             # Static assets
├── icons/              # Application icons
├── package.json        # Node.js dependencies
├── tauri.conf.json    # Tauri configuration
├── vite.config.ts      # Vite configuration
└── Cargo.toml          # Rust dependencies
```

## Getting Started

### Prerequisites

- Node.js 18+ (for frontend)
- Rust 1.70+ (for Tauri)
- Python 3.10+ (for backend)

### Installation

1. Install frontend dependencies:
   ```bash
   cd app
   npm install
   ```

2. Install Tauri CLI:
   ```bash
   npm install --global @tauri-apps/cli
   ```

3. Ensure backend dependencies are installed (from project root):
   ```bash
   cd ..
   pip install -r amp/backend/requirements.txt
   ```

### Development

Run the frontend in development mode:
```bash
cd app
npm run dev
```

This will start the Vite dev server at `http://localhost:5173`.

To use the app, you also need to run the backend server:
```bash
# In another terminal, from project root
python amp/backend/main.py
```

The app will automatically connect to the backend at `http://localhost:8000`.

### Build

Build the app for production:
```bash
cd app
npm run build
```

This will create a production build in the `dist` directory.

## Authentication Flow

The app uses a simple cookie-based authentication with YouTube Music:

1. User clicks "Login with YouTube Music"
2. App triggers `ytmusicapi oauth` command
3. Browser opens for YouTube login
4. User authenticates with YouTube
5. Cookies are saved locally
6. App uses cookies to access YouTube Music data

No Google Cloud OAuth credentials required!

## Backend Integration

The app communicates with the backend via HTTP requests to:

- `POST /api/auth/cookie-auth` - Trigger browser authentication
- `GET /api/auth/status` - Check authentication status
- `GET /api/user/likes` - Get liked songs
- `POST /api/auth/logout` - Logout

## Configuration

The backend URL is hardcoded to `http://localhost:8000` in development. For production, you may want to make this configurable.

## Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run tauri` | Run Tauri commands |

## Tauri Commands

| Command | Description |
|---------|-------------|
| `tauri dev` | Run app in development mode |
| `tauri build` | Build app for production |
| `tauri serve` | Serve production build |

## Notes

- The app expects the backend to be running before it can function properly
- In production, you may want to bundle the backend with the app or run it as a separate service
- The current implementation uses `cmd /C` for Windows to start the backend - adjust for other platforms

## Troubleshooting

### Backend not starting
Make sure you have all Python dependencies installed:
```bash
pip install -r amp/backend/requirements.txt
```

### Authentication not working
Ensure `ytmusicapi` is installed:
```bash
pip install ytmusicapi
```

### Browser doesn't open
Try manually running:
```bash
python -m ytmusicapi oauth
```

## License

MIT
