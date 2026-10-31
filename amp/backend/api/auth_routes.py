"""Auth routes.

Sign-in paths (Phase 5): the Tauri webview login (primary, POST /tauri-cookies),
a pasted Cookie header (POST /cookies), and Firefox cookie import. Every path
stores only youtube.com cookies (AuthService.set_cookies filters).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.auth import filter_youtube_cookies, get_auth_service
from backend.utils.logger import get_logger

logger = get_logger("backend.api.auth_routes")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# yt-dlp can't decrypt Chrome/Edge cookies on Windows (app-bound encryption); Firefox still works
IMPORT_BROWSERS = {"firefox"}


class CookiesRequest(BaseModel):
    cookie_header: str


class TauriCookie(BaseModel):
    """A single cookie from the Tauri webview."""
    name: str
    value: str
    domain: Optional[str] = None


class TauriCookiesRequest(BaseModel):
    """Cookies from the Tauri webview sign-in."""
    cookies: list[TauriCookie]


@router.get("/status")
def auth_status(verify: bool = False):
    """GET /api/auth/status?verify="""
    auth = get_auth_service()
    return auth.status(verify=verify)


@router.post("/cookies")
def set_cookies(body: CookiesRequest):
    """POST /api/auth/cookies — set cookies from a pasted Cookie header (domain .youtube.com)."""
    auth = get_auth_service()
    return auth.set_cookies_from_header(body.cookie_header)


@router.post("/cookie-header")
def set_cookie_header(body: CookiesRequest):
    """POST /api/auth/cookie-header — alias for /cookies."""
    auth = get_auth_service()
    return auth.set_cookies_from_header(body.cookie_header)


@router.post("/import-browser")
def import_browser(browser: str = "firefox"):
    """POST /api/auth/import-browser?browser=firefox

    Reads Firefox's cookie store with yt-dlp (no network request) and keeps
    only youtube.com cookies. Firefox must be closed (its profile DB is locked
    while it runs).
    """
    if browser not in IMPORT_BROWSERS:
        raise HTTPException(
            status_code=400,
            detail=f"Import from {browser} is not supported; only Firefox works reliably. "
                   "Use 'Sign in with YouTube' instead.",
        )
    auth = get_auth_service()
    try:
        from yt_dlp.cookies import extract_cookies_from_browser

        yt_cookies = filter_youtube_cookies(extract_cookies_from_browser(browser))
    except Exception as e:
        logger.error("Browser import failed (%s): %s", browser, e)
        msg = str(e)
        if "lock" in msg.lower() or "permission" in msg.lower():
            msg += " — Close Firefox and try again."
        raise HTTPException(status_code=500, detail=f"Import failed: {msg}")

    if not yt_cookies:
        raise HTTPException(
            status_code=404,
            detail="No YouTube cookies found in Firefox. Sign in to YouTube Music in Firefox, "
                   "close Firefox, then try again.",
        )
    result = auth.set_cookies(yt_cookies)
    logger.info("Imported %d YouTube cookies from %s", len(yt_cookies), browser)
    return result


@router.post("/tauri-cookies")
def set_tauri_cookies(body: TauriCookiesRequest):
    """POST /api/auth/tauri-cookies — cookies read from the Tauri sign-in webview.

    The webview reads music.youtube.com and www.youtube.com; anything not on a
    youtube.com domain (e.g. .google.com) is dropped.
    """
    cookies = filter_youtube_cookies(body.cookies)
    if not cookies:
        raise HTTPException(
            status_code=400,
            detail="No YouTube cookies found in the response. Make sure you completed the sign-in.",
        )
    result = get_auth_service().set_cookies(cookies)
    logger.info("Received %d cookies from Tauri webview, kept %d YouTube cookies",
                len(body.cookies), len(cookies))
    return result


@router.post("/logout")
def logout():
    """POST /api/auth/logout"""
    auth = get_auth_service()
    auth.logout()
    return {"message": "logged out"}
