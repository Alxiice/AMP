"""
Configuration for AMP Backend
=============================
"""
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # App
    APP_NAME: str = "AMP Backend"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Directories
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    CACHE_DIR: Path = BASE_DIR / ".amp" / "cache"
    CHUNKS_DIR: Path = CACHE_DIR / "chunks"
    LOGS_DIR: Path = BASE_DIR / ".amp" / "logs"
    
    # Database
    USERDB_PATH: Path = BASE_DIR / "userdb.sqlite"
    PLAYDB_PATH: Path = BASE_DIR / "playdb.sqlite"
    
    # Cache settings
    CACHE_MAX_SIZE_MB: int = 500
    CHUNK_SIZE_SEC: int = 10
    BUFFER_AHEAD_SEC: int = 15
    
    # Audio
    AUDIO_QUALITY: str = "high"
    AUDIO_FORMAT: str = "mp3"
    AUDIO_BITRATE: int = 192
    
    # YouTube
    YOUTUBE_API_KEY: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path = LOGS_DIR / "app.log"


# Initialize settings
settings = Settings()

# Ensure directories exist
os.makedirs(settings.CACHE_DIR, exist_ok=True)
os.makedirs(settings.CHUNKS_DIR, exist_ok=True)
os.makedirs(settings.LOGS_DIR, exist_ok=True)

# Export settings
APP_NAME = settings.APP_NAME
APP_VERSION = settings.APP_VERSION
DEBUG = settings.DEBUG
HOST = settings.HOST
PORT = settings.PORT
BASE_DIR = settings.BASE_DIR
CACHE_DIR = settings.CACHE_DIR
CHUNKS_DIR = settings.CHUNKS_DIR
LOGS_DIR = settings.LOGS_DIR
USERDB_PATH = settings.USERDB_PATH
PLAYDB_PATH = settings.PLAYDB_PATH
CACHE_MAX_SIZE_MB = settings.CACHE_MAX_SIZE_MB
CHUNK_SIZE_SEC = settings.CHUNK_SIZE_SEC
BUFFER_AHEAD_SEC = settings.BUFFER_AHEAD_SEC
AUDIO_QUALITY = settings.AUDIO_QUALITY
AUDIO_FORMAT = settings.AUDIO_FORMAT
AUDIO_BITRATE = settings.AUDIO_BITRATE
YOUTUBE_API_KEY = settings.YOUTUBE_API_KEY
LOG_LEVEL = settings.LOG_LEVEL
LOG_FILE = settings.LOG_FILE
