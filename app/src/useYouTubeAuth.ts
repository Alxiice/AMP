import { useCallback, useEffect, useState } from "react";

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

/** True when running inside a Tauri webview. */
function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function timestamp(): string {
  return new Date().toLocaleTimeString();
}

// Candidate API base URLs, tried in order. First one that responds wins.
// 1. User-configured (localStorage)
// 2. Vite env var
// 3. Same-host loopback (works when backend runs on same machine)
// 4. Common WSL2 gateway IPs (Windows host from WSL2)
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

async function findApiBase(addLog: (log: DebugLog) => void): Promise<string> {
  if (resolvedApiBase) return resolvedApiBase;

  const candidates = getCandidates();
  addLog({ time: timestamp(), type: "info", message: `Probing ${candidates.length} API URLs...` });

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
      addLog({ time: timestamp(), type: "warn", message: `API not reachable at ${base}` });
    }
  }

  // None worked — use the first candidate and let requests fail with details
  resolvedApiBase = candidates[0];
  addLog({
    time: timestamp(),
    type: "error",
    message: `No API found. Tried: ${candidates.join(", ")}`,
    detail: "If running Tauri in WSL2 with backend on Windows, set the API URL manually.\nEdit localStorage 'amp_api_url' or set VITE_API_URL env var.",
  });
  return resolvedApiBase;
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
      detail: `${msg}\n\nIf running Tauri in WSL2 with backend on Windows, set the API URL to your Windows host IP.`,
    });
    throw new Error(`Cannot reach backend at ${base} — ${msg}`);
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
  const [apiUrl, setApiUrl] = useState<string>("");
  const [apiUrlInput, setApiUrlInput] = useState<string>("");

  const addLog = useCallback((log: DebugLog) => {
    setLogs((prev) => [...prev.slice(-99), log]);
  }, []);

  // On app start: find the API, then check auth status
  useEffect(() => {
    addLog({ time: timestamp(), type: "info", message: `App started. Tauri: ${isTauri()}` });

    findApiBase(addLog).then((base) => {
      setApiUrl(base);
      setApiUrlInput(base);

      api<AuthStatus>("/auth/status?verify=true", undefined, addLog)
        .then((s) => {
          setStatus(s);
          setBackendReachable(true);
          addLog({ time: timestamp(), type: "info", message: `Auth status: ${s.state}` });
        })
        .catch((e) => {
          setStatus(SIGNED_OUT);
          setBackendReachable(true); // API is reachable, auth just failed
          addLog({ time: timestamp(), type: "error", message: `Auth status check failed: ${e.message}` });
        });
    });
  }, [addLog]);

  const setApiUrlManually = useCallback(
    (url: string) => {
      const cleaned = url.replace(/\/$/, "").replace(/\/api$/, "");
      resolvedApiBase = cleaned;
      localStorage.setItem("amp_api_url", cleaned);
      setApiUrl(cleaned);
      setApiUrlInput(cleaned);
      addLog({ time: timestamp(), type: "info", message: `API URL set to ${cleaned}` });

      // Re-check auth with new URL
      api<AuthStatus>("/auth/status?verify=true", undefined, addLog)
        .then((s) => {
          setStatus(s);
          setBackendReachable(true);
        })
        .catch(() => setBackendReachable(false));
    },
    [addLog],
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

  const login = useCallback(
    () =>
      run(async () => {
        if (!isTauri()) {
          throw new Error("Sign-in window requires the Tauri desktop app.");
        }
        addLog({ time: timestamp(), type: "info", message: "Opening Tauri sign-in window..." });
        const cookies = await invoke<TauriCookie[]>("youtube_login");
        addLog({ time: timestamp(), type: "info", message: `Received ${cookies.length} cookies` });
        return api<AuthStatus>("/auth/cookies", { method: "POST", body: JSON.stringify({ cookies }) }, addLog);
      }),
    [run, addLog],
  );

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
    status, busy, error, login, importFromBrowser, logout,
    inTauri, logs, backendReachable,
    apiUrl, apiUrlInput, setApiUrlInput, setApiUrlManually,
  };
}
