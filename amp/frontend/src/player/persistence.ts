/**
 * Queue + volume persistence (localStorage key amp.queue.v1).
 *
 * Pure (de)serialisation here; the store does the debounced writes. Anything
 * unexpected in storage is dropped rather than trusted.
 */

import type { Song } from "../api";

export const QUEUE_STORAGE_KEY = "amp.queue.v1";

export interface PersistedQueue {
  songs: Song[];
  currentIndex: number;
  volume: number;
}

export function serializeQueue(q: PersistedQueue): string {
  return JSON.stringify({ songs: q.songs, currentIndex: q.currentIndex, volume: q.volume });
}

function isSong(x: unknown): x is Song {
  const s = x as Partial<Song> | null;
  return !!s && typeof s.id === "string" && /^[A-Za-z0-9_-]{11}$/.test(s.id);
}

function normalizeSong(s: Song): Song {
  return {
    id: s.id,
    title: typeof s.title === "string" ? s.title : "",
    artist: typeof s.artist === "string" ? s.artist : "",
    album: typeof s.album === "string" ? s.album : "",
    duration_ms: Number.isFinite(s.duration_ms) ? s.duration_ms : 0,
    thumbnail_url: typeof s.thumbnail_url === "string" ? s.thumbnail_url : "",
    is_explicit: s.is_explicit === true,
  };
}

/** null when raw is missing or unusable. */
export function parseQueue(raw: string | null): PersistedQueue | null {
  if (!raw) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  const d = data as Partial<PersistedQueue> | null;
  if (!d || !Array.isArray(d.songs)) return null;
  const songs = d.songs.filter(isSong).map(normalizeSong);
  const idx = typeof d.currentIndex === "number" && Number.isInteger(d.currentIndex) ? d.currentIndex : -1;
  const currentIndex = idx >= 0 && idx < songs.length ? idx : songs.length > 0 ? 0 : -1;
  const v = typeof d.volume === "number" && Number.isFinite(d.volume) ? d.volume : 1;
  return { songs, currentIndex, volume: Math.min(1, Math.max(0, v)) };
}

export function loadQueue(): PersistedQueue | null {
  try {
    return parseQueue(localStorage.getItem(QUEUE_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function saveQueue(q: PersistedQueue): void {
  try {
    localStorage.setItem(QUEUE_STORAGE_KEY, serializeQueue(q));
  } catch {
    // storage full or blocked: persistence is a convenience
  }
}
