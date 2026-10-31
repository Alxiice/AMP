"""Phase 4 API contract: /play resolves then plays, one error shape, prefetch mode."""

import threading
from unittest.mock import patch

import pytest

from backend.services.extractor import ExtractionError
from backend.services.streaming import Priority, SegState, StreamingService, get_streaming_service
from backend.tests.test_streaming import _make_stream_info

SONG = "dQw4w9WgXcQ"
OTHER = "BAgTQhR8MLo"


@pytest.fixture()
def svc(client_no_auth):
    """The app's service with extraction mocked and the download queue recorded, not run."""
    service = get_streaming_service()
    enqueued = []
    with patch.object(service, "_build_stream_info", side_effect=lambda sid: _make_stream_info(sid, 10)), \
         patch.object(service._dl_manager, "enqueue",
                      side_effect=lambda *args: enqueued.append(args) or True):
        service.enqueued = enqueued
        yield service


def _code(resp):
    return resp.json()["detail"]["code"]


class TestErrorModel:
    def test_invalid_song_id_is_400(self, client_no_auth):
        resp = client_no_auth.post("/api/stream/bad/play")
        assert resp.status_code == 400
        assert _code(resp) == "invalid_id"
        assert resp.json()["detail"]["message"]

    @pytest.mark.parametrize("path", [
        "/api/stream/info/bad", "/api/stream/bad/audio", "/api/stream/bad/chunks", "/api/song/bad",
    ])
    def test_invalid_id_everywhere(self, client_no_auth, path):
        resp = client_no_auth.get(path)
        assert resp.status_code == 400 and _code(resp) == "invalid_id"

    @pytest.mark.parametrize("code, status", [
        ("unavailable", 404), ("no_audio", 404), ("auth_required", 401),
        ("node_missing", 503), ("extract_failed", 502), ("weird_new_code", 502),
    ])
    def test_play_extraction_error_is_coded(self, svc, client_no_auth, code, status):
        with patch.object(svc, "_build_stream_info", side_effect=ExtractionError(code, "boom")):
            resp = client_no_auth.post(f"/api/stream/{SONG}/play")
        assert resp.status_code == status
        assert _code(resp) == (code if code != "weird_new_code" else "extract_failed")
        assert svc.get_playback_state()["song_id"] == ""  # a failed /play doesn't take the session

    def test_play_unavailable_is_404_coded(self, svc, client_no_auth):
        with patch.object(svc, "_build_stream_info", side_effect=ExtractionError("unavailable")):
            resp = client_no_auth.post(f"/api/stream/{SONG}/play")
        assert resp.status_code == 404
        assert resp.json() == {"detail": {"code": "unavailable", "message": "This video is unavailable."}}

    def test_table_build_failure_is_extract_failed(self, svc, client_no_auth):
        with patch.object(svc, "_build_stream_info", return_value=None):
            resp = client_no_auth.post(f"/api/stream/{SONG}/play")
        assert resp.status_code == 502 and _code(resp) == "extract_failed"

    def test_audio_error_is_json(self, svc, client_no_auth):
        with patch.object(svc, "_build_stream_info", side_effect=ExtractionError("auth_required")):
            resp = client_no_auth.get(f"/api/stream/{SONG}/audio")
        assert resp.status_code == 401
        assert resp.headers["content-type"].startswith("application/json")
        assert _code(resp) == "auth_required"

    def test_stream_info_error_is_coded(self, svc, client_no_auth):
        with patch.object(svc, "_build_stream_info", side_effect=ExtractionError("no_audio")):
            resp = client_no_auth.get(f"/api/stream/info/{SONG}")
        assert resp.status_code == 404 and _code(resp) == "no_audio"

    def test_ready_route_removed(self, client_no_auth):
        assert client_no_auth.get(f"/api/stream/{SONG}/ready").status_code == 404


class TestPlay:
    def test_play_returns_summary(self, svc, client_no_auth):
        resp = client_no_auth.post(f"/api/stream/{SONG}/play")
        assert resp.status_code == 200
        body = resp.json()
        assert body["song_id"] == SONG
        assert body["duration_ms"] == 50_000
        assert body["mime_type"] == "audio/mp4"
        assert body["segment_count"] == 10
        assert body["epoch"] == 0 and body["is_dash"] is True
        assert body["cached_ahead"] is False
        assert svc.get_playback_state()["song_id"] == SONG
        assert (SONG, 0, Priority.CRITICAL, 0) in svc.enqueued

    def test_cached_ahead_when_init_and_first_segment_done(self, svc, client_no_auth):
        for index in (-1, 0):
            svc._registry.claim((SONG, index))
            svc._registry.complete((SONG, index), True)
        assert client_no_auth.post(f"/api/stream/{SONG}/play").json()["cached_ahead"] is True

    def test_superseded_play_leaves_session_alone(self, temp_dirs):
        """A slow /play for A that finishes after /play B must not take the session back."""
        svc = StreamingService()
        a_resolving, release_a = threading.Event(), threading.Event()

        def build(song_id):
            if song_id == SONG:
                a_resolving.set()
                release_a.wait(5)
            return _make_stream_info(song_id, 4)

        results = {}
        with patch.object(svc, "_build_stream_info", side_effect=build), \
             patch.object(svc._dl_manager, "enqueue", return_value=True):
            t = threading.Thread(target=lambda: results.setdefault("a", svc.start_playback(SONG)))
            t.start()
            assert a_resolving.wait(5)
            results["b"] = svc.start_playback(OTHER)
            release_a.set()
            t.join(5)
        assert results["b"]["message"] == "playback started"
        assert results["a"]["message"] == "superseded"
        assert svc.get_playback_state()["song_id"] == OTHER


class TestPrefetch:
    def test_prefetch_uses_low_priority(self, svc, client_no_auth):
        client_no_auth.post(f"/api/stream/{OTHER}/play")
        before = svc.get_playback_state()
        svc.enqueued.clear()
        resp = client_no_auth.post(f"/api/stream/buffer/{SONG}?mode=prefetch")
        assert resp.status_code == 200
        assert resp.json()["queued"] == 3
        assert svc.enqueued == [(SONG, -1, Priority.LOW, 0), (SONG, 0, Priority.LOW, 0), (SONG, 1, Priority.LOW, 0)]
        after = svc.get_playback_state()
        assert after["song_id"] == OTHER == before["song_id"]
        assert after["epoch"] == before["epoch"]

    def test_prefetch_then_play_outranks_low(self, temp_dirs):
        """Playing the prefetched song re-ranks its LOW items (registry re-rank on better priority)."""
        svc = StreamingService()
        svc._stream_info_cache.set(SONG, _make_stream_info(SONG, 10))
        svc.prefetch(SONG)
        assert svc._registry.get((SONG, 0)) == SegState.QUEUED
        assert svc._registry._songs[SONG][0].priority == Priority.LOW
        svc.start_playback(SONG)
        assert svc._registry._songs[SONG][0].priority == Priority.CRITICAL

    def test_prefetch_error_is_coded(self, svc, client_no_auth):
        with patch.object(svc, "_build_stream_info", side_effect=ExtractionError("unavailable")):
            resp = client_no_auth.post(f"/api/stream/buffer/{SONG}?mode=prefetch")
        assert resp.status_code == 404 and _code(resp) == "unavailable"

    def test_bad_mode_is_422(self, client_no_auth):
        assert client_no_auth.post(f"/api/stream/buffer/{SONG}?mode=nope").status_code == 422

    def test_default_mode_is_current(self, svc, client_no_auth):
        resp = client_no_auth.post(f"/api/stream/buffer/{SONG}")
        assert resp.status_code == 200 and resp.json()["mode"] == "current"
