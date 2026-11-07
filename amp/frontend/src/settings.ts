/**
 * User settings (theme, accent, fade between songs), kept in localStorage
 * (amp.settings.v1) and applied to the document as soon as this module loads,
 * so the first render already has the right colours.
 */

import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light" | "system";

export interface Settings {
  theme: Theme;
  accent: string; // #rrggbb
  fadeSec: number; // 0 = off, up to MAX_FADE_SEC
}

export const SETTINGS_KEY = "amp.settings.v1";
export const MAX_FADE_SEC = 10;
export const DEFAULT_SETTINGS: Settings = { theme: "dark", accent: "#ff4d67", fadeSec: 0 };
export const ACCENT_PRESETS = ["#ff4d67", "#ff7ab8", "#b47cff", "#5aa9ff", "#2ec4b6", "#2ecc71", "#f0a500", "#ff7a45"];

const HEX = /^#[0-9a-f]{6}$/i;

/** Validate what localStorage holds; anything wrong falls back to the default for that field. */
export function parseSettings(raw: string | null): Settings {
  let data: Partial<Record<keyof Settings, unknown>> = {};
  try {
    const parsed = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object") data = parsed;
  } catch {
    // corrupt: defaults
  }
  const theme = data.theme === "light" || data.theme === "system" || data.theme === "dark" ? data.theme : DEFAULT_SETTINGS.theme;
  const accent = typeof data.accent === "string" && HEX.test(data.accent) ? data.accent.toLowerCase() : DEFAULT_SETTINGS.accent;
  const fade = typeof data.fadeSec === "number" && Number.isFinite(data.fadeSec) ? data.fadeSec : DEFAULT_SETTINGS.fadeSec;
  return { theme, accent, fadeSec: Math.min(MAX_FADE_SEC, Math.max(0, Math.round(fade * 2) / 2)) };
}

/** Text on the accent: white while it keeps the 3:1 contrast bold UI text needs, else near-black. */
export function onAccentColor(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return 1.05 / (luminance + 0.05) >= 3 ? "#ffffff" : "#111114";
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

function read(): Settings {
  try {
    return parseSettings(localStorage.getItem(SETTINGS_KEY));
  } catch {
    return DEFAULT_SETTINGS;
  }
}

let current: Settings = read();
const listeners = new Set<() => void>();
const systemDark = typeof window !== "undefined" ? window.matchMedia?.("(prefers-color-scheme: dark)") : undefined;

function apply(s: Settings): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const theme = s.theme === "system" ? (systemDark?.matches === false ? "light" : "dark") : s.theme;
  root.dataset.theme = theme;
  root.style.setProperty("--accent", s.accent);
  root.style.setProperty("--on-accent", onAccentColor(s.accent));
}

systemDark?.addEventListener?.("change", () => apply(current));
apply(current);

export function getSettings(): Settings {
  return current;
}

export function updateSettings(patch: Partial<Settings>): void {
  current = parseSettings(JSON.stringify({ ...current, ...patch }));
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(current));
  } catch {
    // still applied for this session
  }
  apply(current);
  for (const l of listeners) l();
}

export function resetSettings(): void {
  updateSettings(DEFAULT_SETTINGS);
}

export function useSettings(): Settings {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => current,
  );
}
