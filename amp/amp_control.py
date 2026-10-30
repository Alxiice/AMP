#!/usr/bin/env python3
"""AMP v2 Control Panel — tkinter GUI for managing backend and frontend.

Double-click to run. Provides:
  - Start / Stop / Restart the FastAPI backend (port 8000)
  - Force-kill whatever process is using port 8000
  - Start / Stop / Restart the Vite frontend dev server (port 1420)
  - Force-kill whatever process is using port 1420
  - View backend health status
  - View recent backend log lines

Usage:
    python amp_control.py
    # or double-click the file in Explorer
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

# --- Paths ---

AMP_DIR = Path(__file__).resolve().parent
VENV_PYTHON = AMP_DIR / "venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = AMP_DIR / "venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)  # fallback to system python

FRONTEND_DIR = AMP_DIR / "frontend"
NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"

BACKEND_PORT = 8000
FRONTEND_PORT = 1420


# --- Port utilities ---

def find_pid_on_port(port: int) -> Optional[int]:
    """Find the PID of the process listening on the given port."""
    try:
        if os.name == "nt":
            # Windows: use netstat
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, timeout=5,
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


def kill_pid(pid: int) -> bool:
    """Kill a process by PID. Returns True on success."""
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=10,
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
    """Force-kill whatever is on the given port. Returns a status message."""
    # First, try to find a listening process
    pid = find_pid_on_port(port)
    if pid is not None:
        if kill_pid(pid):
            # Wait for the port to be released
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
    """Check if something is accepting connections on the port (socket test)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_port_listening(port: int) -> bool:
    """Check if something is listening on the port (netstat/lsof test)."""
    return find_pid_on_port(port) is not None


def find_any_pid_on_port(port: int) -> Optional[int]:
    """Find the PID of any process using the given port (not just listening)."""
    try:
        if os.name == "nt":
            # Windows: use netstat - find any TCP connection with this port
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, timeout=5,
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


# --- Process manager ---

class ProcessManager:
    """Manages a single subprocess with start/stop/restart."""

    def __init__(self, name: str, log_callback) -> None:
        self.name = name
        self.process: Optional[subprocess.Popen] = None
        self._log_callback = log_callback
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def start(self, cmd: list, cwd: str) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                self._log(f"[{self.name}] Already running (PID {self.process.pid})")
                return
            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                )
                self._log(f"[{self.name}] Started (PID {self.process.pid})")
                # Reader thread
                threading.Thread(target=self._read_output, daemon=True).start()
            except FileNotFoundError:
                self._log(f"[{self.name}] ERROR: command not found: {cmd[0]}")
            except Exception as e:
                self._log(f"[{self.name}] ERROR: {e}")

    def stop(self) -> None:
        with self._lock:
            if not self.process or self.process.poll() is not None:
                self._log(f"[{self.name}] Not running")
                self.process = None
                return
            pid = self.process.pid
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True, timeout=5,
                    )
                else:
                    os.killpg(os.getpgid(pid), 9)
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self._log(f"[{self.name}] Stopped (PID {pid})")
            self.process = None

    def restart(self, cmd: list, cwd: str) -> None:
        self.stop()
        time.sleep(0.5)
        self.start(cmd, cwd)

    def _read_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        try:
            for line in self.process.stdout:
                self._log(f"[{self.name}] {line.rstrip()}")
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        self._log_callback(msg)


# --- GUI ---

class ControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AMP v2 — Control Panel")
        self.geometry("700x550")
        self.minsize(600, 450)

        # Dark theme colors
        self.bg = "#0f0f0f"
        self.bg_elev = "#1a1a1a"
        self.fg = "#f1f1f1"
        self.fg_dim = "#aaaaaa"
        self.accent = "#ff0033"
        self.success = "#1db954"
        self.warning = "#f0a500"
        self.error = "#e74c3c"

        self.configure(bg=self.bg)

        self.log_lines: list[str] = []

        # Process managers
        self.backend = ProcessManager("backend", self._append_log)
        self.frontend = ProcessManager("frontend", self._append_log)

        self._build_ui()
        self._start_status_timer()

    def _build_ui(self) -> None:
        # --- Title ---
        title = tk.Label(
            self, text="AMP v2 Control Panel",
            font=("Segoe UI", 18, "bold"),
            bg=self.bg, fg=self.accent,
        )
        title.pack(pady=(16, 4))

        subtitle = tk.Label(
            self, text=f"Backend port {BACKEND_PORT}  ·  Frontend port {FRONTEND_PORT}",
            font=("Segoe UI", 10),
            bg=self.bg, fg=self.fg_dim,
        )
        subtitle.pack(pady=(0, 12))

        # --- Backend section ---
        backend_frame = self._section_frame("Backend (FastAPI — port 8000)")
        self.backend_status = tk.Label(
            backend_frame, text="● Stopped",
            font=("Segoe UI", 10, "bold"),
            bg=self.bg_elev, fg=self.fg_dim,
        )
        self.backend_status.pack(side=tk.LEFT, padx=(0, 12))

        self._btn(backend_frame, "Start", self._start_backend, self.success)
        self._btn(backend_frame, "Stop", self._stop_backend, self.error)
        self._btn(backend_frame, "Restart", self._restart_backend, self.warning)
        self._btn(backend_frame, "Force Kill Port", self._kill_backend_port, self.error)
        backend_frame.pack(fill=tk.X, padx=20, pady=(0, 8))

        # --- Frontend section ---
        frontend_frame = self._section_frame("Frontend (Vite dev — port 1420)")
        self.frontend_status = tk.Label(
            frontend_frame, text="● Stopped",
            font=("Segoe UI", 10, "bold"),
            bg=self.bg_elev, fg=self.fg_dim,
        )
        self.frontend_status.pack(side=tk.LEFT, padx=(0, 12))

        self._btn(frontend_frame, "Start", self._start_frontend, self.success)
        self._btn(frontend_frame, "Stop", self._stop_frontend, self.error)
        self._btn(frontend_frame, "Restart", self._restart_frontend, self.warning)
        self._btn(frontend_frame, "Force Kill Port", self._kill_frontend_port, self.error)
        frontend_frame.pack(fill=tk.X, padx=20, pady=(0, 8))

        # --- Health check ---
        health_frame = self._section_frame("Health")
        self.health_label = tk.Label(
            health_frame, text="Checking...",
            font=("Segoe UI", 10),
            bg=self.bg_elev, fg=self.fg_dim,
        )
        self.health_label.pack(side=tk.LEFT)
        self._btn(health_frame, "Check Now", self._check_health, self.accent)
        health_frame.pack(fill=tk.X, padx=20, pady=(0, 8))

        # --- Log ---
        log_label = tk.Label(
            self, text="Log",
            font=("Segoe UI", 11, "bold"),
            bg=self.bg, fg=self.fg,
        )
        log_label.pack(anchor=tk.W, padx=20, pady=(8, 4))

        self.log_text = scrolledtext.ScrolledText(
            self,
            height=14,
            bg=self.bg_elev,
            fg=self.fg_dim,
            font=("Consolas", 9),
            insertbackground=self.fg,
            selectbackground=self.accent,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 8))

        # Clear log button
        clear_btn = tk.Button(
            self, text="Clear Log",
            command=self._clear_log,
            bg=self.bg_elev, fg=self.fg_dim,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=12, pady=4,
        )
        clear_btn.pack(pady=(0, 12))

    def _section_frame(self, title: str) -> tk.Frame:
        frame = tk.Frame(self, bg=self.bg_elev, padx=12, pady=10)
        label = tk.Label(
            frame, text=title,
            font=("Segoe UI", 11, "bold"),
            bg=self.bg_elev, fg=self.fg,
        )
        label.pack(side=tk.LEFT, padx=(0, 16))
        return frame

    def _btn(self, parent: tk.Frame, text: str, command, color: str) -> tk.Button:
        btn = tk.Button(
            parent, text=text, command=command,
            bg=color, fg="#ffffff" if color != self.warning else "#000000",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=12, pady=4,
            cursor="hand2",
        )
        btn.pack(side=tk.LEFT, padx=2)
        return btn

    # --- Backend actions ---

    def _backend_cmd(self) -> list:
        return [
            str(VENV_PYTHON), "-m", "backend.main",
            "--host", "127.0.0.1",
            "--port", str(BACKEND_PORT),
        ]

    def _start_backend(self) -> None:
        threading.Thread(
            target=self.backend.start,
            args=(self._backend_cmd(), str(AMP_DIR)),
            daemon=True,
        ).start()

    def _stop_backend(self) -> None:
        threading.Thread(target=self.backend.stop, daemon=True).start()

    def _restart_backend(self) -> None:
        threading.Thread(
            target=self.backend.restart,
            args=(self._backend_cmd(), str(AMP_DIR)),
            daemon=True,
        ).start()

    def _kill_backend_port(self) -> None:
        def _kill():
            msg = force_kill_port(BACKEND_PORT)
            self._append_log(f"[system] {msg}")
        threading.Thread(target=_kill, daemon=True).start()

    # --- Frontend actions ---

    def _frontend_cmd(self) -> list:
        return [NPM_CMD, "run", "dev", "--", "--port", str(FRONTEND_PORT), "--host", "127.0.0.1"]

    def _start_frontend(self) -> None:
        threading.Thread(
            target=self.frontend.start,
            args=(self._frontend_cmd(), str(FRONTEND_DIR)),
            daemon=True,
        ).start()

    def _stop_frontend(self) -> None:
        threading.Thread(target=self.frontend.stop, daemon=True).start()

    def _restart_frontend(self) -> None:
        threading.Thread(
            target=self.frontend.restart,
            args=(self._frontend_cmd(), str(FRONTEND_DIR)),
            daemon=True,
        ).start()

    def _kill_frontend_port(self) -> None:
        def _kill():
            msg = force_kill_port(FRONTEND_PORT)
            self._append_log(f"[system] {msg}")
        threading.Thread(target=_kill, daemon=True).start()

    # --- Health check ---

    def _check_health(self) -> None:
        def _check():
            try:
                import urllib.request
                req = urllib.request.Request(f"http://127.0.0.1:{BACKEND_PORT}/api/health")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = resp.read().decode()
                    self.after(0, lambda: self.health_label.config(
                        text=f"OK — {data[:120]}", fg=self.success,
                    ))
            except Exception as e:
                self.after(0, lambda: self.health_label.config(
                    text=f"Unreachable: {e}", fg=self.error,
                ))
        threading.Thread(target=_check, daemon=True).start()

    # --- Status timer ---

    def _start_status_timer(self) -> None:
        self._update_status()
        self.after(2000, self._start_status_timer)

    def _update_status(self) -> None:
        # Backend
        if self.backend.is_running():
            self.backend_status.config(text=f"● Running (PID {self.backend.process.pid if self.backend.process else '?'})", fg=self.success)
        elif is_port_listening(BACKEND_PORT):
            self.backend_status.config(text="● Port in use (external)", fg=self.warning)
        else:
            self.backend_status.config(text="● Stopped", fg=self.fg_dim)

        # Frontend
        if self.frontend.is_running():
            self.frontend_status.config(text=f"● Running (PID {self.frontend.process.pid if self.frontend.process else '?'})", fg=self.success)
        elif is_port_listening(FRONTEND_PORT):
            self.frontend_status.config(text="● Port in use (external)", fg=self.warning)
        else:
            self.frontend_status.config(text="● Stopped", fg=self.fg_dim)

    # --- Log ---

    def _append_log(self, msg: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        self.log_lines.append(line)
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]

        def _update():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, line + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.after(0, _update)

    def _clear_log(self) -> None:
        self.log_lines.clear()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)


def main() -> None:
    app = ControlPanel()
    app.mainloop()


if __name__ == "__main__":
    main()
