"""
YouTube Music authentication (replaces services/auth.py)
========================================================

Why cookies? YouTube Music has no public API. ytmusicapi talks to the same
private endpoints the web player uses, and the only thing those accept is a
logged-in browser session (cookies). Google's OAuth tokens, including the
"TV / device code" flow ytmusicapi used to offer, stopped being accepted by
YouTube Music in 2025, so there is no OAuth path to build on.

How the user connects (no copy/paste):
  1. Tauri opens a sign-in window (see youtube_login.rs) and the user logs in
     normally. Tauri reads the session cookies from that window.
  2. The frontend POSTs the cookies to /api/auth/cookies  -> connect_with_cookies()
  3. Optional shortcut: import_from_browser("firefox") reuses an existing login.

This module is the ONLY owner of auth state. YouTubeService must call
`get_auth_service().client` instead of keeping its own YTMusic instance.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Mapping, Optional, Union

logger = logging.getLogger(__name__)

ORIGIN = "https://music.youtube.com"
REQUIRED_COOKIE = "__Secure-3PAPISID"  # ytmusicapi derives its Authorization hash from this
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

SIGNED_OUT, SIGNED_IN, EXPIRED = "signed_out", "signed_in", "expired"


class AuthError(Exception):
    """Raised when credentials are missing, incomplete or rejected by YouTube."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
CookieInput = Union[Mapping[str, str], Iterable[Mapping[str, Any]]]


def normalize_cookies(cookies: CookieInput) -> Dict[str, str]:
    """Accept {"name": "value"} or [{"name":..., "value":..., "domain":...}] and return a dict.

    Cookie names are case-sensitive (SAPISID != sapisid), so names are kept as-is.
    When the same name exists for several domains, a youtube.com one wins.
    """
    if isinstance(cookies, Mapping):
        return {str(k): str(v) for k, v in cookies.items()}

    out: Dict[str, str] = {}
    from_youtube: set = set()
    for c in cookies:
        name, value = c.get("name"), c.get("value")
        if not name or value is None:
            continue
        is_yt = "youtube.com" in (c.get("domain") or "youtube.com")
        if name in out and name in from_youtube and not is_yt:
            continue
        out[name] = value
        if is_yt:
            from_youtube.add(name)
    return out


def build_headers(cookies: Mapping[str, str], authuser: str = "0") -> Dict[str, str]:
    """Build the headers dict ytmusicapi's browser auth expects.

    ytmusicapi (>=1.x) requires `cookie` + `authorization` to be present and
    recomputes `authorization` for every request, so the value here only has
    to exist.
    """
    sapisid = cookies.get(REQUIRED_COOKIE)
    if not sapisid:
        raise AuthError(
            f"Login incomplete: cookie {REQUIRED_COOKIE} not found. "
            "Make sure you finished signing in to YouTube Music."
        )
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sapisid} {ORIGIN}".encode()).hexdigest()
    return {
        "accept": "*/*",
        "authorization": f"SAPISIDHASH {ts}_{digest}",
        "content-type": "application/json",
        "cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "origin": ORIGIN,
        "x-origin": ORIGIN,
        "x-goog-authuser": authuser,
        "user-agent": USER_AGENT,
    }


def cookies_from_browser(browser: str, profile: Optional[str] = None) -> Dict[str, str]:
    """Read YouTube cookies from an installed browser using yt-dlp (already a dependency).

    Works best with Firefox. Chrome/Edge on Windows (v127+) use app-bound
    encryption that yt-dlp often cannot read, so treat this as a shortcut,
    not the main path.
    """
    try:
        from yt_dlp.cookies import extract_cookies_from_browser

        jar = extract_cookies_from_browser(browser, profile)
        logger.info("yt-dlp returned %d cookies from %s", len(jar), browser)
    except Exception as e:  # yt-dlp raises many different errors
        logger.error("yt-dlp cookie extraction failed for %s: %s", browser, e)
        raise AuthError(f"Could not read cookies from {browser}: {e}") from e

    cookies = {c.name: c.value for c in jar if c.domain.lstrip(".").endswith("youtube.com") and c.value}
    logger.info("Found %d YouTube cookies in %s", len(cookies), browser)
    if not cookies:
        raise AuthError(f"No YouTube cookies found in {browser}. Sign in to music.youtube.com there first.")
    return cookies


def _is_auth_failure(exc: Exception) -> bool:
    """True if the exception means 'credentials rejected' rather than 'network down'."""
    from ytmusicapi.exceptions import YTMusicServerError, YTMusicUserError

    if isinstance(exc, YTMusicUserError):
        return True
    if isinstance(exc, YTMusicServerError):
        return any(code in str(exc) for code in ("401", "403"))
    # A logged-out session returns a page without the expected fields.
    return isinstance(exc, (KeyError, TypeError))


# --------------------------------------------------------------------------- #
# Credential storage
# --------------------------------------------------------------------------- #
class CredentialStore:
    """Stores the headers JSON in one file readable only by the current user.

    (OS keyrings are not used on purpose: Windows Credential Manager caps a
    secret at ~2.5 KB, and a YouTube cookie header is usually larger.)
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> Optional[Dict[str, str]]:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            logger.warning("Ignoring unreadable credential file %s: %s", self.path, e)
            return None

    def write(self, headers: Mapping[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dict(headers), f)
        os.replace(tmp, self.path)  # atomic: never leaves a half-written file
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass  # not meaningful on Windows

    def delete(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class AuthService:
    def __init__(self, store_path: Path, client_factory: Optional[Callable[..., Any]] = None):
        if client_factory is None:
            from ytmusicapi import YTMusic as client_factory  # type: ignore[no-redef]
        self._factory = client_factory
        self._store = CredentialStore(store_path)
        self._lock = threading.RLock()
        self._state = SIGNED_OUT
        self._headers: Optional[Dict[str, str]] = None
        self._client: Any = None
        self._anonymous: Any = None
        self._account: Optional[Dict[str, Any]] = None
        self.load()

    # ---- state ------------------------------------------------------------
    @property
    def is_authenticated(self) -> bool:
        return self._state == SIGNED_IN

    @property
    def account(self) -> Optional[Dict[str, Any]]:
        return self._account

    def _ensure_client(self) -> Any:
        """Build the authenticated client on first use.

        ytmusicapi's constructor makes a network request (visitor id), so this
        must not happen at import/startup or an offline launch would look like
        a broken login. Network errors propagate; rejected credentials flip the
        state to 'expired'.
        """
        with self._lock:
            if self._client is None and self._headers:
                try:
                    self._client = self._factory(auth=self._headers)
                except Exception as e:
                    if _is_auth_failure(e):
                        self.mark_expired()
                    raise
            return self._client

    @property
    def client(self) -> Any:
        """The YTMusic instance everything else should use (authenticated if signed in)."""
        with self._lock:
            if self._state == SIGNED_IN:
                try:
                    return self._ensure_client()
                except Exception as e:
                    if self._state == SIGNED_IN:  # network problem, not a dead session
                        raise
                    logger.warning("Falling back to anonymous client: %s", e)
            if self._anonymous is None:
                self._anonymous = self._factory()
            return self._anonymous

    def status(self) -> Dict[str, Any]:
        return {
            "state": self._state,
            "is_authenticated": self.is_authenticated,
            "account": self._account,
        }

    # ---- lifecycle --------------------------------------------------------
    def load(self) -> None:
        """Restore a saved session at startup. Makes no network call (the client is built lazily)."""
        headers = self._store.read()
        if headers and "cookie" in headers:
            with self._lock:
                self._headers, self._state = headers, SIGNED_IN
            logger.info("Found saved YouTube Music session")

    def verify(self) -> Dict[str, Any]:
        """Ask YouTube whether the saved session still works. Call once when the app starts."""
        if self._state != SIGNED_IN:
            return self.status()
        try:
            self._account = self._ensure_client().get_account_info()
        except Exception as e:
            if _is_auth_failure(e):
                self.mark_expired()
            else:  # offline etc. - keep the session, try again later
                logger.warning("Could not verify session (will retry later): %s", e)
        return self.status()

    def connect_with_cookies(self, cookies: CookieInput, authuser: str = "0") -> Dict[str, Any]:
        """Validate cookies against YouTube, then persist them and switch to signed-in."""
        headers = build_headers(normalize_cookies(cookies), authuser)
        try:
            candidate = self._factory(auth=headers)
            account = candidate.get_account_info()
            if not account or not account.get("accountName"):
                raise AuthError("YouTube did not recognise this session (not signed in?).")
        except AuthError:
            raise
        except Exception as e:
            if _is_auth_failure(e):
                raise AuthError("YouTube rejected this session. Please sign in again.") from e
            raise AuthError(f"Could not reach YouTube Music: {e}") from e

        with self._lock:
            self._store.write(headers)
            self._headers, self._client, self._account, self._state = headers, candidate, account, SIGNED_IN
        logger.info("Signed in as %s", account.get("accountName"))
        return self.status()

    def import_from_browser(self, browser: str, profile: Optional[str] = None) -> Dict[str, Any]:
        return self.connect_with_cookies(cookies_from_browser(browser, profile))

    def mark_expired(self) -> None:
        """Called when YouTube starts rejecting the session; the UI should offer 'Sign in again'."""
        with self._lock:
            if self._state == SIGNED_IN:
                logger.warning("YouTube Music session expired")
                self._state = EXPIRED

    def logout(self) -> None:
        with self._lock:
            self._store.delete()
            self._headers = self._client = self._account = None
            self._state = SIGNED_OUT

    @contextmanager
    def guard(self) -> Iterator[None]:
        """Wrap authenticated ytmusicapi calls so a dead session flips the state to 'expired'."""
        try:
            yield
        except Exception as e:
            if _is_auth_failure(e):
                self.mark_expired()
            raise


# --------------------------------------------------------------------------- #
_instance: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _instance
    if _instance is None:
        from backend.config import CACHE_DIR  # imported lazily to keep this module testable

        _instance = AuthService(Path(CACHE_DIR) / "ytm_session.json")
    return _instance
