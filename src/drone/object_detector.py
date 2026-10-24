"""
src/drone/object_detector.py
Real-Time AI Object & Human/Person Detector for Tello Control Station using YOLOv8 Nano.

Features:
  - Runs inference asynchronously in a background daemon thread
  - Single-frame buffer to ensure zero latency / zero lag on video stream
  - Distinguishes Persons ([ TGT // PERSON ]) from Objects ([ OBJ // <LABEL> ])
  - Emits Qt signal with normalized bounding boxes and confidence scores
  - Toggleable ON/OFF at runtime
"""

import threading
import time
from typing import List, Dict, Any, Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


class ObjectDetector(QObject):
    """
    Asynchronous YOLOv8 detector worker.
    """

    detections_ready = Signal(list)   # List[Dict[str, Any]]
    model_loaded     = Signal(bool)

    def __init__(self, model_path: str = "yolov8n.pt", parent=None):
        super().__init__(parent)
        self._model_path = model_path
        self._model = None
        self._enabled = True

        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="yolo-detector")
        self._thread.start()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            # Clear detections immediately
            self.detections_ready.emit([])

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def push_frame(self, frame: np.ndarray):
        """Called by video stream whenever a new camera frame arrives."""
        if not self._enabled or self._model is None:
            return
        with self._frame_lock:
            # Keep only the newest frame
            self._latest_frame = frame

    def _worker_loop(self):
        # 1. Load YOLO model
        try:
            from ultralytics import YOLO
            self._model = YOLO(self._model_path)
            self.model_loaded.emit(True)
        except Exception as e:
            print(f"[Detector] Failed to load YOLO model: {e}")
            self.model_loaded.emit(False)
            return

        # 2. Continuous detection loop (~12-15 FPS cadence)
        while self._running:
            if not self._enabled:
                time.sleep(0.08)
                continue

            frame_to_process = None
            with self._frame_lock:
                if self._latest_frame is not None:
                    frame_to_process = self._latest_frame
                    self._latest_frame = None

            if frame_to_process is None:
                time.sleep(0.03)
                continue

            # Run inference
            try:
                # Resize input slightly to 480 for fast inference
                h, w = frame_to_process.shape[:2]
                results = self._model(frame_to_process, imgsz=480, conf=0.35, verbose=False)

                detections = []
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        coords = box.xyxy[0].cpu().numpy()  # x1, y1, x2, y2
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        cls_name = r.names.get(cls_id, str(cls_id))

                        is_person = (cls_name.lower() == "person")

                        # Normalize coordinates [0.0 .. 1.0] relative to frame size
                        x1 = coords[0] / w
                        y1 = coords[1] / h
                        x2 = coords[2] / w
                        y2 = coords[3] / h

                        detections.append({
                            "box_norm": (x1, y1, x2, y2),
                            "label": cls_name.upper(),
                            "conf": conf,
                            "is_person": is_person,
                        })

                self.detections_ready.emit(detections)

            except Exception as e:
                pass

            # Yield briefly to maintain CPU efficiency
            time.sleep(0.05)

    def stop(self):
        self._running = False
