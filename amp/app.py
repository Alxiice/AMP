#!/usr/bin/env python3
"""AMP v2 App Launcher — tkinter GUI for managing the full stack.

Standard library only. Provides:

  Top bar:
    - Backend:  Start / Stop / Restart / Force Kill (port 8000)
    - Frontend: Start / Stop / Restart / Force Kill (port 1420)
    - Browser selector dropdown + Open in Browser

  Tab zone (ttk.Notebook):
    Tab 1 — Logs:     Live backend log viewer with search + syntax highlighting
    Tab 2 — API:      HTTP request tester against the backend (any method/path/body)
    Tab 3 — Chunks:   Auto-refreshing segment (chunk) database viewer from SQLite

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

BACKEND_PORT = 8000
FRONTEND_PORT = 1420
API_BASE = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"

DB_PATH = AMP_DIR / "userdb.sqlite"
APP_LOG_PATH = AMP_DIR / ".amp" / "logs" / "app.log"
SEGMENTS_DIR = AMP_DIR / ".amp" / "cache" / "segments"

MAX_LOG_LINES = 2000        # lines kept in memory / shown in the log widget
MAX_CHUNK_ROWS = 5000       # rows shown in the chunk table
LOG_RELOAD_BYTES = 256 * 1024  # how much of app.log "Reload All" re-reads

# Hide console windows for helper processes on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_SUBPROC_FLAGS = _NO_WINDOW if os.name == "nt" else 0

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# ---------------------------------------------------------------------------
# Colour palette (dark theme, matches amp_control.py)
# ---------------------------------------------------------------------------

BG = "#0f0f0f"
BG_ELEV = "#1a1a1a"
BG_INPUT = "#252525"
FG = "#f1f1f1"
FG_DIM = "#aaaaaa"
ACCENT = "#ff0033"
SUCCESS = "#1db954"
WARNING = "#f0a500"
ERROR_CLR = "#e74c3c"
INFO_CLR = "#4a9eff"
DEBUG_CLR = "#888888"
CRITICAL_CLR = "#ff2222"

# Log-level tag colours for the Text widget
LOG_TAGS = {
    "error": ERROR_CLR,
    "warning": WARNING,
    "info": INFO_CLR,
    "debug": DEBUG_CLR,
    "critical": CRITICAL_CLR,
    "timestamp": "#666666",
    "search_hit": "#ffdd00",
}


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
# Main application
# ---------------------------------------------------------------------------

class AppLauncher(tk.Tk):
    """AMP v2 launcher window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("AMP v2 — App Launcher")
        self.geometry("960x720")
        self.minsize(800, 600)
        self.configure(bg=BG)

        # ttk style
        self._style = ttk.Style(self)
        try:
            self._style.theme_use("clam")
        except tk.TclError:
            pass
        self._style.configure("TNotebook", background=BG, borderwidth=0)
        self._style.configure("TNotebook.Tab", background=BG_ELEV, foreground=FG_DIM,
                              padding=[16, 8], font=("Segoe UI", 10, "bold"))
        self._style.map("TNotebook.Tab", background=[("selected", ACCENT)],
                        foreground=[("selected", "#ffffff")])
        self._style.configure("TFrame", background=BG)
        self._style.configure("TLabelframe", background=BG, foreground=FG)
        self._style.configure("TLabelframe.Label", background=BG, foreground=FG,
                              font=("Segoe UI", 10, "bold"))
        self._style.configure("Treeview", background=BG_ELEV, foreground=FG,
                              fieldbackground=BG_ELEV, rowheight=22,
                              font=("Consolas", 9))
        self._style.configure("Treeview.Heading", background=BG_INPUT, foreground=FG,
                              font=("Segoe UI", 9, "bold"))
        self._style.map("Treeview", background=[("selected", ACCENT)],
                        foreground=[("selected", "#ffffff")])

        # Thread -> UI plumbing. Tk is not thread-safe, so worker threads never
        # touch widgets or call self.after(); they put things on these queues and
        # the main thread drains them in _pump().
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

        # State
        self._log_lines: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._search_var = tk.StringVar()
        self._auto_scroll = tk.BooleanVar(value=True)
        self._browsers: dict[str, str] = {}
        self._browser_var = tk.StringVar()
        self._chunks_auto_refresh = tk.BooleanVar(value=True)
        self._chunks_filter_var = tk.StringVar()
        self._chunk_rows: list[tuple] = []
        self._chunk_error = ""
        self._chunk_busy = False
        self._status_busy = False

        # Process managers (log callback feeds the log tab)
        self.backend = ProcessManager("backend", self._append_log)
        self.frontend = ProcessManager("frontend", self._append_log)

        # Log tailer
        self.log_tailer = LogTailer(APP_LOG_PATH, self._append_log)

        self._build_ui()
        self._detect_and_set_browsers()

        if not VENV_FOUND:
            self._append_log(
                f"[system] WARNING: no venv found in {AMP_DIR / 'venv'}; "
                f"backend will use {VENV_PYTHON}")

        # Start tailing logs + timers
        self.log_tailer.start()
        self._pump()
        self._schedule_status()
        self._refresh_chunks()
        self._chunk_tick()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ===== Top control bar =====
        top = tk.Frame(self, bg=BG_ELEV, padx=16, pady=12)
        top.pack(fill=tk.X, padx=12, pady=(12, 0))

        # --- Title ---
        title = tk.Label(top, text="AMP v2", font=("Segoe UI", 20, "bold"),
                         bg=BG_ELEV, fg=ACCENT)
        title.grid(row=0, column=0, rowspan=2, padx=(0, 20), sticky=tk.W)

        # --- Backend section ---
        be_frame = tk.LabelFrame(top, text="  Backend (FastAPI :8000)  ",
                                 bg=BG_ELEV, fg=FG, font=("Segoe UI", 10, "bold"),
                                 padx=10, pady=8)
        be_frame.grid(row=0, column=1, padx=4, pady=2, sticky=tk.W)

        self.be_status = tk.Label(be_frame, text="● Stopped", font=("Segoe UI", 10, "bold"),
                                  bg=BG_ELEV, fg=FG_DIM)
        self.be_status.pack(side=tk.LEFT, padx=(0, 10))

        self._cbtn(be_frame, "Start", self._start_backend, SUCCESS)
        self._cbtn(be_frame, "Stop", self._stop_backend, ERROR_CLR)
        self._cbtn(be_frame, "Restart", self._restart_backend, WARNING)
        self._cbtn(be_frame, "Force Kill Port", self._kill_backend_port, ERROR_CLR)

        # --- Frontend section ---
        fe_frame = tk.LabelFrame(top, text="  Frontend (Vite :1420)  ",
                                 bg=BG_ELEV, fg=FG, font=("Segoe UI", 10, "bold"),
                                 padx=10, pady=8)
        fe_frame.grid(row=1, column=1, padx=4, pady=2, sticky=tk.W)

        self.fe_status = tk.Label(fe_frame, text="● Stopped", font=("Segoe UI", 10, "bold"),
                                  bg=BG_ELEV, fg=FG_DIM)
        self.fe_status.pack(side=tk.LEFT, padx=(0, 10))

        self._cbtn(fe_frame, "Start", self._start_frontend, SUCCESS)
        self._cbtn(fe_frame, "Stop", self._stop_frontend, ERROR_CLR)
        self._cbtn(fe_frame, "Restart", self._restart_frontend, WARNING)
        self._cbtn(fe_frame, "Force Kill Port", self._kill_frontend_port, ERROR_CLR)

        # --- Browser section ---
        br_frame = tk.LabelFrame(top, text="  Browser  ",
                                 bg=BG_ELEV, fg=FG, font=("Segoe UI", 10, "bold"),
                                 padx=10, pady=8)
        br_frame.grid(row=0, column=2, rowspan=2, padx=4, pady=2, sticky=tk.N)

        self.browser_combo = ttk.Combobox(br_frame, textvariable=self._browser_var,
                                          state="readonly", width=18,
                                          font=("Segoe UI", 9))
        self.browser_combo.pack(pady=(0, 6))

        self._cbtn(br_frame, "Open in Browser", self._open_browser, ACCENT)

        # ===== Tab zone =====
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 12))

        self._build_log_tab()
        self._build_api_tab()
        self._build_chunks_tab()

        # Refresh the chunk table immediately when its tab is opened
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _cbtn(self, parent: tk.Frame, text: str, command: Callable,
              color: str) -> tk.Button:
        """Create a coloured flat button."""
        fg = "#000000" if color == WARNING else "#ffffff"
        btn = tk.Button(
            parent, text=text, command=command,
            bg=color, fg=fg, font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2",
            activebackground=color, activeforeground=fg,
        )
        btn.pack(side=tk.LEFT, padx=2)
        return btn

    # ------------------------------------------------------------------
    # Tab 1 — Logs
    # ------------------------------------------------------------------

    def _build_log_tab(self) -> None:
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text="  Logs  ")

        # --- Toolbar ---
        toolbar = tk.Frame(tab, bg=BG_ELEV, padx=10, pady=6)
        toolbar.pack(fill=tk.X, padx=8, pady=(8, 0))

        tk.Label(toolbar, text="Search:", bg=BG_ELEV, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        search_entry = tk.Entry(toolbar, textvariable=self._search_var,
                                bg=BG_INPUT, fg=FG, insertbackground=FG,
                                font=("Consolas", 9), width=30,
                                relief=tk.FLAT, highlightthickness=1,
                                highlightbackground=FG_DIM, highlightcolor=ACCENT)
        search_entry.pack(side=tk.LEFT, padx=2)
        search_entry.bind("<KeyRelease>", lambda _e: self._refresh_log_display())

        tk.Button(toolbar, text="Clear Search", command=self._clear_search,
                  bg=BG_INPUT, fg=FG_DIM, font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=2, cursor="hand2"
                  ).pack(side=tk.LEFT, padx=4)

        tk.Checkbutton(toolbar, text="Auto-scroll", variable=self._auto_scroll,
                       bg=BG_ELEV, fg=FG_DIM, selectcolor=BG_INPUT,
                       activebackground=BG_ELEV, activeforeground=FG,
                       font=("Segoe UI", 9)
                       ).pack(side=tk.LEFT, padx=(12, 0))

        self.log_count_label = tk.Label(toolbar, text="0 lines", bg=BG_ELEV, fg=FG_DIM,
                                        font=("Segoe UI", 9))
        self.log_count_label.pack(side=tk.RIGHT)

        tk.Button(toolbar, text="Clear Log", command=self._clear_log,
                  bg=BG_INPUT, fg=FG_DIM, font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=2, cursor="hand2"
                  ).pack(side=tk.RIGHT, padx=4)

        tk.Button(toolbar, text="Reload All", command=self._reload_log_file,
                  bg=BG_INPUT, fg=FG_DIM, font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, pady=2, cursor="hand2"
                  ).pack(side=tk.RIGHT, padx=4)

        # --- Log text area ---
        text_frame = tk.Frame(tab, bg=BG)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.log_text = tk.Text(
            text_frame, bg=BG_ELEV, fg=FG_DIM,
            font=("Consolas", 9), insertbackground=FG,
            selectbackground=ACCENT, selectforeground="#ffffff",
            wrap=tk.NONE, state=tk.DISABLED,
            padx=6, pady=4,
        )
        log_scroll_y = ttk.Scrollbar(text_frame, command=self.log_text.yview)
        log_scroll_x = ttk.Scrollbar(text_frame, command=self.log_text.xview, orient=tk.HORIZONTAL)
        self.log_text.configure(yscrollcommand=log_scroll_y.set, xscrollcommand=log_scroll_x.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll_y.grid(row=0, column=1, sticky="ns")
        log_scroll_x.grid(row=1, column=0, sticky="ew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        # --- Configure syntax-highlight tags ---
        self.log_text.tag_configure("error", foreground=LOG_TAGS["error"])
        self.log_text.tag_configure("warning", foreground=LOG_TAGS["warning"])
        self.log_text.tag_configure("info", foreground=LOG_TAGS["info"])
        self.log_text.tag_configure("debug", foreground=LOG_TAGS["debug"])
        self.log_text.tag_configure("critical", foreground=LOG_TAGS["critical"])
        self.log_text.tag_configure("timestamp", foreground=LOG_TAGS["timestamp"])
        self.log_text.tag_configure("system", foreground=FG_DIM)
        # Configured last => highest priority, so highlights win over level colours
        self.log_text.tag_configure("search_hit", foreground=LOG_TAGS["search_hit"],
                                    background="#4a4400")

    # ------------------------------------------------------------------
    # Tab 2 — API Tester
    # ------------------------------------------------------------------

    def _build_api_tab(self) -> None:
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text="  API Request  ")

        # --- Quick-access buttons ---
        quick = tk.Frame(tab, bg=BG_ELEV, padx=10, pady=6)
        quick.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(quick, text="Quick:", bg=BG_ELEV, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        for label, method, path in [
            ("Health", "GET", "/api/health"),
            ("Playback State", "GET", "/api/stream/playback-state"),
            ("Cache Info", "GET", "/api/stream/cache-info"),
            ("Stream Logs", "GET", "/api/stream/logs?n=50"),
            ("Search", "GET", "/api/search?q=test&limit=3"),
            ("Auth Status", "GET", "/api/auth/status"),
        ]:
            tk.Button(quick, text=label,
                      command=lambda m=method, p=path: self._api_quick_fill(m, p),
                      bg=BG_INPUT, fg=FG, font=("Segoe UI", 8),
                      relief=tk.FLAT, padx=8, pady=3, cursor="hand2"
                      ).pack(side=tk.LEFT, padx=2)

        # --- Request builder ---
        req_frame = tk.LabelFrame(tab, text="  Request  ", bg=BG, fg=FG,
                                  font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        req_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        # Method + Path row
        row1 = tk.Frame(req_frame, bg=BG)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="Method:", bg=BG, fg=FG_DIM, font=("Segoe UI", 9)
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self.api_method = tk.StringVar(value="GET")
        method_combo = ttk.Combobox(row1, textvariable=self.api_method,
                                    values=["GET", "POST", "PUT", "DELETE", "PATCH"],
                                    state="readonly", width=8, font=("Segoe UI", 9))
        method_combo.pack(side=tk.LEFT, padx=2)

        tk.Label(row1, text="Path:", bg=BG, fg=FG_DIM, font=("Segoe UI", 9)
                 ).pack(side=tk.LEFT, padx=(12, 4))
        self.api_path = tk.StringVar(value="/api/health")
        path_entry = tk.Entry(row1, textvariable=self.api_path,
                              bg=BG_INPUT, fg=FG, insertbackground=FG,
                              font=("Consolas", 10), relief=tk.FLAT,
                              highlightthickness=1, highlightbackground=FG_DIM,
                              highlightcolor=ACCENT)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        path_entry.bind("<Return>", lambda _e: self._api_send())

        send_btn = tk.Button(row1, text="Send", command=self._api_send,
                             bg=ACCENT, fg="#ffffff", font=("Segoe UI", 10, "bold"),
                             relief=tk.FLAT, padx=16, pady=4, cursor="hand2")
        send_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Body row
        row2 = tk.Frame(req_frame, bg=BG)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Body (JSON, optional):", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(anchor=tk.W)
        self.api_body = tk.Text(row2, height=4, bg=BG_INPUT, fg=FG,
                                font=("Consolas", 9), insertbackground=FG,
                                relief=tk.FLAT, highlightthickness=1,
                                highlightbackground=FG_DIM, highlightcolor=ACCENT,
                                wrap=tk.NONE)
        self.api_body.pack(fill=tk.X, pady=(2, 0))

        # --- Response ---
        resp_frame = tk.LabelFrame(tab, text="  Response  ", bg=BG, fg=FG,
                                   font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        resp_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.api_status_label = tk.Label(resp_frame, text="—", bg=BG, fg=FG_DIM,
                                         font=("Segoe UI", 10, "bold"))
        self.api_status_label.pack(anchor=tk.W)

        # Scrollbars are packed BEFORE the expanding Text so they are not
        # squeezed out of view when the window is small.
        resp_scroll_x = ttk.Scrollbar(resp_frame, orient=tk.HORIZONTAL)
        resp_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        resp_scroll_y = ttk.Scrollbar(resp_frame)
        resp_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.api_response = tk.Text(resp_frame, bg=BG_ELEV, fg=FG,
                                    font=("Consolas", 9), insertbackground=FG,
                                    selectbackground=ACCENT, selectforeground="#ffffff",
                                    wrap=tk.NONE, state=tk.DISABLED,
                                    padx=6, pady=4)
        resp_scroll_y.configure(command=self.api_response.yview)
        resp_scroll_x.configure(command=self.api_response.xview)
        self.api_response.configure(yscrollcommand=resp_scroll_y.set,
                                    xscrollcommand=resp_scroll_x.set)
        self.api_response.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    # ------------------------------------------------------------------
    # Tab 3 — Chunk Database
    # ------------------------------------------------------------------

    def _build_chunks_tab(self) -> None:
        tab = tk.Frame(self.notebook, bg=BG)
        self._chunks_tab = tab
        self.notebook.add(tab, text="  Chunk Database  ")

        # --- Summary bar ---
        summary = tk.Frame(tab, bg=BG_ELEV, padx=10, pady=6)
        summary.pack(fill=tk.X, padx=8, pady=(8, 0))

        self.chunk_summary = tk.Label(summary, text="Loading…", bg=BG_ELEV, fg=FG_DIM,
                                      font=("Segoe UI", 9))
        self.chunk_summary.pack(side=tk.LEFT)

        tk.Button(summary, text="Refresh Now", command=self._refresh_chunks,
                  bg=BG_INPUT, fg=FG, font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=10, pady=2, cursor="hand2"
                  ).pack(side=tk.RIGHT, padx=2)

        tk.Checkbutton(summary, text="Auto-refresh (2s)", variable=self._chunks_auto_refresh,
                       bg=BG_ELEV, fg=FG_DIM, selectcolor=BG_INPUT,
                       activebackground=BG_ELEV, activeforeground=FG,
                       font=("Segoe UI", 9)
                       ).pack(side=tk.RIGHT, padx=(16, 8))

        # Filter
        filter_entry = tk.Entry(summary, textvariable=self._chunks_filter_var,
                                bg=BG_INPUT, fg=FG, insertbackground=FG,
                                font=("Consolas", 9), width=18,
                                relief=tk.FLAT, highlightthickness=1,
                                highlightbackground=FG_DIM, highlightcolor=ACCENT)
        filter_entry.pack(side=tk.RIGHT, padx=2)
        # Filtering only re-renders the rows we already have; no DB query needed
        filter_entry.bind("<KeyRelease>", lambda _e: self._render_chunk_tree())
        tk.Label(summary, text="Filter song:", bg=BG_ELEV, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(20, 4))

        # --- Treeview ---
        tree_frame = tk.Frame(tab, bg=BG)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        columns = ("song_id", "index", "status", "size", "duration", "file_path", "last_accessed")
        self.chunk_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        self.chunk_tree.heading("song_id", text="Song ID")
        self.chunk_tree.heading("index", text="Idx")
        self.chunk_tree.heading("status", text="Status")
        self.chunk_tree.heading("size", text="Size")
        self.chunk_tree.heading("duration", text="Duration")
        self.chunk_tree.heading("file_path", text="File Path")
        self.chunk_tree.heading("last_accessed", text="Last Accessed")

        self.chunk_tree.column("song_id", width=110, minwidth=80)
        self.chunk_tree.column("index", width=40, minwidth=30, anchor=tk.CENTER)
        self.chunk_tree.column("status", width=90, minwidth=70, anchor=tk.CENTER)
        self.chunk_tree.column("size", width=80, minwidth=60, anchor=tk.E)
        self.chunk_tree.column("duration", width=70, minwidth=50, anchor=tk.E)
        self.chunk_tree.column("file_path", width=280, minwidth=150)
        self.chunk_tree.column("last_accessed", width=140, minwidth=100)

        tree_scroll_y = ttk.Scrollbar(tree_frame, command=self.chunk_tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, command=self.chunk_tree.xview,
                                      orient=tk.HORIZONTAL)
        self.chunk_tree.configure(yscrollcommand=tree_scroll_y.set,
                                  xscrollcommand=tree_scroll_x.set)

        self.chunk_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Status colour tags
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

    def _frontend_cmd(self) -> list[str]:
        return [NPM_CMD, "run", "dev", "--", "--port", str(FRONTEND_PORT),
                "--host", "127.0.0.1"]

    def _launch(self, pm: ProcessManager, cmd: list[str], cwd: str, port: int) -> None:
        def work() -> None:
            if not pm.is_running() and is_port_open(port):
                self._append_log(
                    f"[system] Port {port} is already in use by another process — "
                    f"use 'Force Kill Port' first")
                return
            pm.start(cmd, cwd)
        threading.Thread(target=work, daemon=True).start()

    def _relaunch(self, pm: ProcessManager, cmd: list[str], cwd: str, port: int) -> None:
        def work() -> None:
            pm.stop(quiet=True)
            if not wait_port_free(port):
                self._append_log(
                    f"[system] Port {port} is still in use — use 'Force Kill Port', then Start")
                return
            pm.start(cmd, cwd)
        threading.Thread(target=work, daemon=True).start()

    def _start_backend(self) -> None:
        self._launch(self.backend, self._backend_cmd(), str(AMP_DIR), BACKEND_PORT)

    def _stop_backend(self) -> None:
        threading.Thread(target=self.backend.stop, daemon=True).start()

    def _restart_backend(self) -> None:
        self._relaunch(self.backend, self._backend_cmd(), str(AMP_DIR), BACKEND_PORT)

    def _kill_backend_port(self) -> None:
        self._kill_port_async(BACKEND_PORT)

    def _start_frontend(self) -> None:
        self._launch(self.frontend, self._frontend_cmd(), str(FRONTEND_DIR), FRONTEND_PORT)

    def _stop_frontend(self) -> None:
        threading.Thread(target=self.frontend.stop, daemon=True).start()

    def _restart_frontend(self) -> None:
        self._relaunch(self.frontend, self._frontend_cmd(), str(FRONTEND_DIR), FRONTEND_PORT)

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
            self._post(lambda: self._apply_status(be, fe))
        finally:
            self._status_busy = False

    def _apply_status(self, be: tuple, fe: tuple) -> None:
        for label, (running, pid, port_open) in ((self.be_status, be), (self.fe_status, fe)):
            if running and port_open:
                label.config(text=f"● Running (PID {pid})", fg=SUCCESS)
            elif running:
                label.config(text=f"● Starting… (PID {pid})", fg=WARNING)
            elif port_open:
                label.config(text="● Port in use (external)", fg=WARNING)
            else:
                label.config(text="● Stopped", fg=FG_DIM)

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

        if self._search_var.get().strip():
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

    def _text_line_count(self) -> int:
        # The widget always ends with an implicit newline, hence the -1.
        return int(self.log_text.index("end-1c").split(".")[0]) - 1

    def _trim_log_widget(self) -> None:
        n = self._text_line_count()
        if n > MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{n - MAX_LOG_LINES + 1}.0")

    def _insert_log_line(self, line: str, pattern: Optional["re.Pattern[str]"]) -> None:
        """Append one line (widget must be in NORMAL state), colour it, mark search hits."""
        tag = self._classify_log_line(line)
        self.log_text.insert(tk.END, line + "\n", (tag,) if tag else ())
        if pattern is not None:
            ln = self._text_line_count()  # the line we just inserted is the last one
            for m in pattern.finditer(line):
                self.log_text.tag_add("search_hit", f"{ln}.{m.start()}", f"{ln}.{m.end()}")

    def _refresh_log_display(self) -> None:
        """Re-render the whole log Text widget with the current search filter."""
        search = self._search_var.get().strip()
        pattern = re.compile(re.escape(search), re.IGNORECASE) if search else None
        lines = list(self._log_lines)
        display = [l for l in lines if pattern.search(l)] if pattern else lines

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for line in display:
            self._insert_log_line(line, pattern)
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

    def _chunks_tab_visible(self) -> bool:
        try:
            return self.notebook.select() == str(self._chunks_tab)
        except tk.TclError:
            return False

    def _on_tab_changed(self, _event=None) -> None:
        if self._chunks_tab_visible():
            self._refresh_chunks()

    def _chunk_tick(self) -> None:
        # Always reschedule (the old version stopped forever once auto-refresh
        # was unticked, so re-ticking it did nothing). Skip the DB read when the
        # tab isn't visible.
        if self._chunks_auto_refresh.get() and self._chunks_tab_visible():
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