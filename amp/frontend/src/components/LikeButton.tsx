import type { Song } from "../api";
import { useAuthStatus } from "../authSession";
import { toggleLike, useLikes } from "../likes";
import { Icon } from "./Icon";

/** Heart for a song; only rendered when signed in, since likes live on the YouTube account. */
export function LikeButton({ song }: { song: Song }) {
  const auth = useAuthStatus();
  const { ids } = useLikes();
  if (!auth?.is_authenticated) return null;
  const liked = ids.has(song.id);
  return (
    <button
      className={`btn-icon like${liked ? " on" : ""}`}
      title={liked ? "Remove from liked songs" : "Add to liked songs"}
      aria-pressed={liked}
      onClick={(e) => {
        e.stopPropagation();
        toggleLike(song);
      }}
    >
      <Icon name={liked ? "heart-filled" : "heart"} size={18} />
    </button>
  );
}
