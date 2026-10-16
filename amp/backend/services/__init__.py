"""
Services Module
==============
Service layer for AMP Backend.

This module contains all service classes for:
- YouTube Music API integration (youtube.py)
- Authentication and OAuth flow (auth.py)
- Audio streaming with yt-dlp (streaming.py)
"""

# Import from individual service modules
from backend.services.youtube import YouTubeService, get_youtube_service
from backend.services.auth import AuthService, get_auth_service
from backend.services.streaming import StreamingService, get_streaming_service


# Also expose the classes and functions at package level for convenience
__all__ = [
    "YouTubeService",
    "AuthService",
    "StreamingService",
    "get_youtube_service",
    "get_auth_service",
    "get_streaming_service",
]
