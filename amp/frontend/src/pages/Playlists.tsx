import { useEffect, useState } from "react";
import { api, ApiError, type PlaylistInfo } from "../api";
import { useAuthStatus } from "../authSession";
import { SignInPrompt } from "../components/SignInPrompt";

export function Playlists() {
  const auth = useAuthStatus();
  const signedIn = auth?.is_authenticated ?? false;
  const [playlists, setPlaylists] = useState<PlaylistInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unauthorized, setUnauthorized] = useState(false);

  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setUnauthorized(false);
    api.getUserPlaylists()
      .then((data) => { if (!cancelled) setPlaylists(data); })
      .catch((e) => {
        if (cancelled) return;
        setPlaylists([]);
        if (e instanceof ApiError && e.status === 401) setUnauthorized(true);
        else setError(e instanceof Error ? e.message : "Failed to load playlists");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [signedIn]);

  const content = () => {
    if (auth === null) return <div className="loading">Checking session...</div>;
    if (!signedIn || unauthorized) return <SignInPrompt status={auth} />;
    if (loading) return <div className="loading">Loading playlists...</div>;
    if (error) return <div className="error-message">{error}</div>;
    if (playlists.length === 0) return <div className="empty-state">No playlists found</div>;
    return (
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
    );
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Your Playlists</h1>
      </div>
      {content()}
    </div>
  );
}
