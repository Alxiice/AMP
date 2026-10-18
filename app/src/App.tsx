import { useState, useEffect, useRef } from 'react';
import { useYouTubeAuth } from './useYouTubeAuth';

const BACKEND_URL = 'http://localhost:8000';

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
  const { status, busy, error: authError, login, logout, importFromBrowser, inTauri, logs, backendReachable } = useYouTubeAuth();
  const [likedSongs, setLikedSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

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

  const handleImportFirefox = () => {
    importFromBrowser('firefox');
  };

  return (
    <div className="container">
      <h1>AMP</h1>
      <p className="powered-by">Powered by YouTube Music</p>

      {/* Backend status indicator */}
      <div style={{ fontSize: '0.8rem', marginBottom: '1rem' }}>
        {backendReachable === null && <span style={{ color: '#888' }}>Checking backend...</span>}
        {backendReachable === true && <span style={{ color: '#4caf50' }}>Backend connected</span>}
        {backendReachable === false && (
          <span style={{ color: '#f44336' }}>
            Backend unreachable — start it with: python amp/backend/main.py
          </span>
        )}
        {' | '}
        <span style={{ color: '#888' }}>{inTauri ? 'Tauri app' : 'Browser mode'}</span>
        {' | '}
        <button
          onClick={() => setShowLogs(!showLogs)}
          style={{ background: 'none', border: 'none', color: '#61dafb', cursor: 'pointer', fontSize: '0.8rem' }}
        >
          {showLogs ? 'Hide logs' : 'Show logs'} ({logs.length})
        </button>
      </div>

      {/* Debug log panel */}
      {showLogs && (
        <div style={{
          background: '#1a1a2e',
          border: '1px solid #333',
          borderRadius: '4px',
          padding: '0.5rem',
          marginBottom: '1rem',
          maxHeight: '200px',
          overflowY: 'auto',
          fontFamily: 'monospace',
          fontSize: '0.75rem',
        }}>
          {logs.length === 0 && <div style={{ color: '#666' }}>No logs yet</div>}
          {logs.map((log, i) => (
            <div key={i} style={{
              color: log.type === 'error' ? '#f44336' : log.type === 'request' ? '#61dafb' : log.type === 'response' ? '#4caf50' : '#aaa',
              marginBottom: '2px',
            }}>
              <span style={{ color: '#666' }}>[{log.time}]</span>{' '}
              {log.message}
              {log.detail && (
                <div style={{ color: '#888', paddingLeft: '1rem', whiteSpace: 'pre-wrap' }}>{log.detail}</div>
              )}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      )}

      {!status.is_authenticated ? (
        <div>
          {inTauri && (
            <button
              className="button"
              onClick={login}
              disabled={busy || loading}
            >
              {busy ? 'Opening sign-in window...' : 'Connect YouTube Music'}
            </button>
          )}

          <button
            className="button"
            onClick={handleImportFirefox}
            disabled={busy || loading}
            style={{ marginLeft: inTauri ? '0.5rem' : 0 }}
          >
            {busy ? 'Importing...' : 'Import from Firefox'}
          </button>

          {!inTauri && (
            <p style={{ color: '#888', fontSize: '0.85rem', marginTop: '0.5rem' }}>
              Running in browser mode. Use "Import from Firefox" to connect,
              or run the Tauri desktop app for one-click sign-in.
            </p>
          )}

          {authError && status.state !== 'expired' && (
            <p className="error">{authError}</p>
          )}

          {status.state === 'expired' && (
            <div className="status" style={{ marginTop: '1rem' }}>
              <p style={{ color: '#ffc107' }}>Your session has expired. Please connect again.</p>
              {inTauri && (
                <button className="button" onClick={login} disabled={busy}>
                  {busy ? 'Connecting...' : 'Connect YouTube Music'}
                </button>
              )}
              <button
                className="button"
                onClick={handleImportFirefox}
                disabled={busy}
                style={{ marginLeft: inTauri ? '0.5rem' : 0 }}
              >
                {busy ? 'Importing...' : 'Import from Firefox'}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div>
          <button className="button" onClick={logout} disabled={loading}>
            {loading ? 'Logging out...' : 'Logout'}
          </button>

          {status.account && (
            <div className="status">
              <h3>Connected as {status.account.accountName}</h3>
              <p>You can now access your YouTube Music library.</p>
            </div>
          )}

          {loading && <p className="loading">Loading your liked songs...</p>}
          {error && <p className="error">{error}</p>}

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

      {error && <p className="error">{error}</p>}

      {!status.is_authenticated && !busy && !loading && (
        <div className="status">
          <h3>Not connected</h3>
          <p>Connect with YouTube Music to access your liked songs.</p>
        </div>
      )}
    </div>
  );
}

export default App;
