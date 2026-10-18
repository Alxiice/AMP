import { useState, useEffect, useRef } from 'react';
import { useYouTubeAuth } from './useYouTubeAuth';

type Song = {
  id: string;
  title: string;
  artist: string | null;
  album: string | null;
  thumbnail_url: string | null;
  duration_ms: number | null;
  year: number | null;
};

const BROWSERS = [
  { id: 'firefox', label: 'Firefox' },
  { id: 'chrome', label: 'Chrome' },
  { id: 'edge', label: 'Edge' },
  { id: 'brave', label: 'Brave' },
] as const;

type BrowserId = typeof BROWSERS[number]['id'];

function App() {
  const {
    status, busy, error: authError, login, completeBrowserSignin, importFromBrowser, logout,
    inTauri, logs, backendReachable,
    apiUrl, apiUrlInput, setApiUrlInput, setApiUrlManually,
    awaitingBrowserSignin, setAwaitingBrowserSignin,
  } = useYouTubeAuth();

  const [likedSongs, setLikedSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [selectedBrowser, setSelectedBrowser] = useState<BrowserId>('firefox');
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
      const base = apiUrl || 'http://localhost:8000';
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

  const handleConnect = () => {
    login(inTauri ? undefined : selectedBrowser);
  };

  const handleCompleteSignin = () => {
    completeBrowserSignin(selectedBrowser);
  };

  const handleQuickImport = () => {
    importFromBrowser(selectedBrowser);
  };

  return (
    <div className="container">
      <h1>AMP</h1>
      <p className="powered-by">Powered by YouTube Music</p>

      {/* Status bar */}
      <div style={{ fontSize: '0.8rem', marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {backendReachable === null && <span style={{ color: '#888' }}>Checking backend...</span>}
        {backendReachable === true && <span style={{ color: '#4caf50' }}>Backend connected</span>}
        {backendReachable === false && <span style={{ color: '#f44336' }}>Backend unreachable</span>}
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
              Tauri/WSL2? Use Windows host IP:{' '}
              <code style={{ color: '#61dafb' }}>cat /etc/resolv.conf | grep nameserver</code>
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
          {/* Browser selector */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.85rem', color: '#aaa', marginRight: '0.5rem' }}>
              {inTauri ? 'Fallback browser:' : 'Sign in with:'}
            </label>
            <select
              value={selectedBrowser}
              onChange={(e) => setSelectedBrowser(e.target.value as BrowserId)}
              disabled={busy}
              style={{
                padding: '0.3rem 0.5rem', borderRadius: '4px',
                border: '1px solid #444', background: '#1a1a2e', color: '#fff',
                fontSize: '0.85rem',
              }}
            >
              {BROWSERS.map((b) => (
                <option key={b.id} value={b.id}>{b.label}</option>
              ))}
            </select>
          </div>

          {/* Step 1: Connect */}
          {!awaitingBrowserSignin ? (
            <div>
              <button
                className="button"
                onClick={handleConnect}
                disabled={busy || loading}
              >
                {busy
                  ? (inTauri ? 'Opening sign-in window...' : 'Opening browser...')
                  : 'Connect YouTube Music'}
              </button>
              <p style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.5rem' }}>
                {inTauri
                  ? 'Opens a sign-in window. Sign in with any Google account.'
                  : 'Opens a browser tab to YouTube Music. Sign in with any Google account, then come back here.'}
              </p>

              {/* Quick import (secondary) */}
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #333' }}>
                <p style={{ color: '#666', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                  Already signed in to YouTube Music in {BROWSERS.find(b => b.id === selectedBrowser)?.label}?
                </p>
                <button
                  className="button"
                  onClick={handleQuickImport}
                  disabled={busy || loading}
                  style={{ fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
                >
                  {busy ? 'Importing...' : `Quick import from ${BROWSERS.find(b => b.id === selectedBrowser)?.label}`}
                </button>
              </div>
            </div>
          ) : (
            /* Step 2: Awaiting sign-in in browser tab */
            <div className="status" style={{ padding: '1rem' }}>
              <h3>Sign in to YouTube Music</h3>
              <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
                A browser tab has been opened to <strong>music.youtube.com</strong>.
                Sign in with the Google account you want to use.
              </p>
              <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
                After signing in, come back here and click the button below.
              </p>
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                <button
                  className="button"
                  onClick={handleCompleteSignin}
                  disabled={busy}
                >
                  {busy ? 'Capturing cookies...' : "I've signed in — capture cookies"}
                </button>
                <button
                  onClick={() => setAwaitingBrowserSignin(false)}
                  disabled={busy}
                  style={{
                    padding: '0.5rem 1rem', borderRadius: '4px',
                    border: '1px solid #444', background: 'transparent',
                    color: '#888', cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
              <p style={{ color: '#666', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                Make sure {BROWSERS.find(b => b.id === selectedBrowser)?.label} is fully closed before capturing
                (yt-dlp reads the cookie database directly).
              </p>
            </div>
          )}

          {authError && status.state !== 'expired' && (
            <p className="error" style={{ marginTop: '1rem' }}>{authError}</p>
          )}

          {status.state === 'expired' && (
            <div className="status" style={{ marginTop: '1rem' }}>
              <p style={{ color: '#ffc107' }}>Session expired. Please connect again.</p>
              <button className="button" onClick={handleConnect} disabled={busy}>
                {busy ? 'Connecting...' : 'Connect YouTube Music'}
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

      {!status.is_authenticated && !busy && !loading && !awaitingBrowserSignin && (
        <div className="status">
          <h3>Not connected</h3>
          <p>Connect with YouTube Music to access your liked songs.</p>
        </div>
      )}
    </div>
  );
}

export default App;
