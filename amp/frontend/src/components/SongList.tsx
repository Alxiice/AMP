import { useState } from "react";
import type { Song } from "../api";
import { formatDuration } from "../format";
import { store, useQueueState } from "../state";
import { Cover } from "./Cover";
import { Icon } from "./Icon";
import { LikeButton } from "./LikeButton";
import { SongMenu } from "./SongMenu";

interface SongListProps {
  songs: Song[];
  loading?: boolean;
  emptyMessage?: string;
  /** Lists whose rows can be removed (saved queue page). */
  onRemove?: (index: number) => void;
}

export function SongList({ songs, loading, emptyMessage, onRemove }: SongListProps) {
  const { currentSong, isPlaying } = useQueueState();
  const [menu, setMenu] = useState<{ index: number; x: number; y: number } | null>(null);

  if (loading) return <div className="loading">Loading...</div>;
  if (songs.length === 0) return <div className="empty-state">{emptyMessage || "No songs found"}</div>;

  return (
    <div className="song-list">
      {songs.map((song, index) => {
        const isCurrent = currentSong?.id === song.id;
        return (
          <div
            key={`${song.id}-${index}`}
            className={`song-row${isCurrent ? " playing" : ""}`}
            onClick={() => store.playList(songs, index)}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu({ index, x: e.clientX, y: e.clientY });
            }}
          >
            <div className="song-cover">
              <Cover url={song.thumbnail_url} songId={song.id} size={44} lazy />
              <span className="song-cover-overlay">
                <Icon name={isCurrent && isPlaying ? "pause" : "play"} size={18} />
              </span>
            </div>
            <div className="song-info">
              <div className="song-title">
                {song.title}
                {song.is_explicit && <span className="explicit" title="Explicit">E</span>}
              </div>
              <div className="song-artist">{song.artist}</div>
            </div>
            <div className="song-album">{song.album}</div>
            <LikeButton song={song} />
            <span className="song-duration">{formatDuration(song.duration_ms)}</span>
            <button
              className="btn-icon song-more"
              title="More"
              onClick={(e) => {
                e.stopPropagation();
                setMenu({ index, x: e.clientX, y: e.clientY });
              }}
            >
              <Icon name="more" size={18} />
            </button>
          </div>
        );
      })}
      {menu && songs[menu.index] && (
        <SongMenu
          song={songs[menu.index]}
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          onRemove={onRemove && (() => onRemove(menu.index))}
        />
      )}
    </div>
  );
}
