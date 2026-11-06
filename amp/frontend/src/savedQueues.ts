/** Saved queues (stored by the backend, /api/queues): the list the menus and pages share, plus the common actions. */

import { useEffect, useSyncExternalStore } from "react";
import { api, type SavedQueueInfo, type Song } from "./api";
import { askName, toast, toastError } from "./ui";
import { plural } from "./format";

let list: SavedQueueInfo[] = [];
const listeners = new Set<() => void>();

export async function refreshSavedQueues(): Promise<void> {
  try {
    list = await api.listSavedQueues();
    for (const l of listeners) l();
  } catch (e) {
    console.warn("Could not list saved queues:", e);
  }
}

export function useSavedQueues(): SavedQueueInfo[] {
  useEffect(() => {
    refreshSavedQueues();
  }, []);
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => list,
  );
}

/** Ask for a name and save these songs as a new queue. */
export async function saveAsNewQueue(songs: Song[], suggestedName = ""): Promise<void> {
  const name = await askName("Save as queue", suggestedName);
  if (!name) return;
  try {
    await api.createSavedQueue(name, songs);
    toast(`Saved "${name}" (${plural(songs.length, "song")})`);
    await refreshSavedQueues();
  } catch (e) {
    toastError(e, "Could not save the queue");
  }
}

export async function addToSavedQueue(queue: SavedQueueInfo, songs: Song[]): Promise<void> {
  try {
    const current = await api.getSavedQueue(queue.id);
    await api.updateSavedQueue(queue.id, { songs: [...current.songs, ...songs] });
    toast(`Added to "${queue.name}"`);
    await refreshSavedQueues();
  } catch (e) {
    toastError(e, "Could not update the queue");
  }
}
