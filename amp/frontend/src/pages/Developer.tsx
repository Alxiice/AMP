import { useCallback, useEffect, useRef, useState } from "react";
import {
  api, getBaseUrl, rawRequest,
  type CacheInfo, type HealthStatus, type NowPlaying, type PlaybackState, type SegmentStatus,
} from "../api";
import type { BackendStatus } from "../sidecar";
import { toast } from "../ui";

const POLL_MS = 2000;
const QUICK = [
  ["Health", "GET", "/api/health"],
  ["Playback state", "GET", "/api/stream/playback-state"],
  ["Now playing", "GET", "/api/stream/now-playing"],
  ["Cache info", "GET", "/api/stream/cache-info"],
  ["Auth status", "GET", "/api/auth/status"],
  ["Search", "GET", "/api/search?q=test&limit=3"],
] as const;

interface Snapshot {
  health: HealthStatus | null;
  playback: PlaybackState | null;
  now: NowPlaying | null;
  cache: CacheInfo | null;
  segments: SegmentStatus[];
}

const EMPTY: Snapshot = { health: null, playback: null, now: null, cache: null, segments: [] };

function formatUptime(s?: number): string {
  if (s === undefined) return "—";
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="kv-row">
      <span className="kv-key">{k}</span>
      <span className="kv-value">{v}</span>
    </div>
  );
}

/** Developer tools: backend status, widget, cache, current song's segments, API tester. */
export function Developer({ backendStatus, onRestart }: { backendStatus: BackendStatus; onRestart: () => void }) {
  const [snap, setSnap] = useState<Snapshot>(EMPTY);
  const inFlight = useRef(false); // P12

  const poll = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [health, playback, now, cache] = await Promise.all([
        api.health().catch(() => null),
        api.getPlaybackState().catch(() => null),
        api.getNowPlaying().catch(() => null),
        api.getCacheInfo().catch(() => null),
      ]);
      const segments = playback?.song_id
        ? (await api.getSegmentStatuses(playback.song_id).catch(() => null))?.segments ?? []
        : [];
      setSnap({ health, playback, now, cache, segments });
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (backendStatus !== "running") {
      setSnap(EMPTY);
      return;
    }
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => clearInterval(timer);
  }, [backendStatus, poll]);

  const { health, playback, now, cache, segments } = snap;
  const extractor = health?.services.extractor;
  const widgetPort = health?.widget_port ?? 0;
  const widgetUrl = `http://127.0.0.1:${widgetPort}/?w=320&h=72`;
  const parts = segments.filter((s) => s.index >= 0);
  const done = parts.filter((s) => s.status === "downloaded").length;

  const copyWidgetUrl = () => {
    navigator.clipboard.writeText(widgetUrl).then(
      () => toast("Widget URL copied"),
      () => toast("Couldn't copy the URL", true),
    );
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Developer</h1>
      </div>

      <div className="dev-grid">
        <section className="dev-card">
          <div className="dev-card-head">
            <h2>Backend</h2>
            <span className={`pill ${backendStatus}`}>{backendStatus}</span>
          </div>
          <Row k="URL" v={<code>{getBaseUrl()}</code>} />
          <Row k="PID · uptime" v={health ? `${health.pid ?? "—"} · ${formatUptime(health.uptime_s)}` : "—"} />
          <Row k="yt-dlp" v={extractor?.yt_dlp ?? "—"} />
          <Row k="Node · EJS" v={extractor ? `${extractor.node ? "found" : "missing"} · ${extractor.ejs ? "ok" : "missing"}` : "—"} />
          <Row k="YouTube session" v={String(health?.services.auth ?? "—")} />
          <div className="btn-row">
            <button className="btn btn-secondary btn-small" onClick={onRestart}>Restart backend</button>
          </div>
        </section>

        <section className="dev-card">
          <div className="dev-card-head">
            <h2>OBS widget</h2>
            <span className={`pill ${widgetPort ? "running" : "stopped"}`}>{widgetPort ? `:${widgetPort}` : "off"}</span>
          </div>
          <Row k="Now playing" v={now?.song_id ? `${now.title || now.song_id}${now.artist ? ` · ${now.artist}` : ""}` : "nothing"} />
          <Row k="State" v={now?.song_id ? (now.is_playing ? "playing" : "paused") : "—"} />
          <div className="btn-row">
            <button className="btn btn-secondary btn-small" onClick={copyWidgetUrl} disabled={!widgetPort}>
              Copy widget URL
            </button>
          </div>
        </section>

        <section className="dev-card">
          <div className="dev-card-head"><h2>Cache</h2></div>
          <Row k="Used" v={cache ? `${cache.total_mb} / ${cache.max_mb} MB (${cache.usage_pct}%)` : "—"} />
          <Row k="Songs · files" v={cache ? `${cache.song_count} · ${cache.file_count}` : "—"} />
          <div className="cache-info-bar dev-cache-bar">
            <div className="cache-info-fill" style={{ width: `${Math.min(cache?.usage_pct ?? 0, 100)}%` }} />
          </div>
        </section>
      </div>

      <section className="dev-card">
        <div className="dev-card-head">
          <h2>Segments{playback?.song_id ? ` · ${playback.song_id}` : ""}</h2>
          <span className="kv-key">{parts.length ? `${done} / ${parts.length} cached · segment ${playback?.current_segment_index ?? 0}` : "no song in the session"}</span>
        </div>
        {parts.length > 0 && (
          <div className="dev-segments">
            {parts.map((s) => (
              <div
                key={s.index}
                className={`dev-segment ${s.status}${s.index === playback?.current_segment_index ? " current" : ""}`}
                title={`Segment ${s.index}: ${s.status}`}
              />
            ))}
          </div>
        )}
      </section>

      <ApiTester />
    </div>
  );
}

function ApiTester() {
  const [method, setMethod] = useState("GET");
  const [path, setPath] = useState("/api/health");
  const [body, setBody] = useState("");
  const [result, setResult] = useState<{ status: number; ms: number; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async (m = method, p = path, b = body) => {
    if (b.trim()) {
      try {
        JSON.parse(b);
      } catch {
        setResult({ status: 0, ms: 0, text: "The body isn't valid JSON." });
        return;
      }
    }
    setBusy(true);
    const r = await rawRequest(m, p.trim(), b.trim() || undefined);
    try {
      r.text = JSON.stringify(JSON.parse(r.text), null, 2);
    } catch {
      // not JSON: show as is
    }
    setResult(r);
    setBusy(false);
  };

  const statusClass = !result ? "" : result.status >= 200 && result.status < 300 ? "ok" : "bad";

  return (
    <section className="dev-card">
      <div className="dev-card-head"><h2>API tester</h2></div>
      <div className="dev-quick">
        {QUICK.map(([label, m, p]) => (
          <button key={label} className="btn btn-secondary btn-small"
            onClick={() => { setMethod(m); setPath(p); setBody(""); send(m, p, ""); }}>
            {label}
          </button>
        ))}
      </div>
      <form className="dev-request" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <select className="search-input dev-method" value={method} onChange={(e) => setMethod(e.target.value)}
          aria-label="Method">
          {["GET", "POST", "PUT", "DELETE"].map((m) => <option key={m}>{m}</option>)}
        </select>
        <input className="search-input dev-path" value={path} onChange={(e) => setPath(e.target.value)}
          aria-label="Path" spellCheck={false} />
        <button className="btn" type="submit" disabled={busy}>Send</button>
      </form>
      <textarea className="cookie-input dev-body" value={body} onChange={(e) => setBody(e.target.value)}
        placeholder='{"title": "Kings & Queens"}' aria-label="JSON body" spellCheck={false} />
      {result && (
        <>
          <div className={`dev-status ${statusClass}`}>
            {result.status ? `HTTP ${result.status}` : "Request failed"} · {Math.round(result.ms)} ms
          </div>
          <pre className="log-container dev-response">{result.text}</pre>
        </>
      )}
    </section>
  );
}
