/**
 * Play queue model: pure functions over an immutable value, no audio or React.
 *
 * Items carry a uid because the same song may be queued twice. Shuffle reorders
 * `items` for real (what you see is what plays); `original` remembers the order
 * to go back to when it is switched off.
 */

import type { Song } from "../api";

export type RepeatMode = "off" | "all" | "one";

export interface QueueItem {
  uid: number;
  song: Song;
}

export interface QueueModel {
  items: QueueItem[];
  currentIndex: number; // -1 = nothing selected
  shuffle: boolean;
  repeat: RepeatMode;
  original: number[] | null; // uids in unshuffled order, while shuffle is on
}

export const emptyQueue: QueueModel = { items: [], currentIndex: -1, shuffle: false, repeat: "off", original: null };

let nextUid = 1;

export function makeItems(songs: Song[]): QueueItem[] {
  return songs.map((song) => ({ uid: nextUid++, song }));
}

function shuffled<T>(list: T[], rng: () => number): T[] {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Replace the queue with a list, starting at `start`. With shuffle on, the rest plays in random order after it. */
export function loadList(q: QueueModel, songs: Song[], start: number, rng = Math.random): QueueModel {
  const items = makeItems(songs);
  if (!q.shuffle || items.length === 0) {
    return { ...q, items, currentIndex: items.length ? start : -1, original: null };
  }
  const rest = items.filter((_, i) => i !== start);
  return {
    ...q,
    items: [items[start], ...shuffled(rest, rng)],
    currentIndex: 0,
    original: items.map((i) => i.uid),
  };
}

/** Insert right after the current song. An empty queue selects the first one inserted. */
export function insertNext(q: QueueModel, songs: Song[]): QueueModel {
  const added = makeItems(songs);
  const at = q.currentIndex + 1;
  const items = [...q.items.slice(0, at), ...added, ...q.items.slice(at)];
  let original = q.original;
  if (original) {
    const cur = q.items[q.currentIndex]?.uid;
    const pos = cur === undefined ? -1 : original.indexOf(cur);
    original = [...original.slice(0, pos + 1), ...added.map((i) => i.uid), ...original.slice(pos + 1)];
  }
  return { ...q, items, original, currentIndex: q.currentIndex < 0 && items.length ? 0 : q.currentIndex };
}

export function append(q: QueueModel, songs: Song[]): QueueModel {
  const added = makeItems(songs);
  const items = [...q.items, ...added];
  return {
    ...q,
    items,
    original: q.original && [...q.original, ...added.map((i) => i.uid)],
    currentIndex: q.currentIndex < 0 && items.length ? 0 : q.currentIndex,
  };
}

/** Removing the current song selects the one that took its place (the last one, at the tail). */
export function remove(q: QueueModel, uid: number): QueueModel {
  const at = q.items.findIndex((i) => i.uid === uid);
  if (at < 0) return q;
  const items = q.items.filter((i) => i.uid !== uid);
  let currentIndex = q.currentIndex;
  if (at < currentIndex) currentIndex--;
  else if (at === currentIndex && currentIndex >= items.length) currentIndex = items.length - 1;
  return { ...q, items, currentIndex, original: q.original && q.original.filter((u) => u !== uid) };
}

/** Move an item to index `to`; the current song stays current. */
export function move(q: QueueModel, from: number, to: number): QueueModel {
  if (from === to || from < 0 || from >= q.items.length || to < 0 || to >= q.items.length) return q;
  const cur = q.items[q.currentIndex]?.uid;
  const items = [...q.items];
  const [item] = items.splice(from, 1);
  items.splice(to, 0, item);
  return { ...q, items, currentIndex: items.findIndex((i) => i.uid === cur) };
}

/** Empty the queue, or with keepCurrent only drop everything but the current song. */
export function clear(q: QueueModel, keepCurrent = false): QueueModel {
  const cur = q.items[q.currentIndex];
  if (keepCurrent && cur) return { ...q, items: [cur], currentIndex: 0, original: q.original && [cur.uid] };
  return { ...q, items: [], currentIndex: -1, original: null };
}

export function setShuffle(q: QueueModel, on: boolean, rng = Math.random): QueueModel {
  if (on === q.shuffle) return q;
  if (on) {
    const upcoming = q.items.slice(q.currentIndex + 1);
    return {
      ...q,
      shuffle: true,
      original: q.items.map((i) => i.uid),
      items: [...q.items.slice(0, q.currentIndex + 1), ...shuffled(upcoming, rng)],
    };
  }
  const cur = q.items[q.currentIndex]?.uid;
  const rank = new Map((q.original ?? []).map((uid, i) => [uid, i]));
  const items = [...q.items].sort((a, b) => (rank.get(a.uid) ?? Infinity) - (rank.get(b.uid) ?? Infinity));
  return { ...q, shuffle: false, original: null, items, currentIndex: items.findIndex((i) => i.uid === cur) };
}

export function cycleRepeat(mode: RepeatMode): RepeatMode {
  return mode === "off" ? "all" : mode === "all" ? "one" : "off";
}

/**
 * Index to play after the current song, null at the end of the queue.
 * "Repeat one" only holds when the song ended by itself: a manual next still moves on.
 */
export function nextIndex(q: QueueModel, manual: boolean): number | null {
  if (q.items.length === 0) return null;
  if (q.repeat === "one" && !manual) return q.currentIndex;
  if (q.currentIndex < q.items.length - 1) return q.currentIndex + 1;
  return q.repeat === "off" ? null : 0;
}

export function previousIndex(q: QueueModel): number | null {
  if (q.items.length === 0) return null;
  if (q.currentIndex > 0) return q.currentIndex - 1;
  return q.repeat === "off" ? null : q.items.length - 1;
}
