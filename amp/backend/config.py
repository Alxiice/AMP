"""Application configuration via pydantic-settings.

Creates runtime directories on import. All settings are read from environment
variables (or .env) with the defaults defined here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Locate the amp/ project root (parent of the backend/ package)."""
    # backend/config.py -> backend/ -> amp/
    return Path(__file__).resolve().parent.parent


# Private path attributes managed by Settings.configure_paths()
_PATH_ATTRS = ("_root", "_cache_dir", "_segments_dir", "_logs_dir", "_db_file")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Server ---
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    AUTH_TOKEN: Optional[str] = None  # optional; if set, all requests require Bearer token
    DEBUG: bool = False

    # --- Paths (relative to project root unless absolute) ---
    AMP_DIR: str = ".amp"
    DB_PATH: str = "userdb.sqlite"

    # --- Cache ---
    CACHE_MAX_SIZE_MB: int = 500
    SEGMENT_BUFFER_AHEAD_SEC: int = 30
    SEGMENT_BEHIND: int = 2
    SEGMENT_TARGET_SEC: int = 5  # progressive fallback segment size

    # --- Streaming ---
    STREAM_FORMAT: str = "140"  # itag; 140 (AAC/MP4) or 251 (Opus/WebM)
    # yt-dlp player clients, tried in order; "default" = yt-dlp's own choice.
    # visionos (2026-10-31): itag 140, no available_at delay, but no cookie support,
    # so it runs anonymously. default (tv_samsung): itag 140 after a ~5 s delay.
    # Env override is JSON: YTDLP_PLAYER_CLIENTS='["default"]'
    YTDLP_PLAYER_CLIENTS: List[str] = ["visionos", "default"]
    DOWNLOAD_WORKERS: int = 4
    HTTP_TIMEOUT_CONNECT_S: float = 5.0
    HTTP_TIMEOUT_READ_S: float = 30.0
    MAX_RETRIES: int = 3
    SEGMENT_SYNC_TIMEOUT_S: float = 15.0  # /audio waits this long for a segment before failing

    # --- Computed paths (set by configure_paths) ---
    # Private attributes: never monkeypatch these directly (pydantic 2.14's
    # private-attr storage breaks monkeypatch.undo). Use configure_paths /
    # snapshot_paths / restore_paths instead.
    _root: Path = Path(".")
    _cache_dir: Path = Path(".")
    _segments_dir: Path = Path(".")
    _logs_dir: Path = Path(".")
    _db_file: Path = Path(".")

    def model_post_init(self, __context) -> None:
        self.configure_paths()

    def configure_paths(self, data_dir: Path | None = None, db_file: Path | None = None) -> None:
        """(Re)compute cache/segments/logs/db paths and create the directories."""
        self._root = _project_root()
        amp = Path(data_dir) if data_dir is not None else self._root / self.AMP_DIR
        self._cache_dir = amp / "cache"
        self._segments_dir = self._cache_dir / "segments"
        self._logs_dir = amp / "logs"
        if db_file is None:
            db_path = Path(self.DB_PATH)
            db_file = db_path if db_path.is_absolute() else self._root / db_path
        self._db_file = Path(db_file)

        for d in (self._cache_dir, self._segments_dir, self._logs_dir, self._db_file.parent):
            d.mkdir(parents=True, exist_ok=True)

    def snapshot_paths(self) -> Dict[str, Path]:
        """Return the current computed paths, for a later restore_paths()."""
        return {name: getattr(self, name) for name in _PATH_ATTRS}

    def restore_paths(self, snapshot: Dict[str, Path]) -> None:
        """Restore computed paths captured by snapshot_paths()."""
        for name in _PATH_ATTRS:
            setattr(self, name, snapshot[name])

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def segments_dir(self) -> Path:
        return self._segments_dir

    @property
    def logs_dir(self) -> Path:
        return self._logs_dir

    @property
    def db_file(self) -> Path:
        return self._db_file

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self._db_file}"

    @property
    def credential_store_path(self) -> Path:
        return self._cache_dir / "ytm_session.json"

    @property
    def cache_max_bytes(self) -> int:
        return self.CACHE_MAX_SIZE_MB * 1024 * 1024


# Module-level singleton — imported everywhere as `from backend.config import settings`
settings = Settings()
