import { useCallback, useEffect, useRef, useState } from "react";

import { invoke } from "@tauri-apps/api/core";

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
  type: "info" | "error" | "request" | "response" | "warn";
  message: string;
  detail?: string;
}

const SIGNED_OUT: AuthStatus = { state: "signed_out", is_authenticated: false, account: null };

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function timestamp(): string {
  return new Date().toLocaleTimeString();
}

const DEFAULT_CANDIDATES = [
  "http://127.0.0.1:8000",
  "http://localhost:8000",
];

function getCandidates(): string[] {
  const stored = localStorage.getItem("amp_api_url");
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;
  const list: string[] = [];
  if (stored) list.push(stored);
  if (envUrl) list.push(envUrl);
  list.push(...DEFAULT_CANDIDATES);
  return [...new Set(list)];
}

let resolvedApiBase: string | null = null;
let probing: Promise<string> | null = null;

async function findApiBase(addLog: (log: DebugLog) => void): Promise<string> {
  if (resolvedApiBase) return resolvedApiBase;
  if (probing) return probing;

  probing = (async () => {
    const candidates = getCandidates();
    addLog({ time: timestamp(), type: "info", message: `Probing ${candidates.length} API URL(s)...` });

    for (const base of candidates) {
      try {
        const res = await fetch(`${base}/api/health`, {
          method: "GET",
          signal: AbortSignal.timeout(3000),
        });
        if (res.ok) {
          resolvedApiBase = base;
          localStorage.setItem("amp_api_url", base);
          addLog({ time: timestamp(), type: "info", message: `API found at ${base}` });
          return base;
        }
      } catch {
        addLog({ time: timestamp(), type: "warn", message: `Not reachable: ${base}` });
      }
    }

    resolvedApiBase = candidates[0];
    addLog({
      time: timestamp(),
      type: "error",
      message: `No API found. Tried: ${candidates.join(", ")}`,
      detail: "Set the API URL in Settings to your Windows host IP.",
    });
    return resolvedApiBase;
  })();

  return probing;
}

async function api<T>(
  path: string,
  init?: RequestInit,
  addLog?: (log: DebugLog) => void,
): Promise<T> {
  const base = resolvedApiBase ?? "http://127.0.0.1:8000";
  const url = `${base}/api${path}`;
  const method = init?.method ?? "GET";

  addLog?.({
    time: timestamp(),
    type: "request",
    message: `${method} ${path}`,
    detail: init?.body ? String(init.body).slice(0, 200) : undefined,
  });

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    addLog?.({ time: timestamp(), type: "error", message: `Network error: ${method} ${path}`, detail: msg });
    throw new Error(`Cannot reach backend at ${base}`);
  }

  const bodyText = await res.text();
  addLog?.({
    time: timestamp(),
    type: "response",
    message: `${res.status} ${method} ${path}`,
    detail: bodyText.slice(0, 300),
  });

  if (!res.ok) {
    let detail: string;
    try {
      const body = JSON.parse(bodyText);
      detail = body.detail ?? bodyText.slice(0, 300);
    } catch {
      detail = bodyText.slice(0, 300) || `HTTP ${res.status}`;
    }
    throw new Error(detail);
  }

  return JSON.parse(bodyText);
}

export function useYouTubeAuth() {
  const [status, setStatus] = useState<AuthStatus>(SIGNED_OUT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inTauri] = useState(isTauri);
  const [logs, setLogs] = useState<DebugLog[]>([]);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);
  const [apiUrl, setApiUrl] = useState<string>(resolvedApiBase ?? "");
  const [apiUrlInput, setApiUrlInput] = useState<string>(resolvedApiBase ?? "");
  // Web-mode sign-in: true when the browser tab is open and user needs to sign in
  const [awaitingBrowserSignin, setAwaitingBrowserSignin] = useState(false);
  const initialized = useRef(false);

  const addLog = useCallback((log: DebugLog) => {
    setLogs((prev) => [...prev.slice(-99), log]);
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const s = await api<AuthStatus>("/auth/status?verify=true", undefined, addLog);
      setStatus(s);
      setBackendReachable(true);
      if (s.state === "signed_in") setAwaitingBrowserSignin(false);
    } catch (e) {
      setStatus(SIGNED_OUT);
      setBackendReachable(resolvedApiBase !== null);
      addLog({
        time: timestamp(),
        type: "warn",
        message: `Auth check failed: ${e instanceof Error ? e.message : String(e)}`,
      });
    }
  }, [addLog]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    addLog({ time: timestamp(), type: "info", message: `App started (${isTauri() ? "Tauri" : "Browser"})` });

    findApiBase(addLog).then((base) => {
      setApiUrl(base);
      setApiUrlInput(base);
      checkAuth();
    });
  }, [addLog, checkAuth]);

  const setApiUrlManually = useCallback(
    (url: string) => {
      const cleaned = url.replace(/\/$/, "").replace(/\/api$/, "");
      resolvedApiBase = cleaned;
      probing = null;
      localStorage.setItem("amp_api_url", cleaned);
      setApiUrl(cleaned);
      setApiUrlInput(cleaned);
      addLog({ time: timestamp(), type: "info", message: `API URL set to ${cleaned}` });

      fetch(`${cleaned}/api/health`, { signal: AbortSignal.timeout(3000) })
        .then((res) => {
          setBackendReachable(res.ok);
          if (res.ok) checkAuth();
        })
        .catch(() => setBackendReachable(false));
    },
    [addLog, checkAuth],
  );

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

  /**
   * Primary sign-in method.
   * - Tauri mode: opens the Tauri sign-in window (individual webview, any account)
   * - Web mode: opens a browser tab to YouTube Music, user signs in there,
   *   then clicks "I've signed in" to capture cookies via import-browser.
   */
  const login = useCallback(
    (browser?: string) =>
      run(async () => {
        if (isTauri()) {
          // Tauri: sign-in window (individual connection)
          addLog({ time: timestamp(), type: "info", message: "Opening Tauri sign-in window..." });
          const cookies = await invoke<TauriCookie[]>("youtube_login");
          addLog({ time: timestamp(), type: "info", message: `Received ${cookies.length} cookies` });
          return api<AuthStatus>("/auth/cookies", { method: "POST", body: JSON.stringify({ cookies }) }, addLog);
        }

        // Web mode: open browser tab for sign-in
        addLog({ time: timestamp(), type: "info", message: "Opening browser for sign-in..." });
        const res = await api<{ opened: boolean; message: string }>(
          "/auth/open-signin",
          { method: "POST", body: JSON.stringify({ browser: browser ?? null }) },
          addLog,
        );
        setAwaitingBrowserSignin(true);
        addLog({ time: timestamp(), type: "info", message: res.message });
        // Return current status — user will complete sign-in and click "I've signed in"
        return api<AuthStatus>("/auth/status", undefined, addLog);
      }),
    [run, addLog],
  );

  /**
   * Web mode step 2: after the user has signed in to YouTube Music in the
   * opened browser tab, capture cookies via yt-dlp import.
   */
  const completeBrowserSignin = useCallback(
    (browser: "firefox" | "chrome" | "edge" | "brave" | "safari") =>
      run(() =>
        api<AuthStatus>("/auth/import-browser", { method: "POST", body: JSON.stringify({ browser }) }, addLog),
      ),
    [run, addLog],
  );

  /** Quick shortcut: import cookies from an already-signed-in browser. */
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

  return {
    status, busy, error, login, completeBrowserSignin, importFromBrowser, logout,
    inTauri, logs, backendReachable,
    apiUrl, apiUrlInput, setApiUrlInput, setApiUrlManually,
    awaitingBrowserSignin, setAwaitingBrowserSignin,
  };
}
