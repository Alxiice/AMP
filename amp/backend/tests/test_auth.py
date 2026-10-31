"""Unit tests for services/auth.py — SAPISIDHASH, CredentialStore, AuthService.

Fully mocked, no network.
"""

import hashlib
import json
import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.auth import (
    V1_COOKIE_ALLOWLIST,
    AuthService,
    AuthState,
    Cookie,
    CredentialStore,
    compute_sapisidhash,
    cookies_by_name,
    filter_youtube_cookies,
)


# ---------------------------------------------------------------------------
# SAPISIDHASH
# ---------------------------------------------------------------------------


class TestSapisidhash:
    def test_deterministic(self):
        """Same inputs → same hash."""
        h1 = compute_sapisidhash("test_sapisid", 1234567890)
        h2 = compute_sapisidhash("test_sapisid", 1234567890)
        assert h1 == h2

    def test_correct_format(self):
        """SHA1 hex digest (40 chars)."""
        h = compute_sapisidhash("test_sapisid", 1234567890)
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_matches_spec(self):
        """SAPISIDHASH = SHA1(ts + ' ' + sapisid + ' ' + origin)."""
        ts = 1234567890
        sapisid = "test_sapisid_value"
        expected_raw = f"{ts} {sapisid} https://music.youtube.com"
        expected = hashlib.sha1(expected_raw.encode()).hexdigest()
        assert compute_sapisidhash(sapisid, ts) == expected

    def test_different_timestamps(self):
        h1 = compute_sapisidhash("sap", 1000)
        h2 = compute_sapisidhash("sap", 2000)
        assert h1 != h2

    def test_different_sapisids(self):
        h1 = compute_sapisidhash("sap1", 1000)
        h2 = compute_sapisidhash("sap2", 1000)
        assert h1 != h2


# ---------------------------------------------------------------------------
# CredentialStore
# ---------------------------------------------------------------------------


class TestCredentialStore:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "creds.json"
        store = CredentialStore(path)
        data = {"cookies": {"SAPISID": "abc", "HSID": "def"}}
        store.save(data)
        loaded = store.load()
        assert loaded == data

    def test_file_permissions(self, tmp_path):
        path = tmp_path / "creds.json"
        store = CredentialStore(path)
        store.save({"cookies": {"a": "b"}})
        import platform
        if platform.system() == "Windows":
            # Windows doesn't support Unix-style chmod — just verify the file exists
            assert path.exists()
        else:
            mode = stat.S_IMODE(os.stat(path).st_mode)
            assert mode == 0o600

    def test_atomic_write(self, tmp_path):
        """Save should use tmp + os.replace (no partial files)."""
        path = tmp_path / "creds.json"
        store = CredentialStore(path)
        store.save({"cookies": {"a": "b"}})
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_load_nonexistent(self, tmp_path):
        store = CredentialStore(tmp_path / "nonexistent.json")
        assert store.load() is None
        assert store.exists() is False

    def test_clear(self, tmp_path):
        path = tmp_path / "creds.json"
        store = CredentialStore(path)
        store.save({"cookies": {"a": "b"}})
        assert store.exists()
        store.clear()
        assert not store.exists()

    def test_load_corrupted(self, tmp_path):
        path = tmp_path / "creds.json"
        path.write_text("not json {{{")
        store = CredentialStore(path)
        assert store.load() is None


# ---------------------------------------------------------------------------
# AuthService
# ---------------------------------------------------------------------------


class TestAuthService:
    def test_initial_state(self, temp_dirs):
        auth = AuthService()
        assert auth.state == AuthState.SIGNED_OUT
        assert auth.is_authenticated is False

    def test_set_cookies_from_header(self, temp_dirs):
        auth = AuthService()
        result = auth.set_cookies_from_header(
            "__Secure-3PAPISID=abc123; HSID=def; SSID=ghi"
        )
        assert result["state"] == "signed_in"
        assert result["cookie_count"] == 3
        assert auth.is_authenticated is True

    def test_set_cookies_dict(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"SAPISID": "xyz", "OTHER": "val"})
        assert auth.is_authenticated is True

    def test_logout(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"__Secure-3PAPISID": "abc"})
        assert auth.is_authenticated is True
        auth.logout()
        assert auth.state == AuthState.SIGNED_OUT
        assert auth.is_authenticated is False

    def test_cookie_header(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"A": "1", "B": "2"})
        header = auth.get_cookie_header()
        assert "A=1" in header
        assert "B=2" in header
        assert ";" in header

    def test_auth_headers_include_sapisidhash(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"__Secure-3PAPISID": "test_sapisid"})
        headers = auth.get_auth_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("SAPISIDHASH ")
        assert "Cookie" in headers

    def test_cdn_headers_include_cookie(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"__Secure-3PAPISID": "test"})
        headers = auth.get_cdn_headers()
        assert "Cookie" in headers
        assert "__Secure-3PAPISID=test" in headers["Cookie"]

    def test_cdn_headers_no_cookie_when_signed_out(self, temp_dirs):
        """When signed out, CDN headers should NOT include a Cookie header."""
        auth = AuthService()
        headers = auth.get_cdn_headers()
        assert "Cookie" not in headers
        assert "User-Agent" in headers

    def test_auth_headers_no_cookie_when_signed_out(self, temp_dirs):
        """When signed out, auth headers should NOT include Cookie or Authorization."""
        auth = AuthService()
        headers = auth.get_auth_headers()
        assert "Cookie" not in headers
        assert "Authorization" not in headers
        assert "User-Agent" in headers

    def test_mark_expired(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"__Secure-3PAPISID": "test"})
        assert auth.state == AuthState.SIGNED_IN
        auth.mark_expired()
        assert auth.state == AuthState.EXPIRED
        assert auth.is_authenticated is False

    def test_no_sapisid_means_signed_out(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"random_cookie": "value"})
        assert auth.state == AuthState.SIGNED_OUT

    def test_persistence(self, temp_dirs):
        """Cookies saved to disk should be loadable by a new instance."""
        auth1 = AuthService()
        auth1.set_cookies({"__Secure-3PAPISID": "persisted"})

        # New instance loads from store
        auth2 = AuthService()
        auth2.load_from_store()
        assert auth2.is_authenticated is True
        assert "__Secure-3PAPISID" in auth2.get_cookies_dict()


# ---------------------------------------------------------------------------
# Netscape cookie file (P23)
# ---------------------------------------------------------------------------


class TestNetscapeCookieFile:
    def test_write_and_cleanup(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies({"__Secure-3PAPISID": "test", "HSID": "abc"})

        path = auth.write_netscape_cookie_file()
        assert path is not None
        assert os.path.exists(path)

        # Check permissions (relaxed on Windows)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        import platform
        if platform.system() != "Windows":
            assert mode == 0o600

        # Check content
        content = Path(path).read_text()
        assert "Netscape HTTP Cookie File" in content
        assert "__Secure-3PAPISID" in content
        assert ".youtube.com" in content

        # Cleanup (P23: caller must delete in finally)
        os.unlink(path)

    def test_no_cookies_returns_none(self, temp_dirs):
        auth = AuthService()
        assert auth.write_netscape_cookie_file() is None


# ---------------------------------------------------------------------------
# filter_youtube_cookies (F12)
# ---------------------------------------------------------------------------


def _cookie(name, value, domain):
    return SimpleNamespace(name=name, value=value, domain=domain)


class TestFilterYoutubeCookies:
    def test_filter_youtube_cookies(self):
        jar = [
            _cookie("SID", "google-value", ".google.com"),
            _cookie("SID", "youtube-value", ".youtube.com"),
            _cookie("session", "secret", "bank.example"),
        ]
        assert filter_youtube_cookies(jar) == [Cookie("SID", "youtube-value", ".youtube.com")]

    def test_same_name_on_two_domains_kept_separately(self):
        jar = [_cookie("PREF", "music", ".music.youtube.com"), _cookie("PREF", "root", ".youtube.com")]
        assert sorted(filter_youtube_cookies(jar), key=lambda c: c.domain) == [
            Cookie("PREF", "music", ".music.youtube.com"),
            Cookie("PREF", "root", ".youtube.com"),
        ]

    def test_root_domain_preferred_over_subdomain_in_header(self):
        for jar in (
            [_cookie("PREF", "music", ".music.youtube.com"), _cookie("PREF", "root", ".youtube.com")],
            [_cookie("PREF", "root", ".youtube.com"), _cookie("PREF", "music", ".music.youtube.com")],
        ):
            assert cookies_by_name(filter_youtube_cookies(jar)) == {"PREF": "root"}

    def test_subdomain_kept_when_unique(self):
        jar = [_cookie("LOGIN_INFO", "x", "music.youtube.com")]
        assert cookies_by_name(filter_youtube_cookies(jar)) == {"LOGIN_INFO": "x"}

    def test_lookalike_domain_rejected(self):
        jar = [
            _cookie("SID", "evil", ".notyoutube.com"),
            _cookie("SID", "evil2", "youtube.com.attacker.example"),
        ]
        assert filter_youtube_cookies(jar) == []

    def test_tauri_cookies_filters_domains(self):
        """Webview cookies: .google.com and third-party cookies are dropped, domains kept."""
        from backend.api.auth_routes import TauriCookie

        jar = [
            TauriCookie(name="SAPISID", value="yt", domain=".youtube.com"),
            TauriCookie(name="LOGIN_INFO", value="m", domain="music.youtube.com"),
            TauriCookie(name="SID", value="g", domain=".google.com"),
            TauriCookie(name="NID", value="g2", domain="accounts.google.com"),
            TauriCookie(name="ads", value="x", domain=".doubleclick.net"),
            TauriCookie(name="nodomain", value="x", domain=None),
        ]
        assert filter_youtube_cookies(jar) == [
            Cookie("SAPISID", "yt", ".youtube.com"),
            Cookie("LOGIN_INFO", "m", "music.youtube.com"),
        ]


# ---------------------------------------------------------------------------
# Credential store v2 + v1 migration (Phase 5)
# ---------------------------------------------------------------------------


def _store_file() -> Path:
    from backend.config import settings
    return settings.credential_store_path


class TestStoreV2:
    def test_store_v2_roundtrip(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies([
            Cookie("SAPISID", "a", ".youtube.com"),
            Cookie("PREF", "m", "music.youtube.com"),
        ])

        data = json.loads(_store_file().read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert data["cookies"] == [
            {"name": "SAPISID", "value": "a", "domain": ".youtube.com"},
            {"name": "PREF", "value": "m", "domain": "music.youtube.com"},
        ]
        import platform
        if platform.system() != "Windows":
            assert stat.S_IMODE(os.stat(_store_file()).st_mode) == 0o600

        reloaded = AuthService()
        assert reloaded.load_from_store()
        assert reloaded.get_cookies() == auth.get_cookies()
        assert reloaded.state == AuthState.SIGNED_IN

    def test_pasted_header_gets_default_domain(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies_from_header("SAPISID=a; HSID=b")
        assert {c.domain for c in auth.get_cookies()} == {".youtube.com"}

    def test_v2_load_drops_foreign_domains(self, temp_dirs):
        """A hand-edited v2 file still only yields youtube.com cookies."""
        _store_file().write_text(json.dumps({"version": 2, "cookies": [
            {"name": "SAPISID", "value": "a", "domain": ".youtube.com"},
            {"name": "SID", "value": "g", "domain": ".google.com"},
        ]}), encoding="utf-8")
        auth = AuthService()
        assert auth.load_from_store()
        assert auth.get_cookies() == [Cookie("SAPISID", "a", ".youtube.com")]

    def test_unknown_version_ignored(self, temp_dirs):
        _store_file().write_text(json.dumps({"version": 99, "cookies": []}), encoding="utf-8")
        auth = AuthService()
        assert not auth.load_from_store()
        assert auth.state == AuthState.SIGNED_OUT

    def test_netscape_file_uses_real_domains(self, temp_dirs):
        auth = AuthService()
        auth.set_cookies([
            Cookie("SAPISID", "a", ".youtube.com"),
            Cookie("PREF", "root", ".youtube.com"),
            Cookie("PREF", "music", "music.youtube.com"),
        ])
        path = auth.write_netscape_cookie_file()
        try:
            rows = [line.split("\t") for line in Path(path).read_text().splitlines() if not line.startswith("#")]
        finally:
            os.unlink(path)

        # each cookie once, on its own domain (was: every cookie on .youtube.com AND .music.youtube.com)
        assert sorted((r[0], r[1], r[5], r[6]) for r in rows) == [
            (".youtube.com", "TRUE", "PREF", "root"),
            (".youtube.com", "TRUE", "SAPISID", "a"),
            ("music.youtube.com", "FALSE", "PREF", "music"),
        ]


class TestMigrateV1:
    def test_migrate_v1_keeps_allowlist_only(self, temp_dirs, caplog):
        v1 = {f"site{i}_cookie": f"value-{i}" for i in range(297)}
        v1.update({"SAPISID": "sapisid-secret", "SID": "sid-secret", "bank_session": "bank-secret"})
        assert len(v1) == 300
        _store_file().write_text(json.dumps({"cookies": v1}), encoding="utf-8")

        auth = AuthService()
        with caplog.at_level("INFO", logger="backend.services.auth"):
            assert auth.load_from_store()

        data = json.loads(_store_file().read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert {c["name"] for c in data["cookies"]} == {"SAPISID", "SID"}
        assert all(c["domain"] == ".youtube.com" for c in data["cookies"])
        assert auth.state == AuthState.SIGNED_IN

        assert "kept 2 of 300 cookies" in caplog.text
        assert any(r.levelname == "WARNING" for r in caplog.records)
        for secret in ("sapisid-secret", "sid-secret", "bank-secret", "value-1"):
            assert secret not in caplog.text  # P24: counts only

        assert auth.status()["migrated_from_full_jar"] is True

    def test_migrate_v1_small_file_no_warning(self, temp_dirs, caplog):
        _store_file().write_text(json.dumps({"cookies": {"SAPISID": "a", "HSID": "b", "PREF": "c"}}),
                                 encoding="utf-8")
        auth = AuthService()
        with caplog.at_level("INFO", logger="backend.services.auth"):
            assert auth.load_from_store()
        assert "kept 3 of 3 cookies" in caplog.text
        assert not any(r.levelname == "WARNING" for r in caplog.records)
        assert auth.status()["migrated_from_full_jar"] is False

    def test_migrated_flag_cleared_by_new_sign_in(self, temp_dirs):
        v1 = {f"x{i}": "v" for i in range(20)}
        v1["SAPISID"] = "a"
        _store_file().write_text(json.dumps({"cookies": v1}), encoding="utf-8")
        auth = AuthService()
        auth.load_from_store()
        assert auth.status()["migrated_from_full_jar"] is True

        auth.set_cookies_from_header("SAPISID=b")
        assert auth.status()["migrated_from_full_jar"] is False

    def test_allowlist(self):
        assert {"SAPISID", "__Secure-3PAPISID", "LOGIN_INFO"} <= V1_COOKIE_ALLOWLIST
        assert "bank_session" not in V1_COOKIE_ALLOWLIST
