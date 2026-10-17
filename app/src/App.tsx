import { useState, useEffect } from 'react';
import { useYouTubeAuth } from './useYouTubeAuth';

// Backend API base URL
const BACKEND_URL = 'http://localhost:8000';

// Types for our data
type Song = {
  id: string;
  title: string;
  artist: string | null;
  album: string | null;
  thumbnail_url: string | null;
  duration_ms: number | null;
  year: number | null;
};

function App() {
  const { status, busy, error: authError, login, logout } = useYouTubeAuth();
  const [likedSongs, setLikedSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load liked songs when authenticated
  useEffect(() => {
    if (status.is_authenticated) {
      loadLikedSongs();
    } else {
      setLikedSongs([]);
    }
  }, [status.is_authenticated]);

  const loadLikedSongs = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${BACKEND_URL}/api/user/likes`);
      
      if (response.status === 401) {
        setLikedSongs([]);
        return;
      }
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const songs = await response.json();
      setLikedSongs(songs);
    } catch (err) {
      setError('Failed to load liked songs');
      console.error('Load liked songs failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h1>AMP</h1>
      <p className="powered-by">Powered by YouTube Music</p>
      
      {!status.is_authenticated ? (
        <div>
          <button 
            className="button" 
            onClick={login}
            disabled={busy || loading}
          >
            {busy ? 'Opening sign-in window...' : loading ? 'Loading...' : 'Connect YouTube Music'}
          </button>
          
          {authError && status.state !== 'expired' && (
            <p className="error">{authError}</p>
          )}
          
          {status.state === 'expired' && (
            <div className="status" style={{ marginTop: '1rem' }}>
              <p style={{ color: '#ffc107' }}>Your session has expired. Please connect again.</p>
              <button 
                className="button" 
                onClick={login}
                disabled={busy}
              >
                {busy ? 'Connecting...' : 'Connect YouTube Music'}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div>
          <button 
            className="button" 
            onClick={logout}
            disabled={loading}
          >
            {loading ? 'Logging out...' : 'Logout'}
          </button>
          
          {status.account && (
            <div className="status">
              <h3>✓ Connected as {status.account.accountName}</h3>
              <p>You can now access your YouTube Music library.</p>
            </div>
          )}
          
          {loading && (
            <p className="loading">Loading your liked songs...</p>
          )}
          
          {error && (
            <p className="error">{error}</p>
          )}
          
          {likedSongs.length > 0 && (
            <div className="songs">
              <h3>Your Liked Songs ({likedSongs.length})</h3>
              {likedSongs.slice(0, 10).map((song) => (
                <div key={song.id} className="song">
                  {song.thumbnail_url && (
                    <img 
                      src={song.thumbnail_url} 
                      alt={song.title}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                  )}
                  <div className="song-info">
                    <div className="song-title">{song.title}</div>
                    <div className="song-artist">{song.artist || 'Unknown Artist'}</div>
                  </div>
                </div>
              ))}
              {likedSongs.length > 10 && (
                <p style={{ color: '#666', fontSize: '0.85rem', marginTop: '1rem' }}>
                  ... and {likedSongs.length - 10} more
                </p>
              )}
            </div>
          )}
        </div>
      )}
      
      {error && (
        <p className="error">{error}</p>
      )}
      
      {!status.is_authenticated && !busy && !loading && (
        <div className="status">
          <h3>Not connected</h3>
          <p>Click the button above to authenticate with YouTube Music and access your liked songs.</p>
        </div>
      )}
    </div>
  );
}

export default App;
