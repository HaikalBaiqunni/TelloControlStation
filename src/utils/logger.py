"""
src/utils/logger.py
Simple flight logger — writes timestamped entries to both an in-memory
ring buffer (for the HUD log panel) and optionally a log file.
"""

import logging
import os
import threading
from collections import deque
from datetime import datetime
from typing import Callable, List, Optional


class FlightLogger:
    """
    Thread-safe flight event logger.

    Usage:
        logger = FlightLogger(max_entries=200)
        logger.info("Takeoff command sent")
        logger.warning("Battery below 20%")
        logger.error("Connection lost")

        for entry in logger.get_entries():
            print(entry)
    """

    LEVEL_OK   = 'ok'
    LEVEL_WARN = 'warn'
    LEVEL_ERR  = 'err'

    def __init__(self, max_entries: int = 300, log_file: Optional[str] = None):
        self._lock = threading.Lock()
        self._entries: deque = deque(maxlen=max_entries)
        self._callbacks: List[Callable] = []

        # Optional file logging
        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            logging.basicConfig(
                filename=log_file,
                level=logging.DEBUG,
                format='%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
        self._file_logger = logging.getLogger('tello_cs')

    # ── Public API ──────────────────────────────────────────────────────

    def info(self, msg: str):
        self._log(msg, self.LEVEL_OK)

    def warning(self, msg: str):
        self._log(msg, self.LEVEL_WARN)

    def error(self, msg: str):
        self._log(msg, self.LEVEL_ERR)

    def add_callback(self, fn: Callable):
        """Register a callback(timestamp, msg, level) called on each new entry."""
        with self._lock:
            self._callbacks.append(fn)

    def get_entries(self) -> List[dict]:
        """Return a snapshot list of {ts, msg, level} dicts (oldest first)."""
        with self._lock:
            return list(self._entries)

    def clear(self):
        with self._lock:
            self._entries.clear()

    # ── Internal ────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str):
        ts = datetime.now().strftime('%H:%M:%S')
        entry = {'ts': ts, 'msg': msg, 'level': level}

        with self._lock:
            self._entries.append(entry)
            callbacks = list(self._callbacks)

        # Fire callbacks outside the lock to avoid deadlocks
        for fn in callbacks:
            try:
                fn(ts, msg, level)
            except Exception:
                pass

        # Also log to file
        if level == self.LEVEL_OK:
            self._file_logger.info(msg)
        elif level == self.LEVEL_WARN:
            self._file_logger.warning(msg)
        else:
            self._file_logger.error(msg)
