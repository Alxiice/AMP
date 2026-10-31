"""AuthService — cookie-based YouTube Music auth.

- SAPISIDHASH = SHA1(ts + " " + __Secure-3PAPISID + " " + "https://music.youtube.com")
- CredentialStore: .amp/cache/ytm_session.json, atomic write (tmp + os.replace), 0600
  v2: {"version": 2, "cookies": [{"name", "value", "domain"}]}, youtube.com cookies only.
  v1 files (flat {name: value}, possibly a whole browser jar) are migrated on load.
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
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("backend.services.auth")

YTMUSIC_ORIGIN = "https://music.youtube.com"

STORE_VERSION = 2
DEFAULT_COOKIE_DOMAIN = ".youtube.com"  # pasted Cookie headers and v1 files carry no domain

# v1 migration keeps only these: a v1 file may hold every site's cookies flattened by name
V1_COOKIE_ALLOWLIST = frozenset({
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS", "__Secure-1PSIDCC", "__Secure-3PSIDCC",
    "SIDCC", "LOGIN_INFO", "PREF", "VISITOR_INFO1_LIVE", "VISITOR_PRIVACY_METADATA", "YSC",
})


@dataclass(frozen=True)
class Cookie:
    name: str
    value: str
    domain: str = DEFAULT_COOKIE_DOMAIN


CookieInput = Union[Mapping[str, str], Iterable[Any]]


class AuthState(str, Enum):
    SIGNED_OUT = "signed_out"
    SIGNED_IN = "signed_in"
    EXPIRED = "expired"


def compute_sapisidhash(sapisid: str, timestamp: Optional[int] = None) -> str:
    """SAPISIDHASH = SHA1(ts + ' ' + __Secure-3PAPISID + ' ' + origin)."""
    ts = timestamp if timestamp is not None else int(time.time())
    raw = f"{ts} {sapisid} {YTMUSIC_ORIGIN}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _is_youtube_domain(domain: str) -> bool:
    bare = domain.lstrip(".")
    return bare == "youtube.com" or bare.endswith(".youtube.com")


def filter_youtube_cookies(cookiejar: Iterable[Any]) -> List[Cookie]:
    """Keep only youtube.com cookies (domain youtube.com or a subdomain), with their domain.

    Accepts anything with .name / .value / .domain (http.cookiejar cookies,
    Tauri cookie models, Cookie). One cookie per (name, domain); the last one wins.
    """
    result: Dict[tuple, Cookie] = {}
    for cookie in cookiejar:
        domain = (getattr(cookie, "domain", None) or "").strip().lower()
        name = getattr(cookie, "name", None)
        if not name or not _is_youtube_domain(domain):
            continue
        result[(name, domain)] = Cookie(name, getattr(cookie, "value", None) or "", domain)
    return list(result.values())


def cookies_by_name(cookies: Iterable[Cookie]) -> Dict[str, str]:
    """{name: value} for a Cookie header: .youtube.com wins over subdomains like music.youtube.com."""
    result: Dict[str, str] = {}
    is_root: Dict[str, bool] = {}
    for c in cookies:
        root = c.domain.lstrip(".") == "youtube.com"
        if c.name in result and (is_root[c.name] or not root):
            continue
        result[c.name] = c.value
        is_root[c.name] = root
    return result


def _to_cookies(cookies: CookieInput) -> List[Cookie]:
    """A {name: value} mapping gets the default domain; cookie objects keep theirs. Filtered."""
    if isinstance(cookies, Mapping):
        cookies = [Cookie(str(n), str(v)) for n, v in cookies.items()]
    return filter_youtube_cookies(cookies)


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
        self._cookies: List[Cookie] = []
        self._by_name: Dict[str, str] = {}  # header view of _cookies (cookies_by_name)
        self._migrated_from_full_jar = False  # v1 file looked like a whole browser jar
        self._state: AuthState = AuthState.SIGNED_OUT
        self._account: Optional[Dict[str, Any]] = None
        self._ytm_client: Any = None  # lazy ytmusicapi.YTMusic

    # --- Cookie management ---

    def set_cookies_from_header(self, cookie_header: str) -> Dict[str, Any]:
        """Parse a pasted Cookie header (no domains: assume .youtube.com) and persist."""
        cookies: Dict[str, str] = {}
        for part in cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                cookies[name.strip()] = value.strip()
        return self.set_cookies(cookies)

    def set_cookies(self, cookies: CookieInput) -> Dict[str, Any]:
        """Replace the session. Every entry point lands here, so only youtube.com cookies are kept."""
        kept = _to_cookies(cookies)
        with self._lock:
            self._set(kept)
            self._save()
            self._migrated_from_full_jar = False
            logger.info("Cookies updated (%d cookies), state=%s", len(self._cookies), self._state.value)
            return {"state": self._state.value, "cookie_count": len(self._cookies)}

    def _set(self, cookies: List[Cookie]) -> None:
        self._cookies = list(cookies)
        self._by_name = cookies_by_name(self._cookies)
        self._ytm_client = None  # invalidate lazy client
        self._state = self._evaluate_state()

    def _save(self) -> None:
        self._store.save({"version": STORE_VERSION, "cookies": [asdict(c) for c in self._cookies]})

    def load_from_store(self) -> bool:
        """Load cookies from disk on startup (migrating v1 files). Returns True if loaded."""
        data = self._store.load()
        if not isinstance(data, dict) or "cookies" not in data:
            return False
        version = data.get("version")
        with self._lock:
            if version is None:
                if not self._migrate_v1(data["cookies"]):
                    return False
            elif version == STORE_VERSION and isinstance(data["cookies"], list):
                entries = [c for c in data["cookies"] if isinstance(c, dict)]
                self._set(filter_youtube_cookies(
                    Cookie(str(c.get("name", "")), str(c.get("value", "")), str(c.get("domain", "")))
                    for c in entries
                ))
            else:
                logger.warning("Credential store has unknown version %r; ignoring it", version)
                return False
        logger.info("Loaded %d cookies from store, state=%s", len(self._cookies), self._state.value)
        return True

    def _migrate_v1(self, raw: Any) -> bool:
        """v1 = flat {name: value}, possibly every site's cookies. Keep the allowlist, rewrite as v2."""
        if not isinstance(raw, dict):
            logger.warning("Credential store v1 has no cookie mapping; ignoring it")
            return False
        kept = [Cookie(str(n), str(v)) for n, v in raw.items() if n in V1_COOKIE_ALLOWLIST]
        self._set(kept)
        self._save()
        total = len(raw)
        logger.info("Migrated credential store v1→v2: kept %d of %d cookies", len(kept), total)  # counts only (P24)
        if total > 3 * len(kept):
            self._migrated_from_full_jar = True
            logger.warning(
                "The old credential store held %d cookies, most of them not YouTube's (a whole browser "
                "jar). Sign in again to rebuild a clean session.", total,
            )
        return True

    def _evaluate_state(self) -> AuthState:
        """Determine auth state from cookie presence."""
        if not self._by_name:
            return AuthState.SIGNED_OUT
        # Check for the key session cookie
        if "__Secure-3PAPISID" in self._by_name or "SAPISID" in self._by_name:
            return AuthState.SIGNED_IN
        return AuthState.SIGNED_OUT

    def logout(self) -> None:
        with self._lock:
            self._cookies, self._by_name = [], {}
            self._migrated_from_full_jar = False
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
        """Return the Cookie header string for CDN requests and ytmusicapi (one value per name)."""
        with self._lock:
            return "; ".join(f"{k}={v}" for k, v in self._by_name.items())

    def get_cookies_dict(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._by_name)

    def get_cookies(self) -> List[Cookie]:
        with self._lock:
            return list(self._cookies)

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
                sapisid = self._by_name.get("__Secure-3PAPISID") or self._by_name.get("SAPISID")
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
                for c in self._cookies:
                    # Each cookie once, on its own domain; include-subdomains iff the domain has a leading dot
                    subdomains = "TRUE" if c.domain.startswith(".") else "FALSE"
                    lines.append(f"{c.domain}\t{subdomains}\t/\tTRUE\t2147483647\t{c.name}\t{c.value}")
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
            "migrated_from_full_jar": self._migrated_from_full_jar,
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
