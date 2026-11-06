import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Song } from "../api";
import { useAuthStatus } from "../authSession";
import { toggleLike, useLikes } from "../likes";
import { addToSavedQueue, saveAsNewQueue, useSavedQueues } from "../savedQueues";
import { store } from "../state";
import { toast } from "../ui";

interface SongMenuProps {
  song: Song;
  x: number;
  y: number;
  onClose: () => void;
  /** Extra entry for lists that can remove a row (saved queue page). */
  onRemove?: () => void;
}

export function SongMenu({ song, x, y, onClose, onRemove }: SongMenuProps) {
  const auth = useAuthStatus();
  const { ids } = useLikes();
  const saved = useSavedQueues();
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });

  // Keep it on screen
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    setPos({
      left: Math.max(8, Math.min(x, window.innerWidth - r.width - 8)),
      top: Math.max(8, Math.min(y, window.innerHeight - r.height - 8)),
    });
  }, [x, y, saved.length]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const item = (label: string, action: () => void) => (
    <button
      className="menu-item"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
        action();
      }}
    >
      {label}
    </button>
  );

  return (
    <div className="menu" ref={ref} style={pos} onClick={(e) => e.stopPropagation()} role="menu">
      {item("Play next", () => { store.playNext([song]); toast("Playing next"); })}
      {item("Add to queue", () => { store.addToQueue([song]); toast("Added to queue"); })}
      {auth?.is_authenticated &&
        item(ids.has(song.id) ? "Remove from liked songs" : "Add to liked songs", () => toggleLike(song))}
      {onRemove && item("Remove from this queue", onRemove)}
      <div className="menu-sep" />
      <div className="menu-label">Add to saved queue</div>
      {item("New saved queue…", () => saveAsNewQueue([song]))}
      {saved.map((q) => (
        <button
          key={q.id}
          className="menu-item"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
            addToSavedQueue(q, [song]);
          }}
        >
          {q.name}
        </button>
      ))}
    </div>
  );
}
