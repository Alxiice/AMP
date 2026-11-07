"""Listening history: POST one play, list newest first with percentages, period filter, delete."""

import datetime as dt

import pytest

SONG = {"id": "BAgTQhR8MLo", "title": "Kings & Queens", "artist": "Ava Max", "album": "Heaven & Hell",
        "duration_ms": 200_000, "thumbnail_url": "https://lh3.googleusercontent.com/x", "is_explicit": False}


def _add(client, **kw):
    body = {"song": SONG, "listened_ms": 150_000, "duration_ms": 200_000, "end_reason": "skipped", **kw}
    resp = client.post("/api/history", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_add_and_list(client_no_auth):
    entry = _add(client_no_auth)
    assert entry["percent"] == 75 and entry["end_reason"] == "skipped"
    assert entry["song"]["title"] == "Kings & Queens"
    data = client_no_auth.get("/api/history").json()
    assert data["total"] == 1 and data["listened_ms"] == 150_000
    assert data["entries"][0]["id"] == entry["id"]


def test_newest_first_and_percent_capped(client_no_auth):
    now = dt.datetime.now(dt.timezone.utc)
    _add(client_no_auth, started_at=(now - dt.timedelta(hours=2)).isoformat())
    _add(client_no_auth, listened_ms=250_000, end_reason="finished", started_at=now.isoformat())
    entries = client_no_auth.get("/api/history").json()["entries"]
    assert [e["percent"] for e in entries] == [100, 75]


def test_days_filter(client_no_auth):
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)
    _add(client_no_auth, started_at=old.isoformat())
    _add(client_no_auth)
    assert client_no_auth.get("/api/history?days=7").json()["total"] == 1
    assert client_no_auth.get("/api/history").json()["total"] == 2


def test_unknown_duration_has_no_percent(client_no_auth):
    entry = _add(client_no_auth, duration_ms=0, song={**SONG, "duration_ms": 0})
    assert entry["percent"] is None


def test_started_at_defaults_to_now_minus_listened(client_no_auth):
    entry = _add(client_no_auth, listened_ms=60_000)
    started = dt.datetime.fromisoformat(entry["started_at"].rstrip("Z"))
    delta = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - started
    assert dt.timedelta(seconds=55) < delta < dt.timedelta(seconds=70)


def test_future_started_at_clamped_to_now(client_no_auth):
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    entry = _add(client_no_auth, started_at=future.isoformat())
    started = dt.datetime.fromisoformat(entry["started_at"].rstrip("Z"))
    assert started <= dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize("bad", [
    {"song": {**SONG, "id": "bad"}},
    {"listened_ms": -1},
    {"end_reason": "exploded"},
])
def test_invalid_bodies_rejected(client_no_auth, bad):
    body = {"song": SONG, "listened_ms": 1000, **bad}
    assert client_no_auth.post("/api/history", json=body).status_code in (400, 422)


def test_delete_one_and_clear(client_no_auth):
    a = _add(client_no_auth)
    _add(client_no_auth)
    assert client_no_auth.delete(f"/api/history/{a['id']}").status_code == 200
    assert client_no_auth.delete(f"/api/history/{a['id']}").status_code == 404
    assert client_no_auth.delete("/api/history").json()["deleted"] == 1
    assert client_no_auth.get("/api/history").json()["total"] == 0
