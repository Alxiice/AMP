import { describe, expect, it } from "vitest";
import type { Song } from "../api";
import { HistoryTracker, MIN_LISTENED_MS, parsePending, type HistoryEntryBody } from "./history";

const song = (id: string): Song => ({
  id, title: "t", artist: "a", album: "", duration_ms: 200_000, thumbnail_url: "", is_explicit: false,
});
const A = song("aaaaaaaaaaa");
const B = song("bbbbbbbbbbb");

function setup() {
  const sent: HistoryEntryBody[] = [];
  const saved: Array<HistoryEntryBody | null> = [];
  const t = new HistoryTracker((e) => sent.push(e), (p) => saved.push(p), () => new Date("2026-11-07T10:00:00Z"));
  return { t, sent, saved };
}

/** Play `song` from `from` to `to` seconds in 0.25 s steps. */
function play(t: HistoryTracker, s: Song, from: number, to: number) {
  for (let pos = from; pos <= to + 1e-9; pos += 0.25) t.tick(s, pos, true, 200_000);
}

describe("HistoryTracker", () => {
  it("counts played time and sends it with the reason", () => {
    const { t, sent } = setup();
    play(t, A, 0, 30);
    t.end("finished");
    expect(sent).toHaveLength(1);
    expect(sent[0].listened_ms).toBe(30_000);
    expect(sent[0].end_reason).toBe("finished");
    expect(sent[0].duration_ms).toBe(200_000);
    expect(sent[0].started_at).toBe("2026-11-07T10:00:00.000Z");
  });

  it("doesn't count seeks, forward or back", () => {
    const { t, sent } = setup();
    play(t, A, 0, 10);
    play(t, A, 100, 110); // jump forward 90 s
    play(t, A, 50, 60);   // jump back
    t.end("skipped");
    expect(sent[0].listened_ms).toBe(30_000);
  });

  it("doesn't count paused updates", () => {
    const { t, sent } = setup();
    play(t, A, 0, 10);
    t.tick(A, 10.5, false, 200_000);
    t.tick(A, 11, false, 200_000);
    play(t, A, 11, 20);
    t.end("stopped");
    expect(sent[0].listened_ms).toBe(19_000); // 0-10 s, then 11-20 s
  });

  it("a new song ends the previous play as skipped", () => {
    const { t, sent } = setup();
    play(t, A, 0, 10);
    play(t, B, 0, 10);
    expect(sent.map((e) => [e.song.id, e.end_reason])).toEqual([[A.id, "skipped"]]);
  });

  it("drops plays shorter than the minimum, and end() without a play is a no-op", () => {
    const { t, sent } = setup();
    play(t, A, 0, MIN_LISTENED_MS / 1000 - 1);
    t.end("skipped");
    t.end("skipped");
    expect(sent).toHaveLength(0);
  });

  it("doesn't start a play while paused", () => {
    const { t, sent } = setup();
    t.tick(A, 0, false, 200_000);
    t.end("stopped");
    expect(sent).toHaveLength(0);
  });

  it("saves the play in progress every 5 s and clears it at the end", () => {
    const { t, saved } = setup();
    play(t, A, 0, 12);
    expect(saved.filter(Boolean).map((p) => p!.listened_ms)).toEqual([5000, 10_000]);
    expect(saved[saved.length - 1]!.end_reason).toBe("closed");
    t.end("finished");
    expect(saved[saved.length - 1]).toBeNull();
  });
});

describe("parsePending", () => {
  it("accepts a saved play and marks it closed", () => {
    const e = { song: A, listened_ms: 12_000, duration_ms: 200_000, started_at: "2026-11-07T10:00:00Z", end_reason: "closed" };
    expect(parsePending(JSON.stringify(e))).toEqual(e);
  });

  it("rejects junk, bad ids and too-short plays", () => {
    expect(parsePending(null)).toBeNull();
    expect(parsePending("{oops")).toBeNull();
    expect(parsePending(JSON.stringify({ song: { id: "x" }, listened_ms: 9000, started_at: "x" }))).toBeNull();
    expect(parsePending(JSON.stringify({ song: A, listened_ms: 100, started_at: "x" }))).toBeNull();
  });
});
