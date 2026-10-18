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
  const {
    status, busy, error: authError, login, logout, importFromBrowser,
    inTauri, logs, backendReachable,
    apiUrl, apiUrlInput, setApiUrlInput, setApiUrlManually,
  } = useYouTubeAuth();
  const [likedSongs, setLikedSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

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
      const base = apiUrl || BACKEND_URL;
      const response = await fetch(`${base}/api/user/likes`);
      if (response.status === 401) {
        setLikedSongs([]);
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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

      {/* Status bar */}
      <div style={{ fontSize: '0.8rem', marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {backendReachable === null && <span style={{ color: '#888' }}>Checking backend...</span>}
        {backendReachable === true && <span style={{ color: '#4caf50' }}>Backend connected</span>}
        {backendReachable === false && (
          <span style={{ color: '#f44336' }}>Backend unreachable</span>
        )}
        {' | '}
        <span style={{ color: '#888' }}>{inTauri ? 'Tauri' : 'Browser'}</span>
        {' | '}
        <button onClick={() => setShowLogs(!showLogs)} style={{ background: 'none', border: 'none', color: '#61dafb', cursor: 'pointer', fontSize: '0.8rem' }}>
          {showLogs ? 'Hide logs' : 'Show logs'} ({logs.length})
        </button>
        {' | '}
        <button onClick={() => setShowSettings(!showSettings)} style={{ background: 'none', border: 'none', color: '#61dafb', cursor: 'pointer', fontSize: '0.8rem' }}>
          {showSettings ? 'Hide settings' : 'Settings'}
        </button>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div style={{
          background: '#1a1a2e', border: '1px solid #333', borderRadius: '4px',
          padding: '0.75rem', marginBottom: '1rem',
        }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem', color: '#aaa' }}>
            API URL (backend address):
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              value={apiUrlInput}
              onChange={(e) => setApiUrlInput(e.target.value)}
              placeholder="http://127.0.0.1:8000"
              style={{
                flex: 1, padding: '0.4rem', borderRadius: '4px',
                border: '1px solid #444', background: '#0d0d1a', color: '#fff',
                fontFamily: 'monospace', fontSize: '0.85rem',
              }}
            />
            <button
              className="button"
              onClick={() => setApiUrlManually(apiUrlInput)}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            >
              Save
            </button>
          </div>
          {inTauri && (
            <p style={{ color: '#888', fontSize: '0.75rem', marginTop: '0.5rem' }}>
              Running in Tauri/WSL2? Use your Windows host IP, e.g.{' '}
              <code style={{ color: '#61dafb' }}>http://172.x.x.x:8000</code>
              {' '}(find it in WSL2 with: <code style={{ color: '#61dafb' }}>cat /etc/resolv.conf | grep nameserver</code>)
            </p>
          )}
        </div>
      )}

      {/* Debug log panel */}
      {showLogs && (
        <div style={{
          background: '#1a1a2e', border: '1px solid #333', borderRadius: '4px',
          padding: '0.5rem', marginBottom: '1rem', maxHeight: '200px', overflowY: 'auto',
          fontFamily: 'monospace', fontSize: '0.75rem',
        }}>
          {logs.length === 0 && <div style={{ color: '#666' }}>No logs yet</div>}
          {logs.map((log, i) => (
            <div key={i} style={{
              color: log.type === 'error' ? '#f44336' : log.type === 'request' ? '#61dafb' : log.type === 'response' ? '#4caf50' : log.type === 'warn' ? '#ffc107' : '#aaa',
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

      {/* Main content */}
      {!status.is_authenticated ? (
        <div>
          {inTauri && (
            <button className="button" onClick={login} disabled={busy || loading}>
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
              Browser mode. Use "Import from Firefox" to connect.
            </p>
          )}

          {authError && status.state !== 'expired' && (
            <p className="error">{authError}</p>
          )}

          {status.state === 'expired' && (
            <div className="status" style={{ marginTop: '1rem' }}>
              <p style={{ color: '#ffc107' }}>Session expired. Please connect again.</p>
              {inTauri && (
                <button className="button" onClick={login} disabled={busy}>
                  {busy ? 'Connecting...' : 'Connect YouTube Music'}
                </button>
              )}
              <button className="button" onClick={handleImportFirefox} disabled={busy} style={{ marginLeft: inTauri ? '0.5rem' : 0 }}>
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
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
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
