"""Phase 6: CLI options, data dir, PID file, parent watch, log rotation, socket binding."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from backend import lifecycle
from backend.config import settings

AMP_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture()
def restore_settings(monkeypatch):
    """apply_args() changes paths and server fields: put everything back afterwards."""
    snapshot = settings.snapshot_paths()
    for name in ("AUTH_TOKEN", "HOST", "PORT", "DEBUG"):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    yield
    settings.restore_paths(snapshot)


class TestArgs:
    def test_main_data_dir_arg(self, tmp_path, restore_settings):
        from backend import main

        args = main.parse_args(["--data-dir", str(tmp_path), "--port", "0", "--parent-watch"])
        main.apply_args(args)
        assert args.parent_watch is True
        assert settings.PORT == 0
        assert settings.data_dir == tmp_path.resolve()
        assert settings.cache_dir.is_relative_to(tmp_path.resolve())
        assert settings.logs_dir.is_dir()
        assert settings.db_file == tmp_path.resolve() / "userdb.sqlite"
        assert settings.credential_store_path.is_relative_to(tmp_path.resolve())
        assert settings.pid_file == tmp_path.resolve() / "backend.pid"

    def test_defaults_keep_checkout_paths(self, restore_settings):
        from backend import main

        before = settings.snapshot_paths()
        args = main.parse_args([])
        main.apply_args(args)
        assert args.data_dir is None and args.parent_watch is False
        assert settings.snapshot_paths() == before

    def test_frozen_default_is_app_data_dir(self, tmp_path, monkeypatch, restore_settings):
        """F16: the sidecar must not keep data next to __file__ (PyInstaller's temp dir)."""
        import backend.config as config

        monkeypatch.setattr(config, "is_frozen", lambda: True)
        monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path / "com.amp.v2")
        settings.configure_paths()
        assert settings.data_dir == tmp_path / "com.amp.v2"
        assert settings.db_file == tmp_path / "com.amp.v2" / "userdb.sqlite"

    def test_app_data_dir_uses_identifier(self):
        from backend.config import APP_IDENTIFIER, app_data_dir

        assert app_data_dir().name == APP_IDENTIFIER == "com.amp.v2"


class TestPidFile:
    def test_pid_file_written(self, tmp_path):
        path = tmp_path / "backend.pid"
        lifecycle.write_pid_file(path, 8123)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        assert data["port"] == 8123
        assert lifecycle.read_pid_file(path)["pid"] == os.getpid()

    def test_remove_keeps_foreign_pid_file(self, tmp_path):
        path = tmp_path / "backend.pid"
        path.write_text(json.dumps({"pid": os.getpid() + 1, "port": 1}), encoding="utf-8")
        lifecycle.remove_pid_file(path)
        assert path.exists()
        lifecycle.write_pid_file(path, 1)
        lifecycle.remove_pid_file(path)
        assert not path.exists()

    @pytest.mark.parametrize("content", ["", "not json", "[]", '{"pid": "x", "port": 1}'])
    def test_junk_pid_file_ignored(self, tmp_path, content):
        path = tmp_path / "backend.pid"
        path.write_text(content, encoding="utf-8")
        assert lifecycle.read_pid_file(path) is None
        assert lifecycle.find_running_backend(path) is None

    def test_live_backend_detected(self, tmp_path, monkeypatch):
        path = tmp_path / "backend.pid"
        path.write_text(json.dumps({"pid": 4242, "port": 8123}), encoding="utf-8")
        monkeypatch.setattr(lifecycle, "probe_backend", lambda port: {"app": "AMP v2", "pid": 4242})
        assert lifecycle.find_running_backend(path) == {"pid": 4242, "port": 8123}

    def test_stale_pid_file_ignored(self, tmp_path, monkeypatch):
        """Recorded port now answers for another process (or nothing): not a live backend."""
        path = tmp_path / "backend.pid"
        path.write_text(json.dumps({"pid": 4242, "port": 8123}), encoding="utf-8")
        monkeypatch.setattr(lifecycle, "probe_backend", lambda port: {"app": "AMP v2", "pid": 1})
        assert lifecycle.find_running_backend(path) is None
        monkeypatch.setattr(lifecycle, "probe_backend", lambda port: None)
        assert lifecycle.find_running_backend(path) is None

    def test_probe_ignores_non_amp_server(self):
        assert lifecycle.probe_backend(_free_port(), timeout=0.2) is None


class TestHealthIdentity:
    def test_health_reports_app_and_pid(self, client_no_auth):
        body = client_no_auth.get("/api/health").json()
        assert body["app"] == lifecycle.APP_NAME
        assert body["pid"] == os.getpid()


class TestBindSocket:
    def test_port_zero_picks_free_port(self):
        sock = lifecycle.bind_socket("127.0.0.1", 0)
        try:
            assert sock.getsockname()[1] > 0
        finally:
            sock.close()

    def test_port_in_use_raises(self):
        first = lifecycle.bind_socket("127.0.0.1", 0)
        first.listen()
        try:
            with pytest.raises(OSError):
                lifecycle.bind_socket("127.0.0.1", first.getsockname()[1])
        finally:
            first.close()


class TestParentWatch:
    def test_eof_calls_on_exit(self):
        r, w = os.pipe()
        called = []
        thread = lifecycle.watch_parent(lambda: called.append(True), fd=r)
        os.close(w)
        thread.join(timeout=3)
        os.close(r)
        assert called == [True]

    def test_exit_line_calls_on_exit(self):
        r, w = os.pipe()
        called = []
        thread = lifecycle.watch_parent(lambda: called.append(True), fd=r)
        os.write(w, b"exit\n")
        thread.join(timeout=3)
        os.close(w)
        os.close(r)
        assert called == [True]

    def test_invalid_fd_not_watched(self):
        r, w = os.pipe()
        os.close(r)
        os.close(w)
        assert lifecycle.watch_parent(lambda: None, fd=r) is None


@pytest.mark.parametrize("how", ["eof", "exit"])
def test_parent_watch_exits_on_eof(tmp_path, how):
    """Real backend process: closing its stdin (the parent died) ends it within 3 s."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.main", "--parent-watch", "--port", "0", "--data-dir", str(tmp_path)],
        cwd=AMP_ROOT, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        info = _wait_for_backend(tmp_path / "backend.pid", proc, timeout=60)
        assert info["port"] > 0
        if how == "exit":
            proc.stdin.write(b"exit\n")
            proc.stdin.flush()
        else:
            proc.stdin.close()
        start = time.monotonic()
        proc.wait(timeout=3)
        assert time.monotonic() - start < 3
        assert lifecycle.probe_backend(info["port"], timeout=0.5) is None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_rotating_handlers(temp_dirs):
    import backend.utils.logger as logger_mod

    root = logging.getLogger()
    before = list(root.handlers)
    was_configured = logger_mod._configured
    logger_mod._configured = False
    try:
        logger_mod.configure_logging()
        added = [h for h in root.handlers if h not in before]
        rotating = [h for h in added if isinstance(h, RotatingFileHandler)]
        names = sorted(Path(h.baseFilename).name for h in rotating)
        assert names == ["app.log", "streaming.log"]
        assert all(h.maxBytes == logger_mod.LOG_MAX_BYTES and h.backupCount == logger_mod.LOG_BACKUP_COUNT
                   for h in rotating)
        assert not any(type(h) is logging.StreamHandler for h in added)  # console only on request
    finally:
        for h in [h for h in root.handlers if h not in before]:
            root.removeHandler(h)
            h.close()
        logger_mod._configured = was_configured


# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_backend(pid_file: Path, proc: subprocess.Popen, timeout: float) -> dict:
    """PID file written and /api/health answering with the same pid."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert proc.poll() is None, f"backend exited early with {proc.returncode}"
        info = lifecycle.read_pid_file(pid_file)
        if info:
            health = lifecycle.probe_backend(info["port"], timeout=0.5)
            if health and health["pid"] == info["pid"]:
                return info
        time.sleep(0.2)
    raise AssertionError("backend did not start")
