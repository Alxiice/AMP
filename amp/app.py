#!/usr/bin/env python3
"""AMP v2 App Launcher — tkinter GUI for debugging the full stack.

The normal entry point is the Tauri app, which starts and stops its own backend.
This launcher is a developer tool. Standard library only. Provides:

  Sidebar: Overview / Logs / API tester / Chunks, browser picker + "Open web app".

  Overview:
    - Backend card:  Start/Stop, Restart (↻), Force kill (✕) — port 8000, or AMP_PORT.
        Data in amp/.amp/ + amp/userdb.sqlite. Force kill uses amp/.amp/backend.pid
        first and port scanning only as a fallback.
    - Frontend card: Web / Desktop mode + Start/Stop, Restart, Force kill (port 1420)
        Web:     Vite dev server, opened in the selected browser once it is up;
                 also starts the backend (a browser can't spawn it)
        Desktop: `npm run tauri dev` (Vite + Tauri window). The app spawns its own
                 backend on a free port with its data in the per-user app data dir
                 (%APPDATA%/com.amp.v2 on Windows), separate from the one above
    - OBS widget card: what the widget on WIDGET_PORT (8001) shows, copy/open its URL
    - Segment strip of the launcher backend's current song, and the last log lines

  Logs:        live backend output + app.log, search, All / Warn+ / Errors filter
  API tester:  any method/path/body against the backend, quick buttons
  Chunks:      auto-refreshing segments table from SQLite, filterable by song

Usage:
    python app.py
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from contextlib import closing
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

AMP_DIR = Path(__file__).resolve().parent

VENV_PYTHON = AMP_DIR / "venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = AMP_DIR / "venv" / "bin" / "python"
VENV_FOUND = VENV_PYTHON.exists()
if not VENV_FOUND:
    VENV_PYTHON = Path(sys.executable)

FRONTEND_DIR = AMP_DIR / "frontend"
NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"

BACKEND_PORT = int(os.environ.get("AMP_PORT") or 8000)
FRONTEND_PORT = 1420
API_BASE = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"
WIDGET_PORT = int(os.environ.get("WIDGET_PORT") or 8001)  # OBS now-playing widget (backend/widget.py)
WIDGET_URL = f"http://127.0.0.1:{WIDGET_PORT}/?w=320&h=72"

DB_PATH = AMP_DIR / "userdb.sqlite"
APP_LOG_PATH = AMP_DIR / ".amp" / "logs" / "app.log"
PID_FILE = AMP_DIR / ".amp" / "backend.pid"  # written by backend.main: {"pid", "port", "started_at"}
SEGMENTS_DIR = AMP_DIR / ".amp" / "cache" / "segments"

FRONTEND_MODES = {"web": "Web app", "desktop": "Desktop app"}
FRONTEND_READY_TIMEOUT_S = 60  # web mode: wait this long for Vite before opening the browser

MAX_LOG_LINES = 2000       # lines kept in memory / shown in the log widget
MAX_CHUNK_ROWS = 5000       # rows shown in the chunk table
LOG_RELOAD_BYTES = 256 * 1024  # how much of app.log "Reload file" re-reads
MINI_LOG_LINES = 200        # lines kept in the Overview's live log
LEVEL_FILTERS = {"warning": {"warning", "error", "critical"}, "error": {"error", "critical"}}  # Logs page

# Hide console windows for helper processes on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_SUBPROC_FLAGS = _NO_WINDOW if os.name == "nt" else 0

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# ---------------------------------------------------------------------------
# Colour palette (dark theme, same tokens as frontend/src/styles.css)
# ---------------------------------------------------------------------------

FONT = "Segoe UI"
MONO = "Consolas"

BG = "#08080b"
SURFACE = "#121217"
SURFACE_2 = "#1b1b22"
SURFACE_3 = "#26262f"
BORDER = "#2a2a33"
FG = "#f4f4f6"
FG_DIM = "#a8a8b3"
FG_MUTED = "#6e6e7a"
ACCENT = "#ff4d67"
ACCENT_HOVER = "#ff6b81"
SUCCESS = "#2ecc71"
WARNING = "#f0a500"
ERROR_CLR = "#ff5f56"
INFO_CLR = "#5aa9ff"
DEBUG_CLR = FG_MUTED
CRITICAL_CLR = "#ff2a4a"

# Log-level tag colours for the Text widgets
LOG_TAGS = {
    "error": ERROR_CLR,
    "warning": WARNING,
    "info": INFO_CLR,
    "debug": DEBUG_CLR,
    "critical": CRITICAL_CLR,
    "timestamp": FG_MUTED,
    "search_hit": "#ffdd00",
}

# Segment strip colours (same as the app's seek bar)
SEG_COLORS = {"downloaded": "#4a4a57", "downloading": WARNING, "pending": "#33333d", "error": ERROR_CLR}


# ---------------------------------------------------------------------------
# Port utilities
# ---------------------------------------------------------------------------

def find_pid_on_port(port: int) -> Optional[int]:
    """Return the PID *listening* on *port*, or None."""
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, timeout=5,
                creationflags=_SUBPROC_FLAGS,
            )
            # Decode with errors='ignore' to handle non-ASCII characters
            stdout = result.stdout.decode('utf-8', errors='ignore')
            # Parse columns instead of matching ":port" anywhere in the line
            # (that also matched ":80001", foreign addresses, etc.). We don't
            # test for the word LISTENING because netstat localises it
            # (e.g. "ÉCOUTE" on French Windows). Listeners are the TCP rows whose
            # foreign address is "<anything>:0".
            for line in stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0].upper() == "TCP":
                    local, foreign = parts[1], parts[2]
                    if (local.rsplit(":", 1)[-1] == str(port)
                            and foreign.rsplit(":", 1)[-1] == "0"):
                        pid = int(parts[-1])
                        if pid:
                            return pid
        else:
            # -sTCP:LISTEN so we don't match clients (e.g. a browser) connected to the port
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True, timeout=5,
            )
            stdout = result.stdout.decode('utf-8', errors='ignore')
            if result.returncode == 0 and stdout.strip():
                return int(stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def find_any_pid_on_port(port: int) -> Optional[int]:
    """Find the PID of any process using the given port (not just listening)."""
    try:
        if os.name == "nt":
            # Windows: use netstat - find any TCP connection with this port
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, timeout=5,
                creationflags=_SUBPROC_FLAGS,
            )
            stdout = result.stdout.decode('utf-8', errors='ignore')
            for line in stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0].upper() == "TCP":
                    local, foreign = parts[1], parts[2]
                    if (local.rsplit(":", 1)[-1] == str(port) or 
                        foreign.rsplit(":", 1)[-1] == str(port)):
                        pid = int(parts[-1])
                        if pid:
                            return pid
        else:
            # Unix: use lsof - find any process using this port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, timeout=5,
            )
            stdout = result.stdout.decode('utf-8', errors='ignore')
            if result.returncode == 0 and stdout.strip():
                return int(stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def kill_pid(pid: int) -> bool:
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=10, creationflags=_SUBPROC_FLAGS,
            )
            # Decode output to avoid threading issues with default encoding
            if result.stdout:
                result.stdout.decode('utf-8', errors='ignore')
            if result.stderr:
                result.stderr.decode('utf-8', errors='ignore')
        else:
            result = subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=5)
            if result.stdout:
                result.stdout.decode('utf-8', errors='ignore')
            if result.stderr:
                result.stderr.decode('utf-8', errors='ignore')
        return result.returncode == 0
    except Exception:
        return False


def force_kill_port(port: int) -> str:
    # First, try to find a listening process
    pid = find_pid_on_port(port)
    if pid is not None:
        if kill_pid(pid):
            for _ in range(10):
                time.sleep(0.3)
                if find_pid_on_port(port) is None:
                    return f"Port {port}: killed PID {pid}"
            return f"Port {port}: killed PID {pid} (may still be releasing)"
        return f"Port {port}: failed to kill PID {pid}"
    
    # If no listening process found, check if port is actually open via socket
    if is_port_open(port):
        # Port is in use but no listening process found - could be TIME_WAIT or a non-listening process
        # Try to find any process using this port (not just listeners)
        pid = find_any_pid_on_port(port)
        if pid is not None:
            if kill_pid(pid):
                for _ in range(10):
                    time.sleep(0.3)
                    if not is_port_open(port):
                        return f"Port {port}: killed non-listening PID {pid}"
                return f"Port {port}: killed non-listening PID {pid} (may still be releasing)"
            return f"Port {port}: failed to kill non-listening PID {pid}"
        # No process found but port is in use - likely TIME_WAIT
        return f"Port {port}: in use but no process found (TIME_WAIT? wait ~30-60s)"
    
    return f"Port {port}: nothing running"


def read_pid_file(path: Path = PID_FILE) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("pid"), int) and isinstance(data.get("port"), int):
        return data
    return None


def backend_pid_from_file(path: Path = PID_FILE) -> Optional[dict]:
    """The PID file's entry if its backend still answers /api/health with that pid (no PID reuse)."""
    data = read_pid_file(path)
    if data is None:
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{data['port']}/api/health", timeout=1) as resp:
            health = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if health.get("app") == "AMP v2" and health.get("pid") == data["pid"] else None


def force_kill_backend(port: int) -> str:
    """Kill the backend recorded in the PID file; fall back to whatever listens on *port*."""
    data = backend_pid_from_file()
    if data is not None:
        pid = data["pid"]
        if kill_pid(pid):
            try:
                PID_FILE.unlink()
            except OSError:
                pass
            return f"Backend: killed PID {pid} (from {PID_FILE.name}, port {data['port']})"
        return f"Backend: failed to kill PID {pid} (from {PID_FILE.name})"
    return force_kill_port(port)


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Cheap check (no netstat/lsof subprocess) — is anything accepting connections?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port_free(port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_port_open(port):
            return True
        time.sleep(0.3)
    return not is_port_open(port)


# ---------------------------------------------------------------------------
# Browser detection
# ---------------------------------------------------------------------------

def _detect_browsers() -> dict[str, str]:
    """Return {display_name: executable_path} for browsers found on the system."""
    found: dict[str, str] = {}

    if os.name != "nt":
        for name, exes in [
            ("Google Chrome", ["google-chrome", "google-chrome-stable", "chrome"]),
            ("Chromium", ["chromium", "chromium-browser"]),
            ("Mozilla Firefox", ["firefox"]),
            ("Brave", ["brave-browser", "brave"]),
            ("Microsoft Edge", ["microsoft-edge"]),
        ]:
            for exe in exes:
                w = shutil.which(exe)
                if w:
                    found[name] = w
                    break
        return found

    candidates: list[tuple[str, list[str]]] = [
        ("Google Chrome", [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]),
        ("Microsoft Edge", [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]),
        ("Mozilla Firefox", [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ]),
        ("Brave", [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        ]),
        ("Opera", [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
            r"C:\Program Files\Opera\opera.exe",
        ]),
    ]

    for name, paths in candidates:
        for p in paths:
            if os.path.isfile(p):
                found[name] = p
                break
        else:
            exe = paths[0].rsplit("\\", 1)[-1] if paths else ""
            if exe:
                w = shutil.which(exe)
                if w:
                    found[name] = w

    return found


def _get_default_browser_name() -> str:
    """Try to read the Windows default browser ProgId from the registry."""
    if os.name != "nt":
        return ""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
        # Real ProgIds: ChromeHTML, FirefoxURL-<hash>, MSEdgeHTM (not "...HTML"),
        # BraveHTML, OperaStable. Substring match so versions/hashes don't matter.
        mapping = [
            ("ChromeHTML", "Google Chrome"),
            ("FirefoxURL", "Mozilla Firefox"),
            ("FirefoxHTML", "Mozilla Firefox"),
            ("MSEdgeHTM", "Microsoft Edge"),
            ("BraveHTML", "Brave"),
            ("Opera", "Opera"),
        ]
        for k, v in mapping:
            if k in prog_id:
                return v
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# ProcessManager — manages one subprocess lifecycle
# ---------------------------------------------------------------------------

class ProcessManager:
    """Start / stop / restart a subprocess, streaming stdout+stderr to a callback."""

    def __init__(self, name: str, log_callback: Callable[[str], None]) -> None:
        self.name = name
        self.process: Optional[subprocess.Popen] = None
        self._log_cb = log_callback
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def pid(self) -> Optional[int]:
        with self._lock:
            return self.process.pid if self.process else None

    def start(self, cmd: list[str], cwd: str) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                self._log(f"[{self.name}] Already running (PID {self.process.pid})")
                return

            if not Path(cwd).is_dir():
                self._log(f"[{self.name}] ERROR: working directory not found: {cwd}")
                return

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"     # otherwise output arrives in delayed blocks
            env["PYTHONIOENCODING"] = "utf-8"
            env["NO_COLOR"] = "1"             # no ANSI colour codes in the log view

            kwargs: dict = {}
            if os.name == "nt":
                kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                           | _NO_WINDOW)
            else:
                # Own session/process group: stop() can then kill the whole tree
                # WITHOUT killing this launcher (killpg on our own group would).
                kwargs["start_new_session"] = True

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **kwargs,
                )
            except FileNotFoundError:
                self._log(f"[{self.name}] ERROR: command not found: {cmd[0]}")
                return
            except Exception as e:
                self._log(f"[{self.name}] ERROR: {e}")
                return

            self.process = proc

        self._log(f"[{self.name}] Started (PID {proc.pid})")
        threading.Thread(target=self._read_output, args=(proc,), daemon=True).start()

    def stop(self, quiet: bool = False) -> None:
        # Grab the process under the lock, but do the slow killing outside of it
        # so is_running()/pid() (used by the UI) never block.
        with self._lock:
            proc = self.process
            self.process = None

        if proc is None or proc.poll() is not None:
            if not quiet:
                self._log(f"[{self.name}] Not running")
            return

        pid = proc.pid
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=10, creationflags=_SUBPROC_FLAGS,
                )
            else:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)      # graceful first
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self._log(f"[{self.name}] Stopped (PID {pid})")

    def _read_output(self, proc: subprocess.Popen) -> None:
        try:
            if proc.stdout:
                for line in proc.stdout:
                    self._log(f"[{self.name}] {line.rstrip()}")
        except Exception:
            pass
        try:
            code = proc.wait(timeout=5)
        except Exception:
            return
        with self._lock:
            still_current = self.process is proc
        if still_current:  # nobody called stop() -> it exited on its own
            self._log(f"[{self.name}] Process exited (code {code})")

    def _log(self, msg: str) -> None:
        self._log_cb(ANSI_RE.sub("", msg))


# ---------------------------------------------------------------------------
# LogTailer — follows app.log and pushes new lines to a callback
# ---------------------------------------------------------------------------

class LogTailer:
    """Tails a log file in a background thread, calling *callback* for each new line.

    Works on raw bytes so file offsets are exact, and only emits complete lines
    (a half-written line is held back until its newline arrives).
    """

    def __init__(self, path: Path, callback: Callable[[str], None]) -> None:
        self._path = path
        self._callback = callback
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pos = 0
        self._buf = b""
        self._reload_bytes: Optional[int] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        # Start at end of file (only show new lines)
        try:
            self._pos = self._path.stat().st_size if self._path.exists() else 0
        except OSError:
            self._pos = 0
        self._buf = b""
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def reload(self, tail_bytes: int = LOG_RELOAD_BYTES) -> None:
        """Ask the running tail thread to re-read the end of the file."""
        with self._lock:
            self._reload_bytes = tail_bytes

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll()
            except Exception:
                pass
            self._stop.wait(0.5)

    def _poll(self) -> None:
        if not self._path.exists():
            self._pos = 0
            self._buf = b""
            return

        size = self._path.stat().st_size
        skip_partial = False

        with self._lock:
            reload_bytes = self._reload_bytes
            self._reload_bytes = None

        if reload_bytes is not None:
            self._pos = max(0, size - reload_bytes)
            self._buf = b""
            skip_partial = self._pos > 0
        elif size < self._pos:
            # File was truncated/rotated — start over
            self._pos = 0
            self._buf = b""

        if size <= self._pos:
            return

        with open(self._path, "rb") as f:
            f.seek(self._pos)
            data = f.read(size - self._pos)
        self._pos += len(data)

        if skip_partial:
            i = data.find(b"\n")
            data = data[i + 1:] if i >= 0 else b""

        data = self._buf + data
        lines = data.split(b"\n")
        self._buf = lines.pop()  # incomplete trailing line, wait for the rest

        for raw in lines:
            if self._stop.is_set():
                return
            self._callback(raw.decode("utf-8", errors="replace").rstrip("\r"))


# ---------------------------------------------------------------------------
# Log-level detection
# ---------------------------------------------------------------------------

_LEVEL_UPPER_RE = re.compile(r"\b(CRITICAL|FATAL|ERROR|WARNING|WARN|INFO|DEBUG)\b")
_ERR_WORD_RE = re.compile(r"\b(error|exception|failed|fatal)\b", re.IGNORECASE)
_WARN_WORD_RE = re.compile(r"\bwarn(ing)?\b", re.IGNORECASE)
_LEVEL_TAG = {
    "CRITICAL": "critical", "FATAL": "critical",
    "ERROR": "error",
    "WARNING": "warning", "WARN": "warning",
    "INFO": "info",
    "DEBUG": "debug",
}


# ---------------------------------------------------------------------------
# Widgets (flat buttons, rounded cards)
# ---------------------------------------------------------------------------

class FlatButton(tk.Button):
    """Flat button with a hover colour. kind picks the colours (see KINDS)."""

    KINDS = {  # kind: (background, hover background, text, border)
        "primary": (ACCENT, ACCENT_HOVER, "#ffffff", ACCENT),
        "secondary": (SURFACE_2, SURFACE_3, FG, BORDER),
        "danger": (SURFACE_2, SURFACE_3, ERROR_CLR, BORDER),
        "chip": (SURFACE, SURFACE_2, FG_DIM, BORDER),
        "chip_on": (SURFACE_3, SURFACE_3, FG, SURFACE_3),
        "nav": (SURFACE, SURFACE_2, FG_DIM, SURFACE),
        "nav_on": (SURFACE_2, SURFACE_2, FG, SURFACE_2),
    }

    def __init__(self, parent: tk.Misc, text: str, command: Callable, kind: str = "secondary",
                 small: bool = False, **kw) -> None:
        kw.setdefault("padx", 8 if small else 12)
        kw.setdefault("pady", 2 if small else 5)
        super().__init__(parent, text=text, command=command, relief=tk.FLAT, bd=0,
                         highlightthickness=1, cursor="hand2",
                         font=(FONT, 9 if small else 10), **kw)
        self.set_kind(kind)
        self.bind("<Enter>", lambda _e: self.config(bg=self._hover) if str(self["state"]) != "disabled" else None)
        self.bind("<Leave>", lambda _e: self.config(bg=self._bg))

    def set_kind(self, kind: str) -> None:
        bg, hover, fg, border = self.KINDS[kind]
        self._bg, self._hover = bg, hover
        self.config(bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                    disabledforeground=FG_MUTED, highlightbackground=border, highlightcolor=border)


class Card(tk.Canvas):
    """Rounded panel: the canvas draws the rounded rectangle, children go in .body.

    auto_height: the card is as tall as its content (otherwise it fills what it is given).
    """

    def __init__(self, parent: tk.Misc, pad: int = 14, radius: int = 12, auto_height: bool = True) -> None:
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=1)
        self._pad, self._radius, self._auto = pad, radius, auto_height
        self.body = tk.Frame(self, bg=SURFACE)
        self._win = self.create_window(pad, pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._layout)
        if auto_height:
            # reqheight, not the actual size: the body only gets a size once the canvas shows it
            self.body.bind("<Configure>", lambda _e: self._fit())
            self.after_idle(self._fit)

    def _fit(self) -> None:
        h = self.body.winfo_reqheight() + 2 * self._pad
        if int(self["height"]) != h:
            self.config(height=h)

    def _layout(self, event: tk.Event) -> None:
        if self._auto:
            self.after_idle(self._fit)  # width changes can rewrap the content
        p = self._pad
        self.itemconfig(self._win, width=max(1, event.width - 2 * p))
        if not self._auto:
            self.itemconfig(self._win, height=max(1, event.height - 2 * p))
        self.delete("bg")
        x2, y2, r = event.width - 1, event.height - 1, self._radius
        pts = [r, 0, x2 - r, 0, x2, 0, x2, r, x2, y2 - r, x2, y2, x2 - r, y2, r, y2, 0, y2, 0, y2 - r, 0, r, 0, 0]
        self.create_polygon(pts, smooth=True, fill=SURFACE, outline=BORDER, tags="bg")
        self.tag_lower("bg")


def _label(parent: tk.Misc, text: str = "", size: int = 10, color: str = FG, bold: bool = False,
           mono: bool = False, **kw) -> tk.Label:
    font = (MONO if mono else FONT, size, "bold") if bold else (MONO if mono else FONT, size)
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color, font=font, **kw)


def _entry(parent: tk.Misc, var: tk.StringVar, width: int = 20, mono: bool = True) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, width=width, bg=SURFACE_2, fg=FG, insertbackground=FG,
                    font=(MONO if mono else FONT, 10), relief=tk.FLAT, highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=ACCENT)


def _check(parent: tk.Misc, text: str, var: tk.BooleanVar) -> tk.Checkbutton:
    return tk.Checkbutton(parent, text=text, variable=var, bg=parent["bg"], fg=FG_DIM,
                          selectcolor=SURFACE_2, activebackground=parent["bg"], activeforeground=FG,
                          font=(FONT, 9), bd=0, highlightthickness=0, cursor="hand2")


def _text(parent: tk.Misc, **kw) -> tk.Text:
    kw.setdefault("state", tk.DISABLED)
    kw.setdefault("fg", FG_DIM)
    return tk.Text(parent, bg=BG, font=(MONO, 9), insertbackground=FG,
                   selectbackground=ACCENT, selectforeground="#ffffff", wrap=tk.NONE,
                   relief=tk.FLAT, bd=0, highlightthickness=0, padx=10, pady=8, **kw)


def _scrolled(parent: tk.Misc, widget_factory: Callable[[tk.Misc], tk.Widget]) -> tk.Widget:
    """Put a Text/Treeview with both scrollbars in *parent* (grid) and return it."""
    w = widget_factory(parent)
    sy = ttk.Scrollbar(parent, command=w.yview)
    sx = ttk.Scrollbar(parent, command=w.xview, orient=tk.HORIZONTAL)
    w.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    w.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")
    parent.grid_rowconfigure(0, weight=1)
    parent.grid_columnconfigure(0, weight=1)
    return w


def _configure_log_tags(text: tk.Text) -> None:
    for tag in ("error", "warning", "info", "debug", "critical", "timestamp"):
        text.tag_configure(tag, foreground=LOG_TAGS[tag])
    text.tag_configure("system", foreground=FG_MUTED)
    # Configured last => highest priority, so highlights win over level colours
    text.tag_configure("search_hit", foreground=LOG_TAGS["search_hit"], background="#4a3a00")


def _get_json(url: str, timeout: float = 0.6) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (local backend)
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _dark_title_bar(win: tk.Tk) -> None:
    """Windows 10/11: dark window title bar (DWMWA_USE_IMMERSIVE_DARK_MODE). No-op elsewhere."""
    if os.name != "nt":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass


def _format_uptime(started_at: object) -> str:
    if not isinstance(started_at, (int, float)):
        return ""
    s = max(0, int(time.time() - started_at))
    return f"{s}s" if s < 60 else f"{s // 60} min" if s < 3600 else f"{s // 3600} h {s % 3600 // 60:02d}"


PILLS = {  # state: (text prefix, background, foreground)
    "running": ("●", "#12301f", SUCCESS),
    "starting": ("●", "#33280a", WARNING),
    "external": ("●", "#33280a", WARNING),
    "stopped": ("○", SURFACE_3, FG_DIM),
}


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class AppLauncher(tk.Tk):
    """AMP v2 launcher window: sidebar + pages (Overview, Logs, API tester, Chunks)."""

    PAGES = (("overview", "◉   Overview"), ("logs", "☰   Logs"),
             ("api", "⇄   API tester"), ("chunks", "▦   Chunks"))

    def __init__(self) -> None:
        super().__init__()
        self.title("AMP launcher")
        self.geometry("1060x740")
        self.minsize(880, 620)
        self.configure(bg=BG)
        self._setup_style()

        # Thread -> UI plumbing. Tk is not thread-safe, so worker threads never
        # touch widgets or call self.after(); they put things on these queues and
        # the main thread drains them in _pump().
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

        # State
        self._log_lines: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._search_var = tk.StringVar()
        self._log_level = "all"  # all | warning | error
        self._auto_scroll = tk.BooleanVar(value=True)
        self._browsers: dict[str, str] = {}
        self._browser_var = tk.StringVar()
        self._frontend_mode = tk.StringVar(value="web")  # key of FRONTEND_MODES
        self._frontend_started_mode = "web"              # mode of the running frontend
        self._chunks_auto_refresh = tk.BooleanVar(value=True)
        self._chunks_filter_var = tk.StringVar()
        self._chunk_rows: list[tuple] = []
        self._chunk_error = ""
        self._chunk_busy = False
        self._status_busy = False
        self._page = "overview"
        self._segments: list[dict] = []
        self._current_segment = -1

        # Process managers (log callback feeds the log views)
        self.backend = ProcessManager("backend", self._append_log)
        self.frontend = ProcessManager("frontend", self._append_log)

        # Log tailer
        self.log_tailer = LogTailer(APP_LOG_PATH, self._append_log)

        self._build_ui()
        self._detect_and_set_browsers()
        _dark_title_bar(self)

        if not VENV_FOUND:
            self._append_log(
                f"[system] WARNING: no venv found in {AMP_DIR / 'venv'}; "
                f"backend will use {VENV_PYTHON}")

        # Start tailing logs + timers
        self.log_tailer.start()
        self._pump()
        self._schedule_status()
        self._chunk_tick()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=SURFACE_2, background=SURFACE_2, foreground=FG,
                        arrowcolor=FG_DIM, bordercolor=BORDER, lightcolor=SURFACE_2, darkcolor=SURFACE_2,
                        selectbackground=SURFACE_2, selectforeground=FG, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", SURFACE_2)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", SURFACE_2)], selectforeground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", SURFACE_2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=SURFACE_3, troughcolor=BG, bordercolor=BG,
                            arrowcolor=FG_MUTED, lightcolor=SURFACE_3, darkcolor=SURFACE_3, gripcount=0)
            style.map(f"{orient}.TScrollbar", background=[("active", BORDER)])
        style.configure("Treeview", background=BG, foreground=FG, fieldbackground=BG, rowheight=24,
                        font=(MONO, 9), borderwidth=0, bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.configure("Treeview.Heading", background=SURFACE_2, foreground=FG_DIM, relief=tk.FLAT,
                        font=(FONT, 9, "bold"), borderwidth=0)
        style.map("Treeview.Heading", background=[("active", SURFACE_3)])
        style.map("Treeview", background=[("selected", SURFACE_3)], foreground=[("selected", FG)])

    # ------------------------------------------------------------------
    # Thread-safe UI helpers
    # ------------------------------------------------------------------

    def _post(self, fn: Callable[[], None]) -> None:
        """Run *fn* on the Tk main thread (safe to call from any thread)."""
        self._ui_queue.put(fn)

    def _pump(self) -> None:
        try:
            while True:
                try:
                    fn = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    traceback.print_exc()
            self._drain_log_queue()
        except Exception:
            traceback.print_exc()
        finally:
            self.after(100, self._pump)

    # ------------------------------------------------------------------
    # UI construction: sidebar + pages
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        side = tk.Frame(self, bg=SURFACE, width=190)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)
        tk.Frame(self, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        brand = tk.Frame(side, bg=SURFACE)
        brand.pack(fill=tk.X, padx=18, pady=(18, 16))
        _label(brand, "AMP", 16, bold=True).pack(side=tk.LEFT)
        _label(brand, " v2", 16, ACCENT, bold=True).pack(side=tk.LEFT)

        self._nav: dict[str, FlatButton] = {}
        for key, text in self.PAGES:
            b = FlatButton(side, text, lambda k=key: self._show_page(k), kind="nav", anchor="w", padx=14, pady=7)
            b.pack(fill=tk.X, padx=8, pady=1)
            self._nav[key] = b

        browser = tk.Frame(side, bg=SURFACE)
        browser.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=16)
        _label(browser, "Browser", 9, FG_MUTED).pack(anchor=tk.W)
        self.browser_combo = ttk.Combobox(browser, textvariable=self._browser_var, state="readonly",
                                          font=(FONT, 9))
        self.browser_combo.pack(fill=tk.X, pady=(4, 6))
        FlatButton(browser, "Open web app", self._open_browser, small=True).pack(fill=tk.X)

        content = tk.Frame(self, bg=BG)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self._pages: dict[str, tk.Frame] = {}
        for key, _text_ in self.PAGES:
            page = tk.Frame(content, bg=BG, padx=18, pady=16)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[key] = page

        self._build_overview(self._pages["overview"])
        self._build_logs(self._pages["logs"])
        self._build_api(self._pages["api"])
        self._build_chunks(self._pages["chunks"])
        self._show_page("overview")

    def _show_page(self, key: str) -> None:
        self._page = key
        self._pages[key].tkraise()
        for k, b in self._nav.items():
            b.set_kind("nav_on" if k == key else "nav")
        if key == "chunks":
            self._refresh_chunks()  # fresh data as soon as the page opens
        elif key == "logs" and self._auto_scroll.get():
            self.log_text.see(tk.END)

    @staticmethod
    def _page_title(page: tk.Frame, title: str, subtitle: str = "") -> tk.Frame:
        head = tk.Frame(page, bg=BG)
        head.pack(fill=tk.X, pady=(0, 12))
        _label(head, title, 15, bold=True).pack(side=tk.LEFT)
        if subtitle:
            _label(head, subtitle, 9, FG_MUTED).pack(side=tk.LEFT, padx=(10, 0), pady=(5, 0))
        return head

    # --- Overview -------------------------------------------------------

    def _service_card(self, parent: tk.Frame, col: int, title: str) -> tuple[tk.Frame, tk.Label]:
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
        head = tk.Frame(card.body, bg=SURFACE)
        head.pack(fill=tk.X)
        _label(head, title, 11, bold=True).pack(side=tk.LEFT)
        pill = _label(head, "○ stopped", 8, FG_DIM, padx=8, pady=1)
        pill.pack(side=tk.RIGHT)
        return card.body, pill

    @staticmethod
    def _set_pill(pill: tk.Label, state: str, text: str) -> None:
        mark, bg, fg = PILLS[state]
        pill.config(text=f"{mark} {text}", bg=bg, fg=fg)

    def _build_overview(self, page: tk.Frame) -> None:
        self._page_title(page, "Overview", f"backend :{BACKEND_PORT} · frontend :{FRONTEND_PORT} "
                                           f"· widget :{WIDGET_PORT}")
        cards = tk.Frame(page, bg=BG)
        cards.pack(fill=tk.X)
        for c in range(3):
            cards.grid_columnconfigure(c, weight=1, uniform="cards")

        # Backend
        body, self.be_pill = self._service_card(cards, 0, "Backend")
        _label(body, "port · pid · uptime", 8, FG_MUTED).pack(anchor=tk.W, pady=(12, 0))
        self.be_detail = _label(body, f"{BACKEND_PORT}", 10, FG_DIM)
        self.be_detail.pack(anchor=tk.W, pady=(0, 12))
        row = tk.Frame(body, bg=SURFACE)
        row.pack(fill=tk.X)
        self.be_main = FlatButton(row, "Start", self._toggle_backend, kind="primary")
        self.be_main.pack(side=tk.LEFT)
        FlatButton(row, "↻", self._restart_backend).pack(side=tk.LEFT, padx=(6, 0))
        FlatButton(row, "✕", self._kill_backend, kind="danger").pack(side=tk.LEFT, padx=(6, 0))

        # Frontend
        body, self.fe_pill = self._service_card(cards, 1, "Frontend")
        seg = tk.Frame(body, bg=SURFACE_2, padx=2, pady=2)
        seg.pack(fill=tk.X, pady=(12, 12))
        self.fe_mode_buttons: dict[str, FlatButton] = {}
        for key, label in FRONTEND_MODES.items():
            b = FlatButton(seg, label.replace(" app", ""), lambda k=key: self._set_frontend_mode(k),
                           kind="chip", small=True)
            b.config(highlightthickness=0)
            b.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.fe_mode_buttons[key] = b
        self._set_frontend_mode("web")
        row = tk.Frame(body, bg=SURFACE)
        row.pack(fill=tk.X)
        self.fe_main = FlatButton(row, "Start", self._toggle_frontend, kind="primary")
        self.fe_main.pack(side=tk.LEFT)
        FlatButton(row, "↻", self._restart_frontend).pack(side=tk.LEFT, padx=(6, 0))
        FlatButton(row, "✕", self._kill_frontend_port, kind="danger").pack(side=tk.LEFT, padx=(6, 0))

        # OBS widget
        body, self.wg_pill = self._service_card(cards, 2, "OBS widget")
        _label(body, "now playing", 8, FG_MUTED).pack(anchor=tk.W, pady=(12, 0))
        self.wg_detail = _label(body, "—", 10, FG_DIM, anchor="w")
        self.wg_detail.pack(fill=tk.X, pady=(0, 12))
        row = tk.Frame(body, bg=SURFACE)
        row.pack(fill=tk.X)
        self.wg_copy = FlatButton(row, "Copy URL", self._copy_widget_url)
        self.wg_copy.pack(side=tk.LEFT)
        FlatButton(row, "Open", lambda: webbrowser.open(WIDGET_URL)).pack(side=tk.LEFT, padx=(6, 0))

        # Segment strip of the backend's current song
        strip = Card(page, pad=12)
        strip.pack(fill=tk.X, pady=(12, 0))
        head = tk.Frame(strip.body, bg=SURFACE)
        head.pack(fill=tk.X)
        self.seg_title = _label(head, "Segments", 9, FG_MUTED)
        self.seg_title.pack(side=tk.LEFT)
        self.seg_count = _label(head, "no song playing", 9, FG_MUTED)
        self.seg_count.pack(side=tk.RIGHT)
        self.seg_canvas = tk.Canvas(strip.body, bg=SURFACE, height=16, highlightthickness=0, bd=0)
        self.seg_canvas.pack(fill=tk.X, pady=(8, 0))
        self.seg_canvas.bind("<Configure>", lambda _e: self._draw_segments())

        # Live log (last lines, unfiltered)
        logcard = Card(page, pad=12, auto_height=False)
        logcard.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        head = tk.Frame(logcard.body, bg=SURFACE)
        head.pack(fill=tk.X, pady=(0, 8))
        _label(head, "Live log", 10, bold=True).pack(side=tk.LEFT)
        FlatButton(head, "Open logs  →", lambda: self._show_page("logs"), kind="chip", small=True).pack(side=tk.RIGHT)
        box = tk.Frame(logcard.body, bg=BG)
        box.pack(fill=tk.BOTH, expand=True)
        self.mini_log = _scrolled(box, _text)
        _configure_log_tags(self.mini_log)

    def _set_frontend_mode(self, key: str) -> None:
        if self.frontend.is_running():
            return  # locked while running (Restart keeps the running mode)
        self._frontend_mode.set(key)
        for k, b in self.fe_mode_buttons.items():
            b.set_kind("chip_on" if k == key else "chip")
            b.config(highlightthickness=0)

    def _copy_widget_url(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(WIDGET_URL)
        self.wg_copy.config(text="Copied")
        self.after(1500, lambda: self.wg_copy.config(text="Copy URL"))

    def _draw_segments(self) -> None:
        c = self.seg_canvas
        c.delete("all")
        segs = [s for s in self._segments if s.get("index", -1) >= 0]
        if not segs:
            return
        w, h, gap = c.winfo_width(), 16, 2
        cell = (w - gap * (len(segs) - 1)) / len(segs)
        for i, s in enumerate(segs):
            x = i * (cell + gap)
            current = s["index"] == self._current_segment
            c.create_rectangle(x, 1, x + cell, h - 1, width=2 if current else 0,
                               outline=ACCENT if current else "",
                               fill=SEG_COLORS.get(s.get("status"), SEG_COLORS["pending"]))

    # --- Logs -----------------------------------------------------------

    def _build_logs(self, page: tk.Frame) -> None:
        self._page_title(page, "Logs", f"backend output + {APP_LOG_PATH.name}")
        bar = Card(page, pad=10)
        bar.pack(fill=tk.X)
        tb = bar.body
        search = _entry(tb, self._search_var, width=30)
        search.pack(side=tk.LEFT, ipady=3)
        search.bind("<KeyRelease>", lambda _e: self._refresh_log_display())
        FlatButton(tb, "✕", self._clear_search, kind="chip", small=True).pack(side=tk.LEFT, padx=(4, 12))
        self._level_buttons: dict[str, FlatButton] = {}
        for key, text in (("all", "All"), ("warning", "Warn+"), ("error", "Errors")):
            b = FlatButton(tb, text, lambda k=key: self._set_log_level(k), kind="chip", small=True)
            b.pack(side=tk.LEFT, padx=2)
            self._level_buttons[key] = b
        self._set_log_level("all")
        _check(tb, "Auto-scroll", self._auto_scroll).pack(side=tk.LEFT, padx=(12, 0))
        FlatButton(tb, "Clear", self._clear_log, kind="chip", small=True).pack(side=tk.RIGHT)
        FlatButton(tb, "Reload file", self._reload_log_file, kind="chip", small=True).pack(side=tk.RIGHT, padx=4)
        self.log_count_label = _label(tb, "0 lines", 9, FG_MUTED)
        self.log_count_label.pack(side=tk.RIGHT, padx=8)

        card = Card(page, pad=2, auto_height=False)
        card.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        box = tk.Frame(card.body, bg=BG)
        box.pack(fill=tk.BOTH, expand=True)
        self.log_text = _scrolled(box, _text)
        _configure_log_tags(self.log_text)

    def _set_log_level(self, key: str) -> None:
        self._log_level = key
        for k, b in self._level_buttons.items():
            b.set_kind("chip_on" if k == key else "chip")
        if hasattr(self, "log_text"):
            self._refresh_log_display()

    # --- API tester -----------------------------------------------------

    def _build_api(self, page: tk.Frame) -> None:
        self._page_title(page, "API tester", API_BASE)
        quick = tk.Frame(page, bg=BG)
        quick.pack(fill=tk.X, pady=(0, 10))
        for label, method, path in [
            ("Health", "GET", "/api/health"),
            ("Playback state", "GET", "/api/stream/playback-state"),
            ("Cache info", "GET", "/api/stream/cache-info"),
            ("Stream logs", "GET", "/api/stream/logs?n=50"),
            ("Search", "GET", "/api/search?q=test&limit=3"),
            ("Auth status", "GET", "/api/auth/status"),
        ]:
            FlatButton(quick, label, lambda m=method, p=path: self._api_quick_fill(m, p),
                       kind="chip", small=True).pack(side=tk.LEFT, padx=(0, 6))

        req = Card(page, pad=12)
        req.pack(fill=tk.X)
        row = tk.Frame(req.body, bg=SURFACE)
        row.pack(fill=tk.X)
        self.api_method = tk.StringVar(value="GET")
        ttk.Combobox(row, textvariable=self.api_method, values=["GET", "POST", "PUT", "DELETE", "PATCH"],
                     state="readonly", width=8, font=(FONT, 10)).pack(side=tk.LEFT)
        self.api_path = tk.StringVar(value="/api/health")
        path_entry = _entry(row, self.api_path)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, ipady=4)
        path_entry.bind("<Return>", lambda _e: self._api_send())
        FlatButton(row, "Send", self._api_send, kind="primary", padx=18).pack(side=tk.LEFT)
        _label(req.body, "Body (JSON, optional)", 9, FG_MUTED).pack(anchor=tk.W, pady=(10, 4))
        self.api_body = tk.Text(req.body, height=4, bg=SURFACE_2, fg=FG, font=(MONO, 9), insertbackground=FG,
                                relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER,
                                highlightcolor=ACCENT, wrap=tk.NONE, padx=8, pady=6)
        self.api_body.pack(fill=tk.X)

        resp = Card(page, pad=12, auto_height=False)
        resp.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.api_status_label = _label(resp.body, "—", 10, FG_DIM, bold=True)
        self.api_status_label.pack(anchor=tk.W, pady=(0, 8))
        box = tk.Frame(resp.body, bg=BG)
        box.pack(fill=tk.BOTH, expand=True)
        self.api_response = _scrolled(box, lambda p: _text(p, fg=FG))

    # --- Chunks ---------------------------------------------------------

    def _build_chunks(self, page: tk.Frame) -> None:
        self._page_title(page, "Chunks", f"segments table in {DB_PATH.name}")
        bar = Card(page, pad=10)
        bar.pack(fill=tk.X)
        tb = bar.body
        self.chunk_summary = _label(tb, "Loading…", 9, FG_DIM)
        self.chunk_summary.pack(side=tk.LEFT)
        FlatButton(tb, "Refresh", self._refresh_chunks, kind="chip", small=True).pack(side=tk.RIGHT)
        _check(tb, "Auto (2 s)", self._chunks_auto_refresh).pack(side=tk.RIGHT, padx=10)
        filter_entry = _entry(tb, self._chunks_filter_var, width=16)
        filter_entry.pack(side=tk.RIGHT, ipady=2)
        # Filtering only re-renders the rows we already have; no DB query needed
        filter_entry.bind("<KeyRelease>", lambda _e: self._render_chunk_tree())
        _label(tb, "Song", 9, FG_MUTED).pack(side=tk.RIGHT, padx=(16, 6))

        card = Card(page, pad=2, auto_height=False)
        card.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        box = tk.Frame(card.body, bg=BG)
        box.pack(fill=tk.BOTH, expand=True)
        columns = ("song_id", "index", "status", "size", "duration", "file_path", "last_accessed")
        self.chunk_tree = _scrolled(box, lambda p: ttk.Treeview(p, columns=columns, show="headings"))
        for col, title, width, anchor in (
            ("song_id", "Song ID", 110, tk.W), ("index", "Idx", 44, tk.CENTER),
            ("status", "Status", 96, tk.CENTER), ("size", "Size", 80, tk.E),
            ("duration", "Duration", 72, tk.E), ("file_path", "File path", 280, tk.W),
            ("last_accessed", "Last accessed", 150, tk.W),
        ):
            self.chunk_tree.heading(col, text=title)
            self.chunk_tree.column(col, width=width, minwidth=min(width, 60), anchor=anchor)
        self.chunk_tree.tag_configure("downloaded", foreground=SUCCESS)
        self.chunk_tree.tag_configure("downloading", foreground=WARNING)
        self.chunk_tree.tag_configure("pending", foreground=FG_DIM)
        self.chunk_tree.tag_configure("error", foreground=ERROR_CLR)

    # ------------------------------------------------------------------
    # Browser detection & selection
    # ------------------------------------------------------------------

    def _detect_and_set_browsers(self) -> None:
        self._browsers = _detect_browsers()
        names = list(self._browsers.keys())
        if not names:
            names = ["Default (system)"]
            self._browsers["Default (system)"] = ""
        self.browser_combo["values"] = names

        # Prefer the OS default browser if detected
        default = _get_default_browser_name()
        if default in self._browsers:
            self._browser_var.set(default)
        else:
            self._browser_var.set(names[0])

    def _open_browser(self) -> None:
        name = self._browser_var.get()
        exe = self._browsers.get(name, "")
        try:
            if exe:
                subprocess.Popen([exe, FRONTEND_URL])
            else:
                webbrowser.open(FRONTEND_URL)
            self._append_log(f"[system] Opened {FRONTEND_URL} in {name}")
        except Exception as e:
            self._append_log(f"[system] Failed to open browser: {e}")
            # Fallback
            try:
                webbrowser.open(FRONTEND_URL)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Backend / frontend actions
    # ------------------------------------------------------------------

    def _backend_cmd(self) -> list[str]:
        # -u: unbuffered, so log lines show up immediately
        return [
            str(VENV_PYTHON), "-u", "-m", "backend.main",
            "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
        ]

    def _frontend_cmd(self, mode: str) -> list[str]:
        if mode == "desktop":
            # Tauri runs `npm run dev` itself (beforeDevCommand) and opens the window on devUrl
            return [NPM_CMD, "run", "tauri", "dev"]
        return [NPM_CMD, "run", "dev", "--", "--port", str(FRONTEND_PORT),
                "--host", "127.0.0.1"]

    def _launch(self, pm: ProcessManager, cmd: list[str], cwd: str, port: int,
                on_ready: Optional[Callable[[], None]] = None) -> None:
        def work() -> None:
            if not pm.is_running() and is_port_open(port):
                self._append_log(
                    f"[system] Port {port} is already in use by another process — "
                    f"use ✕ (force kill) first")
                return
            pm.start(cmd, cwd)
            self._when_listening(pm, port, on_ready)
        threading.Thread(target=work, daemon=True).start()

    def _relaunch(self, pm: ProcessManager, cmd: list[str], cwd: str, port: int,
                  on_ready: Optional[Callable[[], None]] = None) -> None:
        def work() -> None:
            pm.stop(quiet=True)
            if not wait_port_free(port):
                self._append_log(
                    f"[system] Port {port} is still in use — use ✕ (force kill), then Start")
                return
            pm.start(cmd, cwd)
            self._when_listening(pm, port, on_ready)
        threading.Thread(target=work, daemon=True).start()

    def _when_listening(self, pm: ProcessManager, port: int,
                        on_ready: Optional[Callable[[], None]]) -> None:
        """(Worker thread) run *on_ready* on the UI thread once *port* accepts connections."""
        if on_ready is None:
            return
        deadline = time.monotonic() + FRONTEND_READY_TIMEOUT_S
        while pm.is_running() and time.monotonic() < deadline:
            if is_port_open(port):
                self._post(on_ready)
                return
            time.sleep(0.5)
        if pm.is_running():
            self._append_log(f"[system] Port {port} not up after {FRONTEND_READY_TIMEOUT_S}s — "
                             f"open it with 'Open web app' once it is")

    def _toggle_backend(self) -> None:
        if self.backend.is_running():
            self._stop_backend()
        else:
            self._start_backend()

    def _toggle_frontend(self) -> None:
        if self.frontend.is_running():
            self._stop_frontend()
        else:
            self._start_frontend()

    def _start_backend(self) -> None:
        self._launch(self.backend, self._backend_cmd(), str(AMP_DIR), BACKEND_PORT)

    def _stop_backend(self) -> None:
        threading.Thread(target=self.backend.stop, daemon=True).start()

    def _restart_backend(self) -> None:
        self._relaunch(self.backend, self._backend_cmd(), str(AMP_DIR), BACKEND_PORT)

    def _kill_backend(self) -> None:
        def work() -> None:
            self._append_log(f"[system] {force_kill_backend(BACKEND_PORT)}")
        threading.Thread(target=work, daemon=True).start()

    def _start_frontend(self) -> None:
        if self.frontend.is_running():
            self._append_log(f"[frontend] Already running "
                             f"({FRONTEND_MODES[self._frontend_started_mode]}) — Stop it first")
            return
        mode = self._frontend_mode.get()
        self._frontend_started_mode = mode
        self._append_log(f"[system] Launching the {FRONTEND_MODES[mode].lower()}")
        if mode == "desktop":
            self._append_log("[system] First desktop launch compiles the Rust shell (a few minutes)")
            self._append_log("[system] The desktop app runs its own backend (free port, per-user data dir); "
                             "its output is on the app's Logs page")
            self._launch(self.frontend, self._frontend_cmd(mode), str(FRONTEND_DIR), FRONTEND_PORT)
            return
        self._ensure_backend()
        self._launch(self.frontend, self._frontend_cmd(mode), str(FRONTEND_DIR), FRONTEND_PORT,
                     on_ready=self._open_browser)

    def _stop_frontend(self) -> None:
        threading.Thread(target=self.frontend.stop, daemon=True).start()

    def _restart_frontend(self) -> None:
        mode = self._frontend_started_mode if self.frontend.is_running() else self._frontend_mode.get()
        self._frontend_started_mode = mode
        if mode == "web":
            self._ensure_backend()
        # no browser re-open on restart: the open tab reconnects to Vite by itself
        self._relaunch(self.frontend, self._frontend_cmd(mode), str(FRONTEND_DIR), FRONTEND_PORT)

    def _ensure_backend(self) -> None:
        """The web app can't spawn the backend (no Tauri), so start ours unless one is up."""
        def work() -> None:
            if self.backend.is_running() or is_port_open(BACKEND_PORT):
                return
            self._append_log("[system] Starting the backend for the web app")
            self.backend.start(self._backend_cmd(), str(AMP_DIR))
        threading.Thread(target=work, daemon=True).start()

    def _kill_frontend_port(self) -> None:
        self._kill_port_async(FRONTEND_PORT)

    def _kill_port_async(self, port: int) -> None:
        def work() -> None:
            self._append_log(f"[system] {force_kill_port(port)}")
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # Status timer (updates indicator labels every 2 s)
    # ------------------------------------------------------------------

    def _schedule_status(self) -> None:
        # Port probing can be slow on Windows, so it runs in a worker thread
        # instead of freezing the UI.
        if not self._status_busy:
            self._status_busy = True
            threading.Thread(target=self._status_worker, daemon=True).start()
        self.after(2000, self._schedule_status)

    def _status_worker(self) -> None:
        try:
            be = (self.backend.is_running(), self.backend.pid(), is_port_open(BACKEND_PORT))
            fe = (self.frontend.is_running(), self.frontend.pid(), is_port_open(FRONTEND_PORT))
            pid_info = read_pid_file() if be[2] else None
            # The widget port may belong to another backend (the desktop app's): show what it plays
            now = _get_json(f"http://127.0.0.1:{WIDGET_PORT}/now.json") if is_port_open(WIDGET_PORT) else None
            playback = _get_json(API_BASE + "/api/stream/playback-state") if be[2] else None
            song = (playback or {}).get("song_id") or ""
            chunks = _get_json(f"{API_BASE}/api/stream/{song}/chunks") if song else None
            self._post(lambda: self._apply_status(be, fe, pid_info, now, playback, chunks))
        finally:
            self._status_busy = False

    def _apply_status(self, be: tuple, fe: tuple, pid_info: Optional[dict], now: Optional[dict],
                      playback: Optional[dict], chunks: Optional[dict]) -> None:
        for pill, button, (running, _pid, port_open) in ((self.be_pill, self.be_main, be),
                                                         (self.fe_pill, self.fe_main, fe)):
            if running and port_open:
                self._set_pill(pill, "running", "running")
            elif running:
                self._set_pill(pill, "starting", "starting")
            elif port_open:
                self._set_pill(pill, "external", "port in use")
            else:
                self._set_pill(pill, "stopped", "stopped")
            button.config(text="Stop" if running else "Start")
            button.set_kind("secondary" if running else "primary")

        pid = be[1] if be[0] else (pid_info or {}).get("pid")
        parts = [str(BACKEND_PORT)] + ([str(pid)] if pid else [])
        if be[2] and pid_info and pid_info.get("port") == BACKEND_PORT:
            parts.append(_format_uptime(pid_info.get("started_at")))
        self.be_detail.config(text=" · ".join(p for p in parts if p))

        if fe[0]:
            self.fe_pill.config(text=self.fe_pill["text"] + f" · {self._frontend_started_mode}")
        for b in self.fe_mode_buttons.values():
            b.config(state=tk.DISABLED if fe[0] else tk.NORMAL)

        if now is None:
            self._set_pill(self.wg_pill, "stopped", "off")
            self.wg_detail.config(text="backend not running", fg=FG_DIM)
        else:
            self._set_pill(self.wg_pill, "running", f":{WIDGET_PORT}")
            if now.get("song_id"):
                title = now.get("title") or now["song_id"]
                text = f"{title} · {now['artist']}" if now.get("artist") else title
                self.wg_detail.config(text=("❚❚ " if not now.get("is_playing") else "") + text, fg=FG)
            else:
                self.wg_detail.config(text="nothing playing", fg=FG_DIM)

        song = (playback or {}).get("song_id") or ""
        self._segments = (chunks or {}).get("segments") or []
        self._current_segment = (playback or {}).get("current_segment_index", -1) if song else -1
        if song and self._segments:
            real = [x for x in self._segments if x.get("index", -1) >= 0]
            done = sum(1 for x in real if x.get("status") == "downloaded")
            self.seg_title.config(text=f"Segments · {song}")
            self.seg_count.config(text=f"{done} / {len(real)} cached")
        else:
            self.seg_title.config(text="Segments")
            self.seg_count.config(text="no song playing in this backend")
        self._draw_segments()

    # ------------------------------------------------------------------
    # Log handling
    # ------------------------------------------------------------------

    def _append_log(self, line: str) -> None:
        """Thread-safe: queue a log line; the main thread renders it in batches."""
        self._log_queue.put(line)

    def _drain_log_queue(self) -> None:
        new: list[str] = []
        while len(new) < 500:  # cap per tick so a log flood can't freeze the UI
            try:
                new.append(self._log_queue.get_nowait())
            except queue.Empty:
                break
        if not new:
            return

        self._log_lines.extend(new)

        self._append_mini_log(new)
        if self._search_var.get().strip() or self._log_level != "all":
            self._refresh_log_display()          # filtering -> full re-render
        else:
            self.log_text.config(state=tk.NORMAL)
            for line in new:
                self._insert_log_line(line, None)
            self._trim_log_widget()
            self.log_text.config(state=tk.DISABLED)
            self._update_log_count()
            if self._auto_scroll.get():
                self.log_text.see(tk.END)

    def _append_mini_log(self, lines: list[str]) -> None:
        """Overview's live log: the last MINI_LOG_LINES lines, no filter."""
        box = self.mini_log
        box.config(state=tk.NORMAL)
        for line in lines:
            tag = self._classify_log_line(line)
            box.insert(tk.END, line + "\n", (tag,) if tag else ())
        n = self._text_line_count(box)
        if n > MINI_LOG_LINES:
            box.delete("1.0", f"{n - MINI_LOG_LINES + 1}.0")
        box.config(state=tk.DISABLED)
        box.see(tk.END)

    def _text_line_count(self, text: Optional[tk.Text] = None) -> int:
        # The widget always ends with an implicit newline, hence the -1.
        return int((text or self.log_text).index("end-1c").split(".")[0]) - 1

    def _trim_log_widget(self) -> None:
        n = self._text_line_count()
        if n > MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{n - MAX_LOG_LINES + 1}.0")

    def _insert_log_line(self, line: str, pattern: Optional["re.Pattern[str]"],
                         tag: Optional[str] = None) -> None:
        """Append one line (widget must be in NORMAL state), colour it, mark search hits."""
        tag = tag or self._classify_log_line(line)
        self.log_text.insert(tk.END, line + "\n", (tag,) if tag else ())
        if pattern is not None:
            ln = self._text_line_count()  # the line we just inserted is the last one
            for m in pattern.finditer(line):
                self.log_text.tag_add("search_hit", f"{ln}.{m.start()}", f"{ln}.{m.end()}")

    def _refresh_log_display(self) -> None:
        """Re-render the whole log Text widget with the current search filter."""
        search = self._search_var.get().strip()
        pattern = re.compile(re.escape(search), re.IGNORECASE) if search else None
        levels = LEVEL_FILTERS.get(self._log_level)
        display = []
        for line in self._log_lines:
            if pattern and not pattern.search(line):
                continue
            tag = self._classify_log_line(line)
            if levels is None or tag in levels:
                display.append((line, tag))

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for line, tag in display:
            self._insert_log_line(line, pattern, tag)
        self.log_text.config(state=tk.DISABLED)

        self._update_log_count(len(display))
        if self._auto_scroll.get():
            self.log_text.see(tk.END)

    def _update_log_count(self, shown: Optional[int] = None) -> None:
        total = len(self._log_lines)
        if shown is not None and shown != total:
            self.log_count_label.config(text=f"{shown} / {total} lines")
        else:
            self.log_count_label.config(text=f"{total} lines")

    def _classify_log_line(self, line: str) -> Optional[str]:
        """Return a tag name for syntax highlighting based on log content."""
        if line.startswith("Traceback") or "Traceback (most recent call last)" in line:
            return "error"
        m = _LEVEL_UPPER_RE.search(line)
        if m:
            return _LEVEL_TAG[m.group(1)]
        if _ERR_WORD_RE.search(line):
            return "error"
        if _WARN_WORD_RE.search(line):
            return "warning"
        if line.startswith(("[system]", "[backend]", "[frontend]")):
            return "system"
        return None

    def _clear_search(self) -> None:
        self._search_var.set("")
        self._refresh_log_display()

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self._refresh_log_display()

    def _reload_log_file(self) -> None:
        """Re-read the end of app.log from disk."""
        self._log_lines.clear()
        self._refresh_log_display()
        self.log_tailer.reload()
        self._append_log("[system] Reloading log file from disk…")

    # ------------------------------------------------------------------
    # API tester
    # ------------------------------------------------------------------

    def _api_quick_fill(self, method: str, path: str) -> None:
        self.api_method.set(method)
        self.api_path.set(path)
        self.api_body.delete("1.0", tk.END)
        self._api_send()

    def _api_send(self) -> None:
        method = self.api_method.get().upper()
        path = self.api_path.get().strip()
        if not path.startswith("/"):
            path = "/" + path
        url = API_BASE + path

        body_text = self.api_body.get("1.0", tk.END).strip()
        if body_text:
            try:
                json.loads(body_text)
            except ValueError as e:
                self.api_status_label.config(text="Invalid JSON body", fg=ERROR_CLR)
                self._set_response_text(str(e))
                return
        body_bytes = body_text.encode("utf-8") if body_text else None

        self.api_status_label.config(text=f"Sending {method} {url} …", fg=FG_DIM)
        self._set_response_text("")

        def _do_request() -> None:
            status, content_type, raw = 0, "", ""
            t0 = time.perf_counter()
            # NOTE: results are stored in plain variables *inside* the except
            # blocks. The old code used lambdas that referenced the exception
            # variable `e`, which Python deletes when the except block ends, so
            # the lambda crashed with a NameError when it ran later.
            try:
                req = urllib.request.Request(url, data=body_bytes, method=method)
                if body_bytes:
                    req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                    raw = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                status = e.code
                content_type = e.headers.get("Content-Type", "") if e.headers else ""
                raw = e.read().decode("utf-8", errors="replace")
            except urllib.error.URLError as e:
                status, raw = 0, str(e.reason)
            except Exception as e:
                status, raw = 0, str(e)
            ms = (time.perf_counter() - t0) * 1000
            self._post(lambda: self._show_api_response(status, content_type, raw, ms))

        threading.Thread(target=_do_request, daemon=True).start()

    def _show_api_response(self, status: int, content_type: str, raw: str,
                           elapsed_ms: float = 0.0) -> None:
        if status == 0:
            self.api_status_label.config(text="ERROR — connection failed", fg=ERROR_CLR)
            self._set_response_text(raw)
            return

        status_color = SUCCESS if 200 <= status < 300 else (WARNING if 300 <= status < 400 else ERROR_CLR)
        self.api_status_label.config(text=f"HTTP {status}  ·  {elapsed_ms:.0f} ms", fg=status_color)

        # Pretty-print JSON
        display = raw
        if "json" in content_type.lower() or raw.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(raw)
                display = json.dumps(parsed, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass

        self._set_response_text(display)

    def _set_response_text(self, text: str) -> None:
        self.api_response.config(state=tk.NORMAL)
        self.api_response.delete("1.0", tk.END)
        self.api_response.insert("1.0", text)
        self.api_response.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Chunk database
    # ------------------------------------------------------------------

    _CHUNK_QUERY = (
        'SELECT song_id, "index", byte_start, byte_end, size_bytes, '
        'duration_ms, status, file_path, last_accessed '
        'FROM segments ORDER BY last_accessed DESC'
    )

    def _chunk_tick(self) -> None:
        # Always reschedule (the old version stopped forever once auto-refresh
        # was unticked, so re-ticking it did nothing). Skip the DB read when the
        # page isn't visible.
        if self._chunks_auto_refresh.get() and self._page == "chunks":
            self._refresh_chunks()
        self.after(2000, self._chunk_tick)

    def _refresh_chunks(self) -> None:
        """Read the segments table from SQLite (worker thread) and update the view."""
        if self._chunk_busy:
            return
        self._chunk_busy = True

        def _read() -> None:
            rows: list[tuple] = []
            error = ""
            try:
                if not DB_PATH.exists():
                    error = f"Database not found: {DB_PATH.name}"
                else:
                    with closing(sqlite3.connect(str(DB_PATH), timeout=5)) as conn:
                        rows = conn.execute(self._CHUNK_QUERY).fetchall()
            except Exception as e:
                error = f"Error reading DB: {e}"
            finally:
                self._chunk_busy = False
            self._post(lambda: self._apply_chunk_data(rows, error))

        threading.Thread(target=_read, daemon=True).start()

    def _apply_chunk_data(self, rows: list[tuple], error: str) -> None:
        self._chunk_rows = rows
        self._chunk_error = error

        if error:
            self.chunk_summary.config(text=error)
        else:
            by_status: dict[str, int] = {}
            total_size = 0
            for r in rows:
                st = r[6] or "pending"
                by_status[st] = by_status.get(st, 0) + 1
                total_size += r[4] or 0
            status_parts = ", ".join(f"{k}:{v}" for k, v in sorted(by_status.items()))
            self.chunk_summary.config(
                text=f"{len(rows)} segments  |  {status_parts}  |  "
                     f"Total: {total_size / 1024:.1f} KB")
        self._render_chunk_tree()

    def _render_chunk_tree(self) -> None:
        filter_text = self._chunks_filter_var.get().strip().lower()

        entries: list[tuple[str, tuple, tuple]] = []   # (iid, values, tags)
        used: set[str] = set()
        for row in self._chunk_rows:
            song_id = row[0] or ""
            if filter_text and filter_text not in song_id.lower():
                continue
            if len(entries) >= MAX_CHUNK_ROWS:
                break

            index = row[1] if row[1] is not None else -1
            size_bytes = row[4] or 0
            duration_ms = row[5] or 0
            status = row[6] or "pending"
            file_path = row[7] or ""
            last_accessed = row[8] or ""

            idx_display = "init" if index == -1 else str(index)
            dur_display = f"{duration_ms / 1000:.1f}s" if duration_ms else "—"
            path_display = file_path
            if not path_display:
                # Construct expected path
                if index == -1:
                    path_display = str(SEGMENTS_DIR / song_id / "init.bin")
                else:
                    path_display = str(SEGMENTS_DIR / song_id / f"{index:04d}.bin")
            if len(path_display) > 60:
                path_display = "…" + path_display[-57:]

            # Stable row id => selection/scroll survive refreshes
            iid = re.sub(r"[\s{}\\]", "_", f"{song_id}|{index}")
            n = 1
            base = iid
            while iid in used:
                n += 1
                iid = f"{base}#{n}"
            used.add(iid)

            tag = status if status in ("downloaded", "downloading", "pending", "error") else ""
            entries.append((
                iid,
                (song_id, idx_display, status, self._format_bytes(size_bytes),
                 dur_display, path_display, str(last_accessed)),
                (tag,) if tag else (),
            ))

        tree = self.chunk_tree
        current = list(tree.get_children())
        new_ids = [e[0] for e in entries]

        if current == new_ids:
            # Same rows in the same order: update in place (no flicker, no scroll jump)
            for iid, values, tags in entries:
                tree.item(iid, values=values, tags=tags)
            return

        selected = set(tree.selection())
        yview = tree.yview()[0]
        if current:
            tree.delete(*current)
        for iid, values, tags in entries:
            tree.insert("", tk.END, iid=iid, values=values, tags=tags)
        keep = [i for i in new_ids if i in selected]
        if keep:
            tree.selection_set(keep)
        tree.yview_moveto(yview)

    @staticmethod
    def _format_bytes(n: int) -> str:
        n = n or 0
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.2f} MB"

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self.withdraw()  # hide immediately; stopping children may take a moment
        self.log_tailer.stop()
        for pm in (self.backend, self.frontend):
            if pm.is_running():
                pm.stop(quiet=True)
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = AppLauncher()
    app.mainloop()


if __name__ == "__main__":
    main()