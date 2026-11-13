/**
 * Fade between songs: volume factor (0..1) at `positionSec` of a song lasting
 * `durationSec`. Ramps up over the first `fadeSec` seconds and down over the
 * last ones. With a crossfade both ramps run at once on two elements: the
 * ending song fades out while the next one fades in. 1 when fading is off or
 * the duration is unknown (no fade-out then, only the fade-in).
 */
export function fadeGain(positionSec: number, durationSec: number, fadeSec: number): number {
  if (!(fadeSec > 0) || !Number.isFinite(positionSec)) return 1;
  let gain = positionSec / fadeSec;
  if (Number.isFinite(durationSec) && durationSec > 0) gain = Math.min(gain, (durationSec - positionSec) / fadeSec);
  return Math.min(1, Math.max(0, gain));
}

/**
 * True once a song is in its last `fadeSec` seconds: the next song starts
 * there (crossfade). Never for songs not longer than the fade itself.
 */
export function crossfadeDue(positionSec: number, durationSec: number, fadeSec: number): boolean {
  return fadeSec > 0 && Number.isFinite(durationSec) && durationSec > fadeSec && positionSec >= durationSec - fadeSec;
}
