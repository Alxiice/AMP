"""OBS now-playing widget: a read-only HTTP server on its own port (WIDGET_PORT).

GET /          the widget page (widget.html); ?w=<px>&h=<px> sizes the card
GET /now.json  the current song (title, artist, cover, position) or {"song_id": null}

Plain stdlib server in a daemon thread: it never touches the API's middleware,
token or CORS, and serves nothing but these two read-only routes.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from backend.api.server import LOOPBACK_HOSTS, host_name
from backend.services.streaming import get_streaming_service
from backend.utils.logger import get_logger

logger = get_logger(__name__)
PAGE = Path(__file__).with_name("widget.html")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib name)
        if host_name(self.headers.get("Host", "")) not in LOOPBACK_HOSTS:
            self._send(403, "text/plain", b"forbidden host")  # DNS-rebinding guard, like the API (P17)
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif path == "/now.json":
            now = get_streaming_service().now_playing() or {"song_id": None}
            self._send(200, "application/json", json.dumps(now).encode())
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # OBS polls every second; keep the logs quiet


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows SO_REUSEADDR would let a second backend share the port
    daemon_threads = True


def start_widget_server(host: str, port: int) -> Optional[ThreadingHTTPServer]:
    """Serve the widget in a daemon thread. Port in use → WARNING and None (the app keeps running)."""
    try:
        server = _Server((host, port), _Handler)
    except OSError as e:
        logger.warning("Now-playing widget disabled: cannot listen on %s:%d (%s)", host, port, e)
        return None
    threading.Thread(target=server.serve_forever, name="widget", daemon=True).start()
    logger.info("Now-playing widget on http://%s:%d/", host, server.server_address[1])
    return server
