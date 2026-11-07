import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import { api, type SegmentStatus, type Song } from "../api";
import { store, useQueueState } from "../state";
import { Cover } from "./Cover";
import { Icon } from "./Icon";
import { LikeButton } from "./LikeButton";
import type { BackendStatus } from "../sidecar";
import { describeError, describeMediaError } from "../player/errors";
import { coverUrl } from "../format";
import { isPlayPauseKey } from "../player/keyboard";

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
  queueOpen: boolean;
  onToggleQueue: () => void;
}

export function PlayerBar({ backendStatus, queueOpen, onToggleQueue }: PlayerBarProps) {
  const state = useQueueState();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const handledTokenRef = useRef(0); // last playToken the load effect acted on
  // Load sequence (F13): a newer load() invalidates older ones
  const loadGen = useRef(0);
  const loadAbort = useRef<AbortController | null>(null);
  const loadedIdRef = useRef<string>(""); // song whose /audio URL is on the element
  const retriedRef = useRef(false);       // one reload per load after a network error
  const ttfaRef = useRef<{ songId: string; start: number; cached: boolean } | null>(null);

  // Segment visualization state
  const [segments, setSegments] = useState<SegmentStatus[]>([]);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const segInFlightRef = useRef(false); // P12: in-flight guard

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
      const info = await api.playSong(song.id, ctrl.signal, {
        title: song.title,
        artist: song.artist,
        cover_url: song.thumbnail_url ? coverUrl(song.thumbnail_url, 240) : "",
      });
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

  // Load when the store asks for it (a restored queue stays at token 0 and waits for the play button)
  useEffect(() => {
    if (state.playToken === handledTokenRef.current) return;
    handledTokenRef.current = state.playToken;
    if (state.currentSong) load(state.currentSong);
  }, [state.playToken, state.currentSong, load]);

  // The queue was emptied: release the audio element
  const hasSong = !!state.currentSong;
  useEffect(() => {
    if (hasSong) return;
    const audio = audioRef.current;
    if (!audio || !audio.getAttribute("src")) return;
    loadGen.current++;
    loadAbort.current?.abort();
    loadedIdRef.current = "";
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    setSegments([]);
    setAudioError(null);
    setAudioLoading(false);
    api.stop().catch(() => {});
  }, [hasSong]);

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
      api.updatePosition(Math.floor(audio.currentTime * 1000)).catch(() => {}); // the widget freezes here
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

  // Space bar: play/pause from anywhere but text fields
  const playPauseRef = useRef(handlePlayPause);
  playPauseRef.current = handlePlayPause;
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isPlayPauseKey(e)) return;
      e.preventDefault(); // no page scroll, no click on a focused button
      if (!audioLoading) playPauseRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [audioLoading]);

  // Handle stop
  const handleStop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    api.stop().catch(() => {});
    store.setPlaying(false);
  }, []);

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
      store.setPositionMs(positionMs);
      api.seek(positionMs).catch(() => {});
    },
    [state.currentSong],
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
      store.setVolume(v);
    },
    [],
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
      <div className="player-info">
        <Cover url={state.currentSong?.thumbnail_url} songId={state.currentSong?.id} size={56} className="player-cover" />
        <div className="player-meta">
          <div className="player-title">{state.currentSong?.title || "Nothing playing"}</div>
          <div className="player-artist">
            {audioLoading ? "Loading audio..." : state.currentSong?.artist || "—"}
          </div>
          {audioError && <div className="player-error" title={audioError}>{audioError}</div>}
        </div>
        {state.currentSong && <LikeButton song={state.currentSong} />}
      </div>

      <div className="player-center">
        <div className="player-controls">
          <button
            className={`btn-icon toggle${state.shuffle ? " on" : ""}`}
            onClick={() => store.toggleShuffle()}
            title={state.shuffle ? "Shuffle: on" : "Shuffle: off"}
            aria-pressed={state.shuffle}
          >
            <Icon name="shuffle" />
          </button>
          <button className="btn-icon" onClick={handlePrevious} title="Previous"><Icon name="previous" /></button>
          <button
            className="btn-icon play-pause"
            onClick={handlePlayPause}
            disabled={!state.currentSong || audioLoading}
            title={audioLoading ? "Loading..." : state.isPlaying ? "Pause (Space)" : "Play (Space)"}
          >
            {audioLoading ? <span className="spinner" /> : <Icon name={state.isPlaying ? "pause" : "play"} />}
          </button>
          <button className="btn-icon" onClick={handleNext} title="Next"><Icon name="next" /></button>
          <button
            className={`btn-icon toggle${state.repeat !== "off" ? " on" : ""}`}
            onClick={() => store.cycleRepeat()}
            title={`Repeat: ${state.repeat}`}
          >
            <Icon name={state.repeat === "one" ? "repeat-one" : "repeat"} />
          </button>
        </div>

        <div className="player-progress-row">
          <span className="time-label">{formatTime(state.positionMs)}</span>
          {segments.length > 0 && state.currentSong ? (
            <div className="segment-progress-bar" onClick={handleSegmentClick} title="Click to seek">
              <div className="segment-progress-played" style={{ width: `${progressRatio * 100}%` }} />
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
      </div>

      <div className="player-right">
        <button className="btn-icon" onClick={handleStop} disabled={!state.currentSong} title="Stop">
          <Icon name="stop" />
        </button>
        <button
          className={`btn-icon toggle${queueOpen ? " on" : ""}`}
          onClick={onToggleQueue}
          title="Queue"
          aria-pressed={queueOpen}
        >
          <Icon name="queue" />
        </button>
        <Icon name="volume" />
        <input
          type="range"
          className="volume-slider"
          aria-label="Volume"
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
