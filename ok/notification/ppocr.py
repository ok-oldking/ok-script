import threading

import numpy as np


class NotificationPPOCR:
    """Small task-independent adapter around the app's shared PP-OCR instance."""

    def __init__(self, instance_factory):
        self._instance_factory = instance_factory
        self._instance = None
        self._instance_lock = threading.Lock()

    def recognize(self, frame, threshold=.1):
        result = self._get_instance().ocr(frame)
        detections = result[0] if result else []
        boxes = []
        for detection in detections or []:
            if not detection or len(detection) < 2:
                continue
            points, recognition = detection[0], detection[1]
            if not recognition or len(recognition) < 2:
                continue
            text, confidence = recognition[0], float(recognition[1])
            if confidence < threshold:
                continue
            coordinates = np.asarray(points, dtype=float).reshape(-1, 2)
            if coordinates.size == 0:
                continue
            left = int(round(coordinates[:, 0].min()))
            top = int(round(coordinates[:, 1].min()))
            right = int(round(coordinates[:, 0].max()))
            bottom = int(round(coordinates[:, 1].max()))
            boxes.append((
                str(text), left, top,
                max(1, right - left), max(1, bottom - top),
            ))
        return boxes

    def _get_instance(self):
        if self._instance is None:
            with self._instance_lock:
                if self._instance is None:
                    self._instance = self._instance_factory()
                    # Release the bound TaskExecutor method. From this point
                    # onward the notification pipeline only retains PP-OCR.
                    self._instance_factory = None
        return self._instance
