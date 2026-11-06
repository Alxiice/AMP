import { useEffect, useState } from "react";
import { coverUrl } from "../format";
import { Icon } from "./Icon";

interface CoverProps {
  url?: string;
  /** Falls back to the video's own thumbnail when `url` is missing or fails. */
  songId?: string;
  size: number;
  className?: string;
  /** Rows of long lists only; covers that are always on screen load eagerly. */
  lazy?: boolean;
}

/** Album art: the given URL at display size → YouTube's video thumbnail → placeholder. */
export function Cover({ url, songId, size, className = "", lazy = false }: CoverProps) {
  const candidates: string[] = [];
  // 2x for high-DPI screens
  if (url) candidates.push(coverUrl(url, size * 2));
  if (songId) candidates.push(`https://i.ytimg.com/vi/${songId}/mqdefault.jpg`);
  const key = candidates.join("|");
  const [failed, setFailed] = useState(0);
  useEffect(() => setFailed(0), [key]);

  const src = candidates[failed];
  const style = { width: size, height: size };
  if (!src) {
    return (
      <div className={`cover cover-empty ${className}`} style={style}>
        <Icon name="music" size={Math.round(size * 0.45)} />
      </div>
    );
  }
  return (
    <img
      // loading must come before src: React sets attributes in this order
      loading={lazy ? "lazy" : "eager"}
      referrerPolicy="no-referrer"
      className={`cover ${className}`}
      style={style}
      src={src}
      alt=""
      onError={() => setFailed((n) => n + 1)}
    />
  );
}
