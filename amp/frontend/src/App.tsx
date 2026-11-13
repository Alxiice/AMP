import { useEffect, useState, useCallback } from "react";
import { Routes, Route, NavLink, useNavigate } from "react-router-dom";
import { api, type CacheInfo } from "./api";
import { sidecar, type BackendStatus } from "./sidecar";
import { sessionLabel, startAuthPolling, stopAuthPolling, useAuthStatus } from "./authSession";
import { clearLikes, loadLikes } from "./likes";
import { Icon } from "./components/Icon";
import { PlayerBar } from "./components/PlayerBar";
import { QueuePanel } from "./components/QueuePanel";
import { UiLayer } from "./components/UiLayer";
import { Search } from "./pages/Search";
import { Library } from "./pages/Library";
import { Playlists } from "./pages/Playlists";
import { PlaylistDetail } from "./pages/PlaylistDetail";
import { AlbumDetail } from "./pages/AlbumDetail";
import { NowPlaying } from "./pages/NowPlaying";
import { SavedQueues } from "./pages/SavedQueues";
import { SavedQueueDetail } from "./pages/SavedQueueDetail";
import { Auth } from "./pages/Auth";
import { Logs } from "./pages/Logs";
import { Developer } from "./pages/Developer";
import { Settings } from "./pages/Settings";
import { History } from "./pages/History";
import { useSettings } from "./settings";
import { store } from "./state";

const QUEUE_OPEN_KEY = "amp.queuePanel";

const NAV_ITEMS = [
  { path: "/now-playing", label: "Now playing", icon: "music" },
  { path: "/", label: "Search", icon: "search", exact: true },
  { path: "/library", label: "Liked songs", icon: "heart" },
  { path: "/playlists", label: "Playlists", icon: "playlist" },
  { path: "/queues", label: "Saved queues", icon: "saved" },
  { path: "/history", label: "History", icon: "history" },
  { path: "/auth", label: "Account", icon: "account" },
  { path: "/settings", label: "Settings", icon: "settings" },
  { path: "/logs", label: "Logs", icon: "logs" },
  { path: "/developer", label: "Developer", icon: "code" },
];

function readQueueOpen(): boolean {
  try {
    return localStorage.getItem(QUEUE_OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

export default function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("stopped");
  const [backendLogs, setBackendLogs] = useState<string[]>([]);
  const [cacheInfo, setCacheInfo] = useState<CacheInfo | null>(null);
  const [queueOpen, setQueueOpen] = useState(readQueueOpen);
  const authStatus = useAuthStatus();
  const navigate = useNavigate();
  const { fadeSec } = useSettings();

  useEffect(() => store.setFadeSec(fadeSec), [fadeSec]);

  useEffect(() => {
    // Follow the backend Tauri started (health, output); it is not spawned from here
    sidecar.start({
      onStatusChange: setBackendStatus,
      onLog: (line) => {
        setBackendLogs((prev) => {
          const next = [...prev, line];
          return next.length > 1000 ? next.slice(-1000) : next;
        });
      },
    });

    return () => {
      sidecar.stop();
    };
  }, []);

  // A play left unfinished when the app closed is recorded once the backend answers
  useEffect(() => {
    if (backendStatus === "running") store.flushPendingHistory();
  }, [backendStatus]);

  // Session badge: poll /api/auth/status every 60 s while the backend runs
  useEffect(() => {
    if (backendStatus !== "running") return;
    startAuthPolling();
    return stopAuthPolling;
  }, [backendStatus]);

  // Hearts need the liked set from the moment the session is known
  const signedIn = authStatus?.is_authenticated ?? false;
  useEffect(() => {
    if (signedIn) loadLikes();
    else clearLikes();
  }, [signedIn]);

  // Cache usage in the sidebar, every 5 s
  useEffect(() => {
    if (backendStatus !== "running") return;
    const fetchCache = () => api.getCacheInfo().then(setCacheInfo).catch(() => {});
    fetchCache();
    const timer = setInterval(fetchCache, 5000);
    return () => clearInterval(timer);
  }, [backendStatus]);

  const handleRestart = useCallback(() => {
    sidecar.restart({
      onStatusChange: setBackendStatus,
      onLog: (line) => {
        setBackendLogs((prev) => {
          const next = [...prev, line];
          return next.length > 1000 ? next.slice(-1000) : next;
        });
      },
    });
  }, []);

  const toggleQueue = useCallback(() => {
    setQueueOpen((open) => {
      try {
        localStorage.setItem(QUEUE_OPEN_KEY, open ? "0" : "1");
      } catch {
        // a convenience only
      }
      return !open;
    });
  }, []);

  return (
    <div className="app">
      <div className="app-layout">
        <nav className="sidebar">
          <div className="sidebar-header">
            <img className="sidebar-logo" src="/favicon.svg" alt="" />
            AMP
          </div>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.exact}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <Icon name={item.icon} size={18} />
              {item.label}
            </NavLink>
          ))}
          <div className="nav-status">
            {backendStatus === "running" && authStatus && (
              <button
                className={`auth-status-badge session-badge ${authStatus.state}`}
                onClick={() => navigate("/auth")}
                title="YouTube session: open the Account page"
              >
                {sessionLabel(authStatus)}
              </button>
            )}
            {cacheInfo && (
              <div
                className="cache-info"
                title={`${cacheInfo.song_count} songs · ${cacheInfo.file_count} segments`}
              >
                <div className="cache-info-text">Cache {cacheInfo.total_mb} / {cacheInfo.max_mb} MB</div>
                <div className="cache-info-bar">
                  <div className="cache-info-fill" style={{ width: `${Math.min(cacheInfo.usage_pct, 100)}%` }} />
                </div>
              </div>
            )}
            <div>
              <span className={`status-dot ${backendStatus}`} />
              Backend: {backendStatus}
              {backendStatus !== "running" && (
                <button className="btn btn-secondary btn-small restart" onClick={handleRestart}>Restart</button>
              )}
            </div>
          </div>
        </nav>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Search />} />
            <Route path="/library" element={<Library />} />
            <Route path="/playlists" element={<Playlists />} />
            <Route path="/playlists/:id" element={<PlaylistDetail />} />
            <Route path="/albums/:id" element={<AlbumDetail />} />
            <Route path="/now-playing" element={<NowPlaying />} />
            <Route path="/queues" element={<SavedQueues />} />
            <Route path="/queues/:id" element={<SavedQueueDetail />} />
            <Route path="/history" element={<History />} />
            <Route path="/auth" element={<Auth />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/logs" element={<Logs backendLogs={backendLogs} />} />
            <Route path="/developer" element={<Developer backendStatus={backendStatus} onRestart={handleRestart} />} />
          </Routes>
        </main>

        {queueOpen && <QueuePanel onClose={toggleQueue} />}
      </div>

      <PlayerBar backendStatus={backendStatus} queueOpen={queueOpen} onToggleQueue={toggleQueue} />
      <UiLayer />
    </div>
  );
}
