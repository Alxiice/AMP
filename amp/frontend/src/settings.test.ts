import { describe, expect, it } from "vitest";
import { crossfadeDue, fadeGain } from "./player/fade";
import { normalizationGain } from "./player/normalize";
import { DEFAULT_SETTINGS, onAccentColor, parseSettings } from "./settings";

describe("parseSettings", () => {
  it("round-trips valid settings", () => {
    const s = { theme: "light", accent: "#5aa9ff", fadeSec: 4.5, normalize: true };
    expect(parseSettings(JSON.stringify(s))).toEqual(s);
  });

  it("falls back per field on junk", () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("{not json")).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings(JSON.stringify({ theme: "neon", accent: "red", fadeSec: "3", normalize: "yes" }))).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings(JSON.stringify({ theme: "system" }))).toEqual({ ...DEFAULT_SETTINGS, theme: "system" });
  });

  it("clamps the fade to 0-10 s in half seconds", () => {
    expect(parseSettings(JSON.stringify({ fadeSec: 42 })).fadeSec).toBe(10);
    expect(parseSettings(JSON.stringify({ fadeSec: -1 })).fadeSec).toBe(0);
    expect(parseSettings(JSON.stringify({ fadeSec: 2.3 })).fadeSec).toBe(2.5);
  });

  it("normalises the accent to lower case", () => {
    expect(parseSettings(JSON.stringify({ accent: "#FF7AB8" })).accent).toBe("#ff7ab8");
  });
});

describe("onAccentColor", () => {
  it("dark text on light accents, white on dark ones", () => {
    expect(onAccentColor("#f0a500")).toBe("#111114");
    expect(onAccentColor("#2ecc71")).toBe("#111114");
    expect(onAccentColor("#ff4d67")).toBe("#ffffff"); // the default keeps white text (3.2:1)
    expect(onAccentColor("#b47cff")).toBe("#111114");
    expect(onAccentColor("#3c3489")).toBe("#ffffff");
  });
});

describe("fadeGain", () => {
  it("is 1 when off", () => {
    expect(fadeGain(0, 200, 0)).toBe(1);
    expect(fadeGain(199.9, 200, 0)).toBe(1);
  });

  it("fades in at the start and out at the end", () => {
    expect(fadeGain(0, 200, 4)).toBe(0);
    expect(fadeGain(2, 200, 4)).toBe(0.5);
    expect(fadeGain(100, 200, 4)).toBe(1);
    expect(fadeGain(198, 200, 4)).toBe(0.5);
    expect(fadeGain(200, 200, 4)).toBe(0);
  });

  it("fades in only when the duration is unknown, never above 1 or below 0", () => {
    expect(fadeGain(1, NaN, 4)).toBe(0.25);
    expect(fadeGain(50, NaN, 4)).toBe(1);
    expect(fadeGain(5, 3, 4)).toBe(0);
  });
});

describe("crossfadeDue", () => {
  it("starts the next song in the last fadeSec seconds", () => {
    expect(crossfadeDue(195.9, 200, 4)).toBe(false);
    expect(crossfadeDue(196, 200, 4)).toBe(true);
    expect(crossfadeDue(199, 200, 4)).toBe(true);
  });

  it("never when off, without a duration, or for songs shorter than the fade", () => {
    expect(crossfadeDue(199, 200, 0)).toBe(false);
    expect(crossfadeDue(199, NaN, 4)).toBe(false);
    expect(crossfadeDue(3, 4, 4)).toBe(false);
  });
});

describe("normalizationGain", () => {
  it("brings loud tracks down to the -6 dB target", () => {
    expect(normalizationGain(0)).toBeCloseTo(0.501, 3);
    expect(normalizationGain(-3)).toBeCloseTo(0.708, 3);
    expect(normalizationGain(-6)).toBe(1);
    expect(normalizationGain(4, 0)).toBeCloseTo(0.631, 3);
  });

  it("leaves quieter or unknown tracks alone", () => {
    expect(normalizationGain(-9)).toBe(1);
    expect(normalizationGain(null)).toBe(1);
    expect(normalizationGain(undefined)).toBe(1);
    expect(normalizationGain(Number.NaN)).toBe(1);
  });
});
