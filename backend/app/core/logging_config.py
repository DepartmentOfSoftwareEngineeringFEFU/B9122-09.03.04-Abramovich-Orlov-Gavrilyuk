"""
Centralized logging configuration for Diplom3D Backend
"""

import logging
import sys
import os

# Log format
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_logger_initialized = False


def setup_logging(log_level: str = "DEBUG") -> logging.Logger:
    """
    Setup centralized logging for the application.
    Returns the main application logger.
    """
    global _logger_initialized
    
    logger = logging.getLogger("diplom3d")
    
    if _logger_initialized:
        return logger
    
    logger.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))
    
    # Console handler only (simple, no file I/O at import time)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)
    
    _logger_initialized = True
    return logger


def get_logger(name: str = "diplom3d") -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)
