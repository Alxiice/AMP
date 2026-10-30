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
    AuthService,
    AuthState,
    CredentialStore,
    compute_sapisidhash,
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
        assert ".music.youtube.com" in content

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
        assert filter_youtube_cookies(jar) == {"SID": "youtube-value"}

    def test_root_domain_preferred_over_subdomain(self):
        for jar in (
            [_cookie("PREF", "music", ".music.youtube.com"), _cookie("PREF", "root", ".youtube.com")],
            [_cookie("PREF", "root", ".youtube.com"), _cookie("PREF", "music", ".music.youtube.com")],
        ):
            assert filter_youtube_cookies(jar) == {"PREF": "root"}

    def test_subdomain_kept_when_unique(self):
        jar = [_cookie("LOGIN_INFO", "x", "music.youtube.com")]
        assert filter_youtube_cookies(jar) == {"LOGIN_INFO": "x"}

    def test_lookalike_domain_rejected(self):
        jar = [
            _cookie("SID", "evil", ".notyoutube.com"),
            _cookie("SID", "evil2", "youtube.com.attacker.example"),
        ]
        assert filter_youtube_cookies(jar) == {}
