"""AuthService — cookie-based YouTube Music auth.

- SAPISIDHASH = SHA1(ts + " " + __Secure-3PAPISID + " " + "https://music.youtube.com")
- CredentialStore: .amp/cache/ytm_session.json, atomic write (tmp + os.replace), 0600
- Lazy YTMusic client construction
- States: signed_out -> signed_in -> expired
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("backend.services.auth")

YTMUSIC_ORIGIN = "https://music.youtube.com"


class AuthState(str, Enum):
    SIGNED_OUT = "signed_out"
    SIGNED_IN = "signed_in"
    EXPIRED = "expired"


def compute_sapisidhash(sapisid: str, timestamp: Optional[int] = None) -> str:
    """SAPISIDHASH = SHA1(ts + ' ' + __Secure-3PAPISID + ' ' + origin)."""
    ts = timestamp if timestamp is not None else int(time.time())
    raw = f"{ts} {sapisid} {YTMUSIC_ORIGIN}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def filter_youtube_cookies(cookiejar: Iterable[Any]) -> Dict[str, str]:
    """Keep only youtube.com cookies from a cookie jar, as {name: value}.

    A cookie is kept if its domain (leading dot stripped) is youtube.com or a
    subdomain of it. When a name appears on several domains, the
    .youtube.com one wins over subdomains such as music.youtube.com.
    """
    result: Dict[str, str] = {}
    is_root: Dict[str, bool] = {}
    for cookie in cookiejar:
        domain = (cookie.domain or "").lstrip(".").lower()
        if domain != "youtube.com" and not domain.endswith(".youtube.com"):
            continue
        root = domain == "youtube.com"
        if cookie.name in result and (is_root[cookie.name] or not root):
            continue
        result[cookie.name] = cookie.value
        is_root[cookie.name] = root
    return result


class CredentialStore:
    """Persists cookies to .amp/cache/ytm_session.json atomically with 0600 perms."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or settings.credential_store_path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._path.exists():
                return None
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load credentials: %s", e)
                return None

    def save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: tmp + os.replace
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.chmod(tmp, 0o600)
                os.replace(tmp, str(self._path))
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def clear(self) -> None:
        with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass


class AuthService:
    """Thread-safe singleton managing YouTube Music cookie auth."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store = CredentialStore()
        self._cookies: Dict[str, str] = {}
        self._state: AuthState = AuthState.SIGNED_OUT
        self._account: Optional[Dict[str, Any]] = None
        self._ytm_client: Any = None  # lazy ytmusicapi.YTMusic

    # --- Cookie management ---

    def set_cookies_from_header(self, cookie_header: str) -> Dict[str, Any]:
        """Parse a Cookie header string into the cookie dict and persist."""
        cookies: Dict[str, str] = {}
        for part in cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                cookies[name.strip()] = value.strip()
        return self.set_cookies(cookies)

    def set_cookies(self, cookies: Dict[str, str]) -> Dict[str, Any]:
        with self._lock:
            self._cookies = dict(cookies)
            self._store.save({"cookies": self._cookies})
            self._ytm_client = None  # invalidate lazy client
            self._state = self._evaluate_state()
            logger.info("Cookies updated (%d cookies), state=%s", len(self._cookies), self._state.value)
            return {"state": self._state.value, "cookie_count": len(self._cookies)}

    def load_from_store(self) -> bool:
        """Load cookies from disk on startup. Returns True if loaded."""
        data = self._store.load()
        if not data or "cookies" not in data:
            return False
        with self._lock:
            self._cookies = dict(data["cookies"])
            self._ytm_client = None
            self._state = self._evaluate_state()
        logger.info("Loaded %d cookies from store, state=%s", len(self._cookies), self._state.value)
        return True

    def _evaluate_state(self) -> AuthState:
        """Determine auth state from cookie presence."""
        if not self._cookies:
            return AuthState.SIGNED_OUT
        # Check for the key session cookie
        if "__Secure-3PAPISID" in self._cookies or "SAPISID" in self._cookies:
            return AuthState.SIGNED_IN
        return AuthState.SIGNED_OUT

    def logout(self) -> None:
        with self._lock:
            self._cookies = {}
            self._store.clear()
            self._ytm_client = None
            self._account = None
            self._state = AuthState.SIGNED_OUT
        logger.info("Logged out")

    # --- Accessors ---

    @property
    def state(self) -> AuthState:
        return self._state

    @property
    def is_authenticated(self) -> bool:
        return self._state == AuthState.SIGNED_IN

    def get_cookie_header(self) -> str:
        """Return the Cookie header string for CDN requests and ytmusicapi."""
        with self._lock:
            return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def get_cookies_dict(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._cookies)

    def get_auth_headers(self) -> Dict[str, str]:
        """Headers for ytmusicapi requests (includes SAPISIDHASH Authorization when authenticated)."""
        with self._lock:
            headers: Dict[str, str] = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Origin": YTMUSIC_ORIGIN,
                "Referer": YTMUSIC_ORIGIN + "/",
            }
            if self._cookies:
                headers["Cookie"] = self.get_cookie_header()
                sapisid = self._cookies.get("__Secure-3PAPISID") or self._cookies.get("SAPISID")
                if sapisid:
                    ts = int(time.time())
                    headers["Authorization"] = f"SAPISIDHASH {ts}_{compute_sapisidhash(sapisid, ts)}"
            return headers

    def get_cdn_headers(self) -> Dict[str, str]:
        """Headers for googlevideo.com CDN requests.

        P1: Cookie is included when authenticated. When signed out, no Cookie
        header is sent — most stream URLs work without it (yt-dlp extracts
        signed URLs); some videos may return 403, in which case the user
        should sign in.
        """
        headers: Dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        with self._lock:
            if self._cookies:
                headers["Cookie"] = self.get_cookie_header()
        return headers

    def mark_expired(self) -> None:
        with self._lock:
            if self._state == AuthState.SIGNED_IN:
                self._state = AuthState.EXPIRED
                logger.warning("Auth marked as expired")

    def reset_expired(self) -> None:
        with self._lock:
            if self._state == AuthState.EXPIRED:
                self._state = self._evaluate_state()

    @property
    def account(self) -> Optional[Dict[str, Any]]:
        return self._account

    def set_account(self, account: Dict[str, Any]) -> None:
        with self._lock:
            self._account = account

    # --- Lazy YTMusic client ---

    def get_client(self) -> Any:
        """Lazily construct and return a ytmusicapi.YTMusic client.

        ytmusicapi's `auth` parameter accepts a dict of headers (not a raw
        Cookie string). We pass the full auth headers dict including Cookie,
        Authorization (SAPISIDHASH), Origin, and User-Agent so that
        ytmusicapi can determine AuthType.BROWSER and set up SAPISIDHASH
        automatically.
        """
        with self._lock:
            if self._ytm_client is not None:
                return self._ytm_client
            try:
                from ytmusicapi import YTMusic

                if self._cookies:
                    # Pass headers dict — ytmusicapi needs Cookie + Authorization
                    # (SAPISIDHASH) + Origin to detect AuthType.BROWSER
                    self._ytm_client = YTMusic(auth=self.get_auth_headers())
                else:
                    self._ytm_client = YTMusic()
                logger.info("YTMusic client constructed (auth=%s)", self.is_authenticated)
                return self._ytm_client
            except Exception as e:
                logger.error("Failed to construct YTMusic client: %s", e)
                from ytmusicapi import YTMusic
                self._ytm_client = YTMusic()
                return self._ytm_client

    # --- Netscape cookie file for yt-dlp (P23: 0600, deleted in finally) ---

    def write_netscape_cookie_file(self) -> Optional[str]:
        """Write cookies to a temporary Netscape-format file for yt-dlp.

        Caller MUST delete the file in a finally block.
        """
        with self._lock:
            if not self._cookies:
                return None
            fd, path = tempfile.mkstemp(suffix=".cookies.txt", prefix="amp_yt_")
            try:
                lines = ["# Netscape HTTP Cookie File"]
                for name, value in self._cookies.items():
                    lines.append(
                        f".youtube.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}"
                    )
                    lines.append(
                        f".music.youtube.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}"
                    )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                os.chmod(path, 0o600)
                return path
            except Exception:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise

    def status(self, verify: bool = False) -> Dict[str, Any]:
        """Return auth status dict."""
        result: Dict[str, Any] = {
            "state": self._state.value,
            "is_authenticated": self.is_authenticated,
            "account": self._account,
        }
        if verify and self.is_authenticated:
            try:
                client = self.get_client()
                account_info = client.get_account() if hasattr(client, "get_account") else None
                if account_info:
                    self.set_account(account_info)
                    result["account"] = account_info
                    result["state"] = AuthState.SIGNED_IN.value
            except Exception as e:
                logger.warning("Auth verification failed: %s", e)
                self.mark_expired()
                result["state"] = self._state.value
                result["is_authenticated"] = False
        return result


# --- Singleton accessor (thread-safe) ---

_instance: Optional[AuthService] = None
_lock = threading.Lock()


def get_auth_service() -> AuthService:
    global _instance
    with _lock:
        if _instance is None:
            _instance = AuthService()
            _instance.load_from_store()
        return _instance


def reset_auth_service() -> None:
    """Reset singleton (for tests)."""
    global _instance
    with _lock:
        _instance = None
