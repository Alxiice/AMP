"""
Database Module
===============
SQLAlchemy models and session management for AMP.
"""
from .models import (
    Base,
    Song,
    Playlist,
    PlaylistSong,
    Queue,
    QueueItem,
    PlaybackState,
    UserHistory,
    LikedSong,
    SavedQueue,
    CachedChunk,
)
from .session import (
    get_userdb_session,
    get_playdb_session,
    init_userdb,
    init_playdb,
)

__all__ = [
    "Base",
    "Song",
    "Playlist",
    "PlaylistSong",
    "Queue",
    "QueueItem",
    "PlaybackState",
    "UserHistory",
    "LikedSong",
    "SavedQueue",
    "CachedChunk",
    "get_userdb_session",
    "get_playdb_session",
    "init_userdb",
    "init_playdb",
]
