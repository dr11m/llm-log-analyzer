"""Simple logger for log analyzer."""
import logging
import sys
from pathlib import Path

# Create logger
logger = logging.getLogger("log_analyzer")

# Configure if not already configured
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

__all__ = ["logger"]
