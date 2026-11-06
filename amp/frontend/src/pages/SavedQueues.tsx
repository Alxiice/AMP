import { Link } from "react-router-dom";
import { Cover } from "../components/Cover";
import { plural } from "../format";
import { saveAsNewQueue, useSavedQueues } from "../savedQueues";
import { useQueueState } from "../state";

export function SavedQueues() {
  const queues = useSavedQueues();
  const { items } = useQueueState();

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Saved queues</h1>
        <button
          className="btn"
          disabled={items.length === 0}
          onClick={() => saveAsNewQueue(items.map((i) => i.song))}
        >
          Save current queue
        </button>
      </div>
      {queues.length === 0 ? (
        <div className="empty-state">No saved queues yet. Save the current queue, or any list of songs, to find it here.</div>
      ) : (
        <div className="card-grid">
          {queues.map((q) => (
            <Link key={q.id} className="card" to={`/queues/${q.id}`}>
              <Cover url={q.thumbnail_url} size={160} className="card-thumb" />
              <div className="card-title">{q.name}</div>
              <div className="card-subtitle">{plural(q.song_count, "song")}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
