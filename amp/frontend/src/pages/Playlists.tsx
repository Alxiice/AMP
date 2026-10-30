import { useEffect, useState, useCallback } from "react";
import { api, type PlaylistInfo } from "../api";

export function Playlists() {
  const [playlists, setPlaylists] = useState<PlaylistInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const loadPlaylists = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await api.getAuthStatus();
      setIsAuthenticated(status.is_authenticated);
      if (!status.is_authenticated) {
        setError("Sign in to see your playlists");
        setPlaylists([]);
        return;
      }
      const data = await api.getUserPlaylists();
      setPlaylists(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load playlists");
      setPlaylists([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlaylists();
  }, [loadPlaylists]);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Your Playlists</h1>
      </div>

      {error && <div className="error-message">{error}</div>}

      {!isAuthenticated && !loading && (
        <div className="empty-state">
          <p>Sign in on the <a href="/auth" style={{ color: "var(--accent)" }}>Auth page</a> to see your playlists.</p>
        </div>
      )}

      {loading && <div className="loading">Loading playlists...</div>}

      {isAuthenticated && !loading && playlists.length > 0 && (
        <div className="card-grid">
          {playlists.map((pl) => (
            <div key={pl.id} className="card">
              {pl.thumbnail_url ? (
                <img className="card-thumb" src={pl.thumbnail_url} alt="" loading="lazy" />
              ) : (
                <div className="card-thumb" />
              )}
              <div className="card-title">{pl.name}</div>
              <div className="card-subtitle">
                {pl.song_count} songs{pl.owner ? ` · ${pl.owner}` : ""}
              </div>
            </div>
          ))}
        </div>
      )}

      {isAuthenticated && !loading && playlists.length === 0 && (
        <div className="empty-state">No playlists found</div>
      )}
    </div>
  );
}
