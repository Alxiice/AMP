import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatDuration, formatTotal, plural } from "../format";
import { saveAsNewQueue } from "../savedQueues";
import { store, useQueueState } from "../state";
import { askConfirm } from "../ui";
import { Cover } from "./Cover";
import { Icon } from "./Icon";
import { SongMenu } from "./SongMenu";

/** The live queue: click to jump, drag to reorder, ⋮ menu (song info, album…), remove, clear, save. */
export function QueuePanel({ onClose }: { onClose: () => void }) {
  const { items, currentIndex } = useQueueState();
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const currentRef = useRef<HTMLDivElement>(null);
  const [menu, setMenu] = useState<{ uid: number; x: number; y: number } | null>(null);
  const navigate = useNavigate();
  const menuItem = menu ? items.find((i) => i.uid === menu.uid) : undefined;

  const currentUid = items[currentIndex]?.uid;
  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentUid]);

  const remaining = items.slice(currentIndex + 1).reduce((sum, i) => sum + (i.song.duration_ms || 0), 0);

  return (
    <aside className="queue-panel" aria-label="Queue">
      <div className="queue-head">
        <h2>Queue</h2>
        <button className="btn-icon" onClick={onClose} title="Close"><Icon name="close" size={18} /></button>
      </div>
      <div className="queue-sub">
        {plural(items.length, "song")}{remaining ? ` · ${formatTotal(remaining)} left` : ""}
      </div>
      <div className="btn-row queue-actions">
        <button
          className="btn btn-secondary btn-small"
          disabled={items.length === 0}
          onClick={() => saveAsNewQueue(items.map((i) => i.song))}
        >
          Save
        </button>
        <button
          className="btn btn-secondary btn-small"
          disabled={items.length <= 1}
          onClick={() => store.clearQueue(true)}
          title="Remove everything except the current song"
        >
          Clear others
        </button>
        <button
          className="btn btn-secondary btn-small"
          disabled={items.length === 0}
          onClick={async () => {
            if (await askConfirm(`Clear the queue (${plural(items.length, "song")})?`, "Clear")) store.clearQueue();
          }}
        >
          Clear
        </button>
      </div>

      <div className="queue-list">
        {items.length === 0 && (
          <div className="empty-state">The queue is empty. Use a song's ⋮ menu to add it here.</div>
        )}
        {items.map((item, index) => (
          <div
            key={item.uid}
            ref={index === currentIndex ? currentRef : undefined}
            className={
              "queue-row" +
              (index === currentIndex ? " current" : "") +
              (index < currentIndex ? " played" : "") +
              (dragOver === index && dragFrom !== index ? " drop-target" : "")
            }
            draggable
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", String(index)); // required for the drag to start in some engines
              setDragFrom(index);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(index);
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (dragFrom !== null) store.moveItem(dragFrom, index);
              setDragFrom(null);
              setDragOver(null);
            }}
            onDragEnd={() => {
              setDragFrom(null);
              setDragOver(null);
            }}
            onClick={() => store.jumpTo(item.uid)}
          >
            <Cover url={item.song.thumbnail_url} songId={item.song.id} size={40} lazy />
            <div className="song-info">
              <div className="song-title">{item.song.title}</div>
              <div className="song-artist">{item.song.artist} · {formatDuration(item.song.duration_ms)}</div>
            </div>
            <div className="queue-row-actions" onClick={(e) => e.stopPropagation()}>
              <button className="btn-icon" title="More" onClick={(e) => setMenu({ uid: item.uid, x: e.clientX, y: e.clientY })}>
                <Icon name="more" size={16} />
              </button>
              <button className="btn-icon" title="Remove" onClick={() => store.removeItem(item.uid)}>
                <Icon name="close" size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
      {menu && menuItem && (
        <SongMenu
          song={menuItem.song}
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          onShowInfo={() => navigate(`/now-playing?uid=${menuItem.uid}`)}
        />
      )}
    </aside>
  );
}
