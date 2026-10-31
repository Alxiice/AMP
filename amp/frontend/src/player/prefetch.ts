/** When to warm up the next song: < 20 s left or past 80 % of the current one. */

export const PREFETCH_REMAINING_MS = 20_000;
export const PREFETCH_RATIO = 0.8;

export function shouldPrefetch(positionMs: number, durationMs: number): boolean {
  if (!(durationMs > 0) || !(positionMs > 0)) return false;
  return durationMs - positionMs < PREFETCH_REMAINING_MS || positionMs > PREFETCH_RATIO * durationMs;
}
