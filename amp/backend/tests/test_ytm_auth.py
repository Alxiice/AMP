import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
import auth as m  # noqa: E402
from ytmusicapi.exceptions import YTMusicServerError  # noqa: E402

GOOD = [
    {"name": "__Secure-3PAPISID", "value": "abc123", "domain": ".youtube.com"},
    {"name": "SID", "value": "sid", "domain": ".youtube.com"},
    {"name": "SID", "value": "google-sid", "domain": ".google.com"},  # must not override youtube.com
]


class FakeYTM:
    """Stands in for ytmusicapi.YTMusic. `behaviour` controls get_account_info()."""

    behaviour = "ok"

    def __init__(self, auth=None, **_):
        if FakeYTM.behaviour == "offline":  # real YTMusic() does a network call in its constructor
            raise ConnectionError("offline")
        self.auth = auth

    def get_account_info(self):
        if FakeYTM.behaviour == "ok":
            return {"accountName": "Tester"}
        if FakeYTM.behaviour == "rejected":
            raise YTMusicServerError("Server returned HTTP 401: Unauthorized.\nx")
        if FakeYTM.behaviour == "logged_out":
            raise KeyError("accountName")
        raise ConnectionError("offline")


@pytest.fixture(autouse=True)
def _reset():
    FakeYTM.behaviour = "ok"


@pytest.fixture
def svc(tmp_path):
    return m.AuthService(tmp_path / "session.json", client_factory=FakeYTM)


def test_normalize_keeps_case_and_prefers_youtube_domain():
    out = m.normalize_cookies(GOOD)
    assert out["SID"] == "sid" and "__Secure-3PAPISID" in out


def test_build_headers_has_what_ytmusicapi_needs():
    h = m.build_headers({"__Secure-3PAPISID": "x", "SID": "y"})
    assert {"cookie", "authorization", "x-goog-authuser", "x-origin"} <= set(h)
    assert h["authorization"].startswith("SAPISIDHASH ")
    assert "__Secure-3PAPISID=x" in h["cookie"]


def test_incomplete_login_is_rejected():
    with pytest.raises(m.AuthError, match="Login incomplete"):
        m.build_headers({"SID": "y"})


def test_connect_persists_and_flips_state(svc, tmp_path):
    st = svc.connect_with_cookies(GOOD)
    assert st["state"] == m.SIGNED_IN and st["account"]["accountName"] == "Tester"
    assert svc.is_authenticated and isinstance(svc.client, FakeYTM) and svc.client.auth
    f = tmp_path / "session.json"
    assert f.exists()
    if os.name == "posix":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_rejected_cookies_are_not_saved(svc, tmp_path):
    FakeYTM.behaviour = "rejected"
    with pytest.raises(m.AuthError, match="rejected"):
        svc.connect_with_cookies(GOOD)
    assert not svc.is_authenticated and not (tmp_path / "session.json").exists()


def test_logged_out_session_is_rejected(svc):
    FakeYTM.behaviour = "logged_out"
    with pytest.raises(m.AuthError):
        svc.connect_with_cookies(GOOD)


def test_network_error_is_not_reported_as_bad_login(svc):
    FakeYTM.behaviour = "offline"
    with pytest.raises(m.AuthError, match="Could not reach"):
        svc.connect_with_cookies(GOOD)


def test_session_survives_restart_without_network(svc, tmp_path):
    svc.connect_with_cookies(GOOD)
    FakeYTM.behaviour = "offline"
    again = m.AuthService(tmp_path / "session.json", client_factory=FakeYTM)
    assert again.is_authenticated            # restored with no network call
    assert again.verify()["state"] == m.SIGNED_IN  # offline != expired
    with pytest.raises(ConnectionError):     # callers see the real network error...
        again.client
    assert again.is_authenticated            # ...and the session is kept
    FakeYTM.behaviour = "ok"
    assert again.verify()["account"]["accountName"] == "Tester"  # recovers when back online


def test_verify_marks_expired_when_google_rejects(svc, tmp_path):
    svc.connect_with_cookies(GOOD)
    FakeYTM.behaviour = "rejected"
    assert svc.verify()["state"] == m.EXPIRED and not svc.is_authenticated
    assert not isinstance(svc.client.auth, dict)  # anonymous client once expired


def test_guard_flips_to_expired_on_401(svc):
    svc.connect_with_cookies(GOOD)
    with pytest.raises(YTMusicServerError):
        with svc.guard():
            raise YTMusicServerError("Server returned HTTP 403: Forbidden.\nx")
    assert svc.status()["state"] == m.EXPIRED


def test_logout_clears_everything(svc, tmp_path):
    svc.connect_with_cookies(GOOD)
    svc.logout()
    assert svc.status()["state"] == m.SIGNED_OUT and not (tmp_path / "session.json").exists()
