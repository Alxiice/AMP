"""Dev tool: list the top-level MP4 boxes at the start of a song's itag 140 file.

Usage (from amp/):
    venv/Scripts/python.exe scripts/dump_boxes.py BAgTQhR8MLo [Tmz3mpOq8aE ...] [--save-fixture]

--save-fixture writes the bytes up to the end of sidx for the first song to
backend/tests/fixtures/itag140_head.bin (media metadata only; no URL, no cookies).
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.auth import get_auth_service  # noqa: E402
from backend.services.extractor import StreamExtractor  # noqa: E402

HEAD_BYTES = 65536


def top_level_boxes(buf: bytes):
    pos = 0
    while pos + 8 <= len(buf):
        size, kind = struct.unpack(">I4s", buf[pos:pos + 8])
        if size == 1:
            if pos + 16 > len(buf):
                break
            size = struct.unpack(">Q", buf[pos + 8:pos + 16])[0]
        elif size == 0:
            size = len(buf) - pos
        yield kind.decode("latin-1"), pos, size
        if size < 8:
            break
        pos += size


def main(argv: list[str]) -> None:
    save = "--save-fixture" in argv
    songs = [a for a in argv if not a.startswith("--")] or ["BAgTQhR8MLo"]
    extractor = StreamExtractor(get_auth_service())
    for n, song_id in enumerate(songs):
        stream = extractor.get(song_id)
        resp = requests.get(stream.url, headers={"Range": f"bytes=0-{HEAD_BYTES - 1}"}, timeout=30)
        head = resp.content
        print(f"{song_id}: itag={stream.itag} filesize={stream.filesize} duration={stream.duration_ms} ms "
              f"HTTP {resp.status_code} {resp.headers.get('Content-Range')} got {len(head)} B")
        sidx_end = None
        for kind, offset, size in top_level_boxes(head):
            print(f"  {kind:4}  offset={offset:>8}  size={size:>10}")
            if kind == "sidx" and sidx_end is None:
                sidx_end = offset + size
            if kind == "moof":
                break
        if save and n == 0 and sidx_end:
            out = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures" / "itag140_head.bin"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(head[:sidx_end])
            print(f"  saved {sidx_end} B to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
