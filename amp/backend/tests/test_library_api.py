"""Likes, playlist detail and saved queues."""

from unittest.mock import MagicMock, patch

import pytest

from backend.services.youtube import YouTubeService, _parse_song

HOST = {"Host": "127.0.0.1:8000"}
SONG = {"id": "BAgTQhR8MLo", "title": "T", "artist": "A", "album": "", "duration_ms": 1000,
        "thumbnail_url": "https://yt3.googleusercontent.com/x=w120-h120", "is_explicit": False}


def test_parse_song_reads_video_details_shape():
    s = _parse_song({
        "videoId": "BAgTQhR8MLo", "title": "T", "author": "Someone", "lengthSeconds": "61",
        "thumbnail": {"thumbnails": [{"url": "small", "width": 60, "height": 60},
                                     {"url": "big", "width": 120, "height": 120}]},
    })
    assert (s.artist, s.duration_ms, s.thumbnail_url) == ("Someone", 61000, "big")


def test_get_playlist_normalizes_and_skips_unavailable():
    svc = YouTubeService.__new__(YouTubeService)
    svc._auth = MagicMock()
    svc._auth.get_client.return_value.get_playlist.return_value = {
        "id": "PL1", "title": "Mix", "author": {"name": "Me"}, "trackCount": 2,
        "thumbnails": [{"url": "p", "width": 1, "height": 1}],
        "tracks": [{"videoId": "BAgTQhR8MLo", "title": "T", "artists": None, "thumbnails": None},
                   {"videoId": None, "title": "gone"}],
    }
    out = svc.get_playlist("PL1")
    assert (out["name"], out["owner"], out["thumbnail_url"], out["song_count"]) == ("Mix", "Me", "p", 2)
    assert [s["id"] for s in out["songs"]] == ["BAgTQhR8MLo"]


def _svc(client):
    svc = YouTubeService.__new__(YouTubeService)
    svc._auth = MagicMock()
    svc._auth.get_client.return_value = client
    return svc


def test_get_album_normalizes_tracks():
    client = MagicMock()
    client.get_album.return_value = {
        "title": "Disc", "type": "EP", "year": "2015", "artists": [{"name": "A"}, {"name": "B"}],
        "thumbnails": [{"url": "small", "width": 60, "height": 60}, {"url": "big", "width": 544, "height": 544}],
        "tracks": [{"videoId": "BAgTQhR8MLo", "title": "T", "album": "Disc", "duration": "4:52", "thumbnails": None},
                   {"videoId": None, "title": "gone"}],
    }
    out = _svc(client).get_album("MPREb_x")
    assert (out["id"], out["title"], out["artist"], out["year"], out["type"], out["thumbnail_url"]) ==         ("MPREb_x", "Disc", "A, B", "2015", "EP", "big")
    assert [(s["id"], s["album"], s["thumbnail_url"], s["duration_ms"]) for s in out["songs"]] ==         [("BAgTQhR8MLo", "Disc", "big", 292000)]


@pytest.mark.parametrize("tracks,expected", [
    ([{"album": {"name": "Disc", "id": "MPREb_x"}}], "MPREb_x"),
    ([{"album": None}], None),
    ([], None),
])
def test_get_song_album_id(tracks, expected):
    client = MagicMock()
    client.get_watch_playlist.return_value = {"tracks": tracks}
    assert _svc(client).get_song_album_id("BAgTQhR8MLo") == expected


@pytest.mark.parametrize("formats,expected", [
    ([{"mimeType": "video/mp4", "loudnessDb": 9}, {"mimeType": "audio/mp4; codecs", "loudnessDb": -3.78}], -3.78),
    ([{"mimeType": "audio/webm"}], None),
    ([], None),
])
def test_get_loudness_db(formats, expected):
    client = MagicMock()
    client.get_song.return_value = {"streamingData": {"adaptiveFormats": formats}}
    assert _svc(client).get_loudness_db("BAgTQhR8MLo") == expected


class TestSongLookups:
    def test_album_route(self, client_no_auth):
        with patch("backend.api.endpoints.get_youtube_service") as yt:
            yt.return_value.get_song_album_id.return_value = "MPREb_x"
            r = client_no_auth.get(f"/api/song/{SONG['id']}/album", headers=HOST)
        assert r.json() == {"album_id": "MPREb_x"}

    def test_album_route_failure_is_502(self, client_no_auth):
        with patch("backend.api.endpoints.get_youtube_service") as yt:
            yt.return_value.get_song_album_id.side_effect = RuntimeError("boom")
            assert client_no_auth.get(f"/api/song/{SONG['id']}/album", headers=HOST).status_code == 502

    def test_loudness_route(self, client_no_auth):
        with patch("backend.api.endpoints.get_youtube_service") as yt:
            yt.return_value.get_loudness_db.return_value = 4.5
            r = client_no_auth.get(f"/api/song/{SONG['id']}/loudness", headers=HOST)
        assert r.json() == {"loudness_db": 4.5}

    def test_loudness_failure_is_null(self, client_no_auth):
        with patch("backend.api.endpoints.get_youtube_service") as yt:
            yt.return_value.get_loudness_db.side_effect = RuntimeError("boom")
            r = client_no_auth.get(f"/api/song/{SONG['id']}/loudness", headers=HOST)
        assert r.status_code == 200 and r.json() == {"loudness_db": None}

    @pytest.mark.parametrize("route", ["album", "loudness"])
    def test_invalid_id(self, client_no_auth, route):
        assert client_no_auth.get(f"/api/song/bad/{route}", headers=HOST).status_code == 400


class TestLikes:
    def test_requires_auth(self, client_no_auth):
        r = client_no_auth.post(f"/api/user/likes/{SONG['id']}", headers=HOST)
        assert r.status_code == 401

    def test_invalid_id(self, client_no_auth):
        assert client_no_auth.delete("/api/user/likes/bad", headers=HOST).status_code == 400

    @pytest.mark.parametrize("method,liked", [("post", True), ("delete", False)])
    def test_rates_song(self, client_no_auth, method, liked):
        with patch("backend.api.endpoints.get_youtube_service") as yt:
            r = getattr(client_no_auth, method)(f"/api/user/likes/{SONG['id']}", headers=HOST)
        assert r.status_code == 200 and r.json()["liked"] is liked
        yt.return_value.rate_song.assert_called_once_with(SONG["id"], liked)

    def test_youtube_failure_is_502(self, client_no_auth):
        with patch("backend.api.endpoints.get_youtube_service") as yt:
            yt.return_value.rate_song.side_effect = RuntimeError("boom")
            r = client_no_auth.post(f"/api/user/likes/{SONG['id']}", headers=HOST)
        assert r.status_code == 502


class TestSavedQueues:
    def test_crud(self, client_no_auth):
        c = client_no_auth
        created = c.post("/api/queues", json={"name": " Road ", "songs": [SONG]}, headers=HOST)
        assert created.status_code == 201
        qid = created.json()["id"]
        assert created.json()["name"] == "Road"

        listed = c.get("/api/queues", headers=HOST).json()
        assert listed[0]["song_count"] == 1 and "songs" not in listed[0]
        assert listed[0]["thumbnail_url"] == SONG["thumbnail_url"]

        r = c.put(f"/api/queues/{qid}", json={"name": "Trip"}, headers=HOST).json()
        assert r["name"] == "Trip" and r["songs"][0]["id"] == SONG["id"]  # songs untouched
        r = c.put(f"/api/queues/{qid}", json={"songs": []}, headers=HOST).json()
        assert r["name"] == "Trip" and r["songs"] == []

        assert c.delete(f"/api/queues/{qid}", headers=HOST).status_code == 200
        assert c.get(f"/api/queues/{qid}", headers=HOST).status_code == 404

    def test_rejects_bad_input(self, client_no_auth):
        c = client_no_auth
        assert c.post("/api/queues", json={"name": "", "songs": []}, headers=HOST).status_code == 422
        bad = {**SONG, "id": "../../etc"}
        assert c.post("/api/queues", json={"name": "x", "songs": [bad]}, headers=HOST).status_code == 400
