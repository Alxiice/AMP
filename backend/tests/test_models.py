"""
Test Database Models
=====================
Unit tests for SQLAlchemy models.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, Song, Playlist, Queue, PlaybackState
from backend.database.session import init_userdb, init_playdb
from backend.config import USERDB_PATH, PLAYDB_PATH


@pytest.fixture(scope="module")
def test_userdb():
    """Create a test userdb in memory."""
    # Use in-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    def get_session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    yield get_session
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def test_playdb():
    """Create a test playdb in memory."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    def get_session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    yield get_session
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)


class TestSongModel:
    """Tests for Song model."""
    
    def test_create_song(self, test_userdb):
        """Test creating a song."""
        session = next(test_userdb())
        
        song = Song(
            id="dQw4w9WgXcQ",
            title="Never Gonna Give You Up",
            artist="Rick Astley",
            album="Whenever You Need Somebody",
            duration_ms=213000,
        )
        session.add(song)
        session.commit()
        session.refresh(song)
        
        # Verify
        fetched = session.query(Song).filter(Song.id == "dQw4w9WgXcQ").first()
        assert fetched is not None
        assert fetched.title == "Never Gonna Give You Up"
        assert fetched.artist == "Rick Astley"
        assert fetched.duration_ms == 213000


class TestPlaylistModel:
    """Tests for Playlist model."""
    
    def test_create_playlist(self, test_userdb):
        """Test creating a playlist."""
        session = next(test_userdb())
        
        playlist = Playlist(
            id="PL12345",
            name="My Playlist",
            owner="user1",
            is_youtube=True,
        )
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
        
        # Verify
        fetched = session.query(Playlist).filter(Playlist.id == "PL12345").first()
        assert fetched is not None
        assert fetched.name == "My Playlist"
        assert fetched.owner == "user1"


class TestQueueModel:
    """Tests for Queue model."""
    
    def test_create_queue(self, test_userdb):
        """Test creating a queue."""
        session = next(test_userdb())
        
        queue = Queue(
            id="queue1",
            name="My Queue",
            is_infinite=False,
        )
        session.add(queue)
        session.commit()
        session.refresh(queue)
        
        # Verify
        fetched = session.query(Queue).filter(Queue.id == "queue1").first()
        assert fetched is not None
        assert fetched.name == "My Queue"
        assert fetched.is_infinite is False


class TestPlaybackStateModel:
    """Tests for PlaybackState model."""
    
    def test_create_playback_state(self, test_playdb):
        """Test creating playback state."""
        session = next(test_playdb())
        
        state = PlaybackState(
            current_queue_id="queue1",
            current_song_id="song1",
            current_time_ms=10000,
            is_playing=True,
            volume=0.8,
            repeat_mode="all",
            shuffle=True,
        )
        session.add(state)
        session.commit()
        session.refresh(state)
        
        # Verify
        fetched = session.query(PlaybackState).first()
        assert fetched is not None
        assert fetched.current_queue_id == "queue1"
        assert fetched.current_song_id == "song1"
        assert fetched.current_time_ms == 10000
        assert fetched.is_playing is True
        assert fetched.volume == 0.8
        assert fetched.repeat_mode == "all"
        assert fetched.shuffle is True
