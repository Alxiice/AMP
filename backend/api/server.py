"""
FastAPI Server
==============
Main FastAPI application setup for AMP Backend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import APP_NAME, APP_VERSION, DEBUG, HOST, PORT
from backend.utils.logger import setup_logging
from backend.database.session import init_userdb, init_playdb

# Initialize logging (without starting the logger to avoid console issues)
from backend.utils.logger import get_logger
logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Backend API for AMP (Another Music Player)",
    debug=DEBUG,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Initialize databases
try:
    init_userdb()
    init_playdb()
except Exception as e:
    logger.error(f"Failed to initialize databases: {e}")
    raise

# Import and include routers
from backend.api.endpoints import router as api_router
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint - returns API info."""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    logger.info(f"Server running at http://{HOST}:{PORT}")
    logger.info(f"Docs available at http://{HOST}:{PORT}/docs")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.api.server:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
