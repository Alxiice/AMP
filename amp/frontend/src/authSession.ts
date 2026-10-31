/**
 * YouTube session state, shared by the sidebar badge, Auth, Library and Playlists.
 *
 * Polled every 60 s (in-flight guard, P12) and refreshed after any 401 from
 * /api/user/* (api.ts calls the handler registered below).
 */

import { useSyncExternalStore } from "react";
import { api, setUserUnauthorizedHandler, type AuthStatus } from "./api";

const POLL_INTERVAL_MS = 60_000;

let status: AuthStatus | null = null;
let inFlight = false;
let pollTimer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

/** Fetch /api/auth/status. `verify` asks the backend to check the session with YouTube. */
export async function refreshAuthStatus(verify = false): Promise<AuthStatus | null> {
  inFlight = true;
  try {
    status = await api.getAuthStatus(verify);
    emit();
  } catch {
    // backend not reachable: keep the last known state
  } finally {
    inFlight = false;
  }
  return status;
}

export function startAuthPolling(): void {
  if (pollTimer) return;
  void refreshAuthStatus();
  pollTimer = setInterval(() => {
    if (!inFlight) void refreshAuthStatus();
  }, POLL_INTERVAL_MS);
}

export function stopAuthPolling(): void {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

setUserUnauthorizedHandler(() => {
  if (!inFlight) void refreshAuthStatus();
});

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** null until the first status arrives. */
export function useAuthStatus(): AuthStatus | null {
  return useSyncExternalStore(subscribe, () => status);
}

/** Sidebar badge text; the class matches .auth-status-badge.<state>. */
export function sessionLabel(s: AuthStatus | null): string {
  switch (s?.state) {
    case "signed_in":
      return "Signed in";
    case "expired":
      return "Session expired — reconnect";
    case "signed_out":
      return "Signed out";
    default:
      return "Session: unknown";
  }
}
