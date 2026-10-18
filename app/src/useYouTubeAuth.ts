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

export interface DebugLog {
  time: string;
  type: "info" | "error" | "request" | "response";
  message: string;
  detail?: string;
}

const SIGNED_OUT: AuthStatus = { state: "signed_out", is_authenticated: false, account: null };

/** True when running inside a Tauri webview (window.__TAURI_INTERNALS__ is injected). */
function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function timestamp(): string {
  return new Date().toLocaleTimeString();
}

async function api<T>(
  path: string,
  init?: RequestInit,
  addLog?: (log: DebugLog) => void,
): Promise<T> {
  const url = `${API}${path}`;
  const method = init?.method ?? "GET";

  addLog?.({
    time: timestamp(),
    type: "request",
    message: `${method} ${url}`,
    detail: init?.body ? String(init.body) : undefined,
  });

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    addLog?.({
      time: timestamp(),
      type: "error",
      message: `Network error: ${method} ${url}`,
      detail: `${msg}\n\nIf you're running Tauri in WSL2 and the backend on Windows,\n127.0.0.1 won't reach it. Use the Windows host IP instead.`,
    });
    throw new Error(`Cannot reach backend at ${API.replace("/api", "")} — ${msg}`);
  }

  const bodyText = await res.text();
  addLog?.({
    time: timestamp(),
    type: "response",
    message: `${res.status} ${method} ${url}`,
    detail: bodyText.slice(0, 500),
  });

  if (!res.ok) {
    let detail: string;
    try {
      const body = JSON.parse(bodyText);
      detail = body.detail ?? bodyText.slice(0, 500);
    } catch {
      detail = bodyText.slice(0, 500) || `HTTP ${res.status}`;
    }
    throw new Error(detail);
  }

  return JSON.parse(bodyText);
}

export function useYouTubeAuth() {
  const [status, setStatus] = useState<AuthStatus>(SIGNED_OUT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inTauri, setInTauri] = useState(isTauri);
  const [logs, setLogs] = useState<DebugLog[]>([]);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);

  const addLog = useCallback((log: DebugLog) => {
    setLogs((prev) => [...prev.slice(-49), log]);
  }, []);

  // On app start: check backend health, then auth status
  useEffect(() => {
    addLog({ time: timestamp(), type: "info", message: `App started. Tauri: ${isTauri()}, API: ${API}` });

    // Health check
    api<{ status: string }>("/health", undefined, addLog)
      .then(() => {
        setBackendReachable(true);
        addLog({ time: timestamp(), type: "info", message: "Backend is reachable" });
      })
      .catch((e) => {
        setBackendReachable(false);
        addLog({ time: timestamp(), type: "error", message: `Backend health check failed: ${e.message}` });
      });

    // Auth status
    api<AuthStatus>("/auth/status?verify=true", undefined, addLog)
      .then((s) => {
        setStatus(s);
        addLog({ time: timestamp(), type: "info", message: `Auth status: ${s.state}` });
      })
      .catch((e) => {
        setStatus(SIGNED_OUT);
        addLog({ time: timestamp(), type: "error", message: `Auth status check failed: ${e.message}` });
      });
  }, [addLog]);

  const run = useCallback(
    async (fn: () => Promise<AuthStatus>) => {
      setBusy(true);
      setError(null);

      try {
        const result = await fn();
        setStatus(result);
        addLog({ time: timestamp(), type: "info", message: `Success: ${result.state}` });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg !== "cancelled") {
          setError(msg);
          addLog({ time: timestamp(), type: "error", message: msg });
        }
      } finally {
        setBusy(false);
      }
    },
    [addLog],
  );

  /** Main path: sign-in window -> cookies -> backend. No copy/paste. */
  const login = useCallback(
    () =>
      run(async () => {
        if (!isTauri()) {
          throw new Error(
            "Sign-in window requires the Tauri desktop app. Use browser import instead."
          );
        }
        addLog({ time: timestamp(), type: "info", message: "Opening Tauri sign-in window..." });
        const cookies = await invoke<TauriCookie[]>("youtube_login");
        addLog({ time: timestamp(), type: "info", message: `Received ${cookies.length} cookies from sign-in window` });
        return api<AuthStatus>("/auth/cookies", { method: "POST", body: JSON.stringify({ cookies }) }, addLog);
      }),
    [run, addLog],
  );

  /** Optional shortcut: reuse a login that already exists in an installed browser. */
  const importFromBrowser = useCallback(
    (browser: "firefox" | "chrome" | "edge" | "brave" | "safari") =>
      run(() =>
        api<AuthStatus>("/auth/import-browser", { method: "POST", body: JSON.stringify({ browser }) }, addLog),
      ),
    [run, addLog],
  );

  const logout = useCallback(
    () => run(() => api<AuthStatus>("/auth/logout", { method: "POST" }, addLog)),
    [run, addLog],
  );

  return { status, busy, error, login, importFromBrowser, logout, inTauri, logs, backendReachable };
}
