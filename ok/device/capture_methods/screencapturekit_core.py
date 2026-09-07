"""Platform-neutral frame and geometry primitives for ScreenCaptureKit.

This module intentionally imports no PyObjC framework.  It owns the deterministic
parts of the macOS capture contract so they can be tested on every CI platform.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from ok.device.window_target.base import WindowCoordinateSpace, WindowGeometry

# Capture heartbeat, not image-content change. Shared by consumers and input.
MAX_FRAME_AGE_SECONDS = 2.0


@dataclass(frozen=True)
class PixelRect:
    """A rectangle in physical pixels inside a capture surface."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if min(self.x, self.y, self.width, self.height) < 0:
            raise ValueError("pixel rectangle values must be non-negative")


@dataclass(frozen=True)
class StreamFrameMetadata:
    """Small value-only subset of one ``SCStreamFrameInfo`` attachment."""

    complete: bool
    content_rect_points: WindowGeometry | None = None
    display_scale: float | None = None
    content_scale: float | None = None
    screen_rect_points: WindowGeometry | None = None
    global_content_geometry: WindowGeometry | None = None

    def __post_init__(self) -> None:
        for name in ("display_scale", "content_scale"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be finite and positive when known")
        for name in ("screen_rect_points", "global_content_geometry"):
            geometry = getattr(self, name)
            if (
                    geometry is not None
                    and geometry.coordinate_space is not
                    WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS):
                raise ValueError(
                    f"{name} must use macOS logical points when known")


@dataclass(frozen=True)
class CaptureGeometry:
    """Immutable mapping between a normalized frame and global macOS points."""

    target_generation: int
    capture_generation: int
    outer_geometry: WindowGeometry
    global_content_geometry: WindowGeometry
    raw_frame_width: int
    raw_frame_height: int
    content_rect_pixels: PixelRect
    frame_width: int
    frame_height: int
    display_scale: float
    content_scale: float | None = None

    def __post_init__(self) -> None:
        if self.target_generation < 0 or self.capture_generation < 0:
            raise ValueError("capture generations must be non-negative")
        if min(
                self.raw_frame_width,
                self.raw_frame_height,
                self.frame_width,
                self.frame_height) <= 0:
            raise ValueError("frame dimensions must be positive")
        if not math.isfinite(self.display_scale) or self.display_scale <= 0:
            raise ValueError("display_scale must be finite and positive")
        if self.content_scale is not None and (
                not math.isfinite(self.content_scale)
                or self.content_scale <= 0):
            raise ValueError("content_scale must be finite and positive when known")
        if (
                self.content_rect_pixels.x + self.content_rect_pixels.width
                > self.raw_frame_width
                or self.content_rect_pixels.y + self.content_rect_pixels.height
                > self.raw_frame_height):
            raise ValueError("content rectangle must fit inside the raw frame")
        if (
                self.content_rect_pixels.width != self.frame_width
                or self.content_rect_pixels.height != self.frame_height):
            raise ValueError("normalized frame dimensions must match the content rectangle")
        for name, geometry in (
                ("outer_geometry", self.outer_geometry),
                ("global_content_geometry", self.global_content_geometry)):
            if geometry.coordinate_space is not (
                    WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS):
                raise ValueError(f"{name} must use macOS logical points")
            if geometry.width <= 0 or geometry.height <= 0:
                raise ValueError(f"{name} dimensions must be positive")

    def frame_pixel_to_global_point(self, x: float, y: float) -> tuple[float, float]:
        """Map a normalized frame pixel coordinate to a global logical point."""
        if not all(math.isfinite(value) for value in (x, y)):
            raise ValueError("frame coordinates must be finite")
        if x < 0 or y < 0 or x > self.frame_width or y > self.frame_height:
            raise ValueError("frame coordinate is outside the normalized frame")
        content = self.global_content_geometry
        return (
            content.x + x * content.width / self.frame_width,
            content.y + y * content.height / self.frame_height,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "target_generation": self.target_generation,
            "capture_generation": self.capture_generation,
            "outer_geometry": self.outer_geometry.to_dict(),
            "global_content_geometry": self.global_content_geometry.to_dict(),
            "raw_frame_size": [self.raw_frame_width, self.raw_frame_height],
            "content_rect_pixels": {
                "x": self.content_rect_pixels.x,
                "y": self.content_rect_pixels.y,
                "width": self.content_rect_pixels.width,
                "height": self.content_rect_pixels.height,
            },
            "frame_size": [self.frame_width, self.frame_height],
            "display_scale": self.display_scale,
            "content_scale": self.content_scale,
        }


@dataclass(frozen=True)
class PublishedFrame:
    frame: "np.ndarray"
    geometry: CaptureGeometry
    sequence: int
    captured_monotonic: float


class LatestFrameSlot:
    """One-slot publication store; producer speed can never grow a queue."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latest: PublishedFrame | None = None
        self._last_read_sequence = 0
        self._published = 0
        self._overwritten = 0

    def publish(self, frame: PublishedFrame) -> None:
        with self._lock:
            if (
                    self._latest is not None
                    and self._latest.sequence > self._last_read_sequence):
                self._overwritten += 1
            self._latest = frame
            self._published += 1

    def read(
            self,
            *,
            target_generation: int,
            capture_generation: int) -> PublishedFrame | None:
        with self._lock:
            latest = self._latest
            if latest is None:
                return None
            geometry = latest.geometry
            if (
                    geometry.target_generation != target_generation
                    or geometry.capture_generation != capture_generation):
                self._latest = None
                return None
            self._last_read_sequence = latest.sequence
            return latest

    def clear(self) -> None:
        with self._lock:
            self._latest = None

    @property
    def published(self) -> int:
        with self._lock:
            return self._published

    @property
    def overwritten(self) -> int:
        with self._lock:
            return self._overwritten

    @property
    def storage_size(self) -> int:
        with self._lock:
            return int(self._latest is not None)


def content_rect_to_pixels(
        content_rect_points: WindowGeometry | None,
        display_scale: float,
        frame_width: int,
        frame_height: int) -> PixelRect:
    """Convert ScreenCaptureKit's surface-points content rect to pixels."""
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame dimensions must be positive")
    if not math.isfinite(display_scale) or display_scale <= 0:
        raise ValueError("display_scale must be finite and positive")
    if content_rect_points is None:
        return PixelRect(0, 0, frame_width, frame_height)

    left = max(0, math.floor(content_rect_points.x * display_scale))
    top = max(0, math.floor(content_rect_points.y * display_scale))
    right = min(
        frame_width,
        math.ceil((content_rect_points.x + content_rect_points.width) * display_scale),
    )
    bottom = min(
        frame_height,
        math.ceil((content_rect_points.y + content_rect_points.height) * display_scale),
    )
    if right <= left or bottom <= top:
        raise ValueError("ScreenCaptureKit content rectangle is empty or outside the frame")
    return PixelRect(left, top, right - left, bottom - top)


def bgra_to_owned_bgr(
        buffer,
        *,
        width: int,
        height: int,
        bytes_per_row: int,
        crop: PixelRect | None = None) -> "np.ndarray":
    """Normalize a possibly padded BGRA surface into owned contiguous BGR."""
    import numpy as np

    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    minimum_row_bytes = width * 4
    if bytes_per_row < minimum_row_bytes:
        raise ValueError("BGRA row stride is smaller than the pixel width")
    expected_size = bytes_per_row * height
    raw: np.ndarray = np.frombuffer(
        buffer, dtype=np.uint8, count=expected_size)
    if raw.size != expected_size:
        raise ValueError("BGRA buffer is shorter than its declared geometry")
    rows = raw.reshape(height, bytes_per_row)
    bgra = rows[:, :minimum_row_bytes].reshape(height, width, 4)
    region = crop or PixelRect(0, 0, width, height)
    if (
            region.x + region.width > width
            or region.y + region.height > height
            or region.width <= 0
            or region.height <= 0):
        raise ValueError("BGRA crop must be a non-empty rectangle inside the frame")
    # BGRA's first three channels are already BGR.  copy() detaches the result
    # from the IOSurface whose lifetime ends when the callback returns.
    return np.ascontiguousarray(
        bgra[
            region.y:region.y + region.height,
            region.x:region.x + region.width,
            :3,
        ]
    ).copy()
