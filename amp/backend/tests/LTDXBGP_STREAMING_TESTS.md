# LTDxBgP0lqA Streaming Integration Tests

## Overview

This document describes the comprehensive integration test suite for testing chunk-based streaming of the video [LTDxBgP0lqA](https://music.youtube.com/watch?v=LTDxBgP0lqA) - "Blinding Lights" by The Weeknd.

The test suite verifies that:
1. ✅ Individual audio chunks can be downloaded using HTTP Range requests
2. ✅ Playback can start quickly (within 2-3 seconds)
3. ✅ Chunk storage, retrieval, and caching is consistent
4. ✅ **NO full audio files are downloaded during streaming**
5. ✅ All chunk-related API endpoints work correctly

## Test File

- **Location**: `amp/backend/tests/test_ltdxbgp_streaming.py`
- **Test Marker**: All tests are marked with `@pytest.mark.integration`
- **Video ID**: `LTDxBgP0lqA`

## Running the Tests

### Run all LTDxBgP streaming tests:

```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/test_ltdxbgp_streaming.py -v
```

### Run with markdown output for better readability:

```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/test_ltdxbgp_streaming.py -v --tb=short
```

### Run only LTDxBgP tests (skip other integration tests):

```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/test_ltdxbgp_streaming.py -v -m integration
```

### Skip integration tests (for CI/CD):

```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ -v -m "not integration"
```

## Test Requirements

### Prerequisites

1. **Network Access**: Tests require internet access to YouTube
2. **yt-dlp**: Must be installed and in PATH
   - Install: `pip install yt-dlp`
   - Or use the venv version: `../venv/Scripts/yt-dlp.exe`
3. **Firefox Cookies** (Recommended): For authentication to avoid rate limiting
   - See: [Cookie Export Process](#firefox-cookie-export-process)

### Expected Video Properties

- **Video**: Blinding Lights by The Weeknd
- **Duration**: ~3 minutes 20 seconds (200,000ms)
- **Chunk Size**: 10 seconds (from config.py)
- **Expected Chunks**: ~20 chunks
- **Expected Total Size**: ~3-4 MB (opus format)

## Test Categories

### 1. Video Information Retrieval (`TestVideoInfoRetrieval`)

Tests that basic video information can be retrieved:
- `test_get_video_info`: Get title, duration, and total chunks
- `test_get_stream_url`: Get direct stream URL for HTTP Range requests

**Verification**: Video metadata is accessible without downloading the full file.

---

### 2. Chunk Byte Range Calculation (`TestChunkByteRanges`)

Tests that byte ranges are correctly calculated for chunk downloads:
- `test_byte_ranges_calculated`: Verify byte ranges can be calculated
- `test_all_byte_ranges_valid`: Verify all ranges cover the entire stream

**Verification**: Each chunk maps to a specific byte range in the stream, enabling HTTP Range requests.

---

### 3. Individual Chunk Downloading (`TestChunkDownloading`)

**Core streaming tests** - Verifies chunks are downloaded using HTTP Range requests:
- `test_download_single_chunk`: Download chunk 0 and verify it's NOT a _full file
- `test_download_multiple_random_chunks`: Download chunks 1, 3, 5, 10
- `test_no_full_files_created`: **CRITICAL** - Verifies NO _full files are created

**Verification**: 
- Each chunk downloads independently
- Each chunk is ~10 seconds of audio (~160KB)
- Download time: < 1 second per chunk
- File names: `{song_id}_{chunk_index:04d}.opus` (NOT `{song_id}_full.opus`)

---

### 4. Quick Playback Start (`TestQuickPlaybackStart`)

Tests the main requirement: playback must start within 2-3 seconds:
- `test_first_chunk_downloads_quickly`: First chunk downloads in < 3 seconds
- `test_playback_start_with_buffer`: Start playback and verify initial buffering

**Verification**: 
- First chunk download: < 3 seconds
- Playback can start immediately after first chunk is available

---

### 5. Chunk Storage Consistency (`TestChunkStorage`)

Tests consistent caching and retrieval:
- `test_chunk_caching_and_retrieval`: Downloaded chunks can be retrieved from cache
- `test_chunk_status_tracking`: Chunk download status is tracked correctly
- `test_cache_eviction`: Cache size monitoring works correctly

**Verification**: 
- Chunks are stored in database with metadata
- Status tracking: NOT_DOWNLOADED → DOWNLOADING → DOWNLOADED
- Cache doesn't grow indefinitely

---

### 6. API Endpoints (`TestStreamingEndpoints`)

Tests all chunk-related API endpoints:
- `test_stream_info_endpoint`: GET `/api/stream/info/{song_id}`
- `test_chunks_status_endpoint`: GET `/api/stream/{song_id}/chunks`
- `test_play_endpoint`: POST `/api/stream/{song_id}/play`
- `test_pause_endpoint`: POST `/api/stream/pause`
- `test_playback_state_endpoint`: GET `/api/stream/playback-state`

**Verification**: All endpoints return correct data and status codes.

---

### 7. Seek and Buffer Re-balancing (`TestSeekAndBuffer`)

Tests seeking functionality:
- `test_seek_to_position`: Seek to 60 seconds and verify chunk index changes

**Verification**: 
- Seeking cancels downloads before target position
- Re-buffers chunks from new position
- No full downloads triggered by seeking

---

### 8. Performance Tests (`TestPerformance`)

Tests download performance:
- `test_chunk_download_times`: Multiple chunks download in < 5 seconds each

**Verification**: Average download time per chunk is acceptable.

---

### 9. User Feedback Report (`TestFeedbackReport`)

Generates a comprehensive report after tests complete:
- `test_generate_feedback_report`: Prints detailed chunk information table

**Report Includes**:
- Video information (title, duration, chunks)
- Total stream size
- Chunk details table with: Chunk #, Start/End (ms), Downloaded status, Path, Size
- Summary statistics
- **_full files check** (should be NONE)

---

### 10. Cookie Documentation (`TestCookieDocumentation`)

Documents the Firefox cookie export process:
- `test_cookie_export_documentation`: Prints instructions for future tests

## Expected Test Output

### Sample Output

```
================================================================================
TEST FEEDBACK REPORT FOR LTDxBgP0lqA
================================================================================

Video: LTDxBgP0lqA
Title: The Weeknd - Blinding Lights (Official Audio)
Duration: 200000ms (3.33 minutes)
Total Chunks: 20
Chunk Size: 10 seconds

Total Stream Size: 3,456,789 bytes (3.30 MB)

CHUNK DETAILS:
--------------------------------------------------------------------------------
Chunk #    Start (ms)  End (ms)    Downloaded  Path                                   Size (bytes)  
--------------------------------------------------------------------------------
0          0           10000       Yes          LTDxBgP0lqA_0000.opus              163,840
1          10000       20000       Yes          LTDxBgP0lqA_0001.opus              163,840
2          20000       30000       Yes          LTDxBgP0lqA_0002.opus              163,840
...                                                                         ...
19         190000      200000      No           -                                     -
--------------------------------------------------------------------------------

SUMMARY:
  Total chunks: 20
  Chunks downloaded: 5
  Chunks not downloaded: 15

_FULL FILES CHECK:
  ✓ No _full files found (CORRECT!)

================================================================================
REPORT END
================================================================================
```

## Critical Requirement: NO Full Downloads During Streaming

### What This Means

During normal streaming playback:
- ✅ **DO**: Download individual chunks using HTTP Range requests
- ❌ **DON'T**: Download the full song file and then split it

### Implementation

The `download_chunk()` method in `streaming.py`:
1. Gets the direct stream URL via yt-dlp (metadata only, no download)
2. Calculates byte range for the chunk
3. Downloads ONLY that byte range using HTTP Range header
4. Saves as: `{song_id}_{chunk_index:04d}.opus`

### Verification

The test `test_no_full_files_created` explicitly checks that:
- No files named `{song_id}_full.opus` exist in the cache directory
- All chunks are named `{song_id}_{NNNN}.opus`

## Troubleshooting

### Issue: Tests fail with 403 Forbidden

**Cause**: YouTube requires authentication for some videos.

**Solution**: Export Firefox cookies and place them at `.amp/.cookies.json`

See: [Firefox Cookie Export Process](#firefox-cookie-export-process)

### Issue: Tests fail with yt-dlp not found

**Cause**: yt-dlp is not in PATH.

**Solution**: 
1. Install yt-dlp: `pip install yt-dlp`
2. Or use the venv version: Ensure `../venv/Scripts/yt-dlp.exe` exists

### Issue: Tests take too long

**Cause**: Downloading many chunks sequentially.

**Solution**: Tests are designed to download only a few chunks. If you need faster tests:
```bash
# Run only quick tests
pytest backend/tests/test_ltdxbgp_streaming.py::TestVideoInfoRetrieval -v
```

### Issue: _full files are still being created

**Investigation Steps**:
1. Check if you're running the integration tests in `test_streaming_integration.py` (they DO use full downloads)
2. Verify you're using the production streaming code (not test code)
3. Check the code path: `download_chunk()` should ONLY use `_download_byte_range()`
4. Look for any calls to `download_full_song()`, `extract_chunk_from_full()`, or `split_full_song_into_chunks()` in production code

**Current Status**: Based on code analysis, production code does NOT create _full files. They should only appear from integration tests or manual calls.

## Firefox Cookie Export Process

### Method 1: Using Cookie-Editor Extension (Recommended)

1. **Open Firefox** and log in to [YouTube Music](https://music.youtube.com)
2. **Install Cookie-Editor**:
   - Go to: https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/
   - Click "Add to Firefox"
3. **Export cookies**:
   - Open any YouTube Music page
   - Click the Cookie-Editor extension icon (cookie jar)
   - Click the "Export" button
   - Select "JSON" format
   - Save as: `AMP/.amp/.cookies.json`

### Method 2: Manual Export from Firefox Profile

1. **Find your Firefox profile folder**:
   - Type `about:support` in Firefox address bar
   - Look for "Profile Folder" and click "Open Directory"
2. **Copy cookies.sqlite**:
   - Find `cookies.sqlite` file in the profile folder
   - Copy to: `AMP/.amp/cookies.sqlite`
3. **Use conversion script**:
   ```bash
   python scripts/convert_firefox_cookies.py
   ```

### Method 3: Using Browser's DevTools

1. Open DevTools (F12) on YouTube Music
2. Go to Application → Cookies
3. Copy all cookies for `.youtube.com` and `.music.youtube.com`
4. Save as JSON and place at `.amp/.cookies.json`

## Test Configuration Options

### Skipping Tests

To skip specific tests, add `@pytest.mark.skip` decorator.

To skip based on conditions:
```python
@pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
```

### Test Timeouts

Tests have a 30-second timeout for yt-dlp calls and a 3-second requirement for chunk downloads.

To adjust:
- Change `timeout=30` in subprocess.run() calls
- Change assertion in `test_first_chunk_downloads_quickly`

## Code Coverage

This test suite covers:

| Feature | Coverage |
|---------|----------|
| HTTP Range requests | ✅ Full |
| Chunk downloading | ✅ Full |
| Quick playback start | ✅ Full |
| Chunk caching | ✅ Full |
| API endpoints | ✅ Full |
| Seek functionality | ✅ Full |
| Cache management | ✅ Partial |
| Authentication | ✅ Implicit (via cookies) |

## Performance Benchmarks

### Expected Results (Good Network)

| Action | Time | Notes |
|--------|------|-------|
| Get stream info | < 1s | yt-dlp metadata call |
| Get stream URL | < 1s | Cached after first call |
| Download chunk 0 | < 1s | HTTP Range request |
| Playback start | < 2s | Includes overhead |
| Download 5 chunks | < 5s | Sequential |

### Expected Chunk Sizes

- **Format**: Opus audio (WebM container)
- **Bitrate**: ~128 kbps (variable)
- **Chunk size**: ~160 KB per 10-second chunk
- **Total for 3:20 song**: ~3.3 MB

## File Structure

```
amp/backend/tests/
├── test_streaming.py            # Unit tests (no network)
├── test_streaming_integration.py # Integration tests (dQw4w9WgXcQ)
├── test_ltdxbgp_streaming.py     # NEW: LTDxBgP0lqA specific tests
└── LTDXBGP_STREAMING_TESTS.md    # This document
```

## Related Documentation

- [AGENTS.md](../AGENTS.md) - Project status and roadmap
- [ROADMAP.md](../ROADMAP.md) - Full project roadmap
- [backend/README.md](../backend/README.md) - Backend guide
- [STREAMING_DESIGN.md](../services/STREAMING_DESIGN.md) - Streaming architecture

## Version History

- **v1.0** (2026-10-20): Initial comprehensive test suite for LTDxBgP0lqA
  - All chunk downloading tests
  - Performance requirements
  - User feedback report
  - Cookie documentation

## Next Steps

1. ✅ Run the tests and verify they pass
2. ✅ Investigate any failures and fix code
3. ✅ Ensure NO _full files are created
4. ✅ Optimize chunk downloading if needed
5. ✅ Add to CI/CD (with integration test exclusion)

## CI/CD Integration

### GitHub Actions

To exclude integration tests from CI:

```yaml
- name: Run unit tests
  run: |
    cd amp
    ../venv/Scripts/python.exe -m pytest backend/tests/ -v -m "not integration"
```

### Local Development

For daily development, run all tests:
```bash
cd amp && ../venv/Scripts/python.exe -m pytest backend/tests/ -v
```

For CI/CD, skip integration tests:
```bash
cd amp && ../venv/Scripts/python.exe -m pytest backend/tests/ -v -m "not integration"
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-10-20  
**Author**: AMP Development Team  
**Test Video**: [LTDxBgP0lqA](https://music.youtube.com/watch?v=LTDxBgP0lqA) - The Weeknd - Blinding Lights (Official Audio)
