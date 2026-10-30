"""Tests for the signin_flow module."""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from backend.services.signin_flow import (
    SignInFlow,
    SignInFlowManager,
    SignInStatus,
    AUTH_COOKIE_NAMES,
)


class TestSignInStatus:
    """Test SignInStatus enum."""

    def test_status_values(self):
        """Verify all expected status values exist."""
        assert SignInStatus.PENDING.value == "pending"
        assert SignInStatus.POLLING.value == "polling"
        assert SignInStatus.SUCCESS.value == "success"
        assert SignInStatus.FAILED.value == "failed"
        assert SignInStatus.TIMEOUT.value == "timeout"
        assert SignInStatus.CANCELLED.value == "cancelled"


class TestAuthCookieNames:
    """Test AUTH_COOKIE_NAMES constant."""

    def test_contains_essential_cookies(self):
        """Verify essential YouTube auth cookies are tracked."""
        expected = {
            "__Secure-3PAPISID",
            "SAPISID",
            "HSID",
            "SSID",
        }
        assert expected.issubset(AUTH_COOKIE_NAMES)


class TestSignInFlow:
    """Test SignInFlow class."""

    @pytest.fixture
    def flow(self):
        """Create a SignInFlow instance."""
        return SignInFlow(
            session_id="test-session",
            browser="chrome",
            polling_interval=0.1,
            timeout_seconds=1.0,
        )

    def test_init_defaults(self, flow):
        """Test default initialization."""
        assert flow.session_id == "test-session"
        assert flow.browser == "chrome"
        assert flow.polling_interval == 0.1
        assert flow.timeout_seconds == 1.0
        assert flow.status == SignInStatus.PENDING
        assert flow.error is None
        assert flow.is_authenticated is False
        assert flow.cookies_imported == 0

    def test_init_default_browser(self):
        """Test initialization with default browser."""
        flow = SignInFlow(
            session_id="test-session",
            browser="default",
        )
        assert flow.browser is None  # "default" should become None

    def test_has_auth_cookies(self, flow):
        """Test _has_auth_cookies method."""
        # Empty cookies
        assert flow._has_auth_cookies({}) is False

        # Non-auth cookies
        assert flow._has_auth_cookies({"some_cookie": "value"}) is False

        # Auth cookies
        for cookie_name in AUTH_COOKIE_NAMES:
            cookies = {cookie_name: "test_value"}
            assert flow._has_auth_cookies(cookies) is True

    def test_to_dict(self, flow):
        """Test to_dict method."""
        result = flow.to_dict()
        assert result["session_id"] == "test-session"
        assert result["browser"] == "chrome"
        assert result["status"] == "pending"
        assert result["is_authenticated"] is False
        assert result["cookies_imported"] == 0
        assert result["error"] is None
        assert result["polling_interval_ms"] == 100  # 0.1 * 1000
        assert result["timeout_seconds"] == 1.0

    def test_start_sets_status(self, flow):
        """Test that start() sets status to POLLING."""
        # Mock the _get_cookies_from_browser to avoid actual browser access
        with patch.object(flow, "_get_cookies_from_browser", return_value={}):
            flow.start()
            # Give the thread a moment to start
            time.sleep(0.05)
            assert flow.status == SignInStatus.POLLING

    def test_cancel_sets_status(self, flow):
        """Test that cancel() sets status to CANCELLED."""
        # Mock the _get_cookies_from_browser to avoid actual browser access
        with patch.object(flow, "_get_cookies_from_browser", return_value={}):
            flow.start()
            time.sleep(0.05)
            flow.cancel()
            assert flow.status == SignInStatus.CANCELLED
            assert flow.error == "Flow was cancelled by user"

    @patch("backend.services.signin_flow.get_auth_service")
    def test_poll_loop_success(self, mock_get_auth, flow):
        """Test that poll loop detects and imports cookies."""
        # Setup mocks
        mock_auth = MagicMock()
        mock_auth.set_cookies = MagicMock(return_value={"cookie_count": 2})
        mock_get_auth.return_value = mock_auth
        
        # Override _get_cookies_from_browser to return auth cookies after first call
        call_count = [0]
        
        def mock_get_cookies():
            call_count[0] += 1
            if call_count[0] > 1:
                return {"SAPISID": "test_sapisid"}
            return {}
        
        flow._get_cookies_from_browser = mock_get_cookies
        
        # Start the flow
        flow.start()
        
        # Wait for the poll loop to complete
        time.sleep(0.3)
        
        # Check that cookies were imported
        assert flow.status == SignInStatus.SUCCESS
        assert flow.is_authenticated is True
        assert flow.cookies_imported == 2

    @patch("backend.services.signin_flow.get_auth_service")
    def test_poll_loop_timeout(self, mock_get_auth, flow):
        """Test that poll loop times out."""
        # Mock to return empty cookies always
        flow._get_cookies_from_browser = MagicMock(return_value={})
        
        # Set very short timeout
        flow.timeout_seconds = 0.3
        flow.polling_interval = 0.1
        
        # Start the flow
        flow.start()
        
        # Wait for timeout
        time.sleep(0.4)
        
        # Check that it timed out
        assert flow.status == SignInStatus.TIMEOUT
        assert "No cookies detected" in (flow.error or "")

    @patch("backend.services.signin_flow.get_auth_service")
    def test_poll_loop_error(self, mock_get_auth, flow):
        """Test that poll loop handles errors."""
        # Mock to return empty cookies initially, then raise error
        call_count = [0]
        def mock_get_cookies():
            call_count[0] += 1
            if call_count[0] > 2:
                raise RuntimeError("Browser not found")
            return {}
        
        flow._get_cookies_from_browser = mock_get_cookies
        
        # Start the flow
        flow.start()
        
        # Wait a bit for the error to occur
        time.sleep(0.25)
        
        # Check that it failed
        assert flow.status == SignInStatus.FAILED
        assert flow.error is not None
        assert "Browser not found" in flow.error


class TestSignInFlowManager:
    """Test SignInFlowManager class."""

    @pytest.fixture
    def manager(self):
        """Create a SignInFlowManager instance."""
        return SignInFlowManager()

    def test_init(self, manager):
        """Test initialization."""
        assert len(manager.get_all_flows()) == 0

    def test_start_flow(self, manager):
        """Test starting a new flow."""
        with patch("backend.services.signin_flow.SignInFlow") as mock_flow_class:
            # Create a mock flow
            mock_flow = MagicMock()
            mock_flow.session_id = "test-session"
            mock_flow.browser = "chrome"
            mock_flow.start = MagicMock()
            mock_flow_class.return_value = mock_flow
            
            flow = manager.start_flow("test-session", "chrome")
            assert flow.session_id == "test-session"
            assert flow.browser == "chrome"
            assert manager.get_flow("test-session") is flow

    def test_start_flow_replaces_existing(self, manager):
        """Test that starting a flow with existing session_id replaces it."""
        with patch("backend.services.signin_flow.SignInFlow") as mock_flow_class:
            flow1 = MagicMock()
            flow1.cancel = MagicMock()
            flow2 = MagicMock()
            mock_flow_class.return_value = flow2
            
            # Start first flow
            manager._flows["test-session"] = flow1
            
            # Start second flow with same session_id
            result = manager.start_flow("test-session", "chrome")
            
            # Check that old flow was cancelled and replaced
            flow1.cancel.assert_called_once()
            assert "test-session" not in manager._flows or manager._flows["test-session"] is result

    def test_get_flow(self, manager):
        """Test getting a flow by session_id."""
        with patch("backend.services.signin_flow.SignInFlow") as mock_flow_class:
            # Create a mock flow
            mock_flow = MagicMock()
            mock_flow.session_id = "test-session"
            mock_flow.start = MagicMock()
            mock_flow_class.return_value = mock_flow
            
            manager.start_flow("test-session", "chrome")
            flow = manager.get_flow("test-session")
            assert flow is not None
            assert flow.session_id == "test-session"
            
            # Non-existent flow
            assert manager.get_flow("non-existent") is None

    def test_remove_flow(self, manager):
        """Test removing a flow."""
        with patch("backend.services.signin_flow.SignInFlow") as mock_flow_class:
            flow = MagicMock()
            flow.cancel = MagicMock()
            mock_flow_class.return_value = flow
            
            manager.start_flow("test-session", "chrome")
            assert manager.get_flow("test-session") is not None
            
            result = manager.remove_flow("test-session")
            assert result is True
            assert manager.get_flow("test-session") is None
            flow.cancel.assert_called_once()
            
            # Remove non-existent flow
            result = manager.remove_flow("non-existent")
            assert result is False

    def test_cleanup_finished_flows(self, manager):
        """Test cleanup of finished flows."""
        with patch("backend.services.signin_flow.SignInFlow") as mock_flow_class:
            # Create flows with different statuses
            pending_flow = MagicMock()
            pending_flow.status = SignInStatus.PENDING
            
            success_flow = MagicMock()
            success_flow.status = SignInStatus.SUCCESS
            
            failed_flow = MagicMock()
            failed_flow.status = SignInStatus.FAILED
            
            manager._flows = {
                "pending": pending_flow,
                "success": success_flow,
                "failed": failed_flow,
            }
            
            # Cleanup
            removed_count = manager.cleanup_finished_flows()
            
            assert removed_count == 2
            assert "pending" in manager._flows
            assert "success" not in manager._flows
            assert "failed" not in manager._flows

    def test_get_all_flows(self, manager):
        """Test getting all flows."""
        with patch("backend.services.signin_flow.SignInFlow"):
            manager.start_flow("session1", "chrome")
            manager.start_flow("session2", "firefox")
            
            flows = manager.get_all_flows()
            assert len(flows) == 2
            assert "session1" in flows
            assert "session2" in flows
