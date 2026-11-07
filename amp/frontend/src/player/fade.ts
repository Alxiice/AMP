/**
 * Fade between songs: volume factor (0..1) at `positionSec` of a song lasting
 * `durationSec`. Ramps up over the first `fadeSec` seconds and down over the
 * last ones, so one song fades out and the next fades in. 1 when fading is off
 * or the duration is unknown (no fade-out then, only the fade-in).
 */
export function fadeGain(positionSec: number, durationSec: number, fadeSec: number): number {
  if (!(fadeSec > 0) || !Number.isFinite(positionSec)) return 1;
  let gain = positionSec / fadeSec;
  if (Number.isFinite(durationSec) && durationSec > 0) gain = Math.min(gain, (durationSec - positionSec) / fadeSec);
  return Math.min(1, Math.max(0, gain));
}
