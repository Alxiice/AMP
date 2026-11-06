import { useAuthStatus } from "../authSession";
import { CollectionHeader } from "../components/CollectionHeader";
import { SignInPrompt } from "../components/SignInPrompt";
import { SongList } from "../components/SongList";
import { useLikes } from "../likes";

export function Library() {
  const auth = useAuthStatus();
  const { songs, loading, error } = useLikes();

  if (auth === null) return <div className="loading">Checking session...</div>;
  if (!auth.is_authenticated) return <SignInPrompt status={auth} />;
  return (
    <div>
      <CollectionHeader kind="Your library" title="Liked songs" songs={songs} />
      {error && <div className="error-message">{error}</div>}
      <SongList songs={songs} loading={loading && songs.length === 0} emptyMessage="No liked songs yet. Tap a heart to add one." />
    </div>
  );
}
