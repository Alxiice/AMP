import { useEffect, useState, useCallback } from "react";
import { api, type Song } from "../api";
import { SongList } from "../components/SongList";

export function Library() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const loadLikes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await api.getAuthStatus();
      setIsAuthenticated(status.is_authenticated);
      if (!status.is_authenticated) {
        setError("Sign in to see your liked songs");
        setSongs([]);
        return;
      }
      const data = await api.getUserLikes();
      setSongs(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load liked songs");
      setSongs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLikes();
  }, [loadLikes]);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Liked Songs</h1>
      </div>

      {error && <div className="error-message">{error}</div>}

      {!isAuthenticated && !loading && (
        <div className="empty-state">
          <p>Sign in on the <a href="/auth" style={{ color: "var(--accent)" }}>Auth page</a> to see your liked songs.</p>
        </div>
      )}

      {isAuthenticated && (
        <SongList
          songs={songs}
          loading={loading}
          emptyMessage="No liked songs yet"
        />
      )}
    </div>
  );
}
