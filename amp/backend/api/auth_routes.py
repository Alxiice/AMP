"""Auth routes — auth flow endpoints."""

from __future__ import annotations

import threading
import uuid
import webbrowser
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.auth import filter_youtube_cookies, get_auth_service
from backend.services.signin_flow import SignInFlowManager
from backend.utils.logger import get_logger

logger = get_logger("backend.api.auth_routes")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CookiesRequest(BaseModel):
    cookie_header: str


class CookieHeaderRequest(BaseModel):
    cookie_header: str


class StartSignInRequest(BaseModel):
    browser: Optional[str] = None


class TauriCookie(BaseModel):
    """A single cookie from Tauri webview."""
    name: str
    value: str
    domain: Optional[str] = None


class TauriCookiesRequest(BaseModel):
    """Cookies from Tauri webview sign-in."""
    cookies: list[TauriCookie]


# Global sign-in flow manager
signin_flow_manager = SignInFlowManager()


@router.get("/status")
def auth_status(verify: bool = False):
    """GET /api/auth/status?verify="""
    auth = get_auth_service()
    return auth.status(verify=verify)


@router.post("/cookies")
def set_cookies(body: CookiesRequest):
    """POST /api/auth/cookies — set cookies from a Cookie header string."""
    auth = get_auth_service()
    return auth.set_cookies_from_header(body.cookie_header)


@router.post("/cookie-header")
def set_cookie_header(body: CookieHeaderRequest):
    """POST /api/auth/cookie-header — alias for /cookies."""
    auth = get_auth_service()
    return auth.set_cookies_from_header(body.cookie_header)


@router.post("/import-browser")
def import_browser(browser: str = "chrome"):
    """POST /api/auth/import-browser?browser=chrome

    Reads the local browser's cookie store with yt-dlp (no network request)
    and keeps only youtube.com cookies. For Firefox, the browser must be
    closed (profile DB is locked while running).
    """
    auth = get_auth_service()
    try:
        from yt_dlp.cookies import extract_cookies_from_browser

        yt_cookies = filter_youtube_cookies(extract_cookies_from_browser(browser))
        if yt_cookies:
            result = auth.set_cookies(yt_cookies)
            logger.info("Imported %d YouTube cookies from %s", len(yt_cookies), browser)
            return result

        raise HTTPException(
            status_code=500,
            detail=f"No cookies found in {browser}. Make sure you are signed in to YouTube Music in {browser}."
            + (" For Firefox, close the browser first (profile is locked while running)." if browser == "firefox" else ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Browser import failed (%s): %s", browser, e)
        msg = str(e)
        if "lock" in msg.lower() or "permission" in msg.lower():
            msg += " — Close the browser and try again."
        raise HTTPException(status_code=500, detail=f"Import failed: {msg}")


@router.post("/open-signin")
def open_signin():
    """POST /api/auth/open-signin — open YouTube Music sign-in page in browser."""
    url = "https://music.youtube.com/"
    try:
        webbrowser.open(url)
        return {"message": "Sign-in page opened", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open browser: {e}")


@router.post("/tauri-cookies")
def set_tauri_cookies(body: TauriCookiesRequest):
    """POST /api/auth/tauri-cookies — set cookies from Tauri webview sign-in.
    
    This is called by the frontend after Tauri's youtube_login command returns cookies.
    The cookies are already in the format {name, value, domain} from the webview.
    """
    auth = get_auth_service()
    
    # Convert Tauri cookies to the format expected by AuthService
    # Filter to YouTube cookies only
    cookies: Dict[str, str] = {}
    for cookie in body.cookies:
        # Only accept cookies for youtube.com domains
        domain = cookie.domain or ""
        if "youtube.com" in domain or cookie.name in ["SAPISID", "__Secure-3PAPISID", "HSID", "SSID"]:
            cookies[cookie.name] = cookie.value
    
    if not cookies:
        raise HTTPException(
            status_code=400,
            detail="No YouTube cookies found in the response. Make sure you completed the sign-in."
        )
    
    result = auth.set_cookies(cookies)
    logger.info("Received %d cookies from Tauri webview, imported %d YouTube cookies", 
                len(body.cookies), len(cookies))
    return result


@router.post("/logout")
def logout():
    """POST /api/auth/logout"""
    auth = get_auth_service()
    auth.logout()
    return {"message": "logged out"}


@router.post("/start-signin-flow")
def start_signin_flow(body: StartSignInRequest):
    """POST /api/auth/start-signin-flow — start automatic sign-in flow.
    
    Opens the default browser to YouTube Music and starts polling for cookies.
    Returns a session_id that can be used to check the status.
    
    The flow:
    1. User clicks "Sign in with YouTube" in the app
    2. Browser opens to music.youtube.com
    3. User signs in to YouTube Music
    4. Backend polls the browser's cookies every 5 seconds
    5. When auth cookies appear, they are automatically imported
    6. Frontend can poll /signin-status/{session_id} to check progress
    """
    session_id = str(uuid.uuid4())
    browser = body.browser or "default"
    
    # Start the sign-in flow
    signin_flow = signin_flow_manager.start_flow(session_id, browser)
    
    # Open browser to YouTube Music
    url = "https://music.youtube.com/"
    try:
        webbrowser.open(url)
        logger.info("Opened sign-in page for session %s in %s", session_id, browser)
    except Exception as e:
        logger.warning("Failed to open browser: %s", e)
        # Continue anyway - user can manually open the URL
    
    return {
        "message": "Sign-in page opened",
        "session_id": session_id,
        "url": url,
        "browser": browser,
        "polling_interval_ms": signin_flow.polling_interval * 1000,
        "timeout_seconds": signin_flow.timeout_seconds,
    }


@router.get("/signin-status/{session_id}")
def signin_status(session_id: str):
    """GET /api/auth/signin-status/{session_id} — check sign-in flow status.
    
    Returns the current status of the sign-in flow:
    - pending: Still waiting for cookies
    - success: Cookies found and imported
    - failed: Error occurred
    - timeout: No cookies detected within timeout period
    - cancelled: Flow was cancelled
    """
    flow = signin_flow_manager.get_flow(session_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Sign-in session not found")
    
    return flow.to_dict()


@router.post("/cancel-signin-flow/{session_id}")
def cancel_signin_flow(session_id: str):
    """POST /api/auth/cancel-signin-flow/{session_id} — cancel sign-in flow."""
    flow = signin_flow_manager.get_flow(session_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Sign-in session not found")
    
    flow.cancel()
    signin_flow_manager.remove_flow(session_id)
    logger.info("Cancelled sign-in flow %s", session_id)
    return {"message": "Sign-in flow cancelled", "session_id": session_id}
