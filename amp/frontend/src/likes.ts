/**
 * The account's liked songs. One store so every heart and the Library page agree;
 * toggling is optimistic and rolled back if YouTube refuses.
 */

import { useSyncExternalStore } from "react";
import { api, type Song } from "./api";
import { toastError } from "./ui";

export interface LikesState {
  songs: Song[];
  ids: Set<string>;
  loading: boolean;
  error: string | null;
}

const empty: LikesState = { songs: [], ids: new Set(), loading: false, error: null };

let state = empty;
let generation = 0;
const listeners = new Set<() => void>();

function set(partial: Partial<LikesState>): void {
  state = { ...state, ...partial };
  if (partial.songs) state.ids = new Set(partial.songs.map((s) => s.id));
  for (const l of listeners) l();
}

export async function loadLikes(): Promise<void> {
  const gen = ++generation;
  set({ loading: true, error: null });
  try {
    const songs = await api.getUserLikes();
    if (gen === generation) set({ songs, loading: false });
  } catch (e) {
    if (gen === generation) {
      set({ loading: false, error: e instanceof Error ? e.message : "Failed to load liked songs" });
    }
  }
}

export function clearLikes(): void {
  generation++;
  state = empty;
  for (const l of listeners) l();
}

export async function toggleLike(song: Song): Promise<void> {
  const before = state.songs;
  const liked = state.ids.has(song.id);
  generation++; // a load in flight predates this change
  set({ songs: liked ? before.filter((s) => s.id !== song.id) : [song, ...before], loading: false });
  try {
    if (liked) await api.unlikeSong(song.id);
    else await api.likeSong(song);
  } catch (e) {
    set({ songs: before });
    toastError(e, liked ? "Could not remove the like" : "Could not like this song");
  }
}

export function useLikes(): LikesState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
  );
}
