"""Unit tests for services/extractor.py — format selection, single-flight, caches.

All tests mock YoutubeDL; none use the network.
"""

import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from backend.services.extractor import (
    MAX_AVAILABLE_AT_WAIT_S,
    ExtractionError,
    SingleFlight,
    StreamExtractor,
    build_ydl_opts,
    classify_download_error,
    select_audio_format,
)

SONG = "dQw4w9WgXcQ"


def _fmt(itag, acodec="mp4a.40.2", vcodec="none", ext="m4a", abr=128, url=None, **kw):
    return {"format_id": str(itag), "acodec": acodec, "vcodec": vcodec, "ext": ext, "abr": abr,
            "url": url or f"https://cdn.example.com/{itag}?expire=9999999999", **kw}


F140 = _fmt(140, filesize=4_172_237)
F251 = _fmt(251, acodec="opus", ext="webm", abr=160)
F18 = _fmt(18, vcodec="avc1.42001E", ext="mp4", abr=96)
F22 = _fmt(22, vcodec="avc1.64001F", ext="mp4", abr=192)


def _info(*formats, duration=258, title="Song"):
    return {"id": SONG, "title": title, "duration": duration, "formats": list(formats)}


@contextmanager
def mock_ydl(side_effect=None, return_value=None):
    """Patch yt_dlp.YoutubeDL; yields the class mock (call_args = opts)."""
    with patch("yt_dlp.YoutubeDL") as cls:
        ydl = MagicMock()
        ydl.__enter__ = MagicMock(return_value=ydl)
        ydl.__exit__ = MagicMock(return_value=False)
        if side_effect is not None:
            ydl.extract_info.side_effect = side_effect
        else:
            ydl.extract_info.return_value = return_value
        cls.return_value = ydl
        cls.ydl = ydl
        yield cls


def _extractor(clients=("default",), authenticated=False):
    auth = MagicMock()
    auth.is_authenticated = authenticated
    auth.write_netscape_cookie_file.return_value = None
    ex = StreamExtractor(auth, dependencies={"node": True, "ejs": True, "yt_dlp": "test"})
    return ex


@pytest.fixture()
def clients(monkeypatch):
    from backend.config import settings

    def set_clients(*names):
        monkeypatch.setattr(settings, "YTDLP_PLAYER_CLIENTS", list(names))

    set_clients("default")
    return set_clients


# ---------------------------------------------------------------------------
# select_audio_format (pure)
# ---------------------------------------------------------------------------


class TestSelectAudioFormat:
    def test_select_prefers_itag_140(self):
        s = select_audio_format(_info(F251, F140, F18), SONG)
        assert s.itag == "140"
        assert s.mime_type == "audio/mp4"
        assert s.is_audio_only

    def test_select_rejects_muxed_video(self):
        assert select_audio_format(_info(F18, F22), SONG) is None

    def test_select_falls_back_to_opus(self):
        s = select_audio_format(_info(F251, F18), SONG)
        assert s.itag == "251"
        assert s.mime_type == "audio/webm"

    def test_select_prefers_mp4_container_over_bitrate(self):
        f139 = _fmt(139, abr=48)
        assert select_audio_format(_info(F251, f139), SONG).itag == "139"

    def test_select_handles_empty_formats(self):
        assert select_audio_format({"formats": []}, SONG) is None
        assert select_audio_format({}, SONG) is None

    def test_select_skips_formats_without_url(self):
        no_url = dict(F140, url=None)
        assert select_audio_format(_info(no_url, F251), SONG).itag == "251"

    def test_filesize_from_format(self):
        assert select_audio_format(_info(F140), SONG).filesize == 4_172_237

    def test_filesize_from_clen_param(self):
        f = _fmt(140, url="https://cdn.example.com/v?itag=140&clen=3623456&expire=1767225600")
        assert select_audio_format(_info(f), SONG).filesize == 3_623_456

    def test_filesize_unknown(self):
        assert select_audio_format(_info(_fmt(140)), SONG).filesize is None

    def test_expires_at_from_url(self):
        s = select_audio_format(_info(_fmt(140, url="https://cdn.example.com/v?expire=1767225600")), SONG)
        assert s.expires_at == 1767225600 - 300

    def test_expires_at_default_when_missing(self):
        s = select_audio_format(_info(_fmt(140, url="https://cdn.example.com/v")), SONG)
        assert 5 * 3600 - 5 < s.expires_at - time.time() <= 5 * 3600

    def test_metadata(self):
        s = select_audio_format(_info(F140, duration=245.5, title="Hello"), SONG, "visionos")
        assert s.duration_ms == 245_500
        assert s.title == "Hello"
        assert s.player_client == "visionos"
        assert s.song_id == SONG
        assert s.acodec == "mp4a.40.2"


class TestClassify:
    @pytest.mark.parametrize("msg, code", [
        ("ERROR: [youtube] x: Video unavailable", "unavailable"),
        ("ERROR: [youtube] x: Private video. Sign in if you've been granted access", "unavailable"),
        ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "auth_required"),
        ("ERROR: [youtube] x: Sign in to confirm your age", "auth_required"),
        ("ERROR: [youtube] x: The page needs to be reloaded", "extract_failed"),
    ])
    def test_classify(self, msg, code):
        assert classify_download_error(msg) == code


# ---------------------------------------------------------------------------
# build_ydl_opts — option shapes yt-dlp actually honours (F2)
# ---------------------------------------------------------------------------


class TestBuildYdlOpts:
    def test_ydl_opts_player_client_applied(self):
        """yt-dlp must actually see the player_client (no network)."""
        from yt_dlp import YoutubeDL

        with YoutubeDL(build_ydl_opts("android", None, None)) as ydl:
            ie = ydl.get_info_extractor("Youtube")
            assert ie._configuration_arg("player_client") == ["android"]

    def test_ydl_opts_js_runtime_top_level(self):
        opts = build_ydl_opts("android", "bestaudio/best", "/tmp/cookies.txt")
        assert opts["js_runtimes"] == {"node": {}}
        assert opts["extractor_args"]["youtube"]["player_client"] == ["android"]
        assert opts["format"] == "bestaudio/best"
        assert opts["cookiefile"] == "/tmp/cookies.txt"
        assert "nocheckcertificate" not in opts

    def test_ydl_opts_default_client(self):
        opts = build_ydl_opts(None, None, None)
        assert "extractor_args" not in opts
        assert "format" not in opts
        assert "cookiefile" not in opts


# ---------------------------------------------------------------------------
# SingleFlight
# ---------------------------------------------------------------------------


class TestSingleFlight:
    def test_concurrent_callers_share_result(self):
        sf = SingleFlight()
        calls = []
        gate = threading.Event()

        def fn():
            calls.append(1)
            gate.wait(2)
            return object()

        results = []
        threads = [threading.Thread(target=lambda: results.append(sf.do("k", fn))) for _ in range(8)]
        for t in threads:
            t.start()
        time.sleep(0.1)
        gate.set()
        for t in threads:
            t.join(5)
        assert len(calls) == 1
        assert len(results) == 8 and all(r is results[0] for r in results)

    def test_key_free_after_landing(self):
        sf = SingleFlight()
        assert sf.do("k", lambda: 1) == 1
        assert sf.do("k", lambda: 2) == 2

    def test_different_keys_independent(self):
        sf = SingleFlight()
        assert sf.do("a", lambda: "a") == "a"
        assert sf.do("b", lambda: "b") == "b"


# ---------------------------------------------------------------------------
# StreamExtractor
# ---------------------------------------------------------------------------


def _run_concurrently(n, fn):
    results, errors = [], []

    def run():
        try:
            results.append(fn())
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    return results, errors


class TestStreamExtractor:
    def test_single_flight_one_extraction(self, clients):
        ex = _extractor()

        def slow(*a, **kw):
            time.sleep(0.2)
            return _info(F140)

        with mock_ydl(side_effect=slow) as ydl:
            results, errors = _run_concurrently(10, lambda: ex.get(SONG))
        assert not errors
        assert ydl.ydl.extract_info.call_count == 1
        assert len(results) == 10 and all(r is results[0] for r in results)
        assert results[0].itag == "140"

    def test_single_flight_propagates_error(self, clients):
        from yt_dlp.utils import DownloadError

        ex = _extractor()

        def slow(*a, **kw):
            time.sleep(0.2)
            raise DownloadError("ERROR: Video unavailable")

        with mock_ydl(side_effect=slow) as ydl:
            results, errors = _run_concurrently(10, lambda: ex.get(SONG))
        assert not results
        assert len(errors) == 10
        assert all(isinstance(e, ExtractionError) and e.code == "unavailable" for e in errors)
        assert all(e is errors[0] for e in errors)
        assert ydl.ydl.extract_info.call_count == 1

    def test_positive_cache(self, clients):
        ex = _extractor()
        with mock_ydl(return_value=_info(F140)) as ydl:
            first = ex.get(SONG)
            assert ex.get(SONG) is first
        assert ydl.ydl.extract_info.call_count == 1

    def test_expired_entry_re_extracts(self, clients):
        ex = _extractor()
        old = _fmt(140, url=f"https://cdn.example.com/v?expire={int(time.time()) + 100}")  # within margin
        with mock_ydl(return_value=_info(old)) as ydl:
            ex.get(SONG)
            ex.get(SONG)
        assert ydl.ydl.extract_info.call_count == 2

    def test_negative_cache(self, clients):
        from yt_dlp.utils import DownloadError

        ex = _extractor()
        with mock_ydl(side_effect=DownloadError("The page needs to be reloaded")) as ydl:
            with pytest.raises(ExtractionError) as e1:
                ex.get(SONG)
            assert e1.value.code == "extract_failed"
            with pytest.raises(ExtractionError):
                ex.get(SONG)
            assert ydl.ydl.extract_info.call_count == 1  # within TTL: no yt-dlp

        with mock_ydl(return_value=_info(F140)) as ydl:
            assert ex.refresh(SONG).itag == "140"  # refresh clears the negative cache
            assert ydl.ydl.extract_info.call_count == 1

    def test_negative_cache_expires(self, clients):
        from yt_dlp.utils import DownloadError

        ex = _extractor()
        with mock_ydl(side_effect=DownloadError("boom")):
            with pytest.raises(ExtractionError):
                ex.get(SONG)
        failed_at, err = ex._failures.get(SONG)
        ex._failures.set(SONG, (failed_at - 301, err))  # 5 min TTL for extract_failed
        with mock_ydl(return_value=_info(F140)) as ydl:
            assert ex.get(SONG).itag == "140"
        assert ydl.ydl.extract_info.call_count == 1

    def test_unavailable_cached_longer(self, clients):
        from yt_dlp.utils import DownloadError

        ex = _extractor()
        with mock_ydl(side_effect=DownloadError("Video unavailable")):
            with pytest.raises(ExtractionError):
                ex.get(SONG)
        failed_at, err = ex._failures.get(SONG)
        ex._failures.set(SONG, (failed_at - 301, err))  # past 5 min, within 30 min
        with mock_ydl(return_value=_info(F140)) as ydl:
            with pytest.raises(ExtractionError) as e:
                ex.get(SONG)
        assert e.value.code == "unavailable"
        assert ydl.ydl.extract_info.call_count == 0

    def test_refresh_dedup_by_stale_url(self, clients):
        ex = _extractor()
        with mock_ydl(return_value=_info(_fmt(140, url="https://cdn.example.com/old?expire=9999999999"))):
            old = ex.get(SONG)

        def slow(*a, **kw):
            time.sleep(0.2)
            return _info(_fmt(140, url="https://cdn.example.com/new?expire=9999999999"))

        with mock_ydl(side_effect=slow) as ydl:
            results, errors = _run_concurrently(4, lambda: ex.refresh(SONG, old.url))
            late = ex.refresh(SONG, old.url)  # after the flight landed: cached URL differs
        assert not errors
        assert ydl.ydl.extract_info.call_count == 1
        assert all(r.url.startswith("https://cdn.example.com/new") for r in results + [late])

    def test_refresh_logs_layout_change(self, clients, caplog):
        ex = _extractor()
        with mock_ydl(return_value=_info(F140)):
            old = ex.get(SONG)
        with mock_ydl(return_value=_info(F251)), caplog.at_level("WARNING"):
            ex.refresh(SONG, old.url)
        assert "changed layout" in caplog.text

    def test_unavailable_stops_client_rotation(self, clients):
        from yt_dlp.utils import DownloadError

        clients("visionos", "default")
        ex = _extractor()
        with mock_ydl(side_effect=DownloadError("Video unavailable")) as ydl:
            with pytest.raises(ExtractionError) as e:
                ex.get(SONG)
        assert e.value.code == "unavailable"
        assert ydl.call_count == 1  # second client never constructed

    def test_rotation_tries_next_client(self, clients):
        from yt_dlp.utils import DownloadError

        clients("visionos", "default")
        ex = _extractor()
        with mock_ydl(side_effect=[DownloadError("The page needs to be reloaded"), _info(F140)]) as ydl:
            s = ex.get(SONG)
        assert s.player_client == "default"
        opts = [c.args[0] for c in ydl.call_args_list]
        assert opts[0]["extractor_args"]["youtube"]["player_client"] == ["visionos"]
        assert "extractor_args" not in opts[1]
        assert all(o["ignore_no_formats_error"] is True for o in opts)

    def test_no_audio_tries_next_client(self, clients):
        clients("visionos", "default")
        ex = _extractor()
        with mock_ydl(side_effect=[_info(F18), _info(F140)]) as ydl:
            assert ex.get(SONG).itag == "140"
        assert ydl.ydl.extract_info.call_count == 2

    def test_no_audio_anywhere(self, clients):
        clients("visionos", "default")
        ex = _extractor()
        with mock_ydl(side_effect=[_info(F18), {"formats": []}]):
            with pytest.raises(ExtractionError) as e:
                ex.get(SONG)
        assert e.value.code == "no_audio"

    def test_auth_required_wins_after_rotation(self, clients):
        from yt_dlp.utils import DownloadError

        clients("visionos", "default")
        ex = _extractor()
        side = [DownloadError("Sign in to confirm your age"), DownloadError("boom")]
        with mock_ydl(side_effect=side) as ydl:
            with pytest.raises(ExtractionError) as e:
                ex.get(SONG)
        assert e.value.code == "auth_required"
        assert ydl.ydl.extract_info.call_count == 2

    def test_generic_exception_is_extract_failed(self, clients):
        ex = _extractor()
        with mock_ydl(side_effect=RuntimeError("network timeout")):
            with pytest.raises(ExtractionError) as e:
                ex.get(SONG)
        assert e.value.code == "extract_failed"

    def test_node_missing(self, clients):
        auth = MagicMock(is_authenticated=False)
        ex = StreamExtractor(auth, dependencies={"node": False, "ejs": True, "yt_dlp": "x"})
        with mock_ydl(return_value=_info(F140)) as ydl:
            with pytest.raises(ExtractionError) as e:
                ex.get(SONG)
        assert e.value.code == "node_missing"
        ydl.assert_not_called()
        assert ex._failures.get(SONG) is None  # not negative-cached

    def test_cookie_file_only_for_cookie_clients_and_deleted(self, clients, tmp_path):
        clients("visionos", "default")
        cookie = tmp_path / "c.txt"
        cookie.write_text("# Netscape HTTP Cookie File\n")
        auth = MagicMock(is_authenticated=True)
        auth.write_netscape_cookie_file.return_value = str(cookie)
        ex = StreamExtractor(auth, dependencies={"node": True})
        with mock_ydl(side_effect=[_info(F18), _info(F140)]) as ydl:
            ex.get(SONG)
        opts = [c.args[0] for c in ydl.call_args_list]
        assert "cookiefile" not in opts[0]  # visionos: no cookie support, runs anonymously
        assert opts[1]["cookiefile"] == str(cookie)
        assert not cookie.exists()  # P23: deleted in finally


class TestAvailableAt:
    """Some clients (TVHTML5) return URLs that 403 until available_at."""

    def _get(self, available_at):
        ex = _extractor()
        info = _info(_fmt(140, available_at=available_at))
        with mock_ydl(return_value=info), patch("backend.services.extractor.time.sleep") as sleep:
            stream = ex.get(SONG)
        return stream, sleep

    def test_waits_until_available(self, clients):
        stream, sleep = self._get(time.time() + 6)
        assert stream.itag == "140"
        sleep.assert_called_once()
        assert 5 < sleep.call_args.args[0] <= 6

    def test_wait_is_capped(self, clients):
        _, sleep = self._get(time.time() + 3600)
        assert sleep.call_args.args[0] == MAX_AVAILABLE_AT_WAIT_S

    def test_no_wait_when_already_available(self, clients):
        _, sleep = self._get(time.time() - 10)
        sleep.assert_not_called()
