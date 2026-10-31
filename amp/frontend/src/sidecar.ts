/**
 * Backend client. The Tauri app (src-tauri/src/backend.rs) spawns, owns and stops the
 * backend; this module only finds it, polls its health and shows its output:
 *
 * - initBackend() (before the first render): `backend_info` → port → api.ts base URL.
 * - start(): replays the lines logged so far (`backend_logs`), then follows the
 *   `backend-log` / `backend-status` events and polls /api/health every second.
 * - restart(): `restart_backend` (the port may change).
 *
 * Outside Tauri (plain `npm run dev` in a browser) nothing can be spawned: the backend is
 * whatever answers on http://127.0.0.1:8000 (app.py, or `python -m backend.main`).
 *
 * P7: Rust decodes the backend's output lossily as UTF-8 and the backend writes UTF-8.
 */

import { getBaseUrl, setBaseUrl } from "./api";

export type BackendStatus = "starting" | "running" | "stopped" | "error";

interface SidecarCallbacks {
  onStatusChange: (status: BackendStatus) => void;
  onLog: (line: string) => void;
}

interface BackendInfo {
  port: number;
  token: string | null;
}

interface StatusEvent {
  state: "stopped";
  code: number | null;
}

type Unlisten = () => void;

const MAX_LOG_LINES = 1000;
const HEALTH_POLL_MS = 1000;

/** `__TAURI_INTERNALS__` is injected by the Tauri runtime; a plain browser has none. */
function inTauri(): boolean {
  return typeof window !== "undefined" && !!(window as any).__TAURI_INTERNALS__;
}

async function invoke<T>(command: string): Promise<T> {
  const core = await import("@tauri-apps/api/core");
  return core.invoke<T>(command);
}

let initError: string | null = null;

function applyInfo(info: BackendInfo): void {
  setBaseUrl(`http://127.0.0.1:${info.port}`);
}

/** Point api.ts at the backend Tauri started. Call once before rendering. */
export async function initBackend(): Promise<void> {
  if (!inTauri()) return; // keep the :8000 default
  try {
    applyInfo(await invoke<BackendInfo>("backend_info"));
  } catch (e) {
    initError = String(e);
  }
}

class BackendSidecar {
  private status: BackendStatus = "stopped";
  private healthTimer: ReturnType<typeof setInterval> | null = null;
  private logRing: string[] = [];
  private callbacks: SidecarCallbacks | null = null;
  private unlisten: Unlisten[] = [];
  private generation = 0; // stop() during start()'s awaits (StrictMode remount) cancels that start
  private inFlightHealth = false; // P12: in-flight guard

  getStatus(): BackendStatus {
    return this.status;
  }

  getLogs(): string[] {
    return [...this.logRing];
  }

  async start(callbacks: SidecarCallbacks): Promise<void> {
    this.callbacks = callbacks;
    const gen = ++this.generation;
    this._setStatus("starting");

    if (!inTauri()) {
      this._pushLog(`Browser mode: using the backend at ${getBaseUrl()} (start it with app.py)`);
      this._startHealthPoll();
      return;
    }

    try {
      const { listen } = await import("@tauri-apps/api/event");
      const offLog = await listen<string>("backend-log", (e) => this._pushLog(e.payload));
      const offStatus = await listen<StatusEvent>("backend-status", () => this._setStatus("stopped"));
      const earlier = await invoke<string[]>("backend_logs");
      if (gen !== this.generation) {
        offLog();
        offStatus();
        return;
      }
      this.unlisten.push(offLog, offStatus);
      // Lines logged before we listened; a line arriving in between may show twice
      for (const line of earlier) this._pushLog(line);
    } catch (e) {
      this._pushLog(`Cannot follow backend output: ${e}`);
    }

    if (initError) {
      this._pushLog(`Backend unavailable: ${initError}`);
      this._setStatus("error");
      return;
    }
    this._startHealthPoll();
  }

  /** Stop following the backend. It keeps running: the Tauri app stops it on exit. */
  async stop(): Promise<void> {
    this.generation++;
    this._stopHealthPoll();
    for (const off of this.unlisten.splice(0)) off();
  }

  async restart(callbacks: SidecarCallbacks): Promise<void> {
    this.callbacks = callbacks;
    if (!inTauri()) {
      this._pushLog("Browser mode: restart the backend from app.py");
      this._setStatus("starting");
      this._startHealthPoll();
      return;
    }
    this._stopHealthPoll();
    this._setStatus("starting");
    try {
      applyInfo(await invoke<BackendInfo>("restart_backend"));
      initError = null;
      this._startHealthPoll();
    } catch (e) {
      this._pushLog(`Backend restart failed: ${e}`);
      this._setStatus("error");
    }
  }

  // --- Private ---

  private _startHealthPoll(): void {
    this._stopHealthPoll();
    this.healthTimer = setInterval(() => this._checkHealth(), HEALTH_POLL_MS);
    // Check immediately
    this._checkHealth();
  }

  private _stopHealthPoll(): void {
    if (this.healthTimer) {
      clearInterval(this.healthTimer);
      this.healthTimer = null;
    }
  }

  private async _checkHealth(): Promise<void> {
    // P12: in-flight guard
    if (this.inFlightHealth) return;
    this.inFlightHealth = true;

    try {
      const resp = await fetch(`${getBaseUrl()}/api/health`, {
        signal: AbortSignal.timeout(3000),
      });
      if (resp.ok) {
        if (this.status !== "running") {
          this._setStatus("running");
          this._pushLog("Backend health check: OK");
        }
      } else {
        if (this.status === "running") {
          this._setStatus("error");
        }
      }
    } catch {
      if (this.status === "running") {
        this._setStatus("error");
        this._pushLog("Backend health check: FAILED");
      }
    } finally {
      this.inFlightHealth = false;
    }
  }

  private _pushLog(line: string): void {
    const trimmed = line.replace(/\n$/, "");
    this.logRing.push(trimmed);
    if (this.logRing.length > MAX_LOG_LINES) {
      this.logRing = this.logRing.slice(-MAX_LOG_LINES);
    }
    this.callbacks?.onLog(trimmed);
  }

  private _setStatus(status: BackendStatus): void {
    if (this.status !== status) {
      this.status = status;
      this.callbacks?.onStatusChange(status);
    }
  }
}

// Singleton
export const sidecar = new BackendSidecar();
