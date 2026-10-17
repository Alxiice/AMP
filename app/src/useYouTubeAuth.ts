import { useCallback, useEffect, useState } from "react";

import { invoke } from "@tauri-apps/api/core";

const API = "http://127.0.0.1:8000/api";

export type AuthState = "signed_out" | "signed_in" | "expired";

export interface AuthStatus {
  state: AuthState;
  is_authenticated: boolean;
  account: { accountName?: string; accountPhotoUrl?: string } | null;
}

interface TauriCookie {
  name: string;
  value: string;
  domain?: string;
}

const SIGNED_OUT: AuthStatus = { state: "signed_out", is_authenticated: false, account: null };

/** True when running inside a Tauri webview (window.__TAURI_INTERNALS__ is injected). */
function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export function useYouTubeAuth() {
  const [status, setStatus] = useState<AuthStatus>(SIGNED_OUT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inTauri, setInTauri] = useState(isTauri);

  // On app start: ask the backend, and have it check with YouTube that the saved session still works.
  useEffect(() => {
    api<AuthStatus>("/auth/status?verify=true").then(setStatus).catch(() => setStatus(SIGNED_OUT));
  }, []);

  const run = useCallback(async (fn: () => Promise<AuthStatus>) => {
    setBusy(true);
    setError(null);

    try {
      setStatus(await fn());
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg !== "cancelled") setError(msg); // closing the window is not an error
    } finally {
      setBusy(false);
    }
  }, []);

  /** Main path: sign-in window -> cookies -> backend. No copy/paste. */
  const login = useCallback(
    () =>
      run(async () => {
        if (!isTauri()) {
          throw new Error(
            "Sign-in window requires the Tauri desktop app. Use browser import instead (see below)."
          );
        }
        const cookies = await invoke<TauriCookie[]>("youtube_login");
        return api<AuthStatus>("/auth/cookies", { method: "POST", body: JSON.stringify({ cookies }) });
      }),
    [run],
  );

  /** Optional shortcut: reuse a login that already exists in an installed browser. */
  const importFromBrowser = useCallback(
    (browser: "firefox" | "chrome" | "edge" | "brave" | "safari") =>
      run(() => api<AuthStatus>("/auth/import-browser", { method: "POST", body: JSON.stringify({ browser }) })),
    [run],
  );

  const logout = useCallback(() => run(() => api<AuthStatus>("/auth/logout", { method: "POST" })), [run]);

  return { status, busy, error, login, importFromBrowser, logout, inTauri };
}
