import { useEffect, useState, useCallback } from "react";
import { Routes, Route, NavLink } from "react-router-dom";
import { sidecar, type BackendStatus } from "./sidecar";
import { PlayerBar } from "./components/PlayerBar";
import { Search } from "./pages/Search";
import { Library } from "./pages/Library";
import { Playlists } from "./pages/Playlists";
import { Auth } from "./pages/Auth";
import { Logs } from "./pages/Logs";

const NAV_ITEMS = [
  { path: "/", label: "Search", exact: true },
  { path: "/library", label: "Library" },
  { path: "/playlists", label: "Playlists" },
  { path: "/auth", label: "Auth" },
  { path: "/logs", label: "Logs" },
];

export default function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("stopped");
  const [backendLogs, setBackendLogs] = useState<string[]>([]);

  useEffect(() => {
    // Start the backend sidecar on app launch
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

  return (
    <>
      <div className="app-layout">
        <nav className="sidebar">
          <div className="sidebar-header">AMP v2</div>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.exact}
              className={({ isActive }) =>
                `nav-item${isActive ? " active" : ""}`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <div className="nav-status">
            <span className={`status-dot ${backendStatus}`} />
            Backend: {backendStatus}
            {backendStatus !== "running" && (
              <button
                className="btn btn-secondary"
                style={{ marginLeft: 8, padding: "4px 10px", fontSize: 11 }}
                onClick={handleRestart}
              >
                Restart
              </button>
            )}
          </div>
        </nav>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Search />} />
            <Route path="/library" element={<Library />} />
            <Route path="/playlists" element={<Playlists />} />
            <Route path="/auth" element={<Auth />} />
            <Route
              path="/logs"
              element={<Logs backendLogs={backendLogs} />}
            />
          </Routes>
        </main>
      </div>

      <PlayerBar backendStatus={backendStatus} />
    </>
  );
}
