"""OBS now-playing widget: a read-only HTTP server on its own port (WIDGET_PORT).

GET /               the widget page (widget.html); ?w=<px>&h=<px> override the saved card size
GET /now.json       the current song (title, artist, cover, position) or {"song_id": null}
GET /settings.json  size and colours set in the app (WidgetSettings, saved in <data_dir>/widget.json)

Plain stdlib server in a daemon thread: it never touches the API's middleware,
token or CORS, and serves nothing but these read-only routes.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from backend.api.server import LOOPBACK_HOSTS, host_name
from backend.config import settings
from backend.services.streaming import get_streaming_service
from backend.utils.logger import get_logger

logger = get_logger(__name__)
PAGE = Path(__file__).with_name("widget.html")
HEX = r"^#[0-9a-fA-F]{6}$"


class WidgetSettings(BaseModel):
    """Card size (px) and colours, edited on the app's Widget page."""
    width: int = Field(320, ge=50, le=4000)
    height: int = Field(72, ge=20, le=1000)
    border: str = Field("#f4c0d1", pattern=HEX)
    background: str = Field("#fff1f4", pattern=HEX)
    progress: str = Field("#d4537e", pattern=HEX)


def _settings_file() -> Path:
    return settings.data_dir / "widget.json"


def load_widget_settings() -> WidgetSettings:
    """Saved settings; missing or invalid file → defaults."""
    try:
        return WidgetSettings.model_validate_json(_settings_file().read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return WidgetSettings()


def save_widget_settings(ws: WidgetSettings) -> None:
    _settings_file().write_text(ws.model_dump_json(), encoding="utf-8")


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
        elif path == "/settings.json":
            self._send(200, "application/json", load_widget_settings().model_dump_json().encode())
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
