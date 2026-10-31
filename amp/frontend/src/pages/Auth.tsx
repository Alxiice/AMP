import { useState } from "react";
import { api } from "../api";
import { refreshAuthStatus, useAuthStatus } from "../authSession";
import { youtubeLogin, mightBeTauri } from "../tauri_auth";

/**
 * Three things only (Phase 5): status, "Sign in with YouTube" (Tauri webview),
 * and a collapsed "Advanced" section (paste a Cookie header, Firefox import).
 */
export function Auth() {
  const status = useAuthStatus();
  const [busy, setBusy] = useState(false);
  const [waitingForWebview, setWaitingForWebview] = useState(false);
  const [cookieHeader, setCookieHeader] = useState("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const showMessage = (msg: string) => {
    setActionMessage(msg);
    setActionError(null);
    setTimeout(() => setActionMessage(null), 5000);
  };

  const showError = (msg: string) => {
    setActionError(msg);
    setActionMessage(null);
    setTimeout(() => setActionError(null), 8000);
  };

  /** Run an action, then re-verify the session with YouTube. */
  const run = async (action: () => Promise<string>, fallbackError: string) => {
    setBusy(true);
    try {
      const msg = await action();
      await refreshAuthStatus(true);
      showMessage(msg);
    } catch (e) {
      showError(e instanceof Error ? e.message : fallbackError);
    } finally {
      setBusy(false);
    }
  };

  const handleSignIn = () =>
    run(async () => {
      setWaitingForWebview(true);
      try {
        const cookies = await youtubeLogin();
        const result = await api.setTauriCookies(cookies);
        return `Signed in (${result.cookie_count} YouTube cookies kept)`;
      } finally {
        setWaitingForWebview(false);
      }
    }, "Sign-in failed");

  const handleSetCookies = () =>
    run(async () => {
      const result = await api.setCookies(cookieHeader.trim());
      setCookieHeader("");
      return `Cookies saved (${result.cookie_count} YouTube cookies kept)`;
    }, "Failed to set cookies");

  const handleImportFirefox = () =>
    run(async () => {
      const result = await api.importFirefox();
      return `Imported ${result.cookie_count} YouTube cookies from Firefox`;
    }, "Firefox import failed");

  const handleLogout = () =>
    run(async () => {
      await api.logout();
      return "Logged out";
    }, "Logout failed");

  const state = status?.state ?? "signed_out";

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Authentication</h1>
      </div>

      <p style={{ color: "var(--text-secondary)", marginBottom: 24, maxWidth: 500 }}>
        Search and playback work without signing in. Sign in to see your liked songs and playlists.
      </p>

      {/* 1. Status */}
      <div className="auth-section">
        <h3>Status</h3>
        <p style={{ marginTop: 8 }}>
          <span className={`auth-status-badge ${state}`}>{status ? state.replace("_", " ") : "unknown"}</span>
        </p>
        {status?.account && (
          <p style={{ marginTop: 4, color: "var(--text-secondary)" }}>
            Account: {JSON.stringify(status.account)}
          </p>
        )}
        {status?.migrated_from_full_jar && (
          <div className="error-message" style={{ marginTop: 12, borderColor: "var(--warning)", color: "var(--warning)", background: "rgba(240,165,0,0.1)" }}>
            Your saved session came from an older version that stored other sites' cookies. Only YouTube
            cookies were kept. Sign in again to rebuild a complete session.
          </div>
        )}
        <div className="btn-row">
          <button className="btn btn-secondary" onClick={() => run(async () => "Session checked", "Check failed")} disabled={busy}>
            Verify Session
          </button>
          {status?.is_authenticated && (
            <button className="btn btn-danger" onClick={handleLogout} disabled={busy}>
              Logout
            </button>
          )}
        </div>
      </div>

      {/* 2. Primary sign-in: Tauri webview */}
      <div className="auth-section">
        <h3>Sign in with YouTube</h3>
        {mightBeTauri() ? (
          <>
            <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
              Opens a private sign-in window. Your cookies are read from that window when you're done; nothing to copy.
            </p>
            <div className="btn-row">
              <button className="btn" onClick={handleSignIn} disabled={busy}>
                {waitingForWebview ? "Waiting for sign-in..." : "Sign in with YouTube"}
              </button>
            </div>
            {waitingForWebview && (
              <div className="auth-flow-status">
                <div className="status-indicator">
                  <span className="spinner"></span>
                  <span>Complete the sign-in in the pop-up window (10 minute limit).</span>
                </div>
              </div>
            )}
          </>
        ) : (
          <p style={{ color: "var(--warning)", marginTop: 8, fontSize: 14 }}>
            Only available in the desktop app. In a browser, use "Advanced" below.
          </p>
        )}
      </div>

      {/* 3. Advanced: manual paste + Firefox import */}
      <details className="auth-section">
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>Advanced</summary>

        <h4 style={{ marginTop: 16 }}>Paste a Cookie header</h4>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
          1. Open music.youtube.com in your browser and sign in.<br />
          2. Open DevTools (F12) → Network tab → reload the page.<br />
          3. Click any request to music.youtube.com → copy the <code>Cookie</code> request header value.<br />
          4. Paste it below. Only YouTube session cookies are kept.
        </p>
        <textarea
          className="cookie-input"
          placeholder="Paste the Cookie header value here..."
          value={cookieHeader}
          onChange={(e) => setCookieHeader(e.target.value)}
        />
        <div className="btn-row">
          <button className="btn" onClick={handleSetCookies} disabled={busy || !cookieHeader.trim()}>
            Set Cookies
          </button>
        </div>

        <h4 style={{ marginTop: 24 }}>Import from Firefox</h4>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
          Sign in to YouTube Music in Firefox, <strong>close Firefox</strong> (its cookie database is locked while it
          runs), then import. Chrome and Edge aren't supported: their cookies can't be decrypted on Windows.
        </p>
        <div className="btn-row">
          <button className="btn btn-secondary" onClick={handleImportFirefox} disabled={busy}>
            Import from Firefox
          </button>
        </div>
      </details>

      {actionMessage && (
        <div className="error-message" style={{ borderColor: "var(--success)", color: "var(--success)", background: "rgba(29,185,84,0.1)" }}>
          {actionMessage}
        </div>
      )}
      {actionError && <div className="error-message">{actionError}</div>}
    </div>
  );
}
