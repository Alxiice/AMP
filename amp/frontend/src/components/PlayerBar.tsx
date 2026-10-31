import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import { api, type SegmentStatus, type CacheInfo, type Song } from "../api";
import { store, useQueueState, useQueueActions } from "../state";
import type { BackendStatus } from "../sidecar";
import { describeError, describeMediaError } from "../player/errors";

/** Player events go to the API log relay (Logs page → "API relay"). */
function relayLog(line: string): void {
  const ts = new Date().toISOString().slice(11, 23);
  api.postLogs([`${ts} [player] ${line}`]).catch(() => {});
}

function formatTime(ms: number): string {
  if (!ms || isNaN(ms)) return "0:00";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface PlayerBarProps {
  backendStatus: BackendStatus;
}

export function PlayerBar({ backendStatus }: PlayerBarProps) {
  const state = useQueueState();
  const actions = useQueueActions();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const requestedIdRef = useRef<string>(""); // last song the effect saw
  // Load sequence (F13): a newer load() invalidates older ones
  const loadGen = useRef(0);
  const loadAbort = useRef<AbortController | null>(null);
  const loadedIdRef = useRef<string>(""); // song whose /audio URL is on the element
  const retriedRef = useRef(false);       // one reload per load after a network error
  const ttfaRef = useRef<{ songId: string; start: number; cached: boolean } | null>(null);

  // Segment visualization state
  const [segments, setSegments] = useState<SegmentStatus[]>([]);
  const [cacheInfo, setCacheInfo] = useState<CacheInfo | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const segInFlightRef = useRef(false); // P12: in-flight guard
  const cacheInFlightRef = useRef(false);

  // Create the audio element once
  useEffect(() => {
    const audio = new Audio();
    audio.preload = "metadata";
    audioRef.current = audio;
    store.setAudioElement(audio);

    // Surface audio errors in the player bar
    const onError = () => {
      const songId = loadedIdRef.current;
      if (!audio.getAttribute("src") || !songId) return; // source cleared by a newer load
      const code = audio.error?.code;
      if (code === MediaError.MEDIA_ERR_NETWORK && !retriedRef.current) {
        // A segment that fails mid-stream aborts the response (Phase 3): reload once from here
        retriedRef.current = true;
        const at = audio.currentTime;
        relayLog(`network error on ${songId} at ${at.toFixed(1)}s, reloading`);
        audio.src = api.getStreamAudioUrl(songId);
        audio.currentTime = at;
        audio.play().catch(() => {});
        return;
      }
      relayLog(`audio error on ${songId}: code=${code} ${audio.error?.message ?? ""}`);
      setAudioLoading(false);
      setAudioError(describeMediaError(code));
    };
    const onCanPlay = () => {
      setAudioLoading(false);
      setAudioError(null);
    };
    const onWaiting = () => {
      // Audio is waiting for data - show loading
      if (audio.readyState < 3) { // HAVE_FUTURE_DATA
        setAudioLoading(true);
      }
    };
    const onPlaying = () => {
      setAudioLoading(false);
      setAudioError(null);
      const t = ttfaRef.current;
      if (t && t.songId === loadedIdRef.current) {
        ttfaRef.current = null;
        relayLog(`TTFA ${t.songId} ${Math.round(performance.now() - t.start)} cached=${t.cached}`);
      }
    };
    audio.addEventListener("error", onError);
    audio.addEventListener("canplay", onCanPlay);
    audio.addEventListener("waiting", onWaiting);
    audio.addEventListener("playing", onPlaying);

    // Start position reporting to backend every 2s
    store.startPositionReporting((ms) => {
      api.updatePosition(ms).catch(() => {});
    });

    return () => {
      audio.removeEventListener("error", onError);
      audio.removeEventListener("canplay", onCanPlay);
      audio.removeEventListener("waiting", onWaiting);
      audio.removeEventListener("playing", onPlaying);
      store.stopPositionReporting();
      store.setAudioElement(null);
      loadAbort.current?.abort();
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    };
  }, []);

  /** Resolve the stream (/play), then point the audio element at it — unless a newer load started. */
  const load = useCallback(async (song: Song) => {
    const audio = audioRef.current;
    if (!audio) return;
    const gen = ++loadGen.current;
    loadAbort.current?.abort();
    const ctrl = new AbortController();
    loadAbort.current = ctrl;
    const start = performance.now();

    // Stop the previous song now rather than letting it play while this one resolves
    loadedIdRef.current = "";
    retriedRef.current = false;
    ttfaRef.current = null;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    setSegments([]);
    setAudioError(null);
    setAudioLoading(true);
    store.setDurationMs(song.duration_ms || 0);

    try {
      const info = await api.playSong(song.id, ctrl.signal);
      if (gen !== loadGen.current) return; // a newer song was chosen
      store.setDurationMs(info.duration_ms);
      ttfaRef.current = { songId: song.id, start, cached: info.cached_ahead };
      loadedIdRef.current = song.id;
      relayLog(`src ${song.id} (resolved in ${Math.round(performance.now() - start)} ms)`);
      audio.src = api.getStreamAudioUrl(song.id);
      await audio.play();
    } catch (e) {
      if (gen !== loadGen.current) return; // includes the AbortError of a superseded /play
      console.error(`Load of ${song.id} failed:`, e);
      relayLog(`load ${song.id} failed: ${(e as { code?: string }).code ?? (e as Error).message}`);
      setAudioError(describeError(e));
    } finally {
      if (gen === loadGen.current) setAudioLoading(false);
    }
  }, []);

  // Load new song when currentSong changes (a restored song waits for the play button)
  useEffect(() => {
    const song = state.currentSong;
    if (!song || requestedIdRef.current === song.id) return;
    requestedIdRef.current = song.id;
    if (store.takeRestored()) return;
    load(song);
  }, [state.currentSong, load]);

  // Poll segment statuses (P12: in-flight guard)
  useEffect(() => {
    if (!state.currentSong || backendStatus !== "running") return;
    const songId = state.currentSong.id;

    const fetchSegments = async () => {
      if (segInFlightRef.current) return;
      segInFlightRef.current = true;
      try {
        const data = await api.getSegmentStatuses(songId);
        setSegments(data.segments);
      } catch {
        // Silently fail
      } finally {
        segInFlightRef.current = false;
      }
    };

    fetchSegments();
    const timer = setInterval(fetchSegments, 500);
    return () => clearInterval(timer);
  }, [state.currentSong, backendStatus]);

  // Poll cache info every 5s
  useEffect(() => {
    if (backendStatus !== "running") return;

    const fetchCache = async () => {
      if (cacheInFlightRef.current) return;
      cacheInFlightRef.current = true;
      try {
        const data = await api.getCacheInfo();
        setCacheInfo(data);
      } catch {
        // Silently fail
      } finally {
        cacheInFlightRef.current = false;
      }
    };

    fetchCache();
    const timer = setInterval(fetchCache, 5000);
    return () => clearInterval(timer);
  }, [backendStatus]);

  // Handle play/pause
  const handlePlayPause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !state.currentSong) return;

    if (loadedIdRef.current !== state.currentSong.id) {
      load(state.currentSong); // restored at startup, or the last load failed
      return;
    }
    if (state.isPlaying) {
      audio.pause();
      api.pause().catch(() => {});
    } else {
      setAudioError(null);
      setAudioLoading(false);
      audio.play().catch((e) => {
        console.error("Play failed:", e);
        setAudioLoading(false);
        setAudioError(describeError(e));
      });
      api.resume().catch(() => {});
    }
  }, [state.isPlaying, state.currentSong, load]);

  // Handle stop
  const handleStop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    api.stop().catch(() => {});
    actions.setPlaying(false);
  }, [actions]);

  // Handle next/previous
  const handleNext = useCallback(() => {
    const nextSong = store.next();
    if (!nextSong) {
      handleStop();
    }
  }, [handleStop]);

  const handlePrevious = useCallback(() => {
    store.previous();
  }, []);

  // Seek to a position (called from segment bar click)
  const seekTo = useCallback(
    (positionMs: number) => {
      const audio = audioRef.current;
      if (!audio || !state.currentSong) return;
      audio.currentTime = positionMs / 1000;
      actions.setPositionMs(positionMs);
      api.seek(positionMs).catch(() => {});
    },
    [state.currentSong, actions],
  );

  // Handle seek slider change
  const handleSeek = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newTimeSec = parseFloat(e.target.value);
      seekTo(Math.floor(newTimeSec * 1000));
    },
    [seekTo],
  );

  // Handle volume
  const handleVolume = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = parseFloat(e.target.value);
      actions.setVolume(v);
    },
    [actions],
  );

  // Segment bar click — map click position to time
  const handleSegmentClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!state.durationMs || segments.length === 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      seekTo(Math.floor(ratio * state.durationMs));
    },
    [state.durationMs, segments.length, seekTo],
  );

  const durationSec = state.durationMs / 1000;
  const positionSec = state.positionMs / 1000;
  const progressRatio = state.durationMs > 0 ? state.positionMs / state.durationMs : 0;

  // Cumulative segment offsets, once per /chunks update (not per cell)
  const segLayout = useMemo(() => {
    const total = segments.reduce((sum, s) => sum + (s.duration_ms || 0), 0);
    let acc = 0;
    return segments.map((seg) => {
      const dur = seg.duration_ms || 0;
      const leftPct = total > 0 ? (acc / total) * 100 : 0;
      const widthPct = total > 0 ? (dur / total) * 100 : 0;
      acc += dur;
      // Init segment (index -1) gets minimal width
      return seg.index === -1
        ? { seg, left: 0, width: Math.max(widthPct, 0.5) }
        : { seg, left: leftPct, width: widthPct };
    });
  }, [segments]);

  return (
    <div className="player-bar">
      {/* Song info */}
      <div className="player-info">
        {state.currentSong?.thumbnail_url ? (
          <img
            className="player-thumbnail"
            src={state.currentSong.thumbnail_url}
            alt=""
          />
        ) : (
          <div className="player-thumbnail-placeholder">&#9835;</div>
        )}
        <div className="player-meta">
          <div className="player-title">
            {state.currentSong?.title || "Nothing playing"}
          </div>
          <div className="player-artist">
            {audioLoading ? "Loading audio..." : state.currentSong?.artist || "—"}
          </div>
          {audioError && (
            <div className="player-error" style={{
              color: "var(--error, #e53935)",
              fontSize: 11,
              marginTop: 2,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: 200,
            }}>
              {audioError}
            </div>
          )}
        </div>
      </div>

      {/* Controls + progress */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        {/* Control buttons row */}
        <div className="player-controls" style={{ justifyContent: "center" }}>
          <button className="btn-icon" onClick={handlePrevious} title="Previous">
            &#9198;
          </button>
          <button
            className="btn-icon play-pause"
            onClick={handlePlayPause}
            disabled={!state.currentSong || audioLoading}
            title={audioLoading ? "Loading..." : state.isPlaying ? "Pause" : "Play"}
          >
            {audioLoading ? <span className="spinner" /> : state.isPlaying ? "\u23F8" : "\u25B6"}
          </button>
          <button
            className="btn-icon"
            onClick={handleStop}
            disabled={!state.currentSong}
            title="Stop"
          >
            &#9632;
          </button>
          <button className="btn-icon" onClick={handleNext} title="Next">
            &#9197;
          </button>
        </div>

        {/* Segment-based progress bar */}
        <div className="player-progress-row">
          <span className="time-label">{formatTime(state.positionMs)}</span>

          {segments.length > 0 && state.currentSong ? (
            /* Segment visualization bar */
            <div
              className="segment-progress-bar"
              onClick={handleSegmentClick}
              title="Click to seek"
            >
              {/* Played overlay */}
              <div
                className="segment-progress-played"
                style={{ width: `${progressRatio * 100}%` }}
              />
              {/* Segment cells */}
              {segLayout.map(({ seg, left, width }) => (
                <div
                  key={seg.index}
                  className={`segment-progress-cell ${seg.status}`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`Segment ${seg.index === -1 ? "init" : seg.index}: ${seg.status} (${formatBytes(seg.size_bytes)})`}
                />
              ))}
            </div>
          ) : (
            /* Fallback: plain seek slider when no segment data */
            <input
              type="range"
              className="seek-slider"
              min={0}
              max={durationSec || 0}
              step={0.1}
              value={positionSec}
              onChange={handleSeek}
              disabled={!state.currentSong}
            />
          )}

          <span className="time-label">{formatTime(state.durationMs)}</span>
        </div>

        {/* Cache info row */}
        {cacheInfo && (
          <div className="cache-info-row">
            <span className="cache-info-text">
              Cache: {cacheInfo.total_mb} MB / {cacheInfo.max_mb} MB
              ({cacheInfo.usage_pct}%)
            </span>
            <div className="cache-info-bar">
              <div
                className="cache-info-fill"
                style={{
                  width: `${Math.min(cacheInfo.usage_pct, 100)}%`,
                  background:
                    cacheInfo.usage_pct > 90
                      ? "var(--error)"
                      : cacheInfo.usage_pct > 70
                        ? "var(--warning)"
                        : "var(--success)",
                }}
              />
            </div>
            <span className="cache-info-detail">
              {cacheInfo.song_count} songs · {cacheInfo.file_count} segments
            </span>
          </div>
        )}
      </div>

      {/* Volume */}
      <div className="player-volume">
        <span style={{ fontSize: 16 }}>&#128266;</span>
        <input
          type="range"
          className="volume-slider"
          min={0}
          max={1}
          step={0.01}
          value={state.volume}
          onChange={handleVolume}
        />
      </div>
    </div>
  );
}
