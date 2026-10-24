"""
src/drone/video_stream.py
Tello H.264 video stream decoder using OpenCV + FFmpeg backend.

The Tello sends raw H.264 over UDP to port 11111 after 'streamon' is issued.
OpenCV with the FFMPEG backend can open this directly as a UDP stream.

Architecture:
  - VideoStreamThread runs in a daemon thread
  - Emits frame_ready(np.ndarray) signal at ~30 fps
  - Caller connects frame_ready to the camera widget's update slot
"""

import threading
import time
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal


class VideoStreamThread(QObject):
    """
    Captures Tello H.264 UDP stream and emits decoded BGR frames.

    Signals:
        frame_ready(np.ndarray): emitted for each decoded frame (BGR, HxWx3)
        stream_started():        emitted when the capture opens successfully
        stream_stopped():        emitted when the stream is closed
        stream_error(str):       emitted on unrecoverable error
    """

    frame_ready    = Signal(object)   # np.ndarray  (BGR)
    stream_started = Signal()
    stream_stopped = Signal()
    stream_error   = Signal(str)

    # Tello video UDP URL for OpenCV/FFmpeg
    STREAM_URL = 'udp://0.0.0.0:11111?overrun_nonfatal=1&fifo_size=50000000'

    # How many consecutive read failures before giving up
    MAX_FAILURES = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

    # ── Public API ───────────────────────────────────────────────────

    def start(self):
        """Start the video capture thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name='tello-video',
        )
        self._thread.start()

    def stop(self):
        """Stop the video capture thread and release resources."""
        self._running = False
        # Give the thread a moment to exit cleanly
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._release_cap()
        self.stream_stopped.emit()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal ─────────────────────────────────────────────────────

    def _capture_loop(self):
        """Main capture loop — runs in daemon thread."""
        # Small delay to let the 'streamon' command propagate
        time.sleep(0.5)

        cap = cv2.VideoCapture(self.STREAM_URL, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            self.stream_error.emit(
                "Cannot open video stream. "
                "Ensure 'streamon' was sent and ffmpeg is installed."
            )
            self._running = False
            return

        self._cap = cap
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)   # minimize latency
        self.stream_started.emit()

        failures = 0
        while self._running:
            ret, frame = cap.read()
            if not ret or frame is None:
                failures += 1
                if failures >= self.MAX_FAILURES:
                    self.stream_error.emit("Video stream lost (too many read failures).")
                    break
                time.sleep(0.033)   # ~30 fps retry cadence
                continue

            failures = 0
            self.frame_ready.emit(frame)

        self._release_cap()
        self._running = False

    def _release_cap(self):
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
