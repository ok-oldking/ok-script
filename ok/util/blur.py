import queue
import threading
import time

import cv2
import numpy as np

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

BLUR_ALGORITHM = 'Blur'
INPAINT_ALGORITHM = 'Inpaint'
DEFAULT_BLUR_ALGORITHM = INPAINT_ALGORITHM
INPAINT_RADIUS = 5


def get_blur_rects(blur_area, width, height):
    """Resolve and clamp configured blur boxes to the current frame."""
    if not callable(blur_area) or width <= 0 or height <= 0:
        return []
    try:
        boxes = blur_area(width, height)
    except Exception as e:
        logger.warning(f'blur_area failed: {e}')
        return []
    if boxes is None:
        return []
    if not isinstance(boxes, (list, tuple)):
        boxes = [boxes]

    rects = []
    for box in boxes:
        if not all(hasattr(box, name) for name in ('x', 'y', 'width', 'height')):
            logger.warning(f'ignore invalid blur box: {box}')
            continue
        x1 = max(0, min(width, int(box.x)))
        y1 = max(0, min(height, int(box.y)))
        x2 = max(0, min(width, int(box.x + box.width)))
        y2 = max(0, min(height, int(box.y + box.height)))
        if x2 > x1 and y2 > y1:
            rects.append((x1, y1, x2 - x1, y2 - y1))
    return rects


def blur_region(region):
    """Blur a region heavily enough that small static text is unreadable."""
    height, width = region.shape[:2]
    reduced = cv2.resize(region, (min(width, 8), min(height, 8)), interpolation=cv2.INTER_AREA)
    obscured = cv2.resize(reduced, (width, height), interpolation=cv2.INTER_LINEAR)
    sigma = max(4.0, min(width, height) / 5.0)
    return cv2.GaussianBlur(obscured, (0, 0), sigmaX=sigma, sigmaY=sigma)


def inpaint_region(frame, x, y, width, height):
    """Reconstruct a selected region from nearby pixels using OpenCV inpainting."""
    padding = INPAINT_RADIUS * 2
    frame_height, frame_width = frame.shape[:2]
    left = max(0, x - padding)
    top = max(0, y - padding)
    right = min(frame_width, x + width + padding)
    bottom = min(frame_height, y + height + padding)
    source = frame[top:bottom, left:right]
    mask = np.zeros(source.shape[:2], dtype=np.uint8)
    mask[y - top:y - top + height, x - left:x - left + width] = 255
    restored = cv2.inpaint(source, mask, INPAINT_RADIUS, cv2.INPAINT_TELEA)
    return restored[y - top:y - top + height, x - left:x - left + width]


def make_blur_patches(frame, blur_area, algorithm=DEFAULT_BLUR_ALGORITHM):
    if frame is None:
        return []
    height, width = frame.shape[:2]
    patches = []
    for x, y, w, h in get_blur_rects(blur_area, width, height):
        if algorithm == INPAINT_ALGORITHM:
            patch = inpaint_region(frame, x, y, w, h)
        else:
            patch = blur_region(frame[y:y + h, x:x + w])
        patches.append((x, y, w, h, patch))
    return patches


def apply_blur_areas(frame, blur_area, algorithm=DEFAULT_BLUR_ALGORITHM):
    """Return a frame with configured areas obscured; leave the input untouched."""
    patches = make_blur_patches(frame, blur_area, algorithm)
    if not patches:
        return frame
    result = frame.copy()
    for x, y, w, h, patch in patches:
        result[y:y + h, x:x + w] = patch
    return result


def get_blur_algorithm(global_config):
    if global_config is None:
        return DEFAULT_BLUR_ALGORITHM
    try:
        return global_config.get_config('Basic Options').get('Blur Algorithm', DEFAULT_BLUR_ALGORITHM)
    except RuntimeError:
        return DEFAULT_BLUR_ALGORITHM


def patches_changed(previous, current):
    if previous is None or len(previous) != len(current):
        return True
    for old, new in zip(previous, current):
        if old[:4] != new[:4] or old[4].shape != new[4].shape:
            return True
        difference = cv2.absdiff(old[4], new[4])
        changed_pixels = (difference > 8 if len(difference.shape) == 2
                          else np.mean(difference, axis=2) > 8)
        if float(np.mean(difference)) > 3.0 or float(np.mean(changed_pixels)) > 0.1:
            return True
    return False


class BlurOverlayProcessor:
    """Generate foreground overlay patches off the task thread at a configured rate."""

    def __init__(self, blur_area, enabled, emit_patches, clear_patches, exit_event,
                 algorithm=None, interval=None):
        self.blur_area = blur_area
        self.enabled = enabled
        self.visible = False
        self.emit_patches = emit_patches
        self.clear_patches = clear_patches
        self.exit_event = exit_event
        self.algorithm = algorithm or (lambda: DEFAULT_BLUR_ALGORITHM)
        self.interval = interval or (lambda: 1)
        self.last_submitted = 0
        self.last_patches = None
        self.overlay_active = False
        self.queue = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self._worker, name='BlurOverlay', daemon=True)
        self.thread.start()

    def next_frame(self, frame):
        if not self.enabled() or not self.visible:
            self._clear_overlay()
            return
        now = time.monotonic()
        if now - self.last_submitted < max(0.0, float(self.interval())):
            return
        self.last_submitted = now
        try:
            self.queue.put_nowait(frame)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(frame)
            except queue.Full:
                pass

    def set_visible(self, visible, *args):
        visible = bool(visible)
        if self.visible == visible:
            return
        self.visible = visible
        self._clear_overlay()

    def _clear_overlay(self):
        if self.overlay_active:
            self.clear_patches()
        self.overlay_active = False
        self.last_patches = None
        self.last_submitted = 0

    def _active(self):
        return self.enabled() and self.visible

    def _worker(self):
        while not self.exit_event.is_set():
            try:
                frame = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if not self._active():
                    self._clear_overlay()
                    continue
                patches = make_blur_patches(frame, self.blur_area, self.algorithm())
                if not patches:
                    self._clear_overlay()
                elif patches_changed(self.last_patches, patches):
                    if not self._active():
                        self._clear_overlay()
                        continue
                    self.emit_patches(patches)
                    self.last_patches = patches
                    self.overlay_active = True
            except Exception as e:
                logger.warning(f'blur overlay processing failed: {e}')
            finally:
                self.queue.task_done()
