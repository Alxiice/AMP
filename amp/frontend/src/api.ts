/**
 * Typed fetch wrapper with optional Bearer token auth.
 * All API calls go to http://127.0.0.1:8000/api.
 * If no token is set, requests are sent without Authorization header
 * (backend runs in open mode — search and streaming work without auth).
 */

const BASE_URL = "http://127.0.0.1:8000";

let authToken: string = "";

export function setAuthToken(token: string): void {
  authToken = token;
}

export function getAuthToken(): string {
  return authToken;
}

export function clearAuthToken(): void {
  authToken = "";
}

// ---------------------------------------------------------------------------
// Types (mirror backend response shapes)
// ---------------------------------------------------------------------------

export interface Song {
  id: string;
  title: string;
  artist: string;
  album: string;
  duration_ms: number;
  thumbnail_url: string;
  is_explicit: boolean;
}

export interface SegmentStatus {
  index: number; // -1 = init
  status: "pending" | "downloading" | "downloaded" | "error";
  duration_ms: number;
  size_bytes: number;
}

export interface StreamInfoSummary {
  song_id: string;
  title: string;
  duration_ms: number;
  mime_type: string;
  init_range: [number, number];
  total_bytes: number;
  is_dash: boolean;
  segment_count: number;
  segments: Array<{
    index: number;
    byte_start: number;
    byte_end: number;
    duration_ms: number;
  }>;
}

/** POST /api/stream/{id}/play — the stream is resolved when this returns. */
export interface PlayResponse {
  message: string; // "playback started" | "superseded"
  song_id: string;
  duration_ms: number;
  mime_type: string;
  segment_count: number;
  is_dash: boolean;
  epoch: number;
  cached_ahead: boolean; // init + first segment already on disk
}

export interface PlaybackState {
  song_id: string;
  current_segment_index: number;
  position_ms: number;
  is_playing: boolean;
  volume: number;
  epoch: number;
  last_updated: number;
}

export interface AuthStatus {
  state: "signed_out" | "signed_in" | "expired";
  is_authenticated: boolean;
  account: Record<string, unknown> | null;
  /** The stored session was migrated from a v1 file holding a whole browser jar: sign in again. */
  migrated_from_full_jar?: boolean;
}

export interface TauriCookie {
  name: string;
  value: string;
  domain?: string;
}

export interface HealthStatus {
  status: string;
  services: Record<string, string>;
}

export interface CacheInfo {
  total_bytes: number;
  total_mb: number;
  max_mb: number;
  usage_pct: number;
  file_count: number;
  song_count: number;
  songs: Array<{ song_id: string; size_bytes: number; file_count: number }>;
}

export interface PlaylistInfo {
  id: string;
  name: string;
  owner: string;
  thumbnail_url: string;
  song_count: number;
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  status: number;
  /** Backend error code ({detail: {code, message}}), null for string details. */
  code: string | null;
  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** {detail: {code, message}} (streaming routes) or {detail: "..."} (others). */
function parseErrorBody(status: number, text: string): ApiError {
  try {
    const detail = JSON.parse(text)?.detail;
    if (detail && typeof detail === "object" && typeof detail.code === "string") {
      return new ApiError(status, detail.message || detail.code, detail.code);
    }
    if (typeof detail === "string") return new ApiError(status, detail);
  } catch {
    // not JSON
  }
  return new ApiError(status, text);
}

// Called after a 401 from /api/user/* so the session badge can catch up (authSession.ts)
let onUserUnauthorized: (() => void) | null = null;

export function setUserUnauthorizedHandler(fn: (() => void) | null): void {
  onUserUnauthorized = fn;
}

async function fetchApi<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };

  // Only attach Authorization header if a token is configured
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  // Only set Content-Type for non-GET requests with a body
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const resp = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!resp.ok) {
    if (resp.status === 401 && path.startsWith("/api/user/")) onUserUnauthorized?.();
    const text = await resp.text().catch(() => resp.statusText);
    throw parseErrorBody(resp.status, text);
  }

  // Handle empty responses
  const contentType = resp.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return resp.json() as Promise<T>;
  }
  return resp.text() as unknown as Promise<T>;
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

export const api = {
  // --- Health ---
  health: () => fetchApi<HealthStatus>("/api/health", { headers: {} }),

  // --- Search & Library ---
  search: (q: string, type = "songs", limit = 20) =>
    fetchApi<Song[]>(`/api/search?q=${encodeURIComponent(q)}&type=${type}&limit=${limit}`),

  getSong: (id: string) => fetchApi<Song>(`/api/song/${id}`),
  getArtist: (id: string) => fetchApi<Record<string, unknown>>(`/api/artist/${id}`),
  getAlbum: (id: string) => fetchApi<Record<string, unknown>>(`/api/album/${id}`),
  getPlaylist: (id: string) => fetchApi<Record<string, unknown>>(`/api/playlist/${id}`),
  getUserPlaylists: () => fetchApi<PlaylistInfo[]>("/api/user/playlists"),
  getUserLikes: () => fetchApi<Song[]>("/api/user/likes"),

  // --- Streaming ---
  getStreamInfo: (id: string) => fetchApi<StreamInfoSummary>(`/api/stream/info/${id}`),
  getStreamAudioUrl: (id: string) => `${BASE_URL}/api/stream/${id}/audio`,
  getSegmentStatuses: (id: string) =>
    fetchApi<{ segments: SegmentStatus[] }>(`/api/stream/${id}/chunks`),

  playSong: (id: string, signal?: AbortSignal) =>
    fetchApi<PlayResponse>(`/api/stream/${id}/play`, { method: "POST", signal }),

  pause: () => fetchApi<{ message: string }>("/api/stream/pause", { method: "POST" }),
  resume: () => fetchApi<{ message: string }>("/api/stream/resume", { method: "POST" }),
  stop: () => fetchApi<{ message: string }>("/api/stream/stop", { method: "POST" }),

  updatePosition: (positionMs: number) =>
    fetchApi<{ message: string }>(`/api/stream/position?position_ms=${positionMs}`, {
      method: "POST",
    }),

  seek: (positionMs: number) =>
    fetchApi<{ message: string; segment_index: number }>(`/api/stream/seek?position_ms=${positionMs}`, {
      method: "POST",
    }),

  bufferAhead: (id: string, mode: "current" | "prefetch" = "current") =>
    fetchApi<{ message: string }>(`/api/stream/buffer/${id}?mode=${mode}`, { method: "POST" }),

  getPlaybackState: () => fetchApi<PlaybackState>("/api/stream/playback-state"),
  getStreamLogs: (n = 200) =>
    fetchApi<{ lines: string[] }>(`/api/stream/logs?n=${n}`),
  getCacheInfo: () => fetchApi<CacheInfo>("/api/stream/cache-info"),

  // --- Auth ---
  getAuthStatus: (verify = false) =>
    fetchApi<AuthStatus>(`/api/auth/status?verify=${verify}`),

  setCookies: (cookieHeader: string) =>
    fetchApi<{ state: string; cookie_count: number }>("/api/auth/cookies", {
      method: "POST",
      body: JSON.stringify({ cookie_header: cookieHeader }),
    }),

  // Firefox only: yt-dlp can't decrypt Chrome/Edge cookies on Windows
  importFirefox: () =>
    fetchApi<{ state: string; cookie_count: number }>(
      "/api/auth/import-browser?browser=firefox",
      { method: "POST" },
    ),

  setTauriCookies: (cookies: TauriCookie[]) =>
    fetchApi<{ state: string; cookie_count: number }>("/api/auth/tauri-cookies", {
      method: "POST",
      body: JSON.stringify({ cookies }),
    }),

  logout: () =>
    fetchApi<{ message: string }>("/api/auth/logout", { method: "POST" }),

  // --- Logs ---
  getLogs: (n = 500) => fetchApi<{ lines: string[] }>(`/api/logs?n=${n}`),
  postLogs: (lines: string[]) =>
    fetchApi<{ message: string }>("/api/logs", {
      method: "POST",
      body: JSON.stringify({ lines }),
    }),
  clearLogs: () =>
    fetchApi<{ message: string }>("/api/logs", { method: "DELETE" }),
};

export { ApiError };
