import logging
import os
import sys
import time
from pathlib import Path

__version__ = "0.1.0"

# Setup logs directory in workspace root
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Generate unique log file name for this process run
_START_TIME = time.strftime("%Y%m%d_%H%M%S")
_PID = os.getpid()
LOG_FILE = LOGS_DIR / f"research_agent_{_START_TIME}_{_PID}.log"


def initialize_logging() -> None:
    """Initialize the root logger configuration for both file and stream outputs."""
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Define a clean, aligned, and highly readable formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler to write to our unique log file
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Stream handler to output to console/FastAPI output stream
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicates, then add
    root_logger.handlers = []
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    logging.info("Logging initialized. Writing logs to %s", LOG_FILE)


# Run default initialization at import time
initialize_logging()

