import { describe, expect, it } from "vitest";
import type { Song } from "../api";
import {
  append, clear, cycleRepeat, emptyQueue, insertNext, loadList, move, nextIndex, previousIndex,
  remove, setShuffle, type QueueModel,
} from "./queue";

const song = (id: string): Song => ({
  id, title: id, artist: "", album: "", duration_ms: 1000, thumbnail_url: "", is_explicit: false,
});
const songs = (ids: string) => ids.split("").map(song);
const order = (q: QueueModel) => q.items.map((i) => i.song.id).join("");
const current = (q: QueueModel) => q.items[q.currentIndex]?.song.id;
const reverseRng = () => 0; // deterministic, moves items around

describe("queue edits", () => {
  it("inserts after the current song and appends at the end", () => {
    let q = loadList(emptyQueue, songs("abc"), 1);
    q = insertNext(q, songs("x"));
    q = append(q, songs("y"));
    expect(order(q)).toBe("abxcy");
    expect(current(q)).toBe("b");
  });

  it("selects the first song added to an empty queue", () => {
    expect(current(append(emptyQueue, songs("ab")))).toBe("a");
    expect(current(insertNext(emptyQueue, songs("ab")))).toBe("a");
  });

  it("allows duplicates and removes only the targeted one", () => {
    let q = append(emptyQueue, songs("aa"));
    expect(q.items[0].uid).not.toBe(q.items[1].uid);
    q = remove(q, q.items[1].uid);
    expect(order(q)).toBe("a");
  });

  it("keeps the current song when removing around it", () => {
    let q = loadList(emptyQueue, songs("abc"), 1);
    q = remove(q, q.items[0].uid);
    expect(current(q)).toBe("b");
    q = remove(q, q.items[0].uid); // the current one: c takes its place
    expect(current(q)).toBe("c");
    q = remove(q, q.items[0].uid);
    expect(q.currentIndex).toBe(-1);
  });

  it("selects the new last song when the current tail is removed", () => {
    const q = loadList(emptyQueue, songs("ab"), 1);
    expect(current(remove(q, q.items[1].uid))).toBe("a");
  });

  it("moves items and follows the current song", () => {
    const q = move(loadList(emptyQueue, songs("abcd"), 1), 1, 3);
    expect(order(q)).toBe("acdb");
    expect(q.currentIndex).toBe(3);
    const r = loadList(emptyQueue, songs("ab"), 0);
    expect(move(r, 0, 5)).toBe(r);
  });

  it("clears, optionally keeping the current song", () => {
    const q = loadList(emptyQueue, songs("abc"), 1);
    expect(clear(q).currentIndex).toBe(-1);
    const kept = clear(q, true);
    expect(order(kept)).toBe("b");
    expect(kept.currentIndex).toBe(0);
  });
});

describe("shuffle", () => {
  it("only reorders upcoming songs and restores the original order", () => {
    const q = loadList(emptyQueue, songs("abcde"), 1);
    const on = setShuffle(q, true, reverseRng);
    expect(order(on).slice(0, 2)).toBe("ab");
    expect(order(on)).not.toBe("abcde");
    expect([...order(on)].sort().join("")).toBe("abcde");
    const off = setShuffle(on, false);
    expect(order(off)).toBe("abcde");
    expect(current(off)).toBe("b");
  });

  it("restores the original order around songs added while shuffled", () => {
    let q = setShuffle(loadList(emptyQueue, songs("abc"), 0), true, reverseRng);
    q = insertNext(q, songs("x"));
    q = append(q, songs("y"));
    expect(order(setShuffle(q, false))).toBe("axbcy");
  });

  it("starts a list on the chosen song when shuffle is on", () => {
    const q = loadList({ ...emptyQueue, shuffle: true }, songs("abcd"), 2, reverseRng);
    expect(current(q)).toBe("c");
    expect(q.currentIndex).toBe(0);
    expect(order(setShuffle(q, false))).toBe("abcd");
  });
});

describe("navigation", () => {
  const at = (index: number, repeat: QueueModel["repeat"]) =>
    ({ ...loadList(emptyQueue, songs("abc"), index), repeat });

  it("stops at the ends without repeat", () => {
    expect(nextIndex(at(0, "off"), false)).toBe(1);
    expect(nextIndex(at(2, "off"), false)).toBeNull();
    expect(previousIndex(at(0, "off"))).toBeNull();
  });

  it("wraps with repeat all", () => {
    expect(nextIndex(at(2, "all"), false)).toBe(0);
    expect(previousIndex(at(0, "all"))).toBe(2);
  });

  it("repeat one holds only until a manual next", () => {
    expect(nextIndex(at(1, "one"), false)).toBe(1);
    expect(nextIndex(at(1, "one"), true)).toBe(2);
  });

  it("handles an empty queue", () => {
    expect(nextIndex(emptyQueue, true)).toBeNull();
    expect(previousIndex(emptyQueue)).toBeNull();
  });

  it("cycles repeat modes", () => {
    expect(cycleRepeat(cycleRepeat(cycleRepeat("off")))).toBe("off");
  });
});
