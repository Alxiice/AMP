/**
 * User-facing text for playback failures.
 *
 * Backend errors carry a code ({detail: {code, message}}, see
 * backend/api/errors.py); everything else is a fetch or <audio> failure.
 */

const CODE_MESSAGES: Record<string, string> = {
  invalid_id: "Invalid track ID",
  unavailable: "This track is unavailable",
  no_audio: "No audio stream for this track",
  auth_required: "Sign in required for this track",
  node_missing: "Node.js not found. Install it and restart.",
  extract_failed: "Couldn't get the audio stream from YouTube",
  segment_unavailable: "Couldn't download the audio from YouTube",
  network: "Backend not reachable",
};

interface ErrorLike {
  name?: string;
  message?: string;
  code?: string | null;
  status?: number;
}

export function describeError(e: unknown): string {
  const err = (e ?? {}) as ErrorLike;
  if (err.name === "NotAllowedError") return "Autoplay blocked — click play to start";
  if (err.code && CODE_MESSAGES[err.code]) return CODE_MESSAGES[err.code];
  if (err.name === "TypeError") return CODE_MESSAGES.network; // fetch() itself failed
  if (err.status) return err.message || `Backend error (HTTP ${err.status})`;
  return `Play failed: ${err.message || String(e)}`;
}

/** MediaError.code → text, for <audio> errors after the source was set. */
export function describeMediaError(code: number | undefined): string {
  switch (code) {
    case 1: return "Playback aborted";
    case 2: return "Network error while streaming";
    case 3: return "Couldn't decode the audio";
    case 4: return "Audio format not supported";
    default: return "Audio error";
  }
}
