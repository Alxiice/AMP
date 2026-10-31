import { describe, expect, it } from "vitest";
import { ApiError, type Song } from "../api";
import { describeError, describeMediaError } from "./errors";
import { parseQueue, serializeQueue } from "./persistence";
import { shouldPrefetch } from "./prefetch";

const song = (id: string, extra: Partial<Song> = {}): Song => ({
  id, title: "t", artist: "a", album: "", duration_ms: 200_000, thumbnail_url: "", is_explicit: false, ...extra,
});

describe("describeError", () => {
  it("maps backend codes", () => {
    expect(describeError(new ApiError(401, "x", "auth_required"))).toBe("Sign in required for this track");
    expect(describeError(new ApiError(503, "x", "node_missing"))).toBe("Node.js not found. Install it and restart.");
    expect(describeError(new ApiError(404, "x", "unavailable"))).toBe("This track is unavailable");
  });

  it("falls back to the message for unknown codes and string details", () => {
    expect(describeError(new ApiError(418, "teapot", "brew"))).toBe("teapot");
    expect(describeError(new ApiError(500, ""))).toBe("Backend error (HTTP 500)");
  });

  it("recognises autoplay blocks and fetch failures", () => {
    expect(describeError({ name: "NotAllowedError", message: "" })).toContain("Autoplay blocked");
    expect(describeError(new TypeError("Failed to fetch"))).toBe("Backend not reachable");
    expect(describeError(new Error("boom"))).toBe("Play failed: boom");
  });

  it("maps media error codes", () => {
    expect(describeMediaError(2)).toBe("Network error while streaming");
    expect(describeMediaError(undefined)).toBe("Audio error");
  });
});

describe("queue persistence", () => {
  it("round-trips", () => {
    const q = { songs: [song("dQw4w9WgXcQ"), song("BAgTQhR8MLo")], currentIndex: 1, volume: 0.4 };
    expect(parseQueue(serializeQueue(q))).toEqual(q);
  });

  it("rejects junk", () => {
    expect(parseQueue(null)).toBeNull();
    expect(parseQueue("{not json")).toBeNull();
    expect(parseQueue('{"songs": 3}')).toBeNull();
  });

  it("drops invalid songs and clamps index and volume", () => {
    const raw = JSON.stringify({
      songs: [{ id: "../../etc" }, song("dQw4w9WgXcQ", { duration_ms: Number.NaN })], currentIndex: 7, volume: 3,
    });
    const q = parseQueue(raw)!;
    expect(q.songs.map((s) => s.id)).toEqual(["dQw4w9WgXcQ"]);
    expect(q.songs[0].duration_ms).toBe(0);
    expect(q.currentIndex).toBe(0);
    expect(q.volume).toBe(1);
  });

  it("empty queue has no current song", () => {
    expect(parseQueue(JSON.stringify({ songs: [], currentIndex: 0, volume: 0.5 }))).toEqual(
      { songs: [], currentIndex: -1, volume: 0.5 });
  });
});

describe("shouldPrefetch", () => {
  it("fires near the end", () => {
    expect(shouldPrefetch(100_000, 200_000)).toBe(false);
    expect(shouldPrefetch(161_000, 200_000)).toBe(true); // > 80 %
    expect(shouldPrefetch(281_000, 300_000)).toBe(true); // < 20 s left
    expect(shouldPrefetch(239_000, 600_000)).toBe(false);
  });

  it("never fires without a duration or before playback", () => {
    expect(shouldPrefetch(1_000, 0)).toBe(false);
    expect(shouldPrefetch(0, 15_000)).toBe(false);
    expect(shouldPrefetch(1_000, 15_000)).toBe(true); // short song: right away
  });
});
