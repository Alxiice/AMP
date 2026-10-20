import { useState, useEffect, useRef, useCallback, type ChangeEvent, type MouseEvent as ReactMouseEvent, type TouchEvent as ReactTouchEvent } from 'react';
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

type CurrentSong = {
  id: string;
  title: string;
  artist: string | null;
  thumbnail_url: string | null;
  duration_ms: number | null;
};

const BROWSERS = [
  { id: 'firefox', label: 'Firefox' },
  { id: 'chrome', label: 'Chrome' },
  { id: 'edge', label: 'Edge' },
  { id: 'brave', label: 'Brave' },
] as const;

type BrowserId = typeof BROWSERS[number]['id'];

const CHUNK_SIZE_MS = 10 * 1000; // 10 seconds per chunk

// API Log entry type
type ApiLogEntry = {
  id: number;
  timestamp: string;
  method: string;
  url: string;
  status: number | null;
  duration_ms: number | null;
  requestBody?: string;
  responsePreview?: string;
  error?: string;
};

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

  // Player state
  const [currentSong, setCurrentSong] = useState<CurrentSong | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTimeMs, setCurrentTimeMs] = useState<number>(0);
  const [chunksStatus, setChunksStatus] = useState<SongChunksStatus | null>(null);
  const [playerError, setPlayerError] = useState<string | null>(null);
  const [isBuffering, setIsBuffering] = useState<boolean>(false);

  // API monitoring state
  const [apiLogs, setApiLogs] = useState<ApiLogEntry[]>([]);
  const [showApiLogs, setShowApiLogs] = useState<boolean>(false);
  const apiLogIdRef = useRef<number>(0);
  const apiLogsPanelRef = useRef<HTMLDivElement>(null);

  // Audio element ref
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentSongIdRef = useRef<string | null>(null);
  const chunkPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chunkPollInFlightRef = useRef<boolean>(false);

  const logsEndRef = useRef<HTMLDivElement>(null);

  const baseUrl = apiUrl || 'http://localhost:8000';

  // Logged fetch wrapper - tracks every API call for monitoring
  // Share API logs to the external dashboard server (port 8001) via POST
  const shareLogsToDashboard = useCallback((entry: ApiLogEntry) => {
    try {
      fetch(`${baseUrl}/api/logs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: entry.id,
          timestamp: entry.timestamp,
          method: entry.method,
          url: entry.url,
          status: entry.status,
          duration_ms: entry.duration_ms,
          requestBody: entry.requestBody,
          responsePreview: entry.responsePreview?.substring(0, 200),
          error: entry.error,
        }),
      }).catch(() => { /* dashboard not running, ignore */ });
    } catch { /* ignore */ }
  }, [baseUrl]);

  const loggedFetch = useCallback(async (url: string, options?: RequestInit): Promise<Response> => {
    const startTime = performance.now();
    const method = options?.method || 'GET';
    const logId = ++apiLogIdRef.current;
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false, fractionalSecondDigits: 3 });
    const shortUrl = url.replace(baseUrl, '');
    const requestBody = options?.body ? String(options.body).substring(0, 500) : undefined;

    // Skip body preview for streaming/binary endpoints to avoid hanging on large responses
    const skipPreview = shortUrl.includes('/audio') || shortUrl.includes('/chunk/');

    const logAndShare = (status: number | null, duration: number, preview?: string, error?: string) => {
      const entry: ApiLogEntry = {
        id: logId,
        timestamp,
        method,
        url: shortUrl,
        status,
        duration_ms: duration,
        requestBody,
        responsePreview: preview,
        error,
      };
      setApiLogs(prev => [entry, ...prev].slice(0, 200));
      shareLogsToDashboard(entry);
    };

    try {
      const response = await fetch(url, options);
      const duration = Math.round(performance.now() - startTime);

      // Clone response to read body for logging without consuming it
      let responsePreview: string | undefined;
      if (!skipPreview) {
        try {
          const clone = response.clone();
          const text = await Promise.race([
            clone.text(),
            new Promise<string>((_, reject) => setTimeout(() => reject(new Error('timeout')), 2000)),
          ]);
          responsePreview = text.substring(0, 500);
        } catch {
          responsePreview = '(binary or unreadable)';
        }
      }

      logAndShare(response.status, duration, responsePreview);
      return response;
    } catch (err) {
      const duration = Math.round(performance.now() - startTime);
      logAndShare(null, duration, undefined, String(err));
      throw err;
    }
  }, [baseUrl, shareLogsToDashboard]);

  // Auto-scroll the inline API logs panel to bottom (panel only, not the page)
  useEffect(() => {
    if (showApiLogs && apiLogsPanelRef.current) {
      apiLogsPanelRef.current.scrollTop = apiLogsPanelRef.current.scrollHeight;
    }
  }, [apiLogs, showApiLogs]);

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

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
      }
      if (chunkPollRef.current) {
        clearInterval(chunkPollRef.current);
      }
    };
  }, []);

  // Poll chunk status while playing
  useEffect(() => {
    if (currentSong) {
      // Initial fetch
      loadChunksStatus(currentSong.id);
      // Poll every 1000ms for chunk status updates (cached on backend, fast)
      chunkPollRef.current = setInterval(() => {
        loadChunksStatus(currentSong.id);
      }, 1000);
    } else {
      if (chunkPollRef.current) {
        clearInterval(chunkPollRef.current);
        chunkPollRef.current = null;
      }
    }
    return () => {
      if (chunkPollRef.current) {
        clearInterval(chunkPollRef.current);
        chunkPollRef.current = null;
      }
    };
  }, [currentSong?.id]);

  const loadLikedSongs = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await loggedFetch(`${baseUrl}/api/user/likes`);
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

  const loadChunksStatus = useCallback(async (songId: string) => {
    if (chunkPollInFlightRef.current) return;
    chunkPollInFlightRef.current = true;
    try {
      const response = await loggedFetch(`${baseUrl}/api/stream/${songId}/chunks`);
      if (!response.ok) return;
      const data = await response.json();
      setChunksStatus(data);
    } catch (err) {
      console.error('Failed to load chunks status:', err);
    } finally {
      chunkPollInFlightRef.current = false;
    }
  }, [baseUrl, loggedFetch]);

  // Start playback of a song
  const playSong = useCallback(async (song: Song) => {
    // Stop current playback if any
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
    }

    setPlayerError(null);
    setIsBuffering(true);
    setCurrentTimeMs(0);

    // Set current song info
    const songInfo: CurrentSong = {
      id: song.id,
      title: song.title,
      artist: song.artist,
      thumbnail_url: song.thumbnail_url,
      duration_ms: song.duration_ms,
    };
    setCurrentSong(songInfo);
    currentSongIdRef.current = song.id;

    // Start backend playback and buffering (fire-and-forget, don't block audio setup)
    loggedFetch(`${baseUrl}/api/stream/${song.id}/play`, { method: 'POST' }).catch(err => {
      console.error('Failed to start backend playback:', err);
    });
    loggedFetch(`${baseUrl}/api/stream/buffer/${song.id}`, { method: 'POST' }).catch(err => {
      console.error('Failed to start buffering:', err);
    });

    // Load chunks status
    loadChunksStatus(song.id);

    // Fetch stream info to get duration if not already known (non-blocking)
    if (!song.duration_ms) {
      loggedFetch(`${baseUrl}/api/stream/info/${song.id}`).then(res => {
        if (res.ok) return res.json();
      }).then(info => {
        if (info?.duration_ms) {
          setCurrentSong(prev => prev ? { ...prev, duration_ms: info.duration_ms } : null);
        }
      }).catch(err => {
        console.error('Failed to fetch stream info:', err);
      });
    }

    // Create audio element and start playback
    const audio = new Audio();
    audioRef.current = audio;

    // Get actual duration from audio metadata
    audio.addEventListener('loadedmetadata', () => {
      if (audio.duration && isFinite(audio.duration)) {
        const durationMs = Math.floor(audio.duration * 1000);
        setCurrentSong(prev => prev ? { ...prev, duration_ms: durationMs } : null);
      }
    });

    audio.addEventListener('canplay', () => {
      setIsBuffering(false);
      audio.play().then(() => {
        setIsPlaying(true);
      }).catch(err => {
        console.error('Audio play failed:', err);
        setPlayerError('Failed to play audio');
        setIsBuffering(false);
      });
    });

    audio.addEventListener('timeupdate', () => {
      const ms = audio.currentTime * 1000;
      setCurrentTimeMs(ms);
      // Report position to backend
      loggedFetch(`${baseUrl}/api/stream/position?position_ms=${Math.floor(ms)}`, {
        method: 'POST',
      }).catch(() => {});
    });

    audio.addEventListener('ended', () => {
      setIsPlaying(false);
      setCurrentTimeMs(0);
      // Notify backend
      loggedFetch(`${baseUrl}/api/stream/stop`, { method: 'POST' }).catch(() => {});
    });

    audio.addEventListener('error', (e) => {
      console.error('Audio error:', e);
      setPlayerError('Audio playback error');
      setIsBuffering(false);
      setIsPlaying(false);
    });

    audio.addEventListener('waiting', () => {
      setIsBuffering(true);
    });

    // Set source to the full audio streaming endpoint
    audio.src = `${baseUrl}/api/stream/${song.id}/audio`;
    audio.load();
  }, [baseUrl, loadChunksStatus, loggedFetch]);

  // Toggle play/pause
  const togglePlayPause = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !currentSong) return;

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      try {
        await loggedFetch(`${baseUrl}/api/stream/pause`, { method: 'POST' });
      } catch (err) {
        console.error('Failed to pause:', err);
      }
    } else {
      try {
        await audio.play();
        setIsPlaying(true);
        await loggedFetch(`${baseUrl}/api/stream/resume`, { method: 'POST' });
      } catch (err) {
        console.error('Failed to resume:', err);
        setPlayerError('Failed to resume playback');
      }
    }
  }, [isPlaying, currentSong, baseUrl, loggedFetch]);

  // Stop playback
  const stopPlayback = useCallback(async () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    setIsPlaying(false);
    setCurrentSong(null);
    setCurrentTimeMs(0);
    setChunksStatus(null);
    currentSongIdRef.current = null;
    try {
      await loggedFetch(`${baseUrl}/api/stream/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop:', err);
    }
  }, [baseUrl, loggedFetch]);

  // Seek to position (immediate - updates audio element)
  const seekTo = useCallback((positionMs: number) => {
    const audio = audioRef.current;
    if (!audio || !currentSong) return;
    audio.currentTime = positionMs / 1000;
    setCurrentTimeMs(positionMs);
  }, [currentSong]);

  // Seek committed (on release) - notifies backend to re-buffer from new position
  const seekCommitted = useCallback(async (positionMs: number) => {
    if (!currentSong) return;

    // Update audio position
    seekTo(positionMs);

    // Notify backend to cancel old downloads and re-buffer from new position
    try {
      await loggedFetch(`${baseUrl}/api/stream/seek?position_ms=${Math.floor(positionMs)}`, {
        method: 'POST',
      });
      // Reload chunk status to show updated download queue
      await loadChunksStatus(currentSong.id);
    } catch (err) {
      console.error('Failed to seek on backend:', err);
    }
  }, [currentSong, baseUrl, loggedFetch, seekTo, loadChunksStatus]);

  // Handle slider drag - update time display during drag
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragPositionMs, setDragPositionMs] = useState<number>(0);

  const handleSliderChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const ms = parseInt(e.target.value);
    setDragPositionMs(ms);
    setIsDragging(true);
    setCurrentTimeMs(ms);
  }, []);

  const handleSliderCommit = useCallback((e: ReactMouseEvent<HTMLInputElement> | ReactTouchEvent<HTMLInputElement>) => {
    setIsDragging(false);
    seekCommitted(dragPositionMs);
  }, [dragPositionMs, seekCommitted]);

  // Handle clicking on the timeline/chunk area to seek
  const handleTimelineClick = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (!currentSong?.duration_ms) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = clickX / rect.width;
    const positionMs = Math.floor(ratio * currentSong.duration_ms);
    seekTo(positionMs);
  }, [currentSong, seekTo]);

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

  const formatTime = (ms: number | null | undefined) => {
    if (ms === null || ms === undefined) return '0:00';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const getChunkColor = (status: ChunkStatus | string): string => {
    switch (status) {
      case 'downloaded': return '#4caf50';
      case 'downloading': return '#ffc107';
      case 'error': return '#f44336';
      default: return '#9e9e9e';
    }
  };

  // Calculate current chunk index from playback position
  const currentChunkIndex = currentSong?.duration_ms
    ? Math.floor(currentTimeMs / CHUNK_SIZE_MS)
    : 0;

  // Calculate progress percentage
  const progressPercent = currentSong?.duration_ms
    ? (currentTimeMs / currentSong.duration_ms) * 100
    : 0;

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
        <a
          href={`${baseUrl}/dashboard`}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: apiLogs.some(l => l.status === null || l.status >= 400) ? '#f44336' : '#4caf50',
            textDecoration: 'none', fontSize: '0.8rem', fontWeight: 500,
          }}
          title="Open API monitoring dashboard (served by backend)"
        >
          Dashboard ({apiLogs.length})
        </a>
        {' | '}
        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(apiLogs, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `amp_api_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          style={{ background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', fontSize: '0.8rem' }}
          title="Download API logs as JSON"
        >
          Export logs
        </button>
        {' | '}
        <button
          onClick={() => setShowApiLogs(!showApiLogs)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.8rem',
            color: apiLogs.some(l => l.status === null || l.status >= 400) ? '#f44336' : '#8b949e' }}
        >
          {showApiLogs ? 'Hide API logs' : 'API logs'} ({apiLogs.length})
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

      {/* Inline API logs panel - fixed height with own scroll, no page scroll */}
      {showApiLogs && (
        <div style={{
          background: '#0d1117',
          border: '1px solid #30363d',
          borderRadius: '6px',
          marginBottom: '1rem',
          display: 'flex',
          flexDirection: 'column',
          height: '200px',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.35rem 0.75rem',
            borderBottom: '1px solid #30363d',
            flexShrink: 0,
          }}>
            <span style={{ color: '#fff', fontWeight: 600, fontSize: '0.8rem' }}>
              API Logs ({apiLogs.length})
            </span>
            <span style={{ color: '#8b949e', fontSize: '0.7rem' }}>
              {apiLogs.filter(l => l.status !== null && l.status < 400).length} ok, {apiLogs.filter(l => l.status === null || l.status >= 400).length} err
            </span>
          </div>
          <div
            ref={apiLogsPanelRef}
            style={{
              overflowY: 'auto',
              flex: 1,
              fontFamily: 'monospace',
              fontSize: '0.7rem',
            }}
          >
            {apiLogs.length === 0 && (
              <div style={{ color: '#484f58', padding: '1rem', textAlign: 'center' }}>
                No API calls yet.
              </div>
            )}
            {apiLogs.map((log) => {
              const isError = log.status === null || log.status >= 400;
              const statusColor = isError ? '#f44336' : log.status! >= 300 ? '#ffc107' : '#4caf50';
              const methodColor = log.method === 'GET' ? '#61dafb' : log.method === 'POST' ? '#4caf50' : '#ffc107';
              return (
                <div
                  key={log.id}
                  style={{
                    padding: '0.2rem 0.75rem',
                    borderBottom: '1px solid #21262d',
                    background: isError ? 'rgba(244,67,54,0.05)' : 'transparent',
                    display: 'flex',
                    gap: '0.5rem',
                    alignItems: 'center',
                  }}
                >
                  <span style={{ color: '#484f58', flexShrink: 0 }}>{log.timestamp}</span>
                  <span style={{ color: methodColor, fontWeight: 600, minWidth: '35px', flexShrink: 0 }}>{log.method}</span>
                  <span style={{ color: isError ? '#f44336' : '#c9d1d9', wordBreak: 'break-all', flex: 1 }}>{log.url}</span>
                  <span style={{ color: statusColor, fontWeight: 600, flexShrink: 0 }}>
                    {log.status !== null ? log.status : 'ERR'}
                  </span>
                  {log.duration_ms !== null && (
                    <span style={{ color: '#8b949e', flexShrink: 0 }}>{log.duration_ms}ms</span>
                  )}
                </div>
              );
            })}
          </div>
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

          {/* Search bar */}
          <div style={{ marginBottom: '1rem', marginTop: '1rem' }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search your liked songs..."
              className="search-bar"
            />
          </div>

          {filteredSongs.length > 0 && (
            <div className="songs">
              <h3>Your Liked Songs ({likedSongs.length}) — click a song to play</h3>
              {filteredSongs.slice(0, 50).map((song) => {
                const isCurrentSong = currentSong?.id === song.id;
                return (
                  <div
                    key={song.id}
                    className="song"
                    onClick={() => playSong(song)}
                    style={{
                      cursor: 'pointer',
                      background: isCurrentSong ? '#e3f2fd' : undefined,
                      borderLeft: isCurrentSong ? '4px solid #667eea' : '4px solid transparent',
                    }}
                  >
                    {song.thumbnail_url && (
                      <img
                        src={song.thumbnail_url}
                        alt={song.title}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    )}
                    <div className="song-info">
                      <div className="song-title">
                        {isCurrentSong && isPlaying ? '▶ ' : ''}{song.title}
                      </div>
                      <div className="song-artist">{song.artist || 'Unknown Artist'}</div>
                    </div>
                    <span style={{ color: '#999', fontSize: '0.8rem' }}>
                      {formatTime(song.duration_ms)}
                    </span>
                    <button
                      className="play-button"
                      onClick={(e) => { e.stopPropagation(); playSong(song); }}
                    >
                      {isCurrentSong && isPlaying ? 'Playing' : 'Play'}
                    </button>
                  </div>
                );
              })}
              {filteredSongs.length > 50 && (
                <p style={{ color: '#666', fontSize: '0.85rem', marginTop: '1rem' }}>
                  ... and {filteredSongs.length - 50} more
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Mini Player Bar (fixed at bottom) */}
      {currentSong && (
        <div style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          background: '#1a1a2e',
          color: '#fff',
          padding: '0.75rem 1rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
          boxShadow: '0 -4px 12px rgba(0,0,0,0.3)',
          zIndex: 1000,
        }}>
          {/* Song info and controls row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {/* Thumbnail */}
            {currentSong.thumbnail_url && (
              <img
                src={currentSong.thumbnail_url}
                alt={currentSong.title}
                style={{ width: '48px', height: '48px', borderRadius: '4px', objectFit: 'cover' }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            )}

            {/* Song title/artist */}
            <div style={{ minWidth: '150px' }}>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {currentSong.title}
              </div>
              <div style={{ color: '#aaa', fontSize: '0.8rem' }}>
                {currentSong.artist || 'Unknown Artist'}
              </div>
            </div>

            {/* Play/Pause/Stop buttons */}
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <button
                onClick={togglePlayPause}
                disabled={isBuffering}
                style={{
                  width: '40px', height: '40px', borderRadius: '50%',
                  border: 'none', cursor: 'pointer',
                  background: '#667eea', color: '#fff',
                  fontSize: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                {isBuffering ? '...' : isPlaying ? '||' : '>'}
              </button>
              <button
                onClick={stopPlayback}
                style={{
                  width: '36px', height: '36px', borderRadius: '4px',
                  border: '1px solid #555', cursor: 'pointer',
                  background: 'transparent', color: '#aaa',
                  fontSize: '0.8rem',
                }}
              >
                Stop
              </button>
            </div>

            {/* Time display */}
            <div style={{ color: '#aaa', fontSize: '0.8rem', fontFamily: 'monospace', minWidth: '100px', textAlign: 'center' }}>
              {formatTime(currentTimeMs)} / {formatTime(currentSong.duration_ms)}
            </div>

            {/* Chunk stats */}
            {chunksStatus && chunksStatus.total_chunks > 0 && (
              <div style={{ color: '#aaa', fontSize: '0.75rem' }}>
                Chunks: {chunksStatus.cached_count}/{chunksStatus.total_chunks} downloaded
                {chunksStatus.downloading_count > 0 && `, ${chunksStatus.downloading_count} downloading`}
              </div>
            )}

            {/* Error display */}
            {playerError && (
              <span style={{ color: '#f44336', fontSize: '0.75rem' }}>{playerError}</span>
            )}
          </div>

          {/* Progress bar slider with chunk visualization */}
          <div style={{ position: 'relative' }}>
            {/* Chunk segments background */}
            <div
              onClick={handleTimelineClick}
              style={{
                position: 'relative',
                height: '28px',
                background: '#333',
                borderRadius: '4px',
                cursor: 'pointer',
                overflow: 'hidden',
                display: 'flex',
              }}
            >
              {chunksStatus && chunksStatus.total_chunks > 0 ? (
                Array.from({ length: chunksStatus.total_chunks }).map((_, index) => {
                  const status = chunksStatus.chunk_status[index] || 'not_downloaded';
                  const isCurrentChunk = index === currentChunkIndex;
                  return (
                    <div
                      key={index}
                      title={`Chunk ${index} (${formatTime(index * CHUNK_SIZE_MS)}): ${status}`}
                      style={{
                        flex: 1,
                        background: getChunkColor(status),
                        borderRight: '1px solid rgba(0,0,0,0.2)',
                        opacity: isCurrentChunk ? 1 : 0.6,
                        transition: 'opacity 0.2s',
                      }}
                    />
                  );
                })
              ) : (
                <div style={{ width: '100%', height: '100%', background: '#444' }} />
              )}

              {/* Progress fill overlay */}
              <div style={{
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: `${isDragging ? (dragPositionMs / (currentSong.duration_ms || 1)) * 100 : progressPercent}%`,
                background: 'linear-gradient(90deg, rgba(102,126,234,0.3) 0%, rgba(102,126,234,0.5) 100%)',
                pointerEvents: 'none',
                transition: isDragging ? 'none' : 'width 0.1s linear',
              }} />

              {/* Playback position indicator line */}
              <div style={{
                position: 'absolute',
                left: `${isDragging ? (dragPositionMs / (currentSong.duration_ms || 1)) * 100 : progressPercent}%`,
                top: 0,
                bottom: 0,
                width: '3px',
                background: '#fff',
                boxShadow: '0 0 4px rgba(255,255,255,0.8)',
                pointerEvents: 'none',
                transform: 'translateX(-1.5px)',
                transition: isDragging ? 'none' : 'left 0.1s linear',
              }} />
            </div>

            {/* Range slider overlay for seeking - drag to preview, release to commit */}
            <input
              type="range"
              min={0}
              max={currentSong.duration_ms || 0}
              value={isDragging ? dragPositionMs : currentTimeMs}
              onChange={handleSliderChange}
              onMouseUp={handleSliderCommit}
              onTouchEnd={handleSliderCommit}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '28px',
                margin: 0,
                padding: 0,
                opacity: 0,
                cursor: 'grab',
                zIndex: 10,
              }}
            />

            {/* Draggable cursor handle */}
            <div style={{
              position: 'absolute',
              left: `calc(${isDragging ? (dragPositionMs / (currentSong.duration_ms || 1)) * 100 : progressPercent}% - 6px)`,
              top: '-2px',
              width: '12px',
              height: '32px',
              background: isDragging ? '#fff' : 'rgba(255,255,255,0.8)',
              borderRadius: '6px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
              pointerEvents: 'none',
              zIndex: 11,
              transition: isDragging ? 'none' : 'left 0.1s linear',
              cursor: 'grab',
            }} />
          </div>

          {/* Time labels under the slider */}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#888', marginTop: '2px' }}>
            <span style={{ color: isDragging ? '#fff' : '#888', fontWeight: isDragging ? 600 : 400 }}>
              {formatTime(isDragging ? dragPositionMs : currentTimeMs)}
            </span>
            <span>{formatTime(currentSong.duration_ms)}</span>
          </div>

          {/* Legend */}
          <div style={{ display: 'flex', gap: '1rem', fontSize: '0.7rem', color: '#888', justifyContent: 'center' }}>
            <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#9e9e9e', borderRadius: '2px', marginRight: '4px' }} />Not downloaded</span>
            <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#4caf50', borderRadius: '2px', marginRight: '4px' }} />Downloaded</span>
            <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#ffc107', borderRadius: '2px', marginRight: '4px' }} />Downloading</span>
            <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#f44336', borderRadius: '2px', marginRight: '4px' }} />Error</span>
            <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#667eea', borderRadius: '2px', marginRight: '4px' }} />Progress</span>
          </div>
        </div>
      )}

      {/* Spacer for fixed player */}
      {currentSong && <div style={{ height: '160px' }} />}

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
