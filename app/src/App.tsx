import { useState, useEffect, useRef, useCallback } from 'react';
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

type ChunkStatus = 'not_downloaded' | 'downloaded' | 'downloading' | 'error';

type SongChunksStatus = {
  total_chunks: number;
  chunk_status: Record<number, ChunkStatus>;
  cached_count: number;
  downloading_count: number;
  duration_ms: number | null;
};

type PlaybackState = {
  current_song_id: string | null;
  current_time_ms: number;
  is_playing: boolean;
  volume: number;
  current_song_info: {
    song_id: string;
    title: string;
    duration_ms: number | null;
    total_chunks: number;
  } | null;
  current_chunk_index: number;
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
    signinUrl, setSigninUrl, pasteCookies,
  } = useYouTubeAuth();

  const [likedSongs, setLikedSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [selectedBrowser, setSelectedBrowser] = useState<BrowserId>('firefox');
  const [cookiePaste, setCookiePaste] = useState('');
  const [showCookiePaste, setShowCookiePaste] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filteredSongs, setFilteredSongs] = useState<Song[]>([]);
  
  // Playback state
  const [playbackState, setPlaybackState] = useState<PlaybackState | null>(null);
  const [currentSongChunks, setCurrentSongChunks] = useState<SongChunksStatus | null>(null);
  const [showPlaybackView, setShowPlaybackView] = useState<boolean>(false);
  
  // Audio context
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const audioBufferRef = useRef<AudioBuffer | null>(null);
  const isPlayingRef = useRef<boolean>(false);
  const currentSongIdRef = useRef<string | null>(null);
  
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

  useEffect(() => {
    // Filter songs based on search query
    const lowerQuery = searchQuery.toLowerCase();
    if (lowerQuery === '') {
      setFilteredSongs(likedSongs);
    } else {
      const filtered = likedSongs.filter(
        song => 
          song.title?.toLowerCase().includes(lowerQuery) ||
          song.artist?.toLowerCase().includes(lowerQuery)
      );
      setFilteredSongs(filtered);
    }
  }, [likedSongs, searchQuery]);

  // Load playback state
  const loadPlaybackState = useCallback(async () => {
    try {
      const base = apiUrl || 'http://localhost:8000';
      const response = await fetch(`${base}/api/stream/playback-state`);
      if (!response.ok) {
        console.error('Failed to load playback state');
        return;
      }
      const state = await response.json();
      setPlaybackState(state);
      
      if (state.current_song_id) {
        currentSongIdRef.current = state.current_song_id;
        loadSongChunks(state.current_song_id);
      }
    } catch (err) {
      console.error('Failed to load playback state:', err);
    }
  }, [apiUrl]);

  // Load song chunks status
  const loadSongChunks = useCallback(async (songId: string) => {
    try {
      const base = apiUrl || 'http://localhost:8000';
      const response = await fetch(`${base}/api/stream/${songId}/chunks`);
      if (!response.ok) {
        console.error('Failed to load song chunks');
        return;
      }
      const chunks = await response.json();
      setCurrentSongChunks(chunks);
    } catch (err) {
      console.error('Failed to load song chunks:', err);
    }
  }, [apiUrl]);

  // Initialize audio context on first play
  const initAudioContext = useCallback(() => {
    if (audioContextRef.current === null) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    return audioContextRef.current;
  }, []);

  // Start playback
  const startPlayback = useCallback(async (songId: string) => {
    try {
      const base = apiUrl || 'http://localhost:8000';
      
      // Start playback on backend
      const startResponse = await fetch(`${base}/api/stream/${songId}/play`, {
        method: 'POST',
      });
      
      if (!startResponse.ok) {
        console.error('Failed to start playback on backend');
        return;
      }
      
      // Load chunks status
      await loadSongChunks(songId);
      
      // Set current song
      currentSongIdRef.current = songId;
      setShowPlaybackView(true);
      
      // Load playback state
      await loadPlaybackState();
      
    } catch (err) {
      console.error('Failed to start playback:', err);
    }
  }, [apiUrl, loadSongChunks, loadPlaybackState]);

  // Pause playback
  const pausePlayback = useCallback(async () => {
    try {
      const base = apiUrl || 'http://localhost:8000';
      
      if (playbackState?.is_playing) {
        await fetch(`${base}/api/stream/pause`, { method: 'POST' });
        setPlaybackState(prev => prev ? { ...prev, is_playing: false } : null);
      } else {
        await fetch(`${base}/api/stream/resume`, { method: 'POST' });
        setPlaybackState(prev => prev ? { ...prev, is_playing: true } : null);
      }
      
      await loadPlaybackState();
    } catch (err) {
      console.error('Failed to toggle playback:', err);
    }
  }, [apiUrl, playbackState, loadPlaybackState]);

  // Stop playback
  const stopPlayback = useCallback(async () => {
    try {
      const base = apiUrl || 'http://localhost:8000';
      await fetch(`${base}/api/stream/stop`, { method: 'POST' });
      
      // Clean up audio
      if (audioSourceRef.current) {
        audioSourceRef.current.stop();
        audioSourceRef.current = null;
      }
      
      setPlaybackState(null);
      setCurrentSongChunks(null);
      setShowPlaybackView(false);
      currentSongIdRef.current = null;
      
    } catch (err) {
      console.error('Failed to stop playback:', err);
    }
  }, []);

  // Update playback position
  const updatePlaybackPosition = useCallback(async (positionMs: number) => {
    try {
      const base = apiUrl || 'http://localhost:8000';
      await fetch(`${base}/api/stream/position`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_ms: positionMs }),
      });
    } catch (err) {
      console.error('Failed to update playback position:', err);
    }
  }, [apiUrl]);

  // Poll playback state
  useEffect(() => {
    if (!status.is_authenticated || !showPlaybackView) return;
    
    const interval = setInterval(() => {
      loadPlaybackState();
    }, 1000);
    
    return () => clearInterval(interval);
  }, [status.is_authenticated, showPlaybackView, loadPlaybackState]);

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
    setSigninUrl(null);
    login(inTauri ? undefined : selectedBrowser);
  };

  const handleCompleteSignin = () => {
    completeBrowserSignin(selectedBrowser);
  };

  const handleQuickImport = () => {
    importFromBrowser(selectedBrowser);
  };

  const handlePlaySong = (songId: string) => {
    startPlayback(songId);
  };

  const formatTimeMs = (ms: number | null | undefined) => {
    if (ms === null || ms === undefined) return '0:00';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const getChunkColor = (status: ChunkStatus | string) => {
    switch (status) {
      case 'downloaded':
        return '#4caf50'; // Green
      case 'downloading':
        return '#ffc107'; // Yellow/Orange
      case 'error':
        return '#f44336'; // Red
      default:
        return '#9e9e9e'; // Grey
    }
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
              {signinUrl && (
                <p style={{ color: '#61dafb', fontSize: '0.85rem', marginTop: '0.5rem' }}>
                  If the tab didn't open:{' '}
                  <a href={signinUrl} target="_blank" rel="noopener noreferrer" style={{ color: '#61dafb', textDecoration: 'underline' }}>
                    Open YouTube Music manually
                  </a>
                </p>
              )}
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
                  onClick={() => { setAwaitingBrowserSignin(false); setSigninUrl(null); }}
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
              
              {/* Manual cookie paste fallback */}
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #333' }}>
                <button
                  onClick={() => setShowCookiePaste(!showCookiePaste)}
                  style={{ background: 'none', border: 'none', color: '#61dafb', cursor: 'pointer', fontSize: '0.8rem', padding: 0 }}
                >
                  {showCookiePaste ? 'Hide' : "Can't capture cookies? Paste them manually"}
                </button>
                {showCookiePaste && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <p style={{ color: '#888', fontSize: '0.75rem', marginBottom: '0.5rem' }}>
                      In the browser tab where you signed in to YouTube Music, open Dev Tools (F12)
                      then Network, click any request to music.youtube.com, Request Headers, copy the
                      <code style={{ color: '#61dafb' }}> Cookie </code> value. Paste it below:
                    </p>
                    <textarea
                      value={cookiePaste}
                      onChange={(e) => setCookiePaste(e.target.value)}
                      placeholder="__Secure-3PAPISID=...; __Secure-3PSID=...; ..."
                      rows={4}
                      style={{
                        width: '100%', padding: '0.4rem', borderRadius: '4px',
                        border: '1px solid #444', background: '#0d0d1a', color: '#fff',
                        fontFamily: 'monospace', fontSize: '0.7rem', resize: 'vertical',
                      }}
                    />
                    <button
                      className="button"
                      onClick={() => { pasteCookies(cookiePaste); setCookiePaste(''); }}
                      disabled={busy || !cookiePaste.trim()}
                      style={{ marginTop: '0.5rem', fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
                    >
                      {busy ? 'Connecting...' : 'Connect with pasted cookies'}
                    </button>
                  </div>
                )}
              </div>
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

          {/* Playback view */}
          {showPlaybackView && playbackState && (
            <div className="playback-view" style={{
              margin: '1rem 0',
              padding: '1rem',
              background: '#f8f9fa',
              borderRadius: '8px',
            }}>
              <h3 style={{ color: '#333', marginBottom: '1rem' }}>Playback Debug Interface</h3>
              
              {/* Now playing info */}
              <div style={{ marginBottom: '1rem' }}>
                <h4 style={{ color: '#333', marginBottom: '0.5rem' }}>
                  Now Playing: {playbackState.current_song_info?.title || 'Unknown'}
                </h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                  <button
                    className="button"
                    onClick={pausePlayback}
                    style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }}
                  >
                    {playbackState.is_playing ? 'Pause' : 'Play'}
                  </button>
                  <button
                    onClick={stopPlayback}
                    style={{
                      padding: '0.5rem 1rem', borderRadius: '4px',
                      border: '1px solid #dc3545', background: 'transparent',
                      color: '#dc3545', cursor: 'pointer', fontSize: '0.85rem',
                    }}
                  >
                    Stop
                  </button>
                  <span style={{ color: '#666', fontSize: '0.85rem' }}>
                    {formatTimeMs(playbackState.current_time_ms)} / {formatTimeMs(playbackState.current_song_info?.duration_ms)}
                  </span>
                </div>
              </div>
              
              {/* Progress bar */}
              <div style={{ marginBottom: '1rem' }}>
                <input
                  type="range"
                  min={0}
                  max={playbackState.current_song_info?.duration_ms || 100}
                  value={playbackState.current_time_ms}
                  onChange={(e) => updatePlaybackPosition(parseInt(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
              
              {/* Chunk visualization */}
              {currentSongChunks && currentSongChunks.total_chunks > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <h4 style={{ color: '#333', marginBottom: '0.5rem' }}>
                    Chunks ({currentSongChunks.cached_count}/{currentSongChunks.total_chunks} cached, {currentSongChunks.downloading_count} downloading)
                  </h4>
                  <div style={{
                    display: 'flex',
                    gap: '2px',
                    flexWrap: 'wrap',
                    justifyContent: 'center',
                  }}>
                    {Array.from({ length: currentSongChunks.total_chunks }).map((_, index) => {
                      const chunkStatus = currentSongChunks.chunk_status[index] || 'not_downloaded';
                      const isCurrentChunk = playbackState.current_chunk_index === index;
                      
                      return (
                        <div
                          key={index}
                          style={{
                            width: '20px',
                            height: '20px',
                            backgroundColor: getChunkColor(chunkStatus),
                            border: isCurrentChunk ? '2px solid #000' : '1px solid #ddd',
                            borderRadius: '2px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#fff',
                            fontSize: '8px',
                            fontWeight: 'bold',
                          }}
                          title={`Chunk ${index}: ${chunkStatus}`}
                        >
                          {index}
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#666', textAlign: 'center' }}>
                    <div><span style={{ background: '#9e9e9e', padding: '0 0.25rem' }}>grey</span> = not downloaded</div>
                    <div><span style={{ background: '#4caf50', color: '#fff', padding: '0 0.25rem' }}>green</span> = downloaded</div>
                    <div><span style={{ background: '#ffc107', padding: '0 0.25rem' }}>yellow</span> = downloading</div>
                    <div><span style={{ background: '#f44336', color: '#fff', padding: '0 0.25rem' }}>red</span> = error</div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Search bar */}
          <div style={{ marginBottom: '1rem' }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search your liked songs..."
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '4px',
                border: '1px solid #ddd',
                fontSize: '0.9rem',
              }}
            />
          </div>

          {filteredSongs.length > 0 && (
            <div className="songs">
              <h3>Your Liked Songs ({likedSongs.length})</h3>
              {filteredSongs.slice(0, 50).map((song) => (
                <div key={song.id} className="song">
                  {song.thumbnail_url && (
                    <img
                      src={song.thumbnail_url}
                      alt={song.title}
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  )}
                  <div className="song-info" style={{ flex: 1 }}>
                    <div className="song-title">{song.title}</div>
                    <div className="song-artist">{song.artist || 'Unknown Artist'}</div>
                  </div>
                  <button
                    className="play-button"
                    onClick={() => handlePlaySong(song.id)}
                    style={{
                      padding: '0.4rem 0.8rem',
                      borderRadius: '4px',
                      border: 'none',
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      color: 'white',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      fontWeight: '600',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Play
                  </button>
                </div>
              ))}
              {filteredSongs.length > 50 && (
                <p style={{ color: '#666', fontSize: '0.85rem', marginTop: '1rem' }}>
                  ... and {filteredSongs.length - 50} more
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
