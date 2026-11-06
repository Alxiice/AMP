import type { ReactNode } from "react";
import type { Song } from "../api";
import { formatTotal, plural } from "../format";
import { saveAsNewQueue } from "../savedQueues";
import { store } from "../state";
import { toast } from "../ui";
import { Cover } from "./Cover";
import { Icon } from "./Icon";

interface CollectionHeaderProps {
  kind: string;
  title: string;
  subtitle?: string;
  thumbnailUrl?: string;
  songs: Song[];
  /** False on a page that already is a saved queue. */
  canSave?: boolean;
  children?: ReactNode;
}

/** Top of any page showing a list of songs: what it is, and what to do with all of it. */
export function CollectionHeader({ kind, title, subtitle, thumbnailUrl, songs, canSave = true, children }: CollectionHeaderProps) {
  const total = songs.reduce((sum, s) => sum + (s.duration_ms || 0), 0);
  const stats = `${plural(songs.length, "song")}${total ? ` · ${formatTotal(total)}` : ""}`;
  const empty = songs.length === 0;
  return (
    <header className="collection-header">
      <Cover url={thumbnailUrl || songs.find((s) => s.thumbnail_url)?.thumbnail_url} songId={songs[0]?.id} size={160} />
      <div className="collection-meta">
        <div className="collection-kind">{kind}</div>
        <h1 className="collection-title">{title}</h1>
        <div className="collection-sub">{subtitle ? `${subtitle} · ` : ""}{stats}</div>
        <div className="btn-row">
          <button className="btn" disabled={empty} onClick={() => store.playList(songs, 0)}>
            <Icon name="play" size={16} /> Play
          </button>
          <button className="btn btn-secondary" disabled={empty} onClick={() => store.shuffleList(songs)}>
            <Icon name="shuffle" size={16} /> Shuffle
          </button>
          <button
            className="btn btn-secondary"
            disabled={empty}
            onClick={() => { store.playNext(songs); toast(`${plural(songs.length, "song")} playing next`); }}
          >
            Play next
          </button>
          <button
            className="btn btn-secondary"
            disabled={empty}
            onClick={() => { store.addToQueue(songs); toast(`${plural(songs.length, "song")} added to queue`); }}
          >
            <Icon name="add" size={16} /> Add to queue
          </button>
          {canSave && (
            <button className="btn btn-secondary" disabled={empty} onClick={() => saveAsNewQueue(songs, title)}>
              Save as queue
            </button>
          )}
          {children}
        </div>
      </div>
    </header>
  );
}
