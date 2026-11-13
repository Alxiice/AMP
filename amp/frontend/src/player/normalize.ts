/**
 * Volume normalization from YouTube's per-track loudness (`loudnessDb`, in dB
 * relative to YouTube's playback reference; YouTube Music reports roughly −5…+2
 * for released music). Every song is brought down to NORMALIZATION_TARGET_DB,
 * so songs above it play equally loud. Songs quieter than the target stay as
 * they are: the <audio> element's volume can't go above 1. Unknown → 1.
 */
export const NORMALIZATION_TARGET_DB = -6;

export function normalizationGain(loudnessDb: number | null | undefined, targetDb = NORMALIZATION_TARGET_DB): number {
  if (typeof loudnessDb !== "number" || !Number.isFinite(loudnessDb)) return 1;
  return Math.min(1, 10 ** ((targetDb - loudnessDb) / 20));
}
