"""SQLAlchemy 2.x ORM models — single userdb.sqlite."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    # Naive UTC, like the rows already stored (SQLite DateTime keeps no tzinfo)
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    artist: Mapped[str] = mapped_column(String(512), default="")
    album: Mapped[str] = mapped_column(String(512), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    thumbnail_url: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LikedSong(Base):
    __tablename__ = "liked_songs"

    song_id: Mapped[str] = mapped_column(String(32), ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True)
    liked_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    song: Mapped["Song"] = relationship("Song")


class SavedQueue(Base):
    """A named copy of a play queue. Songs are a JSON list of SongResponse dicts, in order."""

    __tablename__ = "saved_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    songs_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ListeningHistory(Base):
    """One play of a song: how long it was actually listened to (seeks excluded) and how it ended."""

    __tablename__ = "listening_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    artist: Mapped[str] = mapped_column(String(500), default="")
    album: Mapped[str] = mapped_column(String(500), default="")
    thumbnail_url: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    listened_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    end_reason: Mapped[str] = mapped_column(String(16), default="skipped")  # finished | skipped | stopped | closed


class Segment(Base):
    """Segment cache metadata. PK = (song_id, index). index -1 == init segment."""

    __tablename__ = "segments"

    song_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    index: Mapped[int] = mapped_column(Integer, primary_key=True)  # -1 = init
    byte_start: Mapped[int] = mapped_column(Integer, default=0)
    byte_end: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|downloading|downloaded|error
    file_path: Mapped[str] = mapped_column(Text, default="")
    layout_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # StreamInfo.layout_id
    last_accessed: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
