import { describe, expect, it } from "vitest";
import { fadeGain } from "./player/fade";
import { DEFAULT_SETTINGS, onAccentColor, parseSettings } from "./settings";

describe("parseSettings", () => {
  it("round-trips valid settings", () => {
    const s = { theme: "light", accent: "#5aa9ff", fadeSec: 4.5 };
    expect(parseSettings(JSON.stringify(s))).toEqual(s);
  });

  it("falls back per field on junk", () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("{not json")).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings(JSON.stringify({ theme: "neon", accent: "red", fadeSec: "3" }))).toEqual(DEFAULT_SETTINGS);
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
