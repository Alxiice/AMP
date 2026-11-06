/** Display helpers shared by the song lists and collection headers. */

export function formatDuration(ms: number): string {
  if (!ms) return "--:--";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = (totalSec % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export function formatTotal(ms: number): string {
  const min = Math.round(ms / 60000);
  return min >= 60 ? `${Math.floor(min / 60)} h ${min % 60} min` : `${min} min`;
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/**
 * YouTube Music thumbnails are resizable through the URL (…=w120-h120-l90-rj),
 * and the API tends to list small ones. Ask for the size actually displayed.
 */
export function coverUrl(url: string, size: number): string {
  return url.replace(/=w\d+-h\d+/, `=w${size}-h${size}`);
}
