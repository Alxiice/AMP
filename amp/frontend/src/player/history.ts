/**
 * Listening history tracker: measures how long each play was actually heard.
 *
 * Fed with the audio element's position on every `timeupdate`. Only forward
 * steps shorter than MAX_STEP_SEC count, so seeks don't add (or remove)
 * listening time. A play ends with a reason (finished / skipped / stopped);
 * plays shorter than MIN_LISTENED_MS aren't recorded. The play in progress is
 * saved to localStorage every few seconds, so closing the app doesn't lose it:
 * the next start records it as "closed".
 */

import type { Song } from "../api";

export type EndReason = "finished" | "skipped" | "stopped" | "closed";

export interface HistoryEntryBody {
  song: Song;
  listened_ms: number;
  duration_ms: number;
  started_at: string; // ISO, UTC
  end_reason: EndReason;
}

interface Play {
  song: Song;
  startedAt: string;
  listenedMs: number;
  durationMs: number;
  lastPos: number;
}

export const PENDING_KEY = "amp.history.pending.v1";
export const MIN_LISTENED_MS = 5000;
const MAX_STEP_SEC = 2;      // a larger jump between two timeupdates is a seek
const PERSIST_EVERY_MS = 5000;

export class HistoryTracker {
  private play: Play | null = null;
  private persistedAt = 0;

  constructor(
    private readonly send: (entry: HistoryEntryBody) => void,
    private readonly persist: (play: HistoryEntryBody | null) => void = () => {},
    private readonly now: () => Date = () => new Date(),
  ) {}

  /** Audio position update. Starts a play on the first update while playing. */
  tick(song: Song | null, positionSec: number, playing: boolean, durationMs: number): void {
    if (!song || !Number.isFinite(positionSec)) return;
    if (this.play && this.play.song.id !== song.id) this.end("skipped");
    if (!this.play) {
      if (!playing) return;
      this.play = { song, startedAt: this.now().toISOString(), listenedMs: 0, durationMs, lastPos: positionSec };
      this.persistedAt = 0;
      return;
    }
    const step = positionSec - this.play.lastPos;
    if (playing && step > 0 && step < MAX_STEP_SEC) this.play.listenedMs += step * 1000;
    this.play.lastPos = positionSec;
    if (durationMs > 0) this.play.durationMs = durationMs;
    if (this.play.listenedMs - this.persistedAt >= PERSIST_EVERY_MS) {
      this.persistedAt = this.play.listenedMs;
      this.persist(this.entry("closed"));
    }
  }

  /** End the current play (no-op without one). */
  end(reason: EndReason): void {
    const entry = this.play && this.entry(reason);
    this.play = null;
    this.persist(null);
    if (entry && entry.listened_ms >= MIN_LISTENED_MS) this.send(entry);
  }

  private entry(reason: EndReason): HistoryEntryBody {
    const p = this.play!;
    return {
      song: p.song,
      listened_ms: Math.round(p.listenedMs),
      duration_ms: p.durationMs || p.song.duration_ms || 0,
      started_at: p.startedAt,
      end_reason: reason,
    };
  }
}

/** The play saved by a previous run that didn't end cleanly, if any (validated). */
export function parsePending(raw: string | null): HistoryEntryBody | null {
  try {
    const e = raw ? JSON.parse(raw) : null;
    if (e && typeof e.song?.id === "string" && /^[A-Za-z0-9_-]{11}$/.test(e.song.id)
        && typeof e.listened_ms === "number" && e.listened_ms >= MIN_LISTENED_MS
        && typeof e.started_at === "string") {
      return { ...e, end_reason: "closed" };
    }
  } catch {
    // corrupt: drop it
  }
  return null;
}
