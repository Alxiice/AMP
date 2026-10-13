"""
Logger Setup
===========
Logging configuration for AMP Backend.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from backend.config import LOG_LEVEL, LOG_FILE, LOGS_DIR


# Ensure logs directory exists
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def setup_logging() -> None:
    """
    Configure logging for the application.
    
    Logs are:
    - Written to file (.amp/logs/app.log)
    - Printed to console (if DEBUG=True)
    """
    from backend.config import DEBUG
    
    # Convert log level string to logging constant
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)
    
    # Console handler (only in debug mode)
    if DEBUG:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)
    
    # Log startup
    root_logger.info(f"Logging initialized: level={LOG_LEVEL}, file={LOG_FILE}")
    if DEBUG:
        root_logger.info("Debug mode enabled")
