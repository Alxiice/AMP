# Pitfalls

Things that have already gone wrong once. Each has a number (Pn) that you'll find in code comments,
e.g. `# P14: never save`. Before changing code that mentions one, read its entry.

??? danger "YouTube & yt-dlp"
    | # | Rule |
    |---|---|
    | P1 | googlevideo requests carry the `Cookie` header when signed in. Signed out, most URLs work without it; some songs need an account |
    | P2 | yt-dlp needs a JS runtime **and** the solver: `js_runtimes={"node": {}}` as a *top-level* option, and `yt-dlp[default]` (pulls in `yt-dlp-ejs`). Node.js is a hard runtime dependency |
    | P3 | Cache extraction and stream info per song (bounded): an extraction costs ~1–2 s |
    | P4 | Stream URLs expire (~6 h). On a CDN 403: refresh the URL, rebuild the segment table, retry once |
    | P5 | Never trust a single Content-Length source: `filesize` → URL `clen=` → `HEAD` → `Range: bytes=0-0` |
    | P22 | Keep itag 140 (AAC/MP4) as the default: every webview plays it. Verify Opus/WebM on the platform before switching to 251 |
    | P25 | yt-dlp **silently ignores** malformed options: `extractor_args` is `{extractor: {key: [values]}}`. Build options with `build_ydl_opts()` and keep `test_ydl_opts_player_client_applied` |
    | P26 | Some clients return URLs that 403 until `available_at` (~5 s): wait for it. `android` without a PO token only offers muxed itag 18: never put it first |

??? danger "Downloads & cache"
    | # | Rule |
    |---|---|
    | P14 | Check every segment response: status **206**, matching `Content-Range`, exact byte count. A 200 (range ignored) saved as a segment corrupts the cache |
    | P15 | Atomic writes only: unique temp file, fsync, `os.replace`. A crash must never leave a partial file that looks complete |
    | P18 | Seeks bump a per-song epoch; newer requests outrank older queued ones. In-flight downloads finish (their bytes are valid), queued ones are re-ranked, never dropped |
    | P19 | Bound every in-memory cache (`BoundedDict(256)`) |
    | P20 | SQLite in WAL mode with `busy_timeout`: workers and handlers write concurrently |

??? danger "HTTP API"
    | # | Rule |
    |---|---|
    | P9 | Declare specific routes before parameterised ones (`/stream/logs` before `/stream/{song_id}`) |
    | P13 | Validate `song_id` against `^[A-Za-z0-9_-]{11}$` before it touches a path |
    | P16 | Implement Range for real (200 / 206 / 416). `<audio>` seeks with it |
    | P21 | Handlers doing HTTP, yt-dlp or file I/O are plain `def`, never `async def` |
    | P24 | Never log full googlevideo URLs or the `Cookie` header: they contain signatures and the user's session |

??? danger "Security"
    | # | Rule |
    |---|---|
    | P17 | Bind `127.0.0.1` only, always validate `Host` (DNS rebinding). The token is optional |
    | P23 | The yt-dlp cookie file holds the user's session: mode `0600`, deleted in a `finally` |
    | P28 | Domain-filter every cookie import: a browser jar holds every site's session. Keep youtube.com only |
    | P29 | Open mode needs an `Origin` check: CORS doesn't stop a cross-site POST from being *sent*. Refuse unsafe methods with a foreign `Origin` |
    | P30 | Store cookies with their domain. Flattening to `{name: value}` lets another site's `SID` overwrite YouTube's |

??? danger "Processes & platform"
    | # | Rule |
    |---|---|
    | P6 | Read a subprocess's stdout and stderr on separate threads (or one event channel), never one after the other |
    | P7 | Decode subprocess output as UTF-8 with replacement (`from_utf8_lossy`, `errors="ignore"`) and set `PYTHONIOENCODING=utf-8`: Windows consoles default to cp1252 |
    | P11 | Webview `localStorage` is per-origin: cross-tool messages go through the `/api/logs` relay |

??? danger "Frontend"
    | # | Rule |
    |---|---|
    | P12 | Every polling timer has an in-flight guard |

??? danger "Tests"
    | # | Rule |
    |---|---|
    | P27 | Don't monkeypatch pydantic private attributes on `settings`: use `configure_paths()` / `restore_paths()` (the `temp_dirs` fixture) |

(Numbers P8 and P10 aren't used.)
