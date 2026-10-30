"""AMP v2 Backend entry point.

Usage:
    python -m backend.main [--token <uuid>] [--host 127.0.0.1] [--port 8000] [--debug]

If --token is omitted, the API is open (no Bearer auth required).
Cookie-based YouTube auth is always optional — search and streaming
work without it; only user-specific features (likes, playlists) need it.
"""

from __future__ import annotations

import argparse

import uvicorn

from backend.config import settings
from backend.utils.logger import configure_logging, get_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AMP v2 Backend")
    parser.add_argument("--token", default=None, help="Optional Bearer auth token (if set, all requests require it)")
    parser.add_argument("--host", default=settings.HOST, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Bind port (default: 8000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    settings.AUTH_TOKEN = args.token
    settings.HOST = args.host
    settings.PORT = args.port
    if args.debug:
        settings.DEBUG = True

    configure_logging()
    logger = get_logger("backend.main")
    auth_mode = "token required" if args.token else "open (no token)"
    logger.info("Starting AMP v2 backend on %s:%d (debug=%s, auth=%s)", settings.HOST, settings.PORT, settings.DEBUG, auth_mode)

    from backend.api.server import create_app

    app = create_app(auth_token=args.token)

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="debug" if settings.DEBUG else "info",
        access_log=settings.DEBUG,
    )


if __name__ == "__main__":
    main()
