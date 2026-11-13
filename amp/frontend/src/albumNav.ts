import type { NavigateFunction } from "react-router-dom";
import { api, type Song } from "./api";
import { toast } from "./ui";

/** Open the album page of a song. Songs don't carry their album ID, so it is looked up first. */
export async function goToAlbum(song: Song, navigate: NavigateFunction): Promise<void> {
  try {
    const { album_id } = await api.getSongAlbumId(song.id);
    if (album_id) navigate(`/albums/${encodeURIComponent(album_id)}`);
    else toast("This song has no album", true);
  } catch {
    toast("Couldn't find the album", true);
  }
}
