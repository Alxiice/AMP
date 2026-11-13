import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type AlbumDetail as Album } from "../api";
import { CollectionHeader } from "../components/CollectionHeader";
import { SongList } from "../components/SongList";

export function AlbumDetail() {
  const { id = "" } = useParams();
  const [album, setAlbum] = useState<Album | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setAlbum(null);
    setError(null);
    api.getAlbum(id)
      .then((data) => { if (!cancelled) setAlbum(data); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load album"); });
    return () => { cancelled = true; };
  }, [id]);

  return (
    <div>
      {error && <div className="error-message">{error}</div>}
      {!error && !album && <div className="loading">Loading album...</div>}
      {album && (
        <>
          <CollectionHeader
            kind={album.type}
            title={album.title}
            subtitle={[album.artist, album.year].filter(Boolean).join(" · ")}
            thumbnailUrl={album.thumbnail_url}
            songs={album.songs}
          />
          <SongList songs={album.songs} emptyMessage="No playable tracks on this album" />
        </>
      )}
    </div>
  );
}
