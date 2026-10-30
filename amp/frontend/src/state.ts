/**
 * Frontend-owned queue + playback state.
 *
 * The backend has no queue API — the queue lives here.
 * Playback position is reported to the backend every 2s (drives buffer-ahead).
 */

import { useSyncExternalStore, useCallback } from "react";
import type { Song } from "./api";

// ---------------------------------------------------------------------------
// Queue state
// ---------------------------------------------------------------------------

interface QueueState {
  songs: Song[];
  currentIndex: number;
  currentSong: Song | null;
  isPlaying: boolean;
  positionMs: number;
  durationMs: number;
  volume: number;
}

type Listener = () => void;

class StateStore {
  private state: QueueState = {
    songs: [],
    currentIndex: -1,
    currentSong: null,
    isPlaying: false,
    positionMs: 0,
    durationMs: 0,
    volume: 1.0,
  };

  private listeners: Set<Listener> = new Set();
  private audio: HTMLAudioElement | null = null;
  private positionTimer: ReturnType<typeof setInterval> | null = null;

  // --- Subscription (useSyncExternalStore) ---

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): QueueState => this.state;

  private emit(): void {
    for (const l of this.listeners) l();
  }

  private setState(partial: Partial<QueueState>): void {
    this.state = { ...this.state, ...partial };
    this.emit();
  }

  // --- Audio element ---

  setAudioElement(audio: HTMLAudioElement | null): void {
    // Clean up old listeners
    if (this.audio) {
      this.audio.removeEventListener("timeupdate", this._onTimeUpdate);
      this.audio.removeEventListener("ended", this._onEnded);
      this.audio.removeEventListener("play", this._onPlay);
      this.audio.removeEventListener("pause", this._onPause);
      this.audio.removeEventListener("loadedmetadata", this._onLoadedMetadata);
      this.audio.removeEventListener("error", this._onError);
      this.audio.removeEventListener("stalled", this._onStalled);
      this.audio.removeEventListener("waiting", this._onStalled);
    }

    this.audio = audio;

    if (audio) {
      audio.addEventListener("timeupdate", this._onTimeUpdate);
      audio.addEventListener("ended", this._onEnded);
      audio.addEventListener("play", this._onPlay);
      audio.addEventListener("pause", this._onPause);
      audio.addEventListener("loadedmetadata", this._onLoadedMetadata);
      audio.addEventListener("error", this._onError);
      audio.addEventListener("stalled", this._onStalled);
      audio.addEventListener("waiting", this._onStalled);
    }
  }

  getAudioElement(): HTMLAudioElement | null {
    return this.audio;
  }

  // --- Queue operations ---

  playSong(song: Song, queue?: Song[]): void {
    if (queue && queue.length > 0) {
      const idx = queue.findIndex((s) => s.id === song.id);
      this.setState({
        songs: queue,
        currentIndex: idx >= 0 ? idx : 0,
        currentSong: song,
      });
    } else {
      // Add to queue if not present
      const existing = this.state.songs.findIndex((s) => s.id === song.id);
      let songs: Song[];
      let index: number;
      if (existing >= 0) {
        songs = this.state.songs;
        index = existing;
      } else {
        songs = [...this.state.songs, song];
        index = songs.length - 1;
      }
      this.setState({ songs, currentIndex: index, currentSong: song });
    }
  }

  playQueue(songs: Song[], startIndex = 0): void {
    if (songs.length === 0) return;
    this.setState({
      songs,
      currentIndex: startIndex,
      currentSong: songs[startIndex],
    });
  }

  next(): Song | null {
    if (this.state.currentIndex < this.state.songs.length - 1) {
      const newIndex = this.state.currentIndex + 1;
      this.setState({
        currentIndex: newIndex,
        currentSong: this.state.songs[newIndex],
        positionMs: 0,
      });
      return this.state.songs[newIndex];
    }
    return null;
  }

  previous(): Song | null {
    // If more than 3s into the song, restart it
    if (this.state.positionMs > 3000) {
      this.setAudioTime(0);
      return this.state.currentSong;
    }
    if (this.state.currentIndex > 0) {
      const newIndex = this.state.currentIndex - 1;
      this.setState({
        currentIndex: newIndex,
        currentSong: this.state.songs[newIndex],
        positionMs: 0,
      });
      return this.state.songs[newIndex];
    }
    return null;
  }

  // --- Playback controls ---

  setPlaying(playing: boolean): void {
    this.setState({ isPlaying: playing });
  }

  setPositionMs(ms: number): void {
    this.setState({ positionMs: ms });
  }

  setDurationMs(ms: number): void {
    this.setState({ durationMs: ms });
  }

  setVolume(v: number): void {
    this.setState({ volume: v });
    if (this.audio) {
      this.audio.volume = v;
    }
  }

  setAudioTime(seconds: number): void {
    if (this.audio) {
      this.audio.currentTime = seconds;
    }
  }

  getAudioTime(): number {
    return this.audio?.currentTime ?? 0;
  }

  // --- Position reporting timer (every 2s to backend) ---

  startPositionReporting(reportFn: (positionMs: number) => void): void {
    this.stopPositionReporting();
    this.positionTimer = setInterval(() => {
      const a = this.audio;
      // Only report when audio is actually playing with data loaded.
      // `paused` is set to false by play() before any data arrives,
      // so also check readyState (>=2 = HAVE_CURRENT_DATA) and currentTime.
      if (a && !a.paused && a.readyState >= 2 && a.currentTime > 0) {
        reportFn(Math.floor(a.currentTime * 1000));
      }
    }, 2000);
  }

  stopPositionReporting(): void {
    if (this.positionTimer) {
      clearInterval(this.positionTimer);
      this.positionTimer = null;
    }
  }

  // --- Audio event handlers ---

  private _onTimeUpdate = (): void => {
    if (this.audio) {
      this.setState({ positionMs: Math.floor(this.audio.currentTime * 1000) });
    }
  };

  private _onEnded = (): void => {
    this.setState({ isPlaying: false });
    const nextSong = this.next();
    if (nextSong) {
      // The audio src change will be handled by the PlayerBar component
      this.emit();
    }
  };

  private _onPlay = (): void => {
    this.setState({ isPlaying: true });
  };

  private _onPause = (): void => {
    this.setState({ isPlaying: false });
  };

  private _onLoadedMetadata = (): void => {
    if (this.audio) {
      this.setState({ durationMs: Math.floor(this.audio.duration * 1000) });
    }
  };

  private _onError = (): void => {
    const a = this.audio;
    const code = a?.error?.code;
    const msg = a?.error?.message || "unknown error";
    console.error(`Audio playback error (code=${code}): ${msg}`);
    this.setState({ isPlaying: false, positionMs: 0 });
    // Notify backend that playback stopped
    this.stopPositionReporting();
  };

  private _onStalled = (): void => {
    // Audio is waiting for data — don't treat as playing
    if (this.audio && this.audio.readyState < 2) {
      // Keep isPlaying state but position won't advance
      console.warn("Audio stalled — waiting for data");
    }
  };
}

// Singleton
export const store = new StateStore();

// React hook
export function useQueueState(): QueueState {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}

export function useQueueActions() {
  return {
    playSong: useCallback((song: Song, queue?: Song[]) => store.playSong(song, queue), []),
    playQueue: useCallback((songs: Song[], startIndex?: number) => store.playQueue(songs, startIndex), []),
    next: useCallback(() => store.next(), []),
    previous: useCallback(() => store.previous(), []),
    setPlaying: useCallback((playing: boolean) => store.setPlaying(playing), []),
    setPositionMs: useCallback((ms: number) => store.setPositionMs(ms), []),
    setVolume: useCallback((v: number) => store.setVolume(v), []),
    setAudioTime: useCallback((s: number) => store.setAudioTime(s), []),
    setAudioElement: useCallback((a: HTMLAudioElement | null) => store.setAudioElement(a), []),
    startPositionReporting: useCallback((fn: (ms: number) => void) => store.startPositionReporting(fn), []),
    stopPositionReporting: useCallback(() => store.stopPositionReporting(), []),
  };
}
