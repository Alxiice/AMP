#!/usr/bin/env python3
"""
AMP Backend Main Entry Point
=============================
Run this script to start the FastAPI server.

Usage:
    python backend/main.py
    
Or with custom host/port:
    python backend/main.py --host 0.0.0.0 --port 8000
"""
import argparse
import os
import sys

# Add backend directory to path
BACKEND_FOLDER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BACKEND_FOLDER))

from backend.api.server import app, HOST, PORT
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="AMP Backend Server")
    parser.add_argument("--host", type=str, default=HOST, help=f"Host to bind (default: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to listen on (default: {PORT})")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug mode")
    parser.add_argument("--reload", action="store_true", default=False, help="Enable auto-reload on code changes")
    return parser.parse_args()


def main():
    """Start the FastAPI server."""
    args = parse_args()
    
    logger.info(f"Starting AMP Backend on {args.host}:{args.port}")
    
    try:
        import uvicorn
        uvicorn.run(
            "backend.api.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload or args.debug,
            log_level="debug" if args.debug else "info",
        )
    except ImportError:
        logger.error("uvicorn is not installed. Run: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
