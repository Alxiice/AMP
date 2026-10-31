import { useEffect, useState } from "react";
import { api, ApiError, type Song } from "../api";
import { useAuthStatus } from "../authSession";
import { SignInPrompt } from "../components/SignInPrompt";
import { SongList } from "../components/SongList";

export function Library() {
  const auth = useAuthStatus();
  const signedIn = auth?.is_authenticated ?? false;
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unauthorized, setUnauthorized] = useState(false);

  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setUnauthorized(false);
    api.getUserLikes()
      .then((data) => { if (!cancelled) setSongs(data); })
      .catch((e) => {
        if (cancelled) return;
        setSongs([]);
        if (e instanceof ApiError && e.status === 401) setUnauthorized(true);
        else setError(e instanceof Error ? e.message : "Failed to load liked songs");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [signedIn]);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Liked Songs</h1>
      </div>

      {auth === null ? (
        <div className="loading">Checking session...</div>
      ) : !signedIn || unauthorized ? (
        <SignInPrompt status={auth} />
      ) : (
        <>
          {error && <div className="error-message">{error}</div>}
          <SongList songs={songs} loading={loading} emptyMessage="No liked songs yet" />
        </>
      )}
    </div>
  );
}
