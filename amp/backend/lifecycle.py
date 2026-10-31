"""Process lifecycle helpers for backend.main: listening socket, PID file, parent watch.

The Tauri app owns the backend (Phase 6): it passes --parent-watch and keeps the
child's stdin pipe open for its whole lifetime. When the app dies, even when it is
killed from the Task Manager, the OS closes the pipe and the backend sees EOF.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from backend.utils.logger import get_logger

logger = get_logger("backend.lifecycle")

APP_NAME = "AMP v2"  # what /api/health answers in "app"
HEALTH_PROBE_TIMEOUT_S = 1.0
EXIT_GRACE_S = 1.5  # graceful shutdown budget before os._exit


def bind_socket(host: str, port: int) -> socket.socket:
    """Bound (not yet listening) socket for uvicorn; port 0 picks a free port.

    Bound here rather than by uvicorn so the real port is known before startup
    (PID file, log line) and so that on Windows another process can't share it:
    SO_EXCLUSIVEADDRUSE instead of the SO_REUSEADDR uvicorn would set.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # TIME_WAIT only on POSIX
        sock.bind((host.strip("[]"), port))
    except OSError:
        sock.close()
        raise
    return sock


# ---------------------------------------------------------------------------
# PID file
# ---------------------------------------------------------------------------

def write_pid_file(path: Path, port: int) -> None:
    """Record {pid, port, started_at} so tools (app.py) can find and stop this backend."""
    payload = {"pid": os.getpid(), "port": port, "started_at": int(time.time())}
    tmp = path.with_suffix(".pid.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def read_pid_file(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int) or not isinstance(data.get("port"), int):
        return None
    return data


def remove_pid_file(path: Path) -> None:
    """Delete the PID file if it is still ours (a newer backend may have replaced it)."""
    data = read_pid_file(path)
    if data is not None and data["pid"] != os.getpid():
        return
    try:
        path.unlink()
    except OSError:
        pass


def probe_backend(port: int, timeout: float = HEALTH_PROBE_TIMEOUT_S) -> Optional[dict]:
    """/api/health of the AMP backend on *port*, or None if nothing (or something else) answers."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as resp:  # noqa: S310 — fixed loopback URL
            body = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) and body.get("app") == APP_NAME else None


def find_running_backend(path: Path) -> Optional[dict]:
    """The PID file's entry if that backend is still alive (its health answers with the same pid)."""
    data = read_pid_file(path)
    if data is None or data["pid"] == os.getpid():
        return None
    health = probe_backend(data["port"])
    if health is None or health.get("pid") != data["pid"]:
        return None
    return data


# ---------------------------------------------------------------------------
# Parent watch
# ---------------------------------------------------------------------------

def watch_parent(on_exit: Callable[[], None], fd: int = 0) -> Optional[threading.Thread]:
    """Call *on_exit* once stdin reaches EOF (parent gone) or receives "exit".

    Reads the raw fd, so it works whatever sys.stdin is (None in some frozen builds).
    Returns None if there is no usable stdin to watch.
    """
    try:
        os.fstat(fd)
    except OSError:
        logger.warning("--parent-watch: no stdin to watch; the backend won't exit with its parent")
        return None

    def run() -> None:
        while True:
            try:
                chunk = os.read(fd, 1024)
            except OSError:
                chunk = b""  # broken pipe: same as EOF
            if not chunk:
                logger.info("Parent process gone (stdin closed); shutting down")
                break
            if b"exit" in chunk:
                logger.info("Exit requested by the parent; shutting down")
                break
        on_exit()

    thread = threading.Thread(target=run, name="parent-watch", daemon=True)
    thread.start()
    return thread


def exit_soon(request_shutdown: Callable[[], None], cleanup: Callable[[], None],
              grace_s: float = EXIT_GRACE_S) -> None:
    """Ask for a graceful shutdown; if the process is still alive after *grace_s*, clean up and exit."""
    def force() -> None:
        try:
            cleanup()
        finally:
            os._exit(0)

    timer = threading.Timer(grace_s, force)
    timer.daemon = True
    timer.start()
    request_shutdown()
