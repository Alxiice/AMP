/**
 * Frontend-owned queue + playback state.
 *
 * The queue itself is the pure model in player/queue.ts; this store applies it
 * to the audio element. `playToken` goes up whenever the current song must
 * (re)load, which PlayerBar watches; a restored queue stays at 0, so it waits
 * for the play button. Playback position is reported to the backend every 2s
 * (drives buffer-ahead). Queue, current index, volume and repeat persist in
 * localStorage (amp.queue.v1); the next song is prefetched near the end of this one.
 */

import { useSyncExternalStore } from "react";
import { api, type Song } from "./api";
import { loadQueue, saveQueue } from "./player/persistence";
import { shouldPrefetch } from "./player/prefetch";
import * as Q from "./player/queue";

const PERSIST_DEBOUNCE_MS = 500;
const RESTART_THRESHOLD_MS = 3000;

// ---------------------------------------------------------------------------
// Queue state
// ---------------------------------------------------------------------------

export interface QueueState extends Q.QueueModel {
  currentSong: Song | null;
  playToken: number;
  isPlaying: boolean;
  positionMs: number;
  durationMs: number;
  volume: number;
}

type Listener = () => void;

class StateStore {
  private state: QueueState = {
    ...Q.emptyQueue,
    currentSong: null,
    playToken: 0,
    isPlaying: false,
    positionMs: 0,
    durationMs: 0,
    volume: 1.0,
  };

  private listeners: Set<Listener> = new Set();
  private audio: HTMLAudioElement | null = null;
  private positionTimer: ReturnType<typeof setInterval> | null = null;
  private persistTimer: ReturnType<typeof setTimeout> | null = null;
  private prefetchedFor: string | null = null; // current song id whose successor was prefetched

  constructor() {
    const saved = loadQueue();
    if (saved) {
      const song = saved.currentIndex >= 0 ? saved.songs[saved.currentIndex] : null;
      this.state = {
        ...this.state,
        items: Q.makeItems(saved.songs),
        currentIndex: saved.currentIndex,
        currentSong: song,
        durationMs: song?.duration_ms ?? 0,
        volume: saved.volume,
        repeat: saved.repeat,
      };
    }
  }

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
    const prev = this.state;
    this.state = { ...prev, ...partial };
    if (this.state.items !== prev.items || this.state.currentIndex !== prev.currentIndex
        || this.state.volume !== prev.volume || this.state.repeat !== prev.repeat) {
      this.schedulePersist();
    }
    this.emit();
  }

  private schedulePersist(): void {
    if (this.persistTimer) clearTimeout(this.persistTimer);
    this.persistTimer = setTimeout(() => {
      this.persistTimer = null;
      const { items, currentIndex, volume, repeat } = this.state;
      saveQueue({ songs: items.map((i) => i.song), currentIndex, volume, repeat });
    }, PERSIST_DEBOUNCE_MS);
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
      audio.volume = this.state.volume;
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

  /** Apply a model change. If the current item changed, it loads when `autoplay`. */
  private apply(q: Q.QueueModel, autoplay: boolean): void {
    const prevUid = this.state.items[this.state.currentIndex]?.uid;
    const song = q.items[q.currentIndex]?.song ?? null;
    const changed = q.items[q.currentIndex]?.uid !== prevUid;
    this.setState({
      ...q,
      currentSong: song,
      ...(changed ? { positionMs: 0, durationMs: song?.duration_ms ?? 0 } : {}),
      ...(changed && autoplay && song ? { playToken: this.state.playToken + 1 } : {}),
    });
  }

  private model(): Q.QueueModel {
    return this.state;
  }

  /** Replace the queue with a list and play from `startIndex`. */
  playList(songs: Song[], startIndex = 0): void {
    if (songs.length === 0) return;
    const sameSong = this.state.currentSong?.id === songs[startIndex].id;
    const q = Q.loadList(this.model(), songs, startIndex);
    if (sameSong && this.audio?.getAttribute("src")) {
      // Already loaded: keep the position instead of restarting the song
      this.setState({ ...q, currentSong: songs[startIndex] });
      this.audio.play().catch(() => {});
      return;
    }
    this.setState({ ...q, currentSong: songs[startIndex], positionMs: 0,
      durationMs: songs[startIndex].duration_ms, playToken: this.state.playToken + 1 });
  }

  /** Replace the queue with a list in random order. */
  shuffleList(songs: Song[]): void {
    if (songs.length === 0) return;
    this.state = { ...this.state, shuffle: true };
    this.playList(songs, Math.floor(Math.random() * songs.length));
  }

  playNext(songs: Song[]): void {
    const wasEmpty = this.state.items.length === 0;
    this.apply(Q.insertNext(this.model(), songs), wasEmpty);
  }

  addToQueue(songs: Song[]): void {
    const wasEmpty = this.state.items.length === 0;
    this.apply(Q.append(this.model(), songs), wasEmpty);
  }

  removeItem(uid: number): void {
    this.apply(Q.remove(this.model(), uid), this.state.isPlaying);
  }

  moveItem(from: number, to: number): void {
    this.apply(Q.move(this.model(), from, to), false);
  }

  clearQueue(keepCurrent = false): void {
    this.apply(Q.clear(this.model(), keepCurrent), false);
  }

  jumpTo(uid: number): void {
    const index = this.state.items.findIndex((i) => i.uid === uid);
    if (index >= 0) this.goTo(index);
  }

  toggleShuffle(): void {
    this.apply(Q.setShuffle(this.model(), !this.state.shuffle), false);
  }

  cycleRepeat(): void {
    this.setState({ repeat: Q.cycleRepeat(this.state.repeat) });
  }

  private goTo(index: number): void {
    const song = this.state.items[index].song;
    this.setState({
      currentIndex: index,
      currentSong: song,
      positionMs: 0,
      durationMs: song.duration_ms,
      playToken: this.state.playToken + 1,
    });
  }

  next(manual = true): Song | null {
    const index = Q.nextIndex(this.model(), manual);
    if (index === null) return null;
    this.goTo(index);
    return this.state.currentSong;
  }

  previous(): Song | null {
    // If more than 3s into the song, restart it
    if (this.state.positionMs > RESTART_THRESHOLD_MS) {
      this.setAudioTime(0);
      return this.state.currentSong;
    }
    const index = Q.previousIndex(this.model());
    if (index === null) return null;
    this.goTo(index);
    return this.state.currentSong;
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
    if (!this.audio) return;
    const positionMs = Math.floor(this.audio.currentTime * 1000);
    this.setState({ positionMs });
    this.maybePrefetchNext(positionMs);
  };

  /** Once per current song: resolve the next song and queue its first segments (LOW). */
  private maybePrefetchNext(positionMs: number): void {
    const { currentSong, items, currentIndex, durationMs } = this.state;
    if (!currentSong || this.prefetchedFor === currentSong.id) return;
    const next = items[currentIndex + 1]?.song;
    if (!next || !shouldPrefetch(positionMs, durationMs)) return;
    this.prefetchedFor = currentSong.id;
    api.bufferAhead(next.id, "prefetch").catch((e) => {
      console.warn(`Prefetch of ${next.id} failed:`, e);
    });
  }

  private _onEnded = (): void => {
    this.setState({ isPlaying: false });
    // The audio src change is handled by the PlayerBar component (playToken)
    this.next(false);
  };

  private _onPlay = (): void => {
    this.setState({ isPlaying: true });
  };

  private _onPause = (): void => {
    this.setState({ isPlaying: false });
  };

  private _onLoadedMetadata = (): void => {
    if (this.audio && Number.isFinite(this.audio.duration)) {
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
