"""Unit tests for config.py and database/models.py."""

import pytest


class TestConfig:
    def test_defaults(self):
        from backend.config import Settings
        s = Settings()
        assert s.HOST == "127.0.0.1"
        assert s.PORT == 8000
        assert s.AUTH_TOKEN is None  # optional — open mode by default
        assert s.STREAM_FORMAT == "140"
        assert s.DOWNLOAD_WORKERS == 4
        assert s.CACHE_MAX_SIZE_MB == 500
        assert s.SEGMENT_BUFFER_AHEAD_SEC == 30
        assert s.SEGMENT_BEHIND == 2
        assert s.MAX_RETRIES == 3

    def test_dirs_created(self, tmp_path, monkeypatch):
        from backend.config import Settings
        s = Settings(AMP_DIR=str(tmp_path / ".amp"), DB_PATH=str(tmp_path / "test.sqlite"))
        assert s.cache_dir.exists()
        assert s.segments_dir.exists()
        assert s.logs_dir.exists()

    def test_cache_max_bytes(self):
        from backend.config import settings
        assert settings.cache_max_bytes == 500 * 1024 * 1024

    def test_db_url(self):
        from backend.config import settings
        assert settings.db_url.startswith("sqlite:///")

    def test_paths_survive_override_restore(self, tmp_path):
        """Regression (F1): overriding and restoring paths must not lose them.

        monkeypatch.setattr on pydantic private attrs deleted them on undo,
        breaking every later test that touched settings.
        """
        from backend.config import settings
        original = settings.snapshot_paths()

        for i in range(2):
            snap = settings.snapshot_paths()
            settings.configure_paths(data_dir=tmp_path / f"amp{i}", db_file=tmp_path / f"db{i}.sqlite")
            assert settings.cache_dir == tmp_path / f"amp{i}" / "cache"
            assert settings.segments_dir.exists()
            assert settings.db_file == tmp_path / f"db{i}.sqlite"
            settings.restore_paths(snap)

        assert settings.snapshot_paths() == original
        assert settings.cache_dir == original["_cache_dir"]
        assert settings.cache_dir.exists()

    def test_temp_dirs_restores_paths(self, temp_dirs):
        """temp_dirs redirects to tmp_path (its teardown is covered by the test above)."""
        from backend.config import settings
        assert settings.cache_dir == temp_dirs["cache_dir"]
        assert temp_dirs["tmp_path"] in settings.cache_dir.parents


class TestModels:
    def test_song_model(self, temp_dirs):
        from backend.database.models import Song
        from backend.database.session import session_scope

        with session_scope() as session:
            song = Song(id="dQw4w9WgXcQ", title="Test", artist="Artist", duration_ms=212000)
            session.add(song)

        with session_scope() as session:
            loaded = session.get(Song, "dQw4w9WgXcQ")
            assert loaded is not None
            assert loaded.title == "Test"
            assert loaded.duration_ms == 212000

    def test_segment_model(self, temp_dirs):
        from backend.database.models import Segment
        from backend.database.session import session_scope

        with session_scope() as session:
            seg = Segment(
                song_id="dQw4w9WgXcQ", index=0,
                byte_start=624, byte_end=50623, size_bytes=50000,
                duration_ms=5000, status="downloaded",
                file_path="/tmp/test/0000.bin",
            )
            session.add(seg)

        with session_scope() as session:
            loaded = session.get(Segment, ("dQw4w9WgXcQ", 0))
            assert loaded is not None
            assert loaded.byte_start == 624
            assert loaded.status == "downloaded"

    def test_liked_song_model(self, temp_dirs):
        from backend.database.models import Song, LikedSong
        from backend.database.session import session_scope

        with session_scope() as session:
            song = Song(id="dQw4w9WgXcQ", title="Test")
            session.add(song)
            liked = LikedSong(song_id="dQw4w9WgXcQ")
            session.add(liked)

        with session_scope() as session:
            loaded = session.get(LikedSong, "dQw4w9WgXcQ")
            assert loaded is not None
            assert loaded.song.title == "Test"

    def test_playlist_models(self, temp_dirs):
        from backend.database.models import Song, Playlist, PlaylistSong
        from backend.database.session import session_scope

        with session_scope() as session:
            pl = Playlist(id="PL123", name="My Playlist", song_count=1)
            song = Song(id="dQw4w9WgXcQ", title="Test")
            ps = PlaylistSong(playlist_id="PL123", song_id="dQw4w9WgXcQ", position=0)
            session.add_all([pl, song, ps])

        with session_scope() as session:
            loaded = session.get(Playlist, "PL123")
            assert loaded.name == "My Playlist"
