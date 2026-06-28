import hashlib
import json
import logging
from pathlib import Path
import sys
import threading
from typing import Any

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / ".cache"
_cache_lock = threading.Lock()

def _get_cache_path(service: str, key: str) -> Path:
    """Get the file path for a cached response using MD5 hash of the key."""
    key_hash = hashlib.md5(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / service / f"{key_hash}.json"

@observe()
def get_cached_response(service: str, key: str) -> dict | None:
    """Retrieve a cached API response if it exists."""
    if "pytest" in sys.modules:
        return None

    path = _get_cache_path(service, key)
    if not path.exists():
        return None
    
    try:
        with _cache_lock:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("Cache hit for %s (key: %s)", service, key[:40])
                return data
    except Exception as e:
        logger.warning("Failed to read cache file %s: %s", path, e)
        return None

@observe()
def set_cached_response(service: str, key: str, value: dict) -> None:
    """Cache an API response."""
    if "pytest" in sys.modules:
        return

    # Avoid caching error responses
    if not value or "error" in value:
        return
        
    path = _get_cache_path(service, key)
    try:
        with _cache_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
                logger.info("Cached response for %s (key: %s)", service, key[:40])
    except Exception as e:
        logger.warning("Failed to write cache file %s: %s", path, e)
