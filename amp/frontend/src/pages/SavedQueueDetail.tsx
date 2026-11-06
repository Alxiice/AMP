import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type SavedQueueDetail as SavedQueue, type Song } from "../api";
import { CollectionHeader } from "../components/CollectionHeader";
import { SongList } from "../components/SongList";
import { refreshSavedQueues } from "../savedQueues";
import { useQueueState } from "../state";
import { askConfirm, askName, toast, toastError } from "../ui";

export function SavedQueueDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { items } = useQueueState();
  const [queue, setQueue] = useState<SavedQueue | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setQueue(null);
    setError(null);
    api.getSavedQueue(Number(id))
      .then((data) => { if (!cancelled) setQueue(data); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load queue"); });
    return () => { cancelled = true; };
  }, [id]);

  const update = async (patch: { name?: string; songs?: Song[] }, done?: string) => {
    if (!queue) return;
    try {
      setQueue(await api.updateSavedQueue(queue.id, patch));
      if (done) toast(done);
      await refreshSavedQueues();
    } catch (e) {
      toastError(e, "Could not update the queue");
    }
  };

  const rename = async () => {
    if (!queue) return;
    const name = await askName("Rename queue", queue.name, "Rename");
    if (name) await update({ name });
  };

  const replace = async () => {
    if (!queue) return;
    if (await askConfirm(`Replace "${queue.name}" with the current queue?`, "Replace")) {
      await update({ songs: items.map((i) => i.song) }, "Queue replaced");
    }
  };

  const remove = async () => {
    if (!queue) return;
    if (!(await askConfirm(`Delete "${queue.name}"?`, "Delete"))) return;
    try {
      await api.deleteSavedQueue(queue.id);
      await refreshSavedQueues();
      toast("Queue deleted");
      navigate("/queues");
    } catch (e) {
      toastError(e, "Could not delete the queue");
    }
  };

  return (
    <div>
      <Link className="back-link" to="/queues">← Saved queues</Link>
      {error && <div className="error-message">{error}</div>}
      {!error && !queue && <div className="loading">Loading queue...</div>}
      {queue && (
        <>
          <CollectionHeader kind="Saved queue" title={queue.name} songs={queue.songs} canSave={false}>
            <button className="btn btn-secondary" onClick={rename}>Rename</button>
            <button className="btn btn-secondary" disabled={items.length === 0} onClick={replace}>
              Replace with current queue
            </button>
            <button className="btn btn-danger" onClick={remove}>Delete</button>
          </CollectionHeader>
          <SongList
            songs={queue.songs}
            emptyMessage="This queue is empty"
            onRemove={(index) => update({ songs: queue.songs.filter((_, i) => i !== index) })}
          />
        </>
      )}
    </div>
  );
}
