"""
Database Models
===============
SQLAlchemy models for AMP databases (userdb and playdb).
"""
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class RepeatMode(str, Enum):
    """Repeat mode options for playback."""
    NONE = "none"
    ALL = "all"
    ONE = "one"


# =============================================================================
# USERDB MODELS (Persistent Data)
# =============================================================================

class Song(Base):
    """
    Song metadata from YouTube Music.
    Stored in userdb for caching.
    """
    __tablename__ = "songs"
    
    id = Column(String, primary_key=True, index=True)  # YouTube video ID
    title = Column(String, nullable=False)
    artist = Column(String, index=True)
    album = Column(String, index=True)
    duration_ms = Column(Integer)  # Duration in milliseconds
    thumbnail_url = Column(String)
    lyrics = Column(Text)
    year = Column(Integer)
    genre = Column(String, index=True)
    bitrate = Column(Integer)
    sample_rate = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    playlist_songs = relationship("PlaylistSong", back_populates="song")
    queue_items = relationship("QueueItem", back_populates="song")
    user_history = relationship("UserHistory", back_populates="song")
    liked_songs = relationship("LikedSong", back_populates="song")
    cached_chunks = relationship("CachedChunk", back_populates="song")


class Playlist(Base):
    """
    Playlist (YouTube or local).
    Stored in userdb.
    """
    __tablename__ = "playlists"
    
    id = Column(String, primary_key=True, index=True)  # YouTube playlist ID or local UUID
    name = Column(String, nullable=False)
    description = Column(Text)
    owner = Column(String, index=True)  # User ID or "local"
    is_youtube = Column(Boolean, default=False)
    thumbnail_url = Column(String)
    song_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    playlist_songs = relationship("PlaylistSong", back_populates="playlist", cascade="all, delete-orphan")


class PlaylistSong(Base):
    """
    Relationship between playlists and songs.
    Stored in userdb.
    """
    __tablename__ = "playlist_songs"
    
    playlist_id = Column(String, ForeignKey("playlists.id"), primary_key=True)
    song_id = Column(String, ForeignKey("songs.id"), primary_key=True)
    position = Column(Integer, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    playlist = relationship("Playlist", back_populates="playlist_songs")
    song = relationship("Song", back_populates="playlist_songs")


class Queue(Base):
    """
    User-created or generated queues.
    Stored in userdb.
    """
    __tablename__ = "queues"
    
    id = Column(String, primary_key=True, index=True)  # UUID
    name = Column(String)
    is_infinite = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    queue_items = relationship("QueueItem", back_populates="queue", cascade="all, delete-orphan")
    saved_queues = relationship("SavedQueue", back_populates="queue")


class QueueItem(Base):
    """
    Items in a queue.
    Stored in userdb.
    """
    __tablename__ = "queue_items"
    
    queue_id = Column(String, ForeignKey("queues.id"), primary_key=True)
    song_id = Column(String, ForeignKey("songs.id"), primary_key=True)
    position = Column(Integer, nullable=False, primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    queue = relationship("Queue", back_populates="queue_items")
    song = relationship("Song", back_populates="queue_items")


class UserHistory(Base):
    """
    Listening history.
    Stored in userdb.
    """
    __tablename__ = "user_history"
    
    user_id = Column(String, primary_key=True)
    song_id = Column(String, ForeignKey("songs.id"), primary_key=True)
    played_at = Column(DateTime, primary_key=True, default=datetime.utcnow)
    duration_ms = Column(Integer)  # How long the song was played
    
    # Relationships
    song = relationship("Song", back_populates="user_history")


class LikedSong(Base):
    """
    Liked songs for a user.
    Stored in userdb.
    """
    __tablename__ = "liked_songs"
    
    user_id = Column(String, primary_key=True)
    song_id = Column(String, ForeignKey("songs.id"), primary_key=True)
    liked_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    song = relationship("Song", back_populates="liked_songs")


class SavedQueue(Base):
    """
    Saved queues for a user.
    Stored in userdb.
    """
    __tablename__ = "saved_queues"
    
    user_id = Column(String, primary_key=True)
    queue_id = Column(String, ForeignKey("queues.id"), primary_key=True)
    saved_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    queue = relationship("Queue", back_populates="saved_queues")


class CachedChunk(Base):
    """
    Metadata for cached audio chunks.
    Files are stored on filesystem, metadata in userdb.
    """
    __tablename__ = "cached_chunks"
    
    song_id = Column(String, ForeignKey("songs.id"), primary_key=True)
    start_ms = Column(Integer, primary_key=True)  # Start time in milliseconds
    end_ms = Column(Integer)  # End time in milliseconds
    file_path = Column(String, nullable=False)  # Path to the chunk file
    size_bytes = Column(Integer)  # File size in bytes
    last_accessed = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)  # Optional expiry time
    
    # Relationships
    song = relationship("Song", back_populates="cached_chunks")


# =============================================================================
# PLAYDB MODELS (Session Data)
# =============================================================================

class PlaybackState(Base):
    """
    Current playback state.
    Stored in playdb (flushed on restart).
    """
    __tablename__ = "playback_state"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    current_queue_id = Column(String, ForeignKey("queues.id"))
    current_song_id = Column(String, ForeignKey("songs.id"))
    current_time_ms = Column(Integer, default=0)  # Playback position in ms
    is_playing = Column(Boolean, default=False)
    volume = Column(Float, default=1.0)
    repeat_mode = Column(String, default=RepeatMode.NONE.value)
    shuffle = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint(
            "repeat_mode IN ('none', 'all', 'one')",
            name="check_repeat_mode"
        ),
    )
