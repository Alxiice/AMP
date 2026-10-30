import type { Song } from "../api";
import { useQueueState, useQueueActions } from "../state";

interface SongListProps {
  songs: Song[];
  loading?: boolean;
  emptyMessage?: string;
}

function formatDuration(ms: number): string {
  if (!ms) return "--:--";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function SongList({ songs, loading, emptyMessage }: SongListProps) {
  const state = useQueueState();
  const actions = useQueueActions();

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (songs.length === 0) {
    return (
      <div className="empty-state">
        {emptyMessage || "No songs found"}
      </div>
    );
  }

  return (
    <div className="song-list">
      {songs.map((song) => {
        const isPlaying = state.currentSong?.id === song.id && state.isPlaying;
        return (
          <div
            key={song.id}
            className={`song-row${state.currentSong?.id === song.id ? " playing" : ""}`}
            onClick={() => actions.playSong(song, songs)}
          >
            {song.thumbnail_url ? (
              <img className="song-thumb" src={song.thumbnail_url} alt="" loading="lazy" />
            ) : (
              <div className="song-thumb-placeholder" />
            )}
            <div className="song-info">
              <div className="song-title">
                {isPlaying ? "\u25B6 " : ""}{song.title}
              </div>
              <div className="song-artist">{song.artist}</div>
            </div>
            <span className="song-duration">{formatDuration(song.duration_ms)}</span>
          </div>
        );
      })}
    </div>
  );
}
