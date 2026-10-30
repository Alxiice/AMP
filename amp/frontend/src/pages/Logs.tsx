import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "../api";

interface LogsProps {
  backendLogs: string[];
}

export function Logs({ backendLogs }: LogsProps) {
  const [streamLogs, setStreamLogs] = useState<string[]>([]);
  const [relayLogs, setRelayLogs] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"backend" | "stream" | "relay">("backend");
  const containerRef = useRef<HTMLDivElement>(null);
  const inFlightStream = useRef(false); // P12
  const inFlightRelay = useRef(false);  // P12

  // Poll streaming logs every 2s
  const fetchStreamLogs = useCallback(async () => {
    if (inFlightStream.current) return;
    inFlightStream.current = true;
    try {
      const data = await api.getStreamLogs(500);
      setStreamLogs(data.lines);
    } catch {
      // ignore
    } finally {
      inFlightStream.current = false;
    }
  }, []);

  // Poll relay logs every 2s
  const fetchRelayLogs = useCallback(async () => {
    if (inFlightRelay.current) return;
    inFlightRelay.current = true;
    try {
      const data = await api.getLogs(500);
      setRelayLogs(data.lines);
    } catch {
      // ignore
    } finally {
      inFlightRelay.current = false;
    }
  }, []);

  useEffect(() => {
    fetchStreamLogs();
    fetchRelayLogs();
    const timer = setInterval(() => {
      fetchStreamLogs();
      fetchRelayLogs();
    }, 2000);
    return () => clearInterval(timer);
  }, [fetchStreamLogs, fetchRelayLogs]);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [backendLogs, streamLogs, relayLogs, activeTab]);

  const handleClearRelay = async () => {
    try {
      await api.clearLogs();
      setRelayLogs([]);
    } catch {
      // ignore
    }
  };

  const lines =
    activeTab === "backend" ? backendLogs :
    activeTab === "stream" ? streamLogs :
    relayLogs;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 className="page-title">Logs</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {(["backend", "stream", "relay"] as const).map((tab) => (
            <button
              key={tab}
              className={`btn ${activeTab === tab ? "" : "btn-secondary"}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "backend" ? "Backend stdout" : tab === "stream" ? "Streaming" : "API relay"}
            </button>
          ))}
          {activeTab === "relay" && (
            <button className="btn btn-danger" onClick={handleClearRelay}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="log-container" ref={containerRef}>
        {lines.length === 0 ? (
          <div className="empty-state">No logs yet</div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="log-line">{line}</div>
          ))
        )}
      </div>
    </div>
  );
}
