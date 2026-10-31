"""FastAPI app: CORS, optional token auth middleware, DNS-rebinding guard, DB init, routers.

P17: Bind 127.0.0.1, validate Host header (always). Bearer token required only
if AUTH_TOKEN is configured — otherwise the API is open for local use.
F15: open mode must not let other web pages change state. Browsers always send
Origin on cross-origin POST/PUT/DELETE, so a non-allowed Origin is rejected;
requests without Origin (curl, the control panel) are allowed. GETs on
/api/auth/* from another site without an allowed Origin (navigations, <img>)
are rejected too.
P21: Blocking handlers are plain `def` (threadpool), never `async def`.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.errors import register_error_handlers
from backend.config import settings
from backend.database.session import init_db
from backend.services.auth import get_auth_service
from backend.services.extractor import get_extraction_dependencies
from backend.services.streaming import get_streaming_service
from backend.utils.logger import configure_logging, get_logger

logger = get_logger("backend.api.server")

ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",  # Windows with useHttpsScheme
    "http://localhost:1420",   # Vite dev
    "http://127.0.0.1:1420",
]

PUBLIC_PATHS = {"/", "/api/health", "/docs", "/openapi.json", "/redoc"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def host_name(host_header: str) -> str:
    """Host header without the port: '127.0.0.1:8000' → '127.0.0.1', '[::1]:8000' → '[::1]'."""
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[:end + 1] if end != -1 else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _forbidden(code: str, message: str) -> JSONResponse:
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=403)


def cross_site_rejection(method: str, path: str, origin: Optional[str], fetch_site: Optional[str]) -> Optional[str]:
    """Why a request from another web page must be refused, or None (F15)."""
    allowed = origin in ALLOWED_ORIGINS
    if method not in SAFE_METHODS:
        if origin is not None and not allowed:
            return "state-changing request from another origin"
    elif path.startswith("/api/auth/") and fetch_site == "cross-site" and not allowed:
        return "auth request from another site"
    return None


def create_app(auth_token: Optional[str] = None) -> FastAPI:
    configure_logging()
    token = auth_token or settings.AUTH_TOKEN
    # Token is optional — if not set, the API is open (no Bearer auth required).
    # Host header validation always applies (DNS-rebinding guard, P17).

    # Sync work in an async lifespan is fine here: nothing is served yet / anymore
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        get_extraction_dependencies()  # computed once, logged (P2)
        get_auth_service()  # loads the credential store now, so a v1→v2 migration is in the startup log
        svc = get_streaming_service()
        svc.start()
        auth_mode = "token required" if token else "open (no token)"
        logger.info("AMP v2 backend started on %s:%d (auth=%s)", settings.HOST, settings.PORT, auth_mode)
        try:
            yield
        finally:
            get_streaming_service().stop()
            logger.info("AMP v2 backend shut down")

    app = FastAPI(title="AMP v2 Backend", version="2.0.0", lifespan=lifespan)

    # --- Auth + Host middleware (P17) ---
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Exempt OPTIONS (CORS preflight) and public paths
            if request.method == "OPTIONS":
                return await call_next(request)
            path = request.url.path
            if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
                return await call_next(request)

            # Host check (DNS-rebinding guard) — always enforced
            if host_name(request.headers.get("host", "")) not in LOOPBACK_HOSTS:
                return JSONResponse({"detail": "Forbidden host"}, status_code=403)

            # Cross-site requests (F15) — always enforced, token or not
            reason = cross_site_rejection(
                request.method, path, request.headers.get("origin"), request.headers.get("sec-fetch-site"),
            )
            if reason:
                logger.warning("Rejected %s %s: %s (Origin=%s)", request.method, path, reason,
                               request.headers.get("origin"))
                return _forbidden("forbidden_origin", f"Forbidden: {reason}")

            # Bearer token check — only enforced if a token is configured
            if token:
                auth_header = request.headers.get("authorization", "")
                if not auth_header.startswith("Bearer "):
                    return JSONResponse({"detail": "Missing or invalid Authorization header"}, status_code=401)
                if auth_header[7:] != token:
                    return JSONResponse({"detail": "Invalid token"}, status_code=401)

            return await call_next(request)

    app.add_middleware(AuthMiddleware)
    register_error_handlers(app)

    # --- CORS (explicit origins only) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Explicitly expose Range header for audio streaming
        expose_headers=["Content-Range", "Content-Length", "Content-Type", "Accept-Ranges"],
    )

    # --- Root + Health (no auth required) ---
    @app.get("/")
    def root():
        return {"app": "AMP v2", "version": "2.0.0", "status": "running"}

    @app.get("/api/health")
    def health():
        from backend.services.auth import get_auth_service
        auth = get_auth_service()
        return {
            "status": "ok",
            "app": "AMP v2",  # lifecycle.probe_backend: tells an AMP backend from anything else on the port
            "pid": os.getpid(),
            "services": {
                "auth": auth.state.value,
                "streaming": "running",
                "database": "connected",
                "extractor": get_extraction_dependencies(),
            },
        }

    # --- Mount routers ---
    from backend.api.endpoints import router as main_router
    from backend.api.auth_routes import router as auth_router

    app.include_router(auth_router)
    app.include_router(main_router)

    return app
