# Streaming System Design Document

## Core Principle

> **NEVER download the full audio file during streaming.**
> 
> Each chunk must be downloaded independently using HTTP Range requests.
> Full file downloads are ONLY for explicit caching operations, never for playback.

---

## Overview

The AMP streaming system implements **true chunk-based streaming** where:
1. Audio is divided into ~10-second chunks
2. Each chunk is downloaded independently via HTTP Range requests
3. Playback starts as soon as the first chunk is available
4. Subsequent chunks download progressively while playing

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Player UI  │───▶│ Audio Element │───▶│ /api/stream/audio │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
│       │                     │                                 │       │
│       ▼                     ▼                                 ▼       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Play/Pause   │    │ onended      │    │ Generate Stream   │   │
│  │ Seek         │    │ event        │    │ (chunk by chunk)  │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    StreamingService                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ get_stream   │  │ download_    │  │ generate_        │  │  │
│  │  │ info()       │──▶│ chunk()      │──▶│ audio_stream()   │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │       │               │                    │               │  │
│  │       ▼               ▼                    ▼               │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ yt-dlp       │  │ HTTP Range   │  │ Yield chunk      │  │  │
│  │  │ (metadata    │  │ Request       │  │ data sequentially │  │  │
│  │  │  only)       │  │               │  │                  │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Chunk Cache                               │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │  │
│  │  │ LTDxBg   │  │ LTDxBg   │  │ LTDxBg   │  │ ...          │  │  │
│  │  │ P0lqA_   │  │ P0lqA_   │  │ P0lqA_   │  │              │  │  │
│  │  │ 0000    │  │ 0001    │  │ 0002    │  │              │  │  │
│  │  │ .opus   │  │ .opus   │  │ .opus   │  │              │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   YouTube CDN   │
                    │   (Direct URL)  │
                    └─────────────────┘
```

## Key Components

### 1. Chunk Structure

```
Song: The Weeknd - Blinding Lights (200,000ms)
├── Chunk 0:   0ms     - 10,000ms   → LTDxBgP0lqA_0000.opus
├── Chunk 1:  10,000ms - 20,000ms   → LTDxBgP0lqA_0001.opus
├── Chunk 2:  20,000ms - 30,000ms   → LTDxBgP0lqA_0002.opus
│           ...
└── Chunk 19: 190,000ms - 200,000ms → LTDxBgP0lqA_0019.opus
```

**Properties:**
- **Duration**: 10 seconds per chunk (configurable via `CHUNK_SIZE_SEC`)
- **Size**: ~160 KB per chunk (at ~128 kbps opus)
- **Format**: Opus audio in WebM container
- **Naming**: `{song_id}_{chunk_index:04d}.opus`

### 2. Download Flow

```
1. User clicks play on song LTDxBgP0lqA
   │
2. Frontend calls: POST /api/stream/LTDxBgP0lqA/play
   │
3. Backend calls: start_playback(LTDxBgP0lqA)
   │
4. StreamingService:
   │  a. Get stream info (yt-dlp --dump-json, metadata only)
   │     → Gets: title, duration, format URL, filesize
   │  
   │  b. Calculate byte ranges:
   │     → total_bytes / total_chunks = bytes_per_chunk
   │     → Chunk 0: bytes 0-163839
   │     → Chunk 1: bytes 163840-327679
   │     → ...
   │  
   │  c. Download chunk 0 via HTTP Range:
   │     → GET https://.../videoplayback?...
   │     → Headers: Range: bytes=0-163839
   │     → Save to: .amp/cache/chunks/LTDxBgP0lqA_0000.opus
   │  
   │  d. Start buffering ahead (chunks 1, 2, 3, ...)
   │
5. Frontend calls: GET /api/stream/LTDxBgP0lqA/audio
   │
6. Backend streams audio:
   │  a. Check if chunk 0 cached → Yes, use it
   │  b. Check if chunk 1 cached → No, download it
   │  c. Yield chunk 0 data
   │  d. Yield chunk 1 data (when downloaded)
   │  e. Continue...
   │
7. Frontend plays audio via <audio> element
```

### 3. HTTP Range Request

**Request:**
```http
GET /videoplayback?... HTTP/1.1
Host: rr1---sn-...googlevideo.com
Range: bytes=0-163839
User-Agent: Mozilla/5.0 ...
Referer: https://www.youtube.com/
Cookie: ... (if authenticated)
```

**Response:**
```http
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-163839/3456789
Content-Length: 163840
Content-Type: audio/webm

[binary audio data for chunk 0]
```

**Key Points:**
- Uses HTTP 206 (Partial Content) for range requests
- Only downloads the requested byte range
- No full file download
- Works with YouTube CDN

## Core Methods

### StreamingService.download_chunk()

**Purpose:** Download a single audio chunk using HTTP Range request

**Signature:**
```python
def download_chunk(self, song_id: str, chunk_index: int, force: bool = False) -> Optional[Path]:
```

**Algorithm:**
```python
1. Check if chunk already cached
   → If yes, return cached path

2. Mark chunk as DOWNLOADING
   → Update _chunk_status[song_id][chunk_index] = DOWNLOADING

3. Get direct stream URL
   → stream_url = _get_stream_url_cached(song_id)
   → Uses yt-dlp -g (get URL only, no download)

4. Calculate byte range
   → byte_range = _get_chunk_byte_range(song_id, chunk_index)
   → Returns (start_byte, end_byte)

5. Generate output path
   → output_path = _generate_chunk_filename(song_id, chunk_index)
   → Returns: .amp/cache/chunks/{song_id}_{chunk_index:04d}.opus

6. Download byte range via HTTP
   → success = _download_byte_range(stream_url, output_path, start_byte, end_byte)
   → Uses requests.get() with Range header

7. If successful:
   → Mark as DOWNLOADED
   → Save to database (CachedChunk)
   → Return output_path
   
8. If failed:
   → Mark as ERROR
   → Return None
```

**⚠️ CRITICAL: This method MUST NOT call:**
- `download_full_song()`
- `extract_chunk_from_full()`
- `split_full_song_into_chunks()`
- Any method that downloads the entire file

### StreamingService.generate_audio_stream()

**Purpose:** Generate audio data chunk-by-chunk for streaming

**Signature:**
```python
def generate_audio_stream(self, song_id: str):
```

**Algorithm:**
```python
1. Get stream info
   → Verify song exists and has chunks

2. For each chunk_index in range(total_chunks):
   a. Check if chunk cached
      → If yes, use cached path
      
   b. If not cached, download it
      → chunk_path = download_chunk(song_id, chunk_index)
      → This triggers HTTP Range request
      
   c. Read chunk file
      → Open chunk_path in binary mode
      
   d. Yield data in 64KB chunks
      → while True:
          data = f.read(65536)
          if not data: break
          yield data
```

**Key Property:**
- Audio stream starts yielding data as soon as chunk 0 is downloaded
- Subsequent chunks download while audio is playing
- No buffering delay (first chunk downloads in ~0.16s)

## What Methods Are NOT for Streaming

### ❌ download_full_song()

**Purpose:** Download the entire song file (for caching/offline playback)

**When to Use:**
- Explicit user request to cache song for offline
- Pre-caching during idle time
- Testing only (with clear documentation)

**When NOT to Use:**
- ❌ During normal streaming playback
- ❌ In `download_chunk()`
- ❌ In `generate_audio_stream()`
- ❌ Any code path triggered by play/pause/seek

**Output:** `{song_id}_full.opus`

### ❌ extract_chunk_from_full()

**Purpose:** Extract a single chunk from a full song file using ffmpeg

**When to Use:**
- Only if HTTP Range requests are not working
- As a last resort with clear warnings
- For debugging purposes only

**When NOT to Use:**
- ❌ During normal streaming (defeats the purpose!)
- ❌ In production code

**Note:** This method requires ffmpeg and downloads the full song first.

### ❌ split_full_song_into_chunks()

**Purpose:** Split a full song file into chunks using ffmpeg

**When to Use:**
- Only for explicit caching operations
- With user consent

**When NOT to Use:**
- ❌ During streaming
- ❌ In any code path that affects playback

## File Naming Convention

| File Type | Pattern | Example | Purpose |
|-----------|---------|---------|---------|
| Chunk | `{song_id}_{NNNN}.opus` | `LTDxBgP0lqA_0000.opus` | Streaming playback |
| Full song | `{song_id}_full.opus` | `LTDxBgP0lqA_full.opus` | **NEVER during streaming** |
| Metadata | `{song_id}.json` | `LTDxBgP0lqA.json` | Cache, metadata only |

**⚠️ If you see `_full.opus` files appearing during streaming, THIS IS A BUG!**

## Verification Checklist

To ensure streaming is working correctly:

1. ✅ **Check file names in cache:**
   ```bash
   ls .amp/cache/chunks/
   ```
   Should see: `LTDxBgP0lqA_0000.opus`, `LTDxBgP0lqA_0001.opus`, etc.
   Should NOT see: `LTDxBgP0lqA_full.opus`

2. ✅ **Check download_chunk() implementation:**
   ```bash
   grep -A 50 "def download_chunk" backend/services/streaming.py
   ```
   Should see: `_download_byte_range()` call
   Should NOT see: `download_full_song()`, `extract_chunk_from_full()`

3. ✅ **Monitor network traffic:**
   - When playing a song, you should see multiple small HTTP requests
   - Each request should have a `Range: bytes=X-Y` header
   - Each response should be HTTP 206 (Partial Content)
   - Should NOT see a single large download of the full file

4. ✅ **Check logs:**
   ```bash
   tail -f .amp/logs/app.log | grep "Downloading chunk"
   ```
   Should see: `Downloading chunk N: bytes X-Y (Z bytes)`
   Should NOT see: `Downloading full song`

## Performance Requirements

| Metric | Requirement | Typical Value |
|--------|-------------|---------------|
| First chunk download | < 3 seconds | ~0.16s |
| Chunk size | ~160 KB | 150-180 KB |
| Playback start | < 3 seconds | ~0.2-0.5s |
| Chunk download | < 5 seconds | ~0.16s |
| Buffer ahead | 15 seconds | Configurable |

## Error Handling

### Content-Length Not Available

YouTube CDN sometimes omits Content-Length header. Fallback chain:

1. **HTTP HEAD request** - Fastest, but sometimes missing
2. **GET with Range: bytes=0-0** - Parse Content-Range header
3. **yt-dlp --get-filesize** - Query yt-dlp for file size
4. **Estimate** - Calculate from bitrate × duration + 10% overhead

### Byte Range Calculation

If content length is estimated:
- Use proportional calculation: `chunk_bytes = total_bytes × (10000ms / duration_ms)`
- This ensures each chunk covers approximately CHUNK_SIZE_SEC seconds
- Works even with estimated sizes

### Authentication

For age-restricted content or rate limiting:
- Export Firefox cookies to `.amp/.cookies.json`
- Auth service automatically copies to `ytm_session.json`
- yt-dlp calls include `--cookies` argument
- HTTP requests include Cookie header

## Testing

### Integration Tests

See: `backend/tests/test_ltdxbgp_streaming.py`

Tests verify:
- ✅ Individual chunk downloads via HTTP Range
- ✅ Quick playback start (< 3 seconds)
- ✅ NO _full files created
- ✅ All chunk-related endpoints
- ✅ Consistent storage and retrieval

### Running Tests

```bash
# Run LTDxBgP streaming tests
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/test_ltdxbgp_streaming.py -v
```

## Troubleshooting

### Problem: _full files appearing during streaming

**Check:**
1. Are you running integration tests? They DO use full downloads
2. Is there any code calling `download_full_song()`?
3. Is `extract_chunk_from_full()` being called?

**Solution:**
- Remove all calls to full download methods from streaming code paths
- Ensure `download_chunk()` only uses `_download_byte_range()`
- Add assertions to fail if _full files are detected

### Problem: Playback takes too long to start

**Check:**
1. Is first chunk downloading via HTTP Range?
2. Is yt-dlp getting metadata quickly?
3. Are there network issues?

**Solution:**
- Verify `_get_stream_url_cached()` returns URL quickly
- Check logs for `Downloading chunk 0` message
- Test network connection to YouTube

### Problem: Chunks are wrong size

**Check:**
1. Is byte range calculation correct?
2. Does content length match actual file size?

**Solution:**
- Verify `_get_url_content_length()` returns correct value
- Check `_get_chunk_byte_range()` calculations
- Test with known video (LTDxBgP0lqA)

## Future Optimizations

### 1. DASH Protocol

YouTube serves audio via DASH (Dynamic Adaptive Streaming over HTTP).
- Audio is already segmented in the manifest
- Each segment is a complete audio chunk
- No need for byte range calculations

**Status:** Current HTTP Range approach works well. DASH could be more reliable but adds complexity.

### 2. Parallel Chunk Downloading

**Current:** 4 parallel download workers
**Potential:** Increase to 8-16 for better buffering
**Consideration:** Don't overwhelm network or hit rate limits

### 3. Cache Warming

Download first N chunks when user hovers over a song (before play).

### 4. Smart Pre-fetching

Predict next song and start buffering based on user behavior.

## Summary

The AMP streaming system implements **true chunk-based streaming** where:

1. ✅ **Each chunk is downloaded independently** using HTTP Range requests
2. ✅ **Playback starts immediately** after first chunk is available
3. ✅ **NO full file downloads** occur during streaming
4. ✅ **Efficient caching** allows offline playback
5. ✅ **Clear separation** between streaming and caching code paths

**Core Principle:** NEVER download the full audio file during streaming. Each chunk must be downloaded independently.

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-20  
**Author:** AMP Development Team
