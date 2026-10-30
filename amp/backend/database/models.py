"""SQLAlchemy 2.x ORM models — single userdb.sqlite."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    artist: Mapped[str] = mapped_column(String(512), default="")
    album: Mapped[str] = mapped_column(String(512), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    thumbnail_url: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), default="")
    owner: Mapped[str] = mapped_column(String(512), default="")
    thumbnail_url: Mapped[str] = mapped_column(Text, default="")
    song_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class PlaylistSong(Base):
    __tablename__ = "playlist_songs"
    __table_args__ = (UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[str] = mapped_column(String(64), ForeignKey("playlists.id", ondelete="CASCADE"), index=True)
    song_id: Mapped[str] = mapped_column(String(32), ForeignKey("songs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    song: Mapped["Song"] = relationship("Song")


class LikedSong(Base):
    __tablename__ = "liked_songs"

    song_id: Mapped[str] = mapped_column(String(32), ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True)
    liked_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    song: Mapped["Song"] = relationship("Song")


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
    last_accessed: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
