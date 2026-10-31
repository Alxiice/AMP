"""AMP v2 Backend entry point.

Usage:
    python -m backend.main [--token <uuid>] [--host 127.0.0.1] [--port 8000]
                           [--data-dir <dir>] [--parent-watch] [--debug]

If --token is omitted, the API is open (no Bearer auth required).
Cookie-based YouTube auth is always optional — search and streaming
work without it; only user-specific features (likes, playlists) need it.

The Tauri app starts the backend with --data-dir <app data dir>, a free --port
and --parent-watch (exit when the app's stdin pipe closes). Without --data-dir
(manual runs, app.py, tests) data stays in amp/.amp/ and amp/userdb.sqlite.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import uvicorn

from backend import lifecycle
from backend.config import is_frozen, settings
from backend.utils.logger import configure_logging, get_logger


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AMP v2 Backend")
    parser.add_argument("--token", default=None, help="Optional Bearer auth token (if set, all requests require it)")
    parser.add_argument("--host", default=settings.HOST, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Bind port (default: 8000; 0 = any free port)")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Cache, logs, credentials and DB go here (default: amp/.amp/ + amp/userdb.sqlite)")
    parser.add_argument("--parent-watch", action="store_true",
                        help="Exit when stdin closes (the parent app died) or reads 'exit'")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    return parser.parse_args(argv)


def apply_args(args: argparse.Namespace) -> None:
    """Copy the CLI options into settings (paths first: logging writes under them)."""
    settings.AUTH_TOKEN = args.token
    settings.HOST = args.host
    settings.PORT = args.port
    if args.debug:
        settings.DEBUG = True
    if args.data_dir is not None:
        data_dir = args.data_dir.resolve()
        settings.configure_paths(data_dir=data_dir, db_file=data_dir / "userdb.sqlite")


def _credentials_hint(logger) -> None:
    """Dev: the app data dir has no sign-in but the checkout's .amp/ does. Never copied automatically."""
    if is_frozen() or settings.credential_store_path.exists():
        return
    legacy = Path(__file__).resolve().parent.parent / settings.AMP_DIR / "cache" / "ytm_session.json"
    if legacy.exists() and legacy != settings.credential_store_path:
        logger.info("Not signed in under %s, but %s holds a session: sign in again from the Auth page "
                    "(credentials are not copied between data dirs)", settings.data_dir, legacy)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    apply_args(args)

    configure_logging(console=True)
    logger = get_logger("backend.main")

    running = lifecycle.find_running_backend(settings.pid_file)
    if running:
        logger.warning("Another AMP backend (pid %d, port %d) is already running with data dir %s",
                       running["pid"], running["port"], settings.data_dir)
    if args.data_dir is not None:
        _credentials_hint(logger)

    try:
        sock = lifecycle.bind_socket(settings.HOST, settings.PORT)
    except OSError as e:
        logger.error("Cannot listen on %s:%d: %s", settings.HOST, settings.PORT, e)
        sys.exit(1)
    settings.PORT = sock.getsockname()[1]

    auth_mode = "token required" if args.token else "open (no token)"
    logger.info("Starting AMP v2 backend on %s:%d (debug=%s, auth=%s, data=%s)",
                settings.HOST, settings.PORT, settings.DEBUG, auth_mode, settings.data_dir)

    from backend.api.server import create_app

    app = create_app(auth_token=args.token)
    server = uvicorn.Server(uvicorn.Config(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="debug" if settings.DEBUG else "info",
        access_log=settings.DEBUG,
        timeout_graceful_shutdown=1,  # open audio streams must not hold up exit
    ))

    pid_file = settings.pid_file
    if args.parent_watch:
        def request_shutdown() -> None:
            server.should_exit = True

        lifecycle.watch_parent(lambda: lifecycle.exit_soon(
            request_shutdown, lambda: lifecycle.remove_pid_file(pid_file)))

    lifecycle.write_pid_file(pid_file, settings.PORT)
    try:
        server.run(sockets=[sock])
    finally:
        lifecycle.remove_pid_file(pid_file)


if __name__ == "__main__":
    main()
