import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type PlaylistDetail as Playlist } from "../api";
import { CollectionHeader } from "../components/CollectionHeader";
import { SongList } from "../components/SongList";

export function PlaylistDetail() {
  const { id = "" } = useParams();
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPlaylist(null);
    setError(null);
    api.getPlaylist(id)
      .then((data) => { if (!cancelled) setPlaylist(data); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load playlist"); });
    return () => { cancelled = true; };
  }, [id]);

  return (
    <div>
      <Link className="back-link" to="/playlists">← Playlists</Link>
      {error && <div className="error-message">{error}</div>}
      {!error && !playlist && <div className="loading">Loading playlist...</div>}
      {playlist && (
        <>
          <CollectionHeader
            kind="Playlist"
            title={playlist.name}
            subtitle={playlist.owner}
            thumbnailUrl={playlist.thumbnail_url}
            songs={playlist.songs}
          />
          <SongList songs={playlist.songs} emptyMessage="This playlist is empty" />
        </>
      )}
    </div>
  );
}
