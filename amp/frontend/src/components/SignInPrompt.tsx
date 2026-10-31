import { useNavigate } from "react-router-dom";
import type { AuthStatus } from "../api";

/** Shown by Library / Playlists instead of a raw 401. */
export function SignInPrompt({ status }: { status: AuthStatus | null }) {
  const navigate = useNavigate();
  const expired = status?.state === "expired";
  return (
    <div className="empty-state">
      <p>{expired ? "Your YouTube session expired. Sign in again to see your library." : "Sign in to see your library."}</p>
      <button className="btn" style={{ marginTop: 16 }} onClick={() => navigate("/auth")}>
        {expired ? "Reconnect" : "Sign in"}
      </button>
    </div>
  );
}
