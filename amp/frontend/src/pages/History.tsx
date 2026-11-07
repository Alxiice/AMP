import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type HistoryEntry } from "../api";
import { Cover } from "../components/Cover";
import { Icon } from "../components/Icon";
import { formatDuration } from "../format";
import { HISTORY_EVENT, store } from "../state";
import { askConfirm, toastError } from "../ui";

const PAGE = 200;
const PERIODS: Array<[number, string]> = [[7, "7 days"], [30, "30 days"], [0, "All time"]];
const REASONS: Record<HistoryEntry["end_reason"], string> = {
  finished: "Finished", skipped: "Skipped", stopped: "Stopped", closed: "App closed",
};

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long",
    year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}

function formatListened(ms: number): string {
  if (ms < 60000) return `${Math.round(ms / 1000)} s`;
  const min = Math.round(ms / 60000);
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}

export function History() {
  const [days, setDays] = useState(7);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [listenedMs, setListenedMs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (period: number, offset = 0) => {
    setLoading(true);
    try {
      const page = await api.getHistory(period, PAGE, offset);
      setEntries((prev) => (offset ? [...prev, ...page.entries] : page.entries));
      setTotal(page.total);
      setListenedMs(page.listened_ms);
      setError(null);
    } catch (e) {
      setError((e as Error).message || "Couldn't load the history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(days);
    // a play saved while this page is open (song ended, skipped, or left over from the last run)
    const reload = () => load(days);
    window.addEventListener(HISTORY_EVENT, reload);
    return () => window.removeEventListener(HISTORY_EVENT, reload);
  }, [days, load]);

  const groups = useMemo(() => {
    const out: Array<{ label: string; items: HistoryEntry[] }> = [];
    for (const e of entries) {
      const label = dayLabel(new Date(e.started_at));
      if (out[out.length - 1]?.label !== label) out.push({ label, items: [] });
      out[out.length - 1].items.push(e);
    }
    return out;
  }, [entries]);

  const remove = async (entry: HistoryEntry) => {
    try {
      await api.deleteHistoryEntry(entry.id);
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
      setTotal((t) => t - 1);
      setListenedMs((ms) => ms - entry.listened_ms);
    } catch (e) {
      toastError(e, "Couldn't remove the entry");
    }
  };

  const clearAll = async () => {
    if (!(await askConfirm("Clear the whole listening history?", "Clear history"))) return;
    try {
      await api.clearHistory();
      load(days);
    } catch (e) {
      toastError(e, "Couldn't clear the history");
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">History</h1>
        <div className="history-actions">
          <div className="segmented" role="radiogroup" aria-label="Period">
            {PERIODS.map(([value, label]) => (
              <button key={value} role="radio" aria-checked={days === value}
                className={days === value ? "on" : ""} onClick={() => setDays(value)}>
                {label}
              </button>
            ))}
          </div>
          <button className="btn btn-danger btn-small" onClick={clearAll} disabled={total === 0}>Clear history</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {total > 0 && (
        <div className="history-summary">
          {total} {total === 1 ? "play" : "plays"} · {formatListened(listenedMs)} listened
        </div>
      )}

      {!loading && entries.length === 0 && !error && (
        <div className="empty-state">Nothing here yet. Songs you listen to for more than 5 seconds show up here.</div>
      )}

      {groups.map((g) => (
        <section key={g.label} className="history-day">
          <h2>{g.label}</h2>
          {g.items.map((e) => (
            <div key={e.id} className="song-row history-row" onClick={() => store.playList([e.song])}
              title={`Listened ${formatDuration(e.listened_ms)} of ${formatDuration(e.duration_ms)}`}>
              <div className="song-cover">
                <Cover url={e.song.thumbnail_url} songId={e.song.id} size={44} lazy />
                <span className="song-cover-overlay"><Icon name="play" size={18} /></span>
              </div>
              <div className="song-info">
                <div className="song-title">{e.song.title || e.song.id}</div>
                <div className="song-artist">{e.song.artist}</div>
              </div>
              <span className="history-reason">{REASONS[e.end_reason]}</span>
              <div className="history-percent" aria-label={e.percent === null ? "Unknown length" : `${e.percent}% listened`}>
                <div className="history-bar"><div style={{ width: `${e.percent ?? 0}%` }} /></div>
                <span>{e.percent === null ? "—" : `${e.percent}%`}</span>
              </div>
              <span className="song-duration">
                {new Date(e.started_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
              </span>
              <button className="btn-icon song-more" title="Remove from history"
                onClick={(ev) => { ev.stopPropagation(); remove(e); }}>
                <Icon name="close" size={16} />
              </button>
            </div>
          ))}
        </section>
      ))}

      {entries.length < total && (
        <div className="btn-row history-more">
          <button className="btn btn-secondary" disabled={loading} onClick={() => load(days, entries.length)}>
            {loading ? "Loading..." : "Show more"}
          </button>
        </div>
      )}
    </div>
  );
}
