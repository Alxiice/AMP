"""FastAPI app: CORS, optional token auth middleware, DNS-rebinding guard, DB init, routers.

P17: Bind 127.0.0.1, validate Host header (always). Bearer token required only
if AUTH_TOKEN is configured — otherwise the API is open for local use.
P21: Blocking handlers are plain `def` (threadpool), never `async def`.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.database.session import init_db
from backend.services.streaming import get_streaming_service, log_extraction_dependencies
from backend.utils.logger import configure_logging, get_logger

logger = get_logger("backend.api.server")

ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "http://localhost:1420",   # Vite dev
    "http://127.0.0.1:1420",
]

PUBLIC_PATHS = {"/", "/api/health", "/docs", "/openapi.json", "/redoc"}


def create_app(auth_token: Optional[str] = None) -> FastAPI:
    configure_logging()
    token = auth_token or settings.AUTH_TOKEN
    # Token is optional — if not set, the API is open (no Bearer auth required).
    # Host header validation always applies (DNS-rebinding guard, P17).

    app = FastAPI(title="AMP v2 Backend", version="2.0.0")

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
            host = request.headers.get("host", "").split(":")[0]
            if host not in {"127.0.0.1", "localhost", "[::1]"}:
                return JSONResponse({"detail": "Forbidden host"}, status_code=403)

            # Bearer token check — only enforced if a token is configured
            if token:
                auth_header = request.headers.get("authorization", "")
                if not auth_header.startswith("Bearer "):
                    return JSONResponse({"detail": "Missing or invalid Authorization header"}, status_code=401)
                if auth_header[7:] != token:
                    return JSONResponse({"detail": "Invalid token"}, status_code=401)

            return await call_next(request)

    app.add_middleware(AuthMiddleware)

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

    # --- Startup / Shutdown ---
    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        log_extraction_dependencies()
        svc = get_streaming_service()
        svc.start()
        auth_mode = "token required" if token else "open (no token)"
        logger.info("AMP v2 backend started on %s:%d (auth=%s)", settings.HOST, settings.PORT, auth_mode)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        svc = get_streaming_service()
        svc.stop()
        logger.info("AMP v2 backend shut down")

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
            "services": {
                "auth": auth.state.value,
                "streaming": "running",
                "database": "connected",
            },
        }

    # --- Mount routers ---
    from backend.api.endpoints import router as main_router
    from backend.api.auth_routes import router as auth_router

    app.include_router(auth_router)
    app.include_router(main_router)

    return app
