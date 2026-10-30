import { useEffect, useState, useCallback, useRef } from "react";
import { api, type AuthStatus, type SignInFlowStatus, type TauriCookie } from "../api";
import { youtubeLogin, isTauriAvailable, mightBeTauri } from "../tauri_auth";

const BROWSERS = ["chrome", "firefox", "edge", "brave", "chromium", "opera", "vivaldi", "safari"];

type SignInState = "idle" | "waiting" | "success" | "failed" | "timeout" | "tauri_waiting";

export function Auth() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [cookieHeader, setCookieHeader] = useState("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedBrowser, setSelectedBrowser] = useState("chrome");
  
  // Auto sign-in flow state
  const [signInState, setSignInState] = useState<SignInState>("idle");
  const [signInSessionId, setSignInSessionId] = useState<string | null>(null);
  const [signInFlowStatus, setSignInFlowStatus] = useState<SignInFlowStatus | null>(null);
  const [pollingCount, setPollingCount] = useState(0);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStatus = useCallback(async (verify = false) => {
    try {
      const data = await api.getAuthStatus(verify);
      setStatus(data);
    } catch (e) {
      setStatus({ state: "signed_out", is_authenticated: false, account: null });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    
    // Cleanup intervals on unmount
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [loadStatus]);

  const showMessage = (msg: string) => {
    setActionMessage(msg);
    setActionError(null);
    setTimeout(() => setActionMessage(null), 5000);
  };

  const showError = (msg: string) => {
    setActionError(msg);
    setActionMessage(null);
    setTimeout(() => setActionError(null), 5000);
  };

  const handleSetCookies = async () => {
    if (!cookieHeader.trim()) return;
    try {
      await api.setCookies(cookieHeader.trim());
      setCookieHeader("");
      await loadStatus(true);
      showMessage("Cookies saved successfully");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to set cookies");
    }
  };

  const handleImportBrowser = async () => {
    try {
      await api.importBrowser(selectedBrowser);
      await loadStatus(true);
      showMessage(`Cookies imported from ${selectedBrowser}`);
    } catch (e) {
      showError(e instanceof Error ? e.message : "Browser import failed");
    }
  };

  const handleOpenSignin = async () => {
    try {
      await api.openSignin();
      showMessage("Sign-in page opened in your browser. After signing in, copy the Cookie header and paste it below.");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to open sign-in page");
    }
  };

  const handleStartSignInFlow = async () => {
    // Cancel any existing flow
    if (signInSessionId) {
      try {
        await api.cancelSignInFlow(signInSessionId);
      } catch (e) {
        // Ignore errors when cancelling
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }

    try {
      setSignInState("waiting");
      setSignInSessionId(null);
      setPollingCount(0);
      
      const data = await api.startSignInFlow(selectedBrowser);
      setSignInSessionId(data.session_id);
      setSignInState("waiting");
      
      showMessage(`Sign-in page opened. Please sign in to YouTube Music within ${data.timeout_seconds} seconds.`);
      
      // Start polling for status
      pollIntervalRef.current = setInterval(async () => {
        try {
          const flowStatus = await api.getSignInStatus(data.session_id);
          setSignInFlowStatus(flowStatus);
          setPollingCount((c) => c + 1);
          
          if (flowStatus.status === "success") {
            // Success! Stop polling and refresh auth status
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
            setSignInState("success");
            await loadStatus(true);
            showMessage(`Successfully signed in! Imported ${flowStatus.cookies_imported} cookies.`);
            
            // Auto-cleanup after 5 seconds
            setTimeout(() => {
              setSignInState("idle");
              setSignInSessionId(null);
              setSignInFlowStatus(null);
            }, 5000);
          } else if (flowStatus.status === "failed" || flowStatus.status === "timeout") {
            // Failed or timeout
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
            setSignInState(flowStatus.status === "timeout" ? "timeout" : "failed");
            showError(flowStatus.error || "Sign-in failed");
          }
        } catch (e) {
          // Polling error - continue polling
          console.warn("Sign-in status polling error:", e);
        }
      }, 2000);
      
      // Auto-timeout cleanup
      setTimeout(() => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        // Check if still waiting (use a function to get current state)
        setSignInState((currentState) => {
          if (currentState === "waiting") {
            return "timeout";
          }
          return currentState;
        });
        if (signInState === "waiting") {
          setSignInSessionId(null);
        }
      }, data.timeout_seconds * 1000 + 5000);
      
    } catch (e) {
      setSignInState("idle");
      showError(e instanceof Error ? e.message : "Failed to start sign-in flow");
    }
  };

  const handleCancelSignInFlow = async () => {
    if (!signInSessionId) return;
    
    try {
      await api.cancelSignInFlow(signInSessionId);
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      setSignInState("idle");
      setSignInSessionId(null);
      setSignInFlowStatus(null);
      setPollingCount(0);
      showMessage("Sign-in flow cancelled");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to cancel sign-in flow");
    }
  };

  const handleTauriSignIn = async () => {
    if (!isTauriAvailable()) {
      showError("Tauri is not available. Please run the app via 'npm run tauri dev' or as a built Tauri app.");
      return;
    }

    try {
      setSignInState("tauri_waiting");
      showMessage("Opening YouTube Music sign-in window...");
      
      // Call Tauri command to open sign-in window
      const cookies = await youtubeLogin();
      
      // Send cookies to backend
      await api.setTauriCookies(cookies);
      
      // Update auth status
      await loadStatus(true);
      
      setSignInState("success");
      showMessage(`Successfully signed in! Imported ${cookies.length} cookies.`);
      
      // Auto-cleanup
      setTimeout(() => {
        setSignInState("idle");
      }, 5000);
      
    } catch (e) {
      setSignInState("idle");
      showError(e instanceof Error ? e.message : "Tauri sign-in failed");
    }
  };

  const handleLogout = async () => {
    try {
      await api.logout();
      await loadStatus();
      showMessage("Logged out");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Logout failed");
    }
  };

  const handleVerify = async () => {
    setLoading(true);
    await loadStatus(true);
    setLoading(false);
  };

  if (loading && !status) {
    return <div className="loading">Loading auth status...</div>;
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Authentication</h1>
      </div>

      {/* Status */}
      <div className="auth-section">
        <h3>Status</h3>
        <p style={{ marginTop: 8 }}>
          State:{" "}
          <span className={`auth-status-badge ${status?.state || "signed_out"}`}>
            {status?.state || "unknown"}
          </span>
        </p>
        {status?.account && (
          <p style={{ marginTop: 4, color: "var(--text-secondary)" }}>
            Account: {JSON.stringify(status.account)}
          </p>
        )}
        <div className="btn-row">
          <button className="btn btn-secondary" onClick={handleVerify}>
            Verify Session
          </button>
          {status?.is_authenticated && (
            <button className="btn btn-danger" onClick={handleLogout}>
              Logout
            </button>
          )}
        </div>
      </div>

      {/* Tauri webview sign-in (BEST METHOD) */}
      <div className="auth-section">
        <h3>Sign In with YouTube (Recommended - Tauri)</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
          Click the button below to open a YouTube Music sign-in window. After signing in, your cookies will be automatically imported.
          <br />
          <strong>Note:</strong> This requires running the app as a Tauri application (via <code>npm run tauri dev</code> or a built binary).
        </p>
        
        {mightBeTauri() ? (
          <div className="btn-row">
            <button 
              className="btn"
              onClick={handleTauriSignIn}
              disabled={signInState === "tauri_waiting"}
            >
              {signInState === "tauri_waiting" ? "Waiting for sign-in..." : "Sign In with YouTube (Tauri)"}
            </button>
          </div>
        ) : (
          <p style={{ color: "var(--warning)", marginTop: 8, fontSize: 14 }}>
            Tauri is not available. Please run the app via &quot;npm run tauri dev&quot; or as a built Tauri app.
          </p>
        )}
        
        {signInState === "tauri_waiting" && (
          <div className="auth-flow-status">
            <div className="status-indicator">
              <span className="spinner"></span>
              <span>Waiting for sign-in in the pop-up window...</span>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: 8, fontSize: 14 }}>
              A sign-in window should have opened. Please complete the sign-in process there.
            </p>
          </div>
        )}
      </div>

      {/* Auto sign-in flow (FALLBACK - for non-Tauri or when Tauri fails) */}
      <div className="auth-section">
        <h3>Sign In with YouTube (Browser Polling - Fallback)</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
          Alternative method: Opens your default browser to YouTube Music and polls for cookies.
          <br />
          <strong>Note:</strong> Firefox users must close their browser before starting. Works best with Chrome, Edge, Brave, and Chromium.
        </p>
        
        {signInState === "idle" || signInState === "tauri_waiting" ? (
          <div className="btn-row">
            <select
              className="search-type-select"
              value={selectedBrowser}
              onChange={(e) => setSelectedBrowser(e.target.value)}
            >
              {BROWSERS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
            <button 
              className="btn"
              onClick={handleStartSignInFlow}
              disabled={signInState !== "idle"}
            >
              Sign In with YouTube (Browser Polling)
            </button>
          </div>
        ) : null}
        
        {signInState !== "idle" && signInState !== "tauri_waiting" && (
          <div className="auth-flow-status">
            <div className="status-indicator">
              {signInState === "waiting" && (
                <>
                  <span className="spinner"></span>
                  <span>Waiting for sign-in...</span>
                </>
              )}
              {signInState === "success" && (
                <>
                  <span className="success-icon">✓</span>
                  <span>Signed in successfully!</span>
                </>
              )}
              {signInState === "failed" && (
                <>
                  <span className="error-icon">✗</span>
                  <span>Sign-in failed</span>
                </>
              )}
              {signInState === "timeout" && (
                <>
                  <span className="error-icon">✗</span>
                  <span>Sign-in timed out</span>
                </>
              )}
            </div>
            
            {signInState === "waiting" && signInFlowStatus && (
              <p style={{ color: "var(--text-secondary)", marginTop: 8, fontSize: 14 }}>
                Polling attempt: {pollingCount} | Status: {signInFlowStatus.status}
                {signInFlowStatus.error && (
                  <span style={{ color: "var(--error)" }}> - {signInFlowStatus.error}</span>
                )}
              </p>
            )}
            
            {(signInState === "waiting" || signInState === "failed" || signInState === "timeout") && (
              <button 
                className="btn btn-secondary"
                onClick={handleCancelSignInFlow}
                style={{ marginTop: 8 }}
              >
                Cancel
              </button>
            )}
          </div>
        )}
      </div>

      {/* Browser import */}
      <div className="auth-section">
        <h3>Import from Browser</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
          Extract cookies directly from your browser. Make sure you are signed in to YouTube Music in that browser.
        </p>
        <div className="btn-row">
          <select
            className="search-type-select"
            value={selectedBrowser}
            onChange={(e) => setSelectedBrowser(e.target.value)}
          >
            {BROWSERS.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          <button className="btn" onClick={handleImportBrowser}>
            Import from {selectedBrowser}
          </button>
        </div>
      </div>

      {/* Manual cookie paste */}
      <div className="auth-section">
        <h3>Manual Cookie Entry</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>
          1. Open YouTube Music in your browser and sign in.<br />
          2. Open DevTools (F12) → Network tab → reload the page.<br />
          3. Click any request to music.youtube.com → copy the <code>Cookie</code> request header value.<br />
          4. Paste it below and click "Set Cookies".
        </p>
        <button className="btn btn-secondary" onClick={handleOpenSignin} style={{ marginTop: 8 }}>
          Open YouTube Music Sign-in
        </button>
        <textarea
          className="cookie-input"
          placeholder="Paste the Cookie header value here..."
          value={cookieHeader}
          onChange={(e) => setCookieHeader(e.target.value)}
        />
        <div className="btn-row">
          <button
            className="btn"
            onClick={handleSetCookies}
            disabled={!cookieHeader.trim()}
          >
            Set Cookies
          </button>
        </div>
      </div>

      {/* Messages */}
      {actionMessage && (
        <div className="error-message" style={{ borderColor: "var(--success)", color: "var(--success)", background: "rgba(29,185,84,0.1)" }}>
          {actionMessage}
        </div>
      )}
      {actionError && <div className="error-message">{actionError}</div>}
    </div>
  );
}
