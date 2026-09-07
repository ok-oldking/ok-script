"""Persistent ScreenCaptureKit selected-window capture for macOS."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math
import threading
import time
from typing import Callable, Protocol

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.capture_methods.screencapturekit_core import (
    CaptureGeometry,
    MAX_FRAME_AGE_SECONDS,
    LatestFrameSlot,
    PublishedFrame,
    StreamFrameMetadata,
    bgra_to_owned_bgr,
    content_rect_to_pixels,
)
from ok.device.services import PermissionKind
from ok.device.window_target.base import (
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowTargetSnapshot,
)
from ok.platform import require_macos_foreground_host
from ok.util.logger import Logger


logger = Logger.get_logger(__name__)
_PYOBJC_OUTPUT_CLASS = None
_PYOBJC_DELEGATE_CLASS = None


class CaptureStreamState(str, Enum):
    INITIAL = "initial"
    STARTING = "starting"
    RUNNING = "running"
    TARGET_UNAVAILABLE = "target-unavailable"
    PERMISSION_REQUIRED = "permission-required"
    PERMISSION_REVOKED = "permission-revoked"
    FATAL = "fatal"
    CLOSED = "closed"


class ScreenCaptureKitCaptureError(RuntimeError):
    pass


class _WindowGeometryPending(ScreenCaptureKitCaptureError):
    """Public window metadata disagrees before any native stream is created."""


class _StreamShutdownPending(ScreenCaptureKitCaptureError):
    """Keep a failed-start binding reachable until native shutdown is confirmed."""

    def __init__(self, detail: str, binding):
        super().__init__(detail)
        self.binding = binding


@dataclass(frozen=True)
class CaptureDiagnostics:
    state: CaptureStreamState
    target_generation: int
    capture_generation: int
    frames_received: int
    frames_published: int
    frames_overwritten: int
    frames_dropped_incomplete: int
    frames_dropped_stale: int
    frame_conversion_errors: int
    geometry_invalidations: int
    rebuilds: int
    fps: float
    frame_age_seconds: float | None
    storage_size: int
    geometry: CaptureGeometry | None
    last_error: str | None
    frame_sequence: int | None = None
    captured_monotonic: float | None = None
    frame_geometry: CaptureGeometry | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "target_generation": self.target_generation,
            "capture_generation": self.capture_generation,
            "frames_received": self.frames_received,
            "frames_published": self.frames_published,
            "frames_overwritten": self.frames_overwritten,
            "frames_dropped_incomplete": self.frames_dropped_incomplete,
            "frames_dropped_stale": self.frames_dropped_stale,
            "frame_conversion_errors": self.frame_conversion_errors,
            "geometry_invalidations": self.geometry_invalidations,
            "rebuilds": self.rebuilds,
            "fps": self.fps,
            "frame_age_seconds": self.frame_age_seconds,
            "frame_sequence": self.frame_sequence,
            "captured_monotonic": self.captured_monotonic,
            "storage_size": self.storage_size,
            "geometry": self.geometry.to_dict() if self.geometry else None,
            "last_error": self.last_error,
        }


class ScreenCaptureKitBackend(Protocol):
    def start_stream(
            self,
            target_snapshot: WindowTargetSnapshot,
            on_sample: Callable[[object, int, int, int, StreamFrameMetadata], None],
            on_stopped: Callable[[str], None],
            on_sample_error: Callable[[str], None],
            *,
            frames_per_second: int,
            timeout: float): ...

    def stop_stream(self, binding, *, timeout: float) -> None: ...


@dataclass
class _PyObjCStreamBinding:
    stream: object
    output: object
    delegate: object
    queue: object
    output_removed: bool = False
    stop_confirmed: bool = False
    drained: bool = False


def _objc_value(instance, name: str):
    value = getattr(instance, name)
    return value() if callable(value) else value


def _error_description(error) -> str:
    if error is None:
        return ""
    try:
        return str(_objc_value(error, "localizedDescription"))
    except AttributeError:
        return str(error)


def _rect_components(rect) -> tuple[float, float, float, float]:
    if hasattr(rect, "CGRectValue"):
        rect = rect.CGRectValue()
    try:
        return (
            float(rect.origin.x),
            float(rect.origin.y),
            float(rect.size.width),
            float(rect.size.height),
        )
    except AttributeError:
        pass

    # On current PyObjC, SCStreamFrameInfoContentRect may bridge as the
    # dictionary representation produced by CGRectCreateDictionaryRepresentation
    # instead of as a CGRect/NSValue.  NSDictionary supports ``get`` here.
    getter = getattr(rect, "get", None)
    if callable(getter):
        values = tuple(getter(key) for key in ("X", "Y", "Width", "Height"))
        if all(value is not None for value in values):
            x, y, width, height = values
            return float(x), float(y), float(width), float(height)

    try:
        (x, y), (width, height) = rect
    except (TypeError, ValueError):
        try:
            x, y, width, height = rect
        except (TypeError, ValueError) as error:
            raise ScreenCaptureKitCaptureError(
                f"unsupported ScreenCaptureKit rectangle {rect!r}") from error
    return float(x), float(y), float(width), float(height)


def _surface_rect(rect) -> WindowGeometry:
    x, y, width, height = _rect_components(rect)
    return WindowGeometry(x, y, width, height, WindowCoordinateSpace.UNKNOWN)


def _request_automatic_capture_resolution(configuration, screen_capture_kit) -> bool:
    """Keep explicit output dimensions authoritative for HiDPI window capture."""
    setter = getattr(configuration, "setCaptureResolution_", None)
    automatic = getattr(screen_capture_kit, "SCCaptureResolutionAutomatic", None)
    if callable(setter) and automatic is not None:
        setter(automatic)
        return True
    return False


def _with_locked_bgra_pixel_buffer(quartz, pixel_buffer, consumer):
    """Expose a bounded BGRA view only for the duration of ``consumer``."""
    if quartz.CVPixelBufferIsPlanar(pixel_buffer):
        raise ScreenCaptureKitCaptureError(
            "ScreenCaptureKit returned an unexpected planar pixel buffer")
    pixel_format = quartz.CVPixelBufferGetPixelFormatType(pixel_buffer)
    if pixel_format != quartz.kCVPixelFormatType_32BGRA:
        raise ScreenCaptureKitCaptureError(
            f"ScreenCaptureKit returned pixel format {pixel_format}, expected BGRA")
    lock_flags = quartz.kCVPixelBufferLock_ReadOnly
    lock_status = quartz.CVPixelBufferLockBaseAddress(pixel_buffer, lock_flags)
    if lock_status != 0:
        raise ScreenCaptureKitCaptureError(
            f"CVPixelBufferLockBaseAddress failed with {lock_status}")
    try:
        width = int(quartz.CVPixelBufferGetWidth(pixel_buffer))
        height = int(quartz.CVPixelBufferGetHeight(pixel_buffer))
        bytes_per_row = int(quartz.CVPixelBufferGetBytesPerRow(pixel_buffer))
        if width <= 0 or height <= 0 or bytes_per_row < width * 4:
            raise ScreenCaptureKitCaptureError(
                "CVPixelBuffer returned invalid dimensions or row stride")
        base_address = quartz.CVPixelBufferGetBaseAddress(pixel_buffer)
        if base_address is None:
            raise ScreenCaptureKitCaptureError(
                "CVPixelBuffer returned a null base address")
        view = base_address.as_buffer(bytes_per_row * height)
        return consumer(view, width, height, bytes_per_row)
    finally:
        quartz.CVPixelBufferUnlockBaseAddress(pixel_buffer, lock_flags)


class PyObjCScreenCaptureKitBackend:
    """Thin public-API PyObjC adapter; imported only on Darwin."""

    def __init__(self):
        require_macos_foreground_host("ScreenCaptureKit capture")
        import AppKit
        import ApplicationServices
        import CoreMedia
        import Foundation
        import Quartz
        import ScreenCaptureKit
        import dispatch
        import objc

        self._appkit = AppKit
        self._application_services = ApplicationServices
        self._core_media = CoreMedia
        self._foundation = Foundation
        self._quartz = Quartz
        self._screen_capture_kit = ScreenCaptureKit
        self._dispatch = dispatch
        self._objc = objc
        self._output_class = self._make_output_class()
        self._delegate_class = self._make_delegate_class()

    def _make_output_class(self):
        global _PYOBJC_OUTPUT_CLASS
        if _PYOBJC_OUTPUT_CLASS is not None:
            return _PYOBJC_OUTPUT_CLASS
        foundation = self._foundation
        objc = self._objc

        class OKScreenCaptureKitStreamOutput(
                foundation.NSObject,
                protocols=[objc.protocolNamed("SCStreamOutput")]):
            def initWithBackend_callbacks_(self, backend, callbacks):
                self = objc.super(OKScreenCaptureKitStreamOutput, self).init()
                if self is not None:
                    self._backend = backend
                    self._callbacks = callbacks
                return self

            def stream_didOutputSampleBuffer_ofType_(self, _stream, sample_buffer, output_type):
                callbacks = self._callbacks
                if callbacks is None:
                    return
                (
                    on_sample,
                    on_sample_error,
                    source_rect,
                    configured_global_content,
                ) = callbacks
                try:
                    with self._backend._objc.autorelease_pool():
                        self._deliver(
                            sample_buffer,
                            output_type,
                            on_sample,
                            source_rect,
                            configured_global_content,
                        )
                except Exception as error:
                    on_sample_error(f"ScreenCaptureKit sample conversion failed: {error}")

            @objc.python_method
            def _deliver(
                    self,
                    sample_buffer,
                    output_type,
                    on_sample,
                    source_rect,
                    configured_global_content):
                owner = self._backend
                screen_capture_kit = owner._screen_capture_kit
                core_media = owner._core_media
                quartz = owner._quartz
                if output_type != screen_capture_kit.SCStreamOutputTypeScreen:
                    return
                if (
                        not core_media.CMSampleBufferIsValid(sample_buffer)
                        or not core_media.CMSampleBufferDataIsReady(sample_buffer)):
                    on_sample(None, 0, 0, 0, StreamFrameMetadata(False))
                    return
                attachments = core_media.CMSampleBufferGetSampleAttachmentsArray(
                    sample_buffer, False) or ()
                frame_info = attachments[0] if attachments else {}
                status = frame_info.get(screen_capture_kit.SCStreamFrameInfoStatus)
                complete = (
                    status is not None
                    and int(status) == int(screen_capture_kit.SCFrameStatusComplete)
                )
                content_rect = frame_info.get(
                    screen_capture_kit.SCStreamFrameInfoContentRect)
                scale_factor = frame_info.get(
                    screen_capture_kit.SCStreamFrameInfoScaleFactor)
                content_scale = frame_info.get(
                    screen_capture_kit.SCStreamFrameInfoContentScale)
                screen_rect_key = getattr(
                    screen_capture_kit, "SCStreamFrameInfoScreenRect", None)
                screen_rect_value = (
                    frame_info.get(screen_rect_key)
                    if screen_rect_key is not None else None)
                screen_rect = None
                global_content_geometry = configured_global_content
                if screen_rect_value is not None:
                    raw_screen_rect = _surface_rect(screen_rect_value)
                    screen_rect = WindowGeometry(
                        raw_screen_rect.x,
                        raw_screen_rect.y,
                        raw_screen_rect.width,
                        raw_screen_rect.height,
                        WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS,
                    )
                    global_content_geometry = WindowGeometry(
                        screen_rect.x + source_rect.x,
                        screen_rect.y + source_rect.y,
                        source_rect.width,
                        source_rect.height,
                        WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS,
                    )
                metadata = StreamFrameMetadata(
                    complete=complete,
                    content_rect_points=(
                        _surface_rect(content_rect) if content_rect is not None else None),
                    display_scale=(
                        float(scale_factor) if scale_factor is not None else None),
                    content_scale=(
                        float(content_scale) if content_scale is not None else None),
                    screen_rect_points=screen_rect,
                    global_content_geometry=global_content_geometry,
                )
                if not complete:
                    on_sample(None, 0, 0, 0, metadata)
                    return
                pixel_buffer = core_media.CMSampleBufferGetImageBuffer(sample_buffer)
                if pixel_buffer is None:
                    raise ScreenCaptureKitCaptureError(
                        "complete sample has no CVPixelBuffer")
                _with_locked_bgra_pixel_buffer(
                    quartz,
                    pixel_buffer,
                    lambda view, width, height, bytes_per_row: on_sample(
                        view, width, height, bytes_per_row, metadata),
                )

        _PYOBJC_OUTPUT_CLASS = OKScreenCaptureKitStreamOutput
        return _PYOBJC_OUTPUT_CLASS

    def _make_delegate_class(self):
        global _PYOBJC_DELEGATE_CLASS
        if _PYOBJC_DELEGATE_CLASS is not None:
            return _PYOBJC_DELEGATE_CLASS
        foundation = self._foundation
        objc = self._objc

        class OKScreenCaptureKitStreamDelegate(
                foundation.NSObject,
                protocols=[objc.protocolNamed("SCStreamDelegate")]):
            def initWithCallback_(self, callback):
                self = objc.super(OKScreenCaptureKitStreamDelegate, self).init()
                if self is not None:
                    self._callback = callback
                return self

            def stream_didStopWithError_(self, _stream, error):
                callback = self._callback
                if callback is not None:
                    callback(_error_description(error))

        _PYOBJC_DELEGATE_CLASS = OKScreenCaptureKitStreamDelegate
        return _PYOBJC_DELEGATE_CLASS

    def _shareable_content(self, timeout: float):
        completed = threading.Event()
        result: dict[str, object] = {}

        def completion(content, error):
            result["content"] = content
            result["error"] = error
            completed.set()

        self._screen_capture_kit.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            True, True, completion)
        if not completed.wait(timeout):
            raise ScreenCaptureKitCaptureError(
                f"ScreenCaptureKit source resolution timed out after {timeout:.1f}s")
        error = result.get("error")
        if error is not None:
            raise ScreenCaptureKitCaptureError(
                f"ScreenCaptureKit source resolution failed: {_error_description(error)}")
        content = result.get("content")
        if content is None:
            raise ScreenCaptureKitCaptureError(
                "ScreenCaptureKit returned no shareable content")
        return content

    @staticmethod
    def _intersection_area(first, second) -> float:
        fx, fy, fw, fh = _rect_components(first)
        sx, sy, sw, sh = _rect_components(second)
        width = max(0.0, min(fx + fw, sx + sw) - max(fx, sx))
        height = max(0.0, min(fy + fh, sy + sh) - max(fy, sy))
        return width * height

    def _display_scale(self, content, window) -> float:
        window_frame = _objc_value(window, "frame")
        selected = None
        selected_area = 0.0
        for display in _objc_value(content, "displays"):
            display_frame = _objc_value(display, "frame")
            area = self._intersection_area(window_frame, display_frame)
            if area > selected_area:
                selected = display
                selected_area = area
        if selected is None:
            raise ScreenCaptureKitCaptureError(
                "could not determine the display containing the selected window")
        display_id = int(_objc_value(selected, "displayID") or 0)
        for screen in self._appkit.NSScreen.screens():
            description = _objc_value(screen, "deviceDescription") or {}
            screen_number = description.get("NSScreenNumber")
            if screen_number is None or int(screen_number) != display_id:
                continue
            scale = float(_objc_value(screen, "backingScaleFactor"))
            if not math.isfinite(scale) or scale <= 0:
                raise ScreenCaptureKitCaptureError(
                    "selected display returned an invalid backing scale factor")
            return scale
        raise ScreenCaptureKitCaptureError(
            "could not resolve the selected ScreenCaptureKit display to NSScreen")

    def _ax_attribute(self, element, name: str):
        error, value = self._application_services.AXUIElementCopyAttributeValue(
            element, name, None)
        return value if int(error) == 0 else None

    def _ax_window_frame(self, element) -> WindowGeometry | None:
        application_services = self._application_services
        position = self._ax_attribute(element, "AXPosition")
        size = self._ax_attribute(element, "AXSize")
        if position is None or size is None:
            return None
        if (
                application_services.AXValueGetType(position)
                != application_services.kAXValueCGPointType
                or application_services.AXValueGetType(size)
                != application_services.kAXValueCGSizeType):
            return None
        position_ok, point = application_services.AXValueGetValue(
            position, application_services.kAXValueCGPointType, None)
        size_ok, dimensions = application_services.AXValueGetValue(
            size, application_services.kAXValueCGSizeType, None)
        if not position_ok or not size_ok:
            return None
        return WindowGeometry(
            float(point.x),
            float(point.y),
            float(dimensions.width),
            float(dimensions.height),
        )

    @staticmethod
    def _same_rect(first: WindowGeometry, second: WindowGeometry) -> bool:
        return all(abs(left - right) <= 0.5 for left, right in (
            (first.x, second.x),
            (first.y, second.y),
            (first.width, second.width),
            (first.height, second.height),
        ))

    def _matching_ax_window(self, candidate: WindowCandidate, outer: WindowGeometry):
        """Match the same standard window for capture and explicit preparation."""
        if not self._same_rect(outer, candidate.outer_geometry):
            raise _WindowGeometryPending(
                "macOS window geometry changed before capture stream creation")
        application_services = self._application_services
        application = application_services.AXUIElementCreateApplication(
            candidate.process_id)
        windows = self._ax_attribute(application, "AXWindows") or ()
        matching = []
        moving = []
        same_title = []
        for window in windows:
            title = str(self._ax_attribute(window, "AXTitle") or "").strip()
            if title and title == candidate.title.strip():
                same_title.append(window)
            frame = self._ax_window_frame(window)
            if frame is None:
                continue
            if candidate.title and title and title != candidate.title.strip():
                continue
            if not self._same_rect(frame, outer):
                if (
                        title and title == candidate.title.strip()
                        and self._ax_attribute(window, "AXSubrole") == "AXStandardWindow"
                        and self._ax_attribute(window, "AXTitleUIElement") is not None):
                    moving.append(window)
                continue
            matching.append(window)
        if not matching and len(moving) == 1 and len(same_title) == 1:
            raise _WindowGeometryPending(
                "ScreenCaptureKit and Accessibility window geometry have not settled")
        if len(matching) != 1:
            raise ScreenCaptureKitCaptureError(
                "Accessibility permission and one matching AXWindow are required "
                "for content-only capture")

        ax_window = matching[0]
        subrole = str(self._ax_attribute(ax_window, "AXSubrole") or "")
        if subrole != "AXStandardWindow":
            raise ScreenCaptureKitCaptureError(
                f"unsupported macOS window subrole for content-only capture: "
                f"{subrole or 'unknown'}")
        if self._ax_attribute(ax_window, "AXTitleUIElement") is None:
            raise ScreenCaptureKitCaptureError(
                "unsupported macOS window without a verifiable standard title bar")
        return ax_window

    def _content_region(
            self,
            candidate: WindowCandidate,
            selected_window) -> tuple[WindowGeometry, WindowGeometry]:
        """Return stream-local source points and global logical content points."""
        outer = _surface_rect(_objc_value(selected_window, "frame"))
        self._matching_ax_window(candidate, outer)
        content = self._appkit.NSWindow.contentRectForFrameRect_styleMask_(
            self._appkit.NSMakeRect(0, 0, outer.width, outer.height),
            self._appkit.NSWindowStyleMaskTitled,
        )
        content_x, content_y, content_width, content_height = _rect_components(
            content)
        top_inset = outer.height - content_y - content_height
        local = WindowGeometry(
            content_x,
            top_inset,
            content_width,
            content_height,
        )
        if local.width <= 0 or local.height <= 0:
            raise ScreenCaptureKitCaptureError(
                "macOS window returned an invalid content rectangle")
        global_content = WindowGeometry(
            outer.x + local.x,
            outer.y + local.y,
            local.width,
            local.height,
            WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS,
        )
        return local, global_content

    def request_content_size(
            self, target, width: int, height: int, *, timeout: float,
            is_stopping: Callable[[], bool]):
        """One public AXSize request; caller must close capture/input first.

        This is a request, not capture-size evidence. A new stream must verify it.
        No activation, position change, system display change or retry is issued.
        """
        if not target.is_foreground():
            raise ScreenCaptureKitCaptureError("window preparation requires the target foreground")
        snapshot = target.snapshot
        candidate = snapshot.candidate
        if candidate is None or not snapshot.exists:
            raise ScreenCaptureKitCaptureError("window preparation target disappeared")
        content = self._shareable_content(timeout)
        selected = []
        for window in _objc_value(content, "windows"):
            application = _objc_value(window, "owningApplication")
            if (application is not None
                    and int(_objc_value(window, "windowID")) == candidate.window_id
                    and int(_objc_value(application, "processID")) == candidate.process_id):
                selected.append(window)
        if len(selected) != 1:
            raise ScreenCaptureKitCaptureError("window preparation requires the same unique window")
        window = selected[0]
        local, _ = self._content_region(candidate, window)
        outer = _surface_rect(_objc_value(window, "frame"))
        scale = self._display_scale(content, window)
        requested_width = width / scale + outer.width - local.width
        requested_height = height / scale + outer.height - local.height
        if not all(math.isfinite(v) and v > 0 for v in (requested_width, requested_height)):
            raise ScreenCaptureKitCaptureError("invalid requested logical window size")
        ax_window = self._matching_ax_window(candidate, outer)
        if (self._ax_attribute(ax_window, "AXFullScreen")
                or self._ax_attribute(ax_window, "AXMinimized")):
            raise ScreenCaptureKitCaptureError("window preparation requires windowed, non-minimized mode")
        services = self._application_services
        error, settable = services.AXUIElementIsAttributeSettable(ax_window, "AXSize", None)
        if int(error) != 0 or not settable:
            raise ScreenCaptureKitCaptureError("selected window does not expose a writable AXSize")
        value = services.AXValueCreate(
            services.kAXValueCGSizeType,
            self._quartz.CGSizeMake(requested_width, requested_height))
        if value is None:
            raise ScreenCaptureKitCaptureError("could not construct AXSize value")
        # Recheck after the native discovery/AX calls. Never activate to rescue
        # a lost-focus request and never write to a rebound/stale AX window.
        if (not services.AXIsProcessTrusted()
                or not self._quartz.CGPreflightScreenCaptureAccess()
                or is_stopping()
                or self._display_scale(content, window) != scale
                or self._matching_ax_window(candidate, outer) != ax_window
                or not target.is_foreground()
                or target.snapshot != snapshot):
            raise ScreenCaptureKitCaptureError("window preparation target, geometry or permission changed")
        error = services.AXUIElementSetAttributeValue(ax_window, "AXSize", value)
        if int(error) != 0:
            raise ScreenCaptureKitCaptureError(f"AXSize request rejected: {int(error)}")
        return {
            "requested_frame_size": [width, height],
            "requested_outer_size": [requested_width, requested_height],
            "display_scale": scale,
            "original_outer_geometry": candidate.outer_geometry.to_dict(),
            "window_id": candidate.window_id,
            "process_id": candidate.process_id,
        }

    def start_stream(
            self,
            target_snapshot: WindowTargetSnapshot,
            on_sample,
            on_stopped,
            on_sample_error,
            *,
            frames_per_second: int,
            timeout: float):
        candidate = target_snapshot.candidate
        if candidate is None or not target_snapshot.exists:
            raise ScreenCaptureKitCaptureError("macOS window target is unavailable")
        content = self._shareable_content(timeout)
        selected_window = None
        for window in _objc_value(content, "windows"):
            application = _objc_value(window, "owningApplication")
            if application is None:
                continue
            if (
                    int(_objc_value(window, "windowID") or 0) == candidate.window_id
                    and int(_objc_value(application, "processID") or 0)
                    == candidate.process_id):
                selected_window = window
                break
        if selected_window is None:
            raise ScreenCaptureKitCaptureError(
                "selected macOS window disappeared before capture stream creation")

        screen_capture_kit = self._screen_capture_kit
        configuration = screen_capture_kit.SCStreamConfiguration.alloc().init()
        scale = self._display_scale(content, selected_window)
        source_rect, global_content_geometry = self._content_region(
            candidate, selected_window)
        output_width = max(1, round(source_rect.width * scale))
        output_height = max(1, round(source_rect.height * scale))
        configuration.setWidth_(output_width)
        configuration.setHeight_(output_height)
        configuration.setSourceRect_(self._quartz.CGRectMake(
            source_rect.x,
            source_rect.y,
            source_rect.width,
            source_rect.height,
        ))
        if hasattr(configuration, "setDestinationRect_"):
            configuration.setDestinationRect_(
                self._quartz.CGRectMake(0, 0, output_width, output_height))
        configuration.setPixelFormat_(self._quartz.kCVPixelFormatType_32BGRA)
        configuration.setMinimumFrameInterval_(
            self._core_media.CMTimeMake(1, frames_per_second))
        configuration.setQueueDepth_(3)
        configuration.setShowsCursor_(False)
        # ``Best`` returns the nominal 1x content buffer for the official
        # client's HiDPI window on current macOS. ``Automatic`` honors the
        # explicitly configured 2x output surface (1920x1080 for 960x540
        # logical content) while remaining available on older runtimes.
        _request_automatic_capture_resolution(configuration, screen_capture_kit)
        if hasattr(configuration, "setCapturesAudio_"):
            configuration.setCapturesAudio_(False)
        if hasattr(configuration, "setScalesToFit_"):
            configuration.setScalesToFit_(True)
        if hasattr(configuration, "setIgnoreShadowsSingleWindow_"):
            configuration.setIgnoreShadowsSingleWindow_(True)

        content_filter = screen_capture_kit.SCContentFilter.alloc().initWithDesktopIndependentWindow_(
            selected_window)
        delegate = self._delegate_class.alloc().initWithCallback_(on_stopped)
        output = self._output_class.alloc().initWithBackend_callbacks_(
            self, (
                on_sample,
                on_sample_error,
                source_rect,
                global_content_geometry,
            ))
        stream = screen_capture_kit.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, configuration, delegate)
        queue = self._dispatch.dispatch_queue_create(
            b"com.ok-script.screencapturekit.frames", None)
        added, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            output,
            screen_capture_kit.SCStreamOutputTypeScreen,
            queue,
            None,
        )
        if not added:
            raise ScreenCaptureKitCaptureError(
                f"failed to add ScreenCaptureKit stream output: {_error_description(error)}")

        completed = threading.Event()
        result: dict[str, object] = {}

        def started(error):
            result["error"] = error
            completed.set()

        binding = _PyObjCStreamBinding(stream, output, delegate, queue)
        try:
            stream.startCaptureWithCompletionHandler_(started)
            if not completed.wait(timeout):
                raise ScreenCaptureKitCaptureError(
                    f"ScreenCaptureKit start timed out after {timeout:.1f}s")
            error = result.get("error")
            if error is not None:
                raise ScreenCaptureKitCaptureError(
                    f"ScreenCaptureKit failed to start: {_error_description(error)}")
        except Exception as error:
            try:
                self.stop_stream(binding, timeout=timeout)
            except Exception as stop_error:
                raise _StreamShutdownPending(
                    f"{error}; failed-start cleanup is unconfirmed: {stop_error}",
                    binding,
                ) from error
            raise
        return binding

    def _check_shutdown_thread(self) -> None:
        # A synchronous drain of our own serial output queue cannot complete.
        # Checking before capture's lifecycle lock also avoids a callback waiting
        # on a closer that is already draining this queue.
        if self._dispatch.dispatch_queue_get_label(None) == b"com.ok-script.screencapturekit.frames":
            raise ScreenCaptureKitCaptureError(
                "ScreenCaptureKit shutdown must run outside the frame callback queue")

    def stop_stream(self, binding, *, timeout: float) -> None:
        self._check_shutdown_thread()
        if binding.drained:
            return
        deadline = time.monotonic() + timeout
        errors = []
        # This rejects callbacks that were queued natively but have not entered
        # Python yet. An in-flight callback keeps its local callbacks reference;
        # the native serial-queue fence below waits for it to return completely.
        binding.output._callbacks = None
        binding.delegate._callback = None
        if not binding.output_removed:
            try:
                removed, error = binding.stream.removeStreamOutput_type_error_(
                    binding.output,
                    self._screen_capture_kit.SCStreamOutputTypeScreen,
                    None,
                )
                if not removed or error is not None:
                    raise ScreenCaptureKitCaptureError(
                        f"failed to remove ScreenCaptureKit stream output: {_error_description(error)}")
                binding.output_removed = True
            except Exception as error:
                errors.append(str(error))

        completed = threading.Event()
        result: dict[str, object] = {}

        def stopped(error):
            result["error"] = error
            if error is None:
                binding.stop_confirmed = True
            completed.set()

        if not binding.stop_confirmed:
            try:
                binding.stream.stopCaptureWithCompletionHandler_(stopped)
                if not completed.wait(max(0.0, deadline - time.monotonic())):
                    errors.append(f"ScreenCaptureKit stop timed out after {timeout:.1f}s")
                elif result.get("error") is not None:
                    errors.append(
                        f"ScreenCaptureKit failed to stop: {_error_description(result['error'])}")
            except Exception as error:
                errors.append(f"ScreenCaptureKit stop failed: {error}")

        try:
            # stopCapture's completion is not an output-queue drain. A dispatch
            # group completes only after its fence block has returned through
            # the Python bridge, unlike setting a Python Event inside a block.
            group = self._dispatch.dispatch_group_create()
            self._dispatch.dispatch_group_async(group, binding.queue, lambda: None)
            remaining_ns = max(0, int((deadline - time.monotonic()) * 1_000_000_000))
            wait_until = self._dispatch.dispatch_time(
                self._dispatch.DISPATCH_TIME_NOW, remaining_ns)
            if self._dispatch.dispatch_group_wait(group, wait_until) != 0:
                errors.append(f"ScreenCaptureKit output queue drain timed out after {timeout:.1f}s")
        except Exception as error:
            errors.append(f"ScreenCaptureKit output queue drain failed: {error}")
        if errors:
            raise ScreenCaptureKitCaptureError("; ".join(errors))
        binding.drained = True


class ScreenCaptureKitCaptureMethod(BaseCaptureMethod):
    """One persistent stream bound to one immutable target generation."""

    name = "ScreenCaptureKit"

    def __init__(
            self,
            exit_event,
            target,
            permission_service,
            *,
            backend: ScreenCaptureKitBackend | None = None,
            frames_per_second: int = 30,
            lifecycle_timeout: float = 10.0,
            monotonic: Callable[[], float] = time.monotonic,
            on_input_invalidated: Callable[[object, str], None] | None = None):
        super().__init__()
        if frames_per_second <= 0:
            raise ValueError("frames_per_second must be positive")
        if lifecycle_timeout <= 0:
            raise ValueError("lifecycle_timeout must be positive")
        self.exit_event = exit_event
        self.target = target
        self.permission_service = permission_service
        self.backend = backend or PyObjCScreenCaptureKitBackend()
        self.frames_per_second = frames_per_second
        self.lifecycle_timeout = lifecycle_timeout
        self._monotonic = monotonic
        self._on_input_invalidated = on_input_invalidated
        self._slot = LatestFrameSlot()
        self._state_lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self._stream = None
        self._unconfirmed_stream = None
        self._state = CaptureStreamState.INITIAL
        self._target_generation = -1
        self._capture_generation = 0
        self._blocked_generation: int | None = None
        self._frames_received = 0
        self._dropped_incomplete = 0
        self._dropped_stale = 0
        self._conversion_errors = 0
        self._rebuilds = 0
        self._stream_starts = 0
        self._geometry_retry_started: float | None = None
        self._geometry_retry_at = 0.0
        self._geometry_retries = 0
        self._sequence = 0
        self._frame_times: deque[float] = deque(maxlen=120)
        self._latest_geometry: CaptureGeometry | None = None
        self._geometry_signature: tuple[object, ...] | None = None
        self._needs_rebuild = False
        self._latest_frame_time: float | None = None
        self._last_error: str | None = None
        self._geometry_invalidations = 0
        self._synchronize_stream()

    def _permission_status(self):
        statuses = tuple(self.permission_service.status(kind) for kind in (
            PermissionKind.SCREEN_RECORDING,
            PermissionKind.ACCESSIBILITY,
        ))
        return next((status for status in statuses if not status.granted), statuses[0])

    def _notify_input_invalidated(self, detail: str) -> None:
        callback = self._on_input_invalidated
        if callback is None:
            return
        try:
            callback(self, detail)
        except Exception as error:
            logger.error(f"capture input-invalidation callback failed: {error}")

    def _set_unavailable(self, state: CaptureStreamState, detail: str) -> None:
        with self._state_lock:
            self._state = state
            self._last_error = detail
            self._latest_geometry = None
            self._geometry_signature = None
            self._latest_frame_time = None
            self._frame_times.clear()
            self._size = (0, 0)
        self._slot.clear()
        self._notify_input_invalidated(detail)

    def _detach_stream(self):
        with self._state_lock:
            stream = self._stream
            self._stream = None
            self._capture_generation += 1
            self._latest_geometry = None
            self._geometry_signature = None
            self._latest_frame_time = None
            self._frame_times.clear()
            self._size = (0, 0)
        self._slot.clear()
        return stream

    def _stop_binding(self, stream) -> str | None:
        if stream is None:
            return None
        try:
            self.backend.stop_stream(stream, timeout=self.lifecycle_timeout)
        except Exception as error:
            detail = f"ScreenCaptureKit stop failed: {error}"
            with self._state_lock:
                self._unconfirmed_stream = stream
                self._last_error = detail
            return detail
        with self._state_lock:
            if self._unconfirmed_stream is stream:
                self._unconfirmed_stream = None
        return None

    def _set_fatal(
            self,
            detail: str,
            *,
            blocked_generation: int | None = None,
            expected_capture_generation: int | None = None) -> bool:
        with self._state_lock:
            if (
                    expected_capture_generation is not None
                    and expected_capture_generation != self._capture_generation):
                return False
            if self._stream is not None:
                # A native error callback does not prove that pending output
                # callbacks have finished. Keep the binding for close's drain.
                self._unconfirmed_stream = self._stream
            self._stream = None
            self._capture_generation += 1
            self._state = CaptureStreamState.FATAL
            self._blocked_generation = (
                self._target_generation
                if blocked_generation is None else blocked_generation)
            self._last_error = detail
            self._latest_geometry = None
            self._geometry_signature = None
            self._latest_frame_time = None
            self._frame_times.clear()
            self._size = (0, 0)
        self._slot.clear()
        self._notify_input_invalidated(detail)
        return True

    def invalidate(self, reason: str = "capture-invalidated") -> None:
        """Immediately reject the current generation before refresh/rebind."""
        if isinstance(self.backend, PyObjCScreenCaptureKitBackend):
            self.backend._check_shutdown_thread()
        with self._lifecycle_lock:
            stream = self._detach_stream()
            with self._state_lock:
                if self._state is not CaptureStreamState.CLOSED:
                    self._state = CaptureStreamState.TARGET_UNAVAILABLE
                    self._blocked_generation = self._target_generation
                    self._last_error = reason
            stop_error = self._stop_binding(stream)
            if stop_error is not None:
                self._set_fatal(stop_error)
            else:
                self._notify_input_invalidated(reason)

    def _synchronize_stream(self) -> None:
        with self._lifecycle_lock:
            with self._state_lock:
                if self._state in (CaptureStreamState.CLOSED, CaptureStreamState.FATAL):
                    return
                if self._unconfirmed_stream is not None:
                    self._state = CaptureStreamState.FATAL
                    return
            permission = self._permission_status()
            if not permission.granted:
                stream = self._detach_stream() if self._stream is not None else None
                state = (
                    CaptureStreamState.PERMISSION_REVOKED
                    if permission.state.value == "permission-revoked"
                    else CaptureStreamState.PERMISSION_REQUIRED)
                self._set_unavailable(
                    state,
                    permission.detail or (
                        f"{permission.state.value}: grant {permission.kind.value} at "
                        f"{permission.settings_path}"),
                )
                stop_error = self._stop_binding(stream)
                if stop_error is not None:
                    self._set_fatal(stop_error)
                return

            retry_started = self._geometry_retry_started
            if retry_started is not None:
                if self.exit_event.is_set():
                    self._set_unavailable(
                        CaptureStreamState.TARGET_UNAVAILABLE,
                        "capture is stopping; window geometry retry cancelled",
                    )
                    return
                now = self._monotonic()
                if now - retry_started >= 5.0:
                    self._set_fatal("macOS window geometry did not settle within 5.0s")
                    return
                if now < self._geometry_retry_at:
                    return

            try:
                with self._state_lock:
                    refresh_for_rebuild = self._needs_rebuild
                if refresh_for_rebuild:
                    self.target.refresh()
                target_exists = bool(self.target.exists())
            except Exception as error:
                stream = self._detach_stream() if self._stream is not None else None
                self._set_unavailable(
                    CaptureStreamState.TARGET_UNAVAILABLE,
                    f"failed to verify selected macOS window target: {error}",
                )
                stop_error = self._stop_binding(stream)
                if stop_error is not None:
                    self._set_fatal(stop_error)
                return

            snapshot = self.target.snapshot
            if not target_exists or not snapshot.exists or snapshot.candidate is None:
                stream = self._detach_stream() if self._stream is not None else None
                self._set_unavailable(
                    CaptureStreamState.TARGET_UNAVAILABLE,
                    "selected macOS window target is unavailable",
                )
                stop_error = self._stop_binding(stream)
                if stop_error is not None:
                    self._set_fatal(stop_error)
                return

            with self._state_lock:
                current_stream = self._stream
                current_generation = self._target_generation
                blocked = self._blocked_generation == snapshot.generation
                needs_rebuild = self._needs_rebuild
            if (
                    current_stream is not None
                    and current_generation == snapshot.generation
                    and not needs_rebuild):
                return
            if blocked:
                return

            old_stream = self._detach_stream() if current_stream is not None else None
            if old_stream is not None:
                self._notify_input_invalidated("macOS capture geometry changed; rebuilding stream")
            stop_error = self._stop_binding(old_stream)
            if stop_error is not None:
                self._set_fatal(stop_error, blocked_generation=snapshot.generation)
                return
            with self._state_lock:
                if self._state in (
                        CaptureStreamState.CLOSED,
                        CaptureStreamState.FATAL):
                    return
                self._needs_rebuild = False
                self._capture_generation += 1
                capture_generation = self._capture_generation
                self._target_generation = snapshot.generation
                self._state = CaptureStreamState.STARTING
                self._last_error = None

            def on_sample(buffer, width, height, bytes_per_row, metadata):
                self._on_sample(
                    capture_generation,
                    snapshot,
                    buffer,
                    width,
                    height,
                    bytes_per_row,
                    metadata,
                )

            try:
                stream = self.backend.start_stream(
                    snapshot,
                    on_sample,
                    lambda detail: self._on_stream_stopped(
                        capture_generation, detail),
                    lambda detail: self._on_sample_error(
                        capture_generation, detail),
                    frames_per_second=self.frames_per_second,
                    timeout=(
                        min(self.lifecycle_timeout, max(
                            0.001, 5.0 - (self._monotonic() - retry_started)))
                        if retry_started is not None else self.lifecycle_timeout),
                )
            except Exception as error:
                detail = str(error)
                if isinstance(error, _StreamShutdownPending):
                    with self._state_lock:
                        self._unconfirmed_stream = error.binding
                    self._set_fatal(detail, expected_capture_generation=capture_generation)
                    return
                permission = self._permission_status()
                if not permission.granted:
                    state = (
                        CaptureStreamState.PERMISSION_REVOKED
                        if permission.state.value == "permission-revoked"
                        else CaptureStreamState.PERMISSION_REQUIRED)
                    self._set_unavailable(
                        state,
                        permission.detail or (
                            f"{permission.state.value}: grant "
                            f"{permission.kind.value} at {permission.settings_path}"),
                    )
                    return
                if isinstance(error, _WindowGeometryPending):
                    now = self._monotonic()
                    with self._state_lock:
                        if (
                                self._state is not CaptureStreamState.STARTING
                                or capture_generation != self._capture_generation):
                            return
                        if self._geometry_retry_started is None:
                            self._geometry_retry_started = now
                        delays = (0.1, 0.2, 0.4, 0.8, 1.0)
                        retry = (
                            self._geometry_retries < len(delays)
                            and now - self._geometry_retry_started < 5.0)
                        if retry:
                            self._geometry_retry_at = now + delays[self._geometry_retries]
                            self._geometry_retries += 1
                            self._needs_rebuild = True
                    if retry:
                        self._set_unavailable(
                            CaptureStreamState.TARGET_UNAVAILABLE,
                            f"{detail}; retrying with fresh window metadata",
                        )
                        return
                    detail = f"macOS window geometry retry limit reached: {detail}"
                self._set_fatal(
                    detail,
                    blocked_generation=snapshot.generation,
                    expected_capture_generation=capture_generation,
                )
                return
            with self._state_lock:
                if (
                        capture_generation != self._capture_generation
                        or self._state is not CaptureStreamState.STARTING):
                    stale_stream = stream
                else:
                    self._stream = stream
                    self._state = CaptureStreamState.RUNNING
                    self._blocked_generation = None
                    self._geometry_retry_started = None
                    self._geometry_retries = 0
                    if self._stream_starts:
                        self._rebuilds += 1
                    self._stream_starts += 1
                    stale_stream = None
            self._stop_binding(stale_stream)

    def _on_sample(
            self,
            capture_generation: int,
            target_snapshot: WindowTargetSnapshot,
            buffer,
            width: int,
            height: int,
            bytes_per_row: int,
            metadata: StreamFrameMetadata) -> None:
        now = self._monotonic()
        with self._state_lock:
            self._frames_received += 1
            if not metadata.complete:
                self._dropped_incomplete += 1
                return
            live_snapshot = self.target.snapshot
            if (
                    capture_generation != self._capture_generation
                    or self._state not in (
                        CaptureStreamState.STARTING,
                        CaptureStreamState.RUNNING)
                    or target_snapshot.generation != live_snapshot.generation
                    or not live_snapshot.exists):
                self._dropped_stale += 1
                self._slot.clear()
                return
        candidate = target_snapshot.candidate
        if candidate is None:
            return
        try:
            if metadata.content_rect_points is None:
                raise ValueError("complete frame has no ScreenCaptureKit content rect")
            if metadata.display_scale is None:
                raise ValueError("complete frame has no ScreenCaptureKit scale factor")
            display_scale = metadata.display_scale
            crop = content_rect_to_pixels(
                metadata.content_rect_points,
                display_scale,
                width,
                height,
            )
            frame = bgra_to_owned_bgr(
                buffer,
                width=width,
                height=height,
                bytes_per_row=bytes_per_row,
                crop=crop,
            )
            global_content = (
                metadata.global_content_geometry
                or candidate.content_geometry
                or candidate.outer_geometry)
            geometry = CaptureGeometry(
                target_generation=target_snapshot.generation,
                capture_generation=capture_generation,
                outer_geometry=(
                    metadata.screen_rect_points or candidate.outer_geometry),
                global_content_geometry=global_content,
                raw_frame_width=width,
                raw_frame_height=height,
                content_rect_pixels=crop,
                frame_width=frame.shape[1],
                frame_height=frame.shape[0],
                display_scale=display_scale,
                content_scale=metadata.content_scale,
            )
            geometry_signature = (
                width,
                height,
                crop,
                display_scale,
                metadata.content_scale,
                metadata.screen_rect_points,
                global_content,
            )
        except Exception as error:
            self._on_sample_error(
                capture_generation,
                f"ScreenCaptureKit frame normalization failed: {error}",
            )
            return

        with self._state_lock:
            live_snapshot = self.target.snapshot
            if (
                    capture_generation != self._capture_generation
                    or self._state not in (
                        CaptureStreamState.STARTING,
                        CaptureStreamState.RUNNING)
                    or target_snapshot.generation != live_snapshot.generation
                    or not live_snapshot.exists):
                self._dropped_stale += 1
                self._slot.clear()
                return
            if (
                    self._geometry_signature is not None
                    and self._geometry_signature != geometry_signature):
                # The current stream configuration/coordinate mapping is no
                # longer immutable.  Reject this sample and every late sample;
                # the next consumer poll rebuilds the persistent stream.
                self._capture_generation += 1
                self._needs_rebuild = True
                self._state = CaptureStreamState.TARGET_UNAVAILABLE
                self._geometry_invalidations += 1
                self._latest_geometry = None
                self._latest_frame_time = None
                self._frame_times.clear()
                self._size = (0, 0)
                self._last_error = "ScreenCaptureKit frame geometry changed; rebuilding stream"
                self._slot.clear()
                return
            self._sequence += 1
            published = PublishedFrame(frame, geometry, self._sequence, now)
            self._latest_geometry = geometry
            self._geometry_signature = geometry_signature
            self._latest_frame_time = now
            self._frame_times.append(now)
            self._size = (frame.shape[1], frame.shape[0])
            self._slot.publish(published)

    def _on_sample_error(self, capture_generation: int, detail: str) -> None:
        with self._state_lock:
            if capture_generation != self._capture_generation:
                return
            self._conversion_errors += 1
            self._last_error = detail
            self._latest_geometry = None
            self._geometry_signature = None
            self._latest_frame_time = None
            self._frame_times.clear()
            self._size = (0, 0)
        # Never let a consumer unknowingly reuse an older frame after the
        # current complete sample could not be normalized safely.
        self._slot.clear()
        self._notify_input_invalidated(detail)

    def _on_stream_stopped(self, capture_generation: int, detail: str) -> None:
        self._set_fatal(
            detail or "ScreenCaptureKit stream stopped unexpectedly",
            expected_capture_generation=capture_generation,
        )

    def get_frame_packet(self) -> PublishedFrame | None:
        """Return the latest frame together with its immutable geometry."""
        self._synchronize_stream()
        return self._read_frame_packet()

    def _read_frame_packet(self) -> PublishedFrame | None:
        """Read only: never discover a window or create/rebuild a stream."""
        with self._state_lock:
            snapshot = self.target.snapshot
            state = self._state
            target_generation = self._target_generation
            capture_generation = self._capture_generation
            detail = self._last_error
            if state in (
                    CaptureStreamState.PERMISSION_REQUIRED,
                    CaptureStreamState.PERMISSION_REVOKED,
                    CaptureStreamState.FATAL):
                raise ScreenCaptureKitCaptureError(detail or state.value)
            if snapshot.generation != target_generation or not snapshot.exists:
                self._slot.clear()
                return None
            packet = self._slot.read(
                target_generation=target_generation,
                capture_generation=capture_generation,
            )
            if packet is not None:
                age = self._monotonic() - packet.captured_monotonic
                if not math.isfinite(age) or not 0 <= age <= MAX_FRAME_AGE_SECONDS:
                    return None
            return packet

    def await_fresh_frame(self, timeout=8.0, *, poll_interval=0.1, sleep=time.sleep):
        """Final input revalidation of an already prepared provider, no recovery."""
        return self.wait_until_ready(
            timeout, poll_interval=poll_interval, sleep=sleep, recover=False)

    def wait_until_ready(self, timeout=8.0, *, poll_interval=0.1, sleep=time.sleep, recover=True):
        """Explicit start/resume preflight; never arms input or activates a target.

        Poll the persistent stream even while the input gate is closed. A lost
        window may be reselected by the existing identity/ambiguity rules, but
        only this explicit request retries discovery; ordinary input never does.
        """
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("readiness timeout and poll interval must be positive")
        started = self._monotonic()
        deadline = started + timeout
        with self._state_lock:
            sequence = self._sequence
        next_refresh = started
        try:
            while not self.exit_event.is_set():
                permission = self._permission_status()
                if not permission.granted:
                    raise ScreenCaptureKitCaptureError(
                        f"{permission.kind.value}: {permission.state.value}; "
                        f"grant permission at {permission.settings_path}")
                with self._state_lock:
                    if self._state in (CaptureStreamState.CLOSED, CaptureStreamState.FATAL):
                        raise ScreenCaptureKitCaptureError(self._last_error or self._state.value)
                now = self._monotonic()
                if now >= deadline:
                    break
                target_exists = self.target.exists()
                if not recover:
                    with self._state_lock:
                        prepared = (self._state is CaptureStreamState.RUNNING
                                    and self._stream is not None and not self._needs_rebuild
                                    and self._target_generation == self.target.snapshot.generation)
                    if not target_exists or not prepared:
                        raise ScreenCaptureKitCaptureError(
                            'MAC_CAPTURE_NOT_PREPARED: reconnect capture before starting input')
                if recover and not target_exists and now >= next_refresh:
                    if getattr(self.target, "unavailable_code", None) == "MAC_TARGET_EXITED":
                        raise ScreenCaptureKitCaptureError(
                            "MAC_TARGET_EXITED: game process ended; explicitly bind the new game process")
                    result = self.target.refresh()
                    if getattr(getattr(result, "status", None), "value", None) == "manual-selection-required":
                        raise ScreenCaptureKitCaptureError(
                            "MAC_TARGET_UNAVAILABLE: multiple credible windows; manually select the game window")
                    next_refresh = self._monotonic() + 0.5
                packet = self.get_frame_packet() if recover else self._read_frame_packet()
                diagnostics = self.diagnostics()
                snapshot = self.target.snapshot
                if (self._monotonic() < deadline
                        and packet is not None and packet.sequence > sequence
                        and packet.captured_monotonic >= started
                        and diagnostics.state is CaptureStreamState.RUNNING
                        and snapshot.exists and snapshot.candidate is not None
                        and packet.geometry == diagnostics.geometry
                        and packet.geometry.target_generation == snapshot.generation
                        and diagnostics.target_generation == snapshot.generation
                        and packet.geometry.capture_generation == diagnostics.capture_generation):
                    return packet
                sleep(min(poll_interval, max(0, deadline - self._monotonic())))
            raise ScreenCaptureKitCaptureError(
                "MAC_CAPTURE_REBIND_FAILED: reconnect timed out or was cancelled; "
                "check game window and permissions, then explicitly resume")
        except Exception:
            self._notify_input_invalidated("macOS capture readiness failed; input remains stopped")
            raise

    def do_get_frame(self):
        published = self.get_frame_packet()
        return published.frame if published is not None else None

    def connected(self):
        self._synchronize_stream()
        with self._state_lock:
            return bool(
                self._state is CaptureStreamState.RUNNING
                and self._stream is not None
                and self.target.snapshot.exists
            )

    @property
    def geometry(self) -> CaptureGeometry | None:
        with self._state_lock:
            return self._latest_geometry

    def frame_pixel_to_global_point(
            self,
            x: float,
            y: float,
            *,
            geometry: CaptureGeometry | None = None) -> tuple[float, float]:
        geometry = geometry or self.geometry
        if geometry is None:
            raise ScreenCaptureKitCaptureError("no current capture geometry")
        return geometry.frame_pixel_to_global_point(x, y)

    def diagnostics(self) -> CaptureDiagnostics:
        with self._state_lock:
            now = self._monotonic()
            times = tuple(self._frame_times)
            if len(times) >= 2 and times[-1] > times[0]:
                fps = (len(times) - 1) / (times[-1] - times[0])
            else:
                fps = 0.0
            packet = self._slot.read(
                target_generation=self._target_generation,
                capture_generation=self._capture_generation)
            frame_age = now - packet.captured_monotonic if packet is not None else None
            return CaptureDiagnostics(
                state=self._state,
                target_generation=self._target_generation,
                capture_generation=self._capture_generation,
                frames_received=self._frames_received,
                frames_published=self._slot.published,
                frames_overwritten=self._slot.overwritten,
                frames_dropped_incomplete=self._dropped_incomplete,
                frames_dropped_stale=self._dropped_stale,
                frame_conversion_errors=self._conversion_errors,
                geometry_invalidations=self._geometry_invalidations,
                rebuilds=self._rebuilds,
                fps=fps,
                frame_age_seconds=frame_age,
                storage_size=self._slot.storage_size,
                geometry=self._latest_geometry,
                last_error=self._last_error,
                frame_sequence=packet.sequence if packet is not None else None,
                captured_monotonic=packet.captured_monotonic if packet is not None else None,
                frame_geometry=packet.geometry if packet is not None else None,
            )

    def request_content_size(self, width: int, height: int) -> dict[str, object]:
        """Close this capture permanently, then request a one-off window size.

        Explicit startup preparation only. Its input invalidation callback must
        be wired normally. The caller must verify a new capture before input.
        """
        if any(type(v) is not int or v <= 0 for v in (width, height)):
            raise ValueError("content dimensions must be positive integer pixels")
        request = getattr(self.backend, "request_content_size", None)
        if not callable(request):
            raise ScreenCaptureKitCaptureError("capture backend does not support window preparation")
        self.close()  # Failure aborts before AXSize; old frames can never revive.
        permission = self._permission_status()
        if not permission.granted or self.exit_event.is_set():
            raise ScreenCaptureKitCaptureError("window preparation permission missing or app stopping")
        return request(
            self.target, width, height, timeout=self.lifecycle_timeout,
            is_stopping=self.exit_event.is_set)

    def close(self):
        if isinstance(self.backend, PyObjCScreenCaptureKitBackend):
            self.backend._check_shutdown_thread()
        self._notify_input_invalidated("ScreenCaptureKit capture closed")
        with self._lifecycle_lock:
            with self._state_lock:
                if self._state is CaptureStreamState.CLOSED:
                    return
                self._state = CaptureStreamState.CLOSED
            stream = self._detach_stream()
            with self._state_lock:
                unconfirmed_stream = self._unconfirmed_stream
            errors = []
            stop_error = self._stop_binding(stream)
            if stop_error is not None:
                errors.append(stop_error)
            if unconfirmed_stream is not None and unconfirmed_stream is not stream:
                stop_error = self._stop_binding(unconfirmed_stream)
                if stop_error is not None:
                    errors.append(stop_error)
            if errors:
                detail = "; ".join(errors)
                self._set_fatal(detail)
                raise ScreenCaptureKitCaptureError(detail)
