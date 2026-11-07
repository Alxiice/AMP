"""OBS now-playing widget: metadata on /play, now_playing(), the widget HTTP server."""

import json
import time
import urllib.error
import urllib.request

import pytest

from backend.tests.test_play_api import SONG, svc  # noqa: F401 (fixture)
from backend.widget import start_widget_server

META = {"title": "Kings & Queens", "artist": "Ava Max", "cover_url": "https://lh3.googleusercontent.com/x=w240-h240"}


def test_idle_is_none(svc):  # noqa: F811
    assert svc.now_playing() is None


def test_play_with_meta(svc, client_no_auth):  # noqa: F811
    assert client_no_auth.post(f"/api/stream/{SONG}/play", json=META).status_code == 200
    now = svc.now_playing()
    assert {k: now[k] for k in META} == META
    assert now["song_id"] == SONG and now["duration_ms"] == 50_000 and now["is_playing"] is True


def test_play_without_meta_still_shows_song(svc, client_no_auth):  # noqa: F811
    client_no_auth.post(f"/api/stream/{SONG}/play")
    assert svc.now_playing()["song_id"] == SONG


def test_position_extrapolated_while_playing_frozen_when_paused(svc, client_no_auth):  # noqa: F811
    client_no_auth.post(f"/api/stream/{SONG}/play", json=META)
    svc.update_position(10_000)
    time.sleep(0.2)
    assert 10_150 <= svc.now_playing()["position_ms"] < 11_000
    svc.pause_playback()
    svc.update_position(12_000)
    time.sleep(0.2)
    now = svc.now_playing()
    assert now["position_ms"] == 12_000 and now["is_playing"] is False


def test_position_capped_at_duration(svc, client_no_auth):  # noqa: F811
    client_no_auth.post(f"/api/stream/{SONG}/play")
    svc.update_position(49_990)
    time.sleep(0.05)
    assert svc.now_playing()["position_ms"] == 50_000


def test_stop_clears(svc, client_no_auth):  # noqa: F811
    client_no_auth.post(f"/api/stream/{SONG}/play", json=META)
    svc.stop_playback()
    assert svc.now_playing() is None


def test_meta_too_long_rejected(svc, client_no_auth):  # noqa: F811
    resp = client_no_auth.post(f"/api/stream/{SONG}/play", json={"title": "x" * 501})
    assert resp.status_code == 422


@pytest.fixture()
def widget(svc):  # noqa: F811
    server = start_widget_server("127.0.0.1", 0)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _get(url, host=None):
    req = urllib.request.Request(url, headers={"Host": host} if host else {})
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 (local test server)
        return resp.status, resp.headers.get("Content-Type"), resp.read()


def test_widget_page_and_json(widget, svc, client_no_auth):  # noqa: F811
    status, ctype, body = _get(widget + "/?w=300&h=72")
    assert status == 200 and ctype.startswith("text/html") and b"/now.json" in body
    assert json.loads(_get(widget + "/now.json")[2]) == {"song_id": None}
    client_no_auth.post(f"/api/stream/{SONG}/play", json=META)
    assert json.loads(_get(widget + "/now.json")[2])["title"] == META["title"]


def test_widget_rejects_foreign_host(widget):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(widget + "/now.json", host="evil.com")
    assert e.value.code == 403


def test_widget_unknown_path_404(widget):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(widget + "/etc")
    assert e.value.code == 404


def test_port_in_use_returns_none(widget):
    port = int(widget.rsplit(":", 1)[1])
    assert start_widget_server("127.0.0.1", port) is None
