#!/usr/bin/env python3
"""
AMP Logging Dashboard Server
=============================

HTTP server that serves the API monitoring dashboard on port 8001 and
accepts log entries from the main app (port 1420) via POST /api/logs.

This allows monitoring API logs in a separate browser tab without
affecting the main app's scroll position.

Endpoints:
    GET  /                  -> Dashboard HTML page
    GET  /api/logs          -> Retrieve stored API logs (JSON)
    POST /api/logs          -> Receive a log entry from the main app (JSON body)
    DELETE /api/logs        -> Clear all stored logs
    GET  /api/health        -> Health check

Usage:
    python app/dashboard/serve_dashboard.py
    python app/dashboard/serve_dashboard.py --port 8001

Then open: http://localhost:8001
"""

import argparse
import http.server
import json
import socketserver
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

DASHBOARD_DIR = Path(__file__).parent.absolute()
MAX_LOGS = 500

# Thread-safe log buffer shared across all request handlers
_log_buffer: deque = deque(maxlen=MAX_LOGS)
_log_lock = threading.Lock()


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

    # -- API: GET /api/logs --
    def _handle_get_logs(self):
        with _log_lock:
            logs = list(_log_buffer)
        self._send_json(200, {"logs": logs, "count": len(logs)})

    # -- API: POST /api/logs --
    def _handle_post_logs(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            entry = json.loads(body)
            # Ensure timestamp exists
            if "timestamp" not in entry:
                entry["timestamp"] = datetime.now().isoformat()
            with _log_lock:
                _log_buffer.append(entry)
            self._send_json(200, {"ok": True})
        except Exception as e:
            self._send_json(400, {"error": str(e)})

    # -- API: DELETE /api/logs --
    def _handle_delete_logs(self):
        with _log_lock:
            _log_buffer.clear()
        self._send_json(200, {"ok": True, "cleared": True})

    # -- API: GET /api/health --
    def _handle_health(self):
        with _log_lock:
            count = len(_log_buffer)
        self._send_json(200, {"status": "ok", "logs": count})

    def _send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/logs":
            self._handle_get_logs()
        elif path == "/api/health":
            self._handle_health()
        else:
            super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/logs":
            self._handle_post_logs()
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path == "/api/logs":
            self._handle_delete_logs()
        else:
            self.send_response(404)
            self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="AMP Logging Dashboard Server")
    parser.add_argument("--port", type=int, default=8001, help="Port to serve on (default: 8001)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    print(f"AMP Logging Dashboard")
    print(f"Serving: {DASHBOARD_DIR}")
    print(f"URL: http://localhost:{args.port}")
    print(f"Backend API: http://localhost:8000")
    print(f"Press Ctrl+C to stop")
    print("-" * 50)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), DashboardHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down dashboard server...")
            httpd.shutdown()


if __name__ == "__main__":
    main()
