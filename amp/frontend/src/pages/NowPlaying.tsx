import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { goToAlbum } from "../albumNav";
import { Cover } from "../components/Cover";
import { Icon } from "../components/Icon";
import { LikeButton } from "../components/LikeButton";
import { formatDuration } from "../format";
import { store, useQueueState } from "../state";

const UP_NEXT = 5;

/**
 * The song playing now, following the queue as it advances. `?uid=` pins one
 * queue item instead (the queue panel's "Display song info").
 */
export function NowPlaying() {
  const { items, currentIndex, isPlaying } = useQueueState();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const pinned = Number(params.get("uid"));
  const pinnedIndex = params.has("uid") ? items.findIndex((i) => i.uid === pinned) : -1;
  const index = pinnedIndex >= 0 ? pinnedIndex : currentIndex;
  const item = items[index];

  if (!item) {
    return <div className="empty-state">Nothing is playing. Pick a song to start the queue.</div>;
  }
  const { song } = item;
  const isCurrent = index === currentIndex;
  const kind = isCurrent ? (isPlaying ? "Now playing" : "Paused") : index > currentIndex ? "Later in the queue" : "Played";
  const upNext = items.slice(index + 1, index + 1 + UP_NEXT);

  return (
    <div className="now-playing">
      {!isCurrent && <Link className="back-link" to="/now-playing">← Current song</Link>}
      <header className="collection-header now-playing-header">
        <Cover url={song.thumbnail_url} songId={song.id} size={280} />
        <div className="collection-meta">
          <div className="collection-kind">{kind}</div>
          <h1 className="collection-title">
            {song.title}
            {song.is_explicit && <span className="explicit" title="Explicit">E</span>}
          </h1>
          <div className="now-playing-artist">{song.artist || "Unknown artist"}</div>
          <dl className="now-playing-facts">
            {song.album && (<><dt>Album</dt><dd>{song.album}</dd></>)}
            <dt>Duration</dt><dd>{formatDuration(song.duration_ms)}</dd>
            <dt>Queue</dt><dd>{index + 1} of {items.length}</dd>
          </dl>
          <div className="btn-row">
            {!isCurrent && (
              <button className="btn" onClick={() => store.jumpTo(item.uid)}>
                <Icon name="play" size={16} /> Play now
              </button>
            )}
            <button className="btn btn-secondary" onClick={() => goToAlbum(song, navigate)}>Go to album</button>
            <LikeButton song={song} />
          </div>
        </div>
      </header>

      {upNext.length > 0 && (
        <section>
          <h2 className="now-playing-next-title">{isCurrent ? "Up next" : "After this song"}</h2>
          <div className="song-list">
            {upNext.map((next) => (
              <div key={next.uid} className="song-row" onClick={() => navigate(`/now-playing?uid=${next.uid}`)}
                title="Show this song">
                <div className="song-cover"><Cover url={next.song.thumbnail_url} songId={next.song.id} size={44} lazy /></div>
                <div className="song-info">
                  <div className="song-title">{next.song.title}</div>
                  <div className="song-artist">{next.song.artist}</div>
                </div>
                <div className="song-album">{next.song.album}</div>
                <span className="song-duration">{formatDuration(next.song.duration_ms)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
