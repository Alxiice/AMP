"""
Auth routes. Include with:  router.include_router(auth_router)   (prefix /api is added by your main router)

These are plain `def` handlers on purpose: they make blocking network calls to
YouTube, and FastAPI runs sync handlers in a thread pool instead of blocking
the event loop.
"""
import logging
import os
import secrets
import traceback
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from backend.services.auth import AuthError, get_auth_service

logger = logging.getLogger(__name__)

# Optional hardening: if Tauri starts the sidecar with AMP_LOCAL_TOKEN set (random per launch)
# and sends it back in X-AMP-Token, other local programs/web pages can't push cookies in.
_TOKEN = os.environ.get("AMP_LOCAL_TOKEN")


def require_local_token(x_amp_token: Optional[str] = Header(default=None)) -> None:
    if _TOKEN and not secrets.compare_digest(x_amp_token or "", _TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden")


router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_local_token)])


class CookieIn(BaseModel):
    name: str
    value: str
    domain: Optional[str] = None


class CookiesBody(BaseModel):
    cookies: List[CookieIn]


class BrowserBody(BaseModel):
    browser: str  # firefox | chrome | edge | brave | safari | chromium
    profile: Optional[str] = None


@router.get("/status")
def status(verify: bool = False):
    """verify=true asks YouTube whether the saved session still works (call once at app start)."""
    auth = get_auth_service()
    return auth.verify() if verify else auth.status()


@router.post("/cookies")
def connect_cookies(body: CookiesBody):
    """Receives the cookies captured by the Tauri sign-in window."""
    try:
        return get_auth_service().connect_with_cookies([c.model_dump() for c in body.cookies])
    except AuthError as e:
        logger.warning("Cookie auth failed: %s", e)
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error in /auth/cookies:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@router.post("/import-browser")
def import_browser(body: BrowserBody):
    """Shortcut for users already signed in to music.youtube.com in an installed browser."""
    logger.info("Import browser request: browser=%s profile=%s", body.browser, body.profile)
    try:
        result = get_auth_service().import_from_browser(body.browser, body.profile)
        logger.info("Import browser success: state=%s", result.get("state"))
        return result
    except AuthError as e:
        logger.warning("Import browser failed: %s", e)
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error in /auth/import-browser:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}: {e}")


@router.post("/logout")
def logout():
    get_auth_service().logout()
    return {"state": "signed_out", "is_authenticated": False}
