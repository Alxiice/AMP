"""SignInFlow — automatic cookie extraction from browser sign-in.

This module provides automatic cookie extraction for YouTube Music sign-in:
- Opens browser to YouTube Music
- Polls the browser's cookie store periodically
- Detects when auth cookies appear
- Automatically imports them

Supports Chrome, Edge, Brave, Chromium, Firefox (when closed), etc.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Dict, Optional

from backend.services.auth import filter_youtube_cookies, get_auth_service
from backend.utils.logger import get_logger

logger = get_logger("backend.services.signin_flow")


class SignInStatus(str, Enum):
    """Status of a sign-in flow."""
    PENDING = "pending"      # Waiting for cookies
    POLLING = "polling"      # Actively polling browser
    SUCCESS = "success"      # Cookies found and imported
    FAILED = "failed"        # Error occurred
    TIMEOUT = "timeout"      # No cookies detected within timeout
    CANCELLED = "cancelled"  # Flow was cancelled


# Key cookies that indicate YouTube authentication
AUTH_COOKIE_NAMES = {
    "__Secure-3PAPISID",
    "SAPISID",
    "HSID",
    "SSID",
    "__Secure-3PSID",
    "__Secure-HPSID",
    "APISID",
    "SID",
}


class SignInFlow:
    """A single sign-in flow that polls a browser for cookies."""

    def __init__(
        self,
        session_id: str,
        browser: str,
        polling_interval: float = 5.0,
        timeout_seconds: float = 120.0,
    ):
        self.session_id = session_id
        self.browser = browser if browser != "default" else None
        self.polling_interval = polling_interval
        self.timeout_seconds = timeout_seconds
        
        self.status: SignInStatus = SignInStatus.PENDING
        self.error: Optional[str] = None
        self.is_authenticated: bool = False
        self.cookies_imported: int = 0
        
        self._initial_cookies: Dict[str, str] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start polling for cookies."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Sign-in flow %s is already running", self.session_id)
                return
            
            self.status = SignInStatus.POLLING
            self.error = None
            self.is_authenticated = False
            self.cookies_imported = 0
            self._stop_event.clear()
            
            # Get initial cookies (before user signs in)
            self._initial_cookies = self._get_cookies_from_browser()
            logger.info(
                "Started sign-in flow %s for browser %s, initial cookies: %d",
                self.session_id,
                self.browser or "default",
                len(self._initial_cookies),
            )
            
            # Start polling thread
            self._thread = threading.Thread(
                target=self._poll_loop,
                name=f"SignInFlow-{self.session_id}",
                daemon=True,
            )
            self._thread.start()

    def _poll_loop(self) -> None:
        """Main polling loop."""
        start_time = time.time()
        
        try:
            while not self._stop_event.is_set():
                elapsed = time.time() - start_time
                if elapsed > self.timeout_seconds:
                    with self._lock:
                        self.status = SignInStatus.TIMEOUT
                        self.error = f"No cookies detected within {self.timeout_seconds} seconds"
                    logger.info(
                        "Sign-in flow %s timed out after %.1fs",
                        self.session_id,
                        elapsed,
                    )
                    break
                
                # Get current cookies
                current_cookies = self._get_cookies_from_browser()
                
                # Check if auth cookies appeared
                if self._has_auth_cookies(current_cookies):
                    # Import cookies
                    auth_service = get_auth_service()
                    result = auth_service.set_cookies(current_cookies)
                    
                    with self._lock:
                        self.status = SignInStatus.SUCCESS
                        self.is_authenticated = True
                        self.cookies_imported = result.get("cookie_count", 0)
                    
                    logger.info(
                        "Sign-in flow %s succeeded, imported %d cookies",
                        self.session_id,
                        self.cookies_imported,
                    )
                    break
                
                # Sleep before next poll
                # Use a loop with small sleeps to allow quick cancellation
                for _ in range(int(self.polling_interval * 10)):
                    if self._stop_event.is_set():
                        return
                    time.sleep(0.1)
            
        except Exception as e:
            with self._lock:
                self.status = SignInStatus.FAILED
                self.error = str(e)
            logger.error("Sign-in flow %s failed: %s", self.session_id, e)

    def _has_auth_cookies(self, cookies: Dict[str, str]) -> bool:
        """Check if cookies contain YouTube auth cookies."""
        return any(name in cookies for name in AUTH_COOKIE_NAMES)

    def _get_cookies_from_browser(self) -> Dict[str, str]:
        """Read youtube.com cookies from the local browser store (no network request)."""
        # If browser is None or "default", use Chrome as default
        browser = self.browser or "chrome"
        try:
            from yt_dlp.cookies import extract_cookies_from_browser

            return filter_youtube_cookies(extract_cookies_from_browser(browser))
        except FileNotFoundError as e:
            # yt-dlp not installed or browser not found
            logger.debug("Cookies from browser failed (browser not found): %s", e)
            raise RuntimeError(
                f"Browser '{browser}' not found or not supported. "
                f"Make sure {browser} is installed and you are signed in."
            )
        except PermissionError as e:
            # Firefox profile is locked
            if "firefox" in (self.browser or "").lower():
                raise RuntimeError(
                    "Firefox profile is locked. Please close Firefox and try again."
                )
            raise RuntimeError(f"Permission denied accessing browser cookies: {e}")
        except Exception as e:
            # Other errors
            logger.debug("Cookies from browser failed: %s", e)
            raise RuntimeError(f"Failed to get cookies from browser: {e}")

    def cancel(self) -> None:
        """Cancel the sign-in flow."""
        with self._lock:
            if self.status in (SignInStatus.SUCCESS, SignInStatus.FAILED, SignInStatus.TIMEOUT):
                return  # Already finished
            
            self._stop_event.set()
            self.status = SignInStatus.CANCELLED
            self.error = "Flow was cancelled by user"
            
            # Wait for thread to finish
            if self._thread is not None:
                self._thread.join(timeout=5)
                self._thread = None
            
            logger.info("Cancelled sign-in flow %s", self.session_id)

    def to_dict(self) -> Dict[str, Any]:
        """Return flow state as a dictionary."""
        with self._lock:
            return {
                "session_id": self.session_id,
                "browser": self.browser,
                "status": self.status.value,
                "is_authenticated": self.is_authenticated,
                "cookies_imported": self.cookies_imported,
                "error": self.error,
                "polling_interval_ms": self.polling_interval * 1000,
                "timeout_seconds": self.timeout_seconds,
                "elapsed_seconds": 0,  # TODO: track elapsed time
            }


class SignInFlowManager:
    """Manages multiple concurrent sign-in flows."""

    def __init__(self) -> None:
        self._flows: Dict[str, SignInFlow] = {}
        self._lock = threading.RLock()

    def start_flow(
        self,
        session_id: str,
        browser: Optional[str] = None,
    ) -> SignInFlow:
        """Start a new sign-in flow."""
        with self._lock:
            # Cancel any existing flow with the same session_id
            if session_id in self._flows:
                old_flow = self._flows[session_id]
                old_flow.cancel()
                del self._flows[session_id]
                logger.info("Replaced existing sign-in flow %s", session_id)
            
            # Create and start new flow
            flow = SignInFlow(
                session_id=session_id,
                browser=browser or "default",
            )
            flow.start()
            self._flows[session_id] = flow
            return flow

    def get_flow(self, session_id: str) -> Optional[SignInFlow]:
        """Get a sign-in flow by session_id."""
        with self._lock:
            return self._flows.get(session_id)

    def remove_flow(self, session_id: str) -> bool:
        """Remove a sign-in flow."""
        with self._lock:
            if session_id in self._flows:
                flow = self._flows.pop(session_id)
                flow.cancel()
                return True
            return False

    def cleanup_finished_flows(self) -> int:
        """Remove finished flows. Returns count of removed flows."""
        with self._lock:
            finished_sessions = [
                sid for sid, flow in self._flows.items()
                if flow.status in (
                    SignInStatus.SUCCESS,
                    SignInStatus.FAILED,
                    SignInStatus.TIMEOUT,
                    SignInStatus.CANCELLED,
                )
            ]
            for sid in finished_sessions:
                del self._flows[sid]
            
            if finished_sessions:
                logger.info("Cleaned up %d finished sign-in flows", len(finished_sessions))
            
            return len(finished_sessions)

    def get_all_flows(self) -> Dict[str, SignInFlow]:
        """Get all active flows."""
        with self._lock:
            return dict(self._flows)
