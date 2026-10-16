"""
API Module
=========
FastAPI endpoints and server configuration for AMP Backend.
"""
from .server import app
from .endpoints import router as api_router

__all__ = ["app", "api_router"]
