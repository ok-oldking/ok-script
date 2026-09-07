"""Public-API macOS window discovery and foreground observation.

ScreenCaptureKit is used here only for low-frequency discovery/rebinding.  The
persistent ``SCStream`` implementation remains isolated in the capture layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import errno
import logging
import os
import threading
import time
from typing import Callable, Protocol

from ok.device.window_target.base import (
    BaseDesktopWindowTarget,
    StableWindowHint,
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowRefreshResult,
    WindowRefreshStatus,
    WindowTargetSnapshot,
)
from ok.device.window_target.selection import (
    WindowMatchHints,
    WindowSelectionResult,
    WindowSelectionStatus,
    select_window_candidate,
)
from ok.platform import require_macos_foreground_host

logger = logging.getLogger(__name__)


class WindowDiscoveryError(RuntimeError):
    """Raised when the operating system cannot provide shareable windows."""


class WindowDiscoveryTimeoutError(WindowDiscoveryError):
    """Raised when ScreenCaptureKit does not complete discovery in time."""


class MacOSWindowSystem(Protocol):
    def enumerate_windows(self, timeout: float) -> tuple[WindowCandidate, ...]: ...

    def frontmost_process_id(self) -> int | None: ...

    def process_exists(self, process_id: int) -> bool: ...

    def process_exit_evidence(self, process_id: int) -> tuple[bool | None, bool | None]: ...

    def window_exists(self, process_id: int, window_id: int) -> bool: ...

    def window_geometry(
            self, process_id: int, window_id: int) -> WindowGeometry | None: ...

    def request_activation(self, process_id: int) -> bool: ...


def _objc_value(instance, name: str):
    value = getattr(instance, name)
    return value() if callable(value) else value


def _geometry_from_rect(
        rect,
        coordinate_space: WindowCoordinateSpace = (
            WindowCoordinateSpace.UNKNOWN)) -> WindowGeometry:
    if isinstance(rect, Mapping):
        try:
            return WindowGeometry(
                float(rect["X"]),
                float(rect["Y"]),
                float(rect["Width"]),
                float(rect["Height"]),
                coordinate_space,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WindowDiscoveryError(
                f"unsupported Core Graphics window bounds {rect!r}") from error
    try:
        return WindowGeometry(
            float(rect.origin.x),
            float(rect.origin.y),
            float(rect.size.width),
            float(rect.size.height),
            coordinate_space,
        )
    except AttributeError:
        try:
            (x, y), (width, height) = rect
            return WindowGeometry(
                float(x), float(y), float(width), float(height),
                coordinate_space)
        except (TypeError, ValueError) as error:
            raise WindowDiscoveryError(
                f"unsupported ScreenCaptureKit window frame {rect!r}") from error


class PyObjCMacOSWindowSystem:
    """Thin adapter around AppKit and ScreenCaptureKit public APIs."""

    def __init__(self):
        require_macos_foreground_host("PyObjC macOS window system")
        import AppKit
        import ApplicationServices
        import Quartz
        import ScreenCaptureKit

        self._appkit = AppKit
        self._application_services = ApplicationServices
        self._quartz = Quartz
        self._screen_capture_kit = ScreenCaptureKit

    def enumerate_windows(self, timeout: float) -> tuple[WindowCandidate, ...]:
        if timeout <= 0:
            raise ValueError("window discovery timeout must be positive")

        completed = threading.Event()
        result: dict[str, object] = {}

        def on_content(content, error):
            result["content"] = content
            result["error"] = error
            completed.set()

        self._screen_capture_kit.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            True,
            True,
            on_content,
        )
        if not completed.wait(timeout):
            raise WindowDiscoveryTimeoutError(
                f"ScreenCaptureKit discovery did not finish within {timeout:.1f}s")

        error = result.get("error")
        if error is not None:
            try:
                description = _objc_value(error, "localizedDescription")
            except AttributeError:
                description = str(error)
            raise WindowDiscoveryError(
                f"ScreenCaptureKit discovery failed: {description}")
        content = result.get("content")
        if content is None:
            raise WindowDiscoveryError("ScreenCaptureKit returned no shareable content")

        frontmost_process_id = self.frontmost_process_id()
        candidates = []
        for window in _objc_value(content, "windows"):
            application = _objc_value(window, "owningApplication")
            if application is None:
                continue
            process_id = int(_objc_value(application, "processID") or 0)
            window_id = int(_objc_value(window, "windowID") or 0)
            if process_id <= 0 or window_id <= 0:
                continue
            candidates.append(WindowCandidate(
                process_id=process_id,
                window_id=window_id,
                bundle_identifier=(
                    str(_objc_value(application, "bundleIdentifier") or "").strip()
                    or None
                ),
                application_name=str(
                    _objc_value(application, "applicationName") or "").strip(),
                title=str(_objc_value(window, "title") or "").strip(),
                layer=int(_objc_value(window, "windowLayer") or 0),
                outer_geometry=_geometry_from_rect(
                    _objc_value(window, "frame"),
                    WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS,
                ),
                # Discovery metadata cannot establish content/capture pixels.
                # The capture layer derives them from actual SCStream frames.
                content_geometry=None,
                capture_geometry=None,
                display_scale=None,
                frontmost=process_id == frontmost_process_id,
            ))
        return tuple(candidates)

    def _running_application(self, process_id: int):
        return self._appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
            process_id)

    def frontmost_process_id(self) -> int | None:
        # Source/worker hardware tests observed frontmostApplication retaining
        # the previous app while this synchronous query already saw the switch.
        # Safety checks must not use that stale NSWorkspace view. These public,
        # deprecated HIServices APIs query
        # the current front process synchronously; never fall back on failure.
        try:
            status, serial = self._application_services.GetFrontProcess(None)
            if status != 0 or serial is None:
                return None
            status, process_id = self._application_services.GetProcessPID(serial, None)
        except Exception as error:
            raise WindowDiscoveryError("failed to query the macOS front process") from error
        if status != 0 or process_id is None or int(process_id) <= 0:
            return None
        return int(process_id)

    def process_exists(self, process_id: int) -> bool:
        application = self._running_application(process_id)
        return bool(application is not None and not application.isTerminated())

    def process_exit_evidence(self, process_id: int) -> tuple[bool | None, bool | None]:
        """Independent observations; unknown must never confirm process death."""
        try:
            os.kill(process_id, 0)
            posix_alive = True
        except OSError as error:
            posix_alive = (False if error.errno == errno.ESRCH else
                           True if error.errno == errno.EPERM else None)
        try:
            windows = self._quartz.CGWindowListCopyWindowInfo(
                self._quartz.kCGWindowListOptionAll,
                self._quartz.kCGNullWindowID)
            window_alive = (None if windows is None else any(
                int(info.get(self._quartz.kCGWindowOwnerPID, 0) or 0) == process_id
                for info in windows))
        except Exception:
            window_alive = None
        return posix_alive, window_alive

    def _window_info(self, process_id: int, window_id: int):
        if process_id <= 0 or window_id <= 0:
            return None
        windows = self._quartz.CGWindowListCopyWindowInfo(
            self._quartz.kCGWindowListOptionIncludingWindow,
            window_id,
        )
        if not windows:
            return None
        return next((
            info for info in windows
            if int(info.get(self._quartz.kCGWindowNumber, 0) or 0) == window_id
            and int(info.get(self._quartz.kCGWindowOwnerPID, 0) or 0) == process_id
        ), None)

    def window_exists(self, process_id: int, window_id: int) -> bool:
        return self._window_info(process_id, window_id) is not None

    def window_geometry(
            self, process_id: int, window_id: int) -> WindowGeometry | None:
        info = self._window_info(process_id, window_id)
        if info is None:
            return None
        bounds = info.get(self._quartz.kCGWindowBounds)
        if bounds is None:
            raise WindowDiscoveryError(
                "Core Graphics returned a matching window without bounds")
        return _geometry_from_rect(
            bounds, WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS)

    def request_activation(self, process_id: int) -> bool:
        application = self._running_application(process_id)
        if application is None or application.isTerminated():
            return False
        return bool(application.activateWithOptions_(
            self._appkit.NSApplicationActivateIgnoringOtherApps))


class MacOSWindowDiscovery:
    def __init__(
            self,
            system: MacOSWindowSystem | None = None,
            *,
            discovery_timeout: float = 10.0):
        self.system = system or PyObjCMacOSWindowSystem()
        if discovery_timeout <= 0:
            raise ValueError("discovery_timeout must be positive")
        self.discovery_timeout = discovery_timeout

    def enumerate_candidates(self) -> tuple[WindowCandidate, ...]:
        return self.system.enumerate_windows(self.discovery_timeout)

    def select(
            self,
            hints: WindowMatchHints,
            *,
            stable_hint: StableWindowHint | None = None,
            manual_window_id: int | None = None) -> WindowSelectionResult:
        return select_window_candidate(
            self.enumerate_candidates(),
            hints,
            stable_hint=stable_hint,
            manual_window_id=manual_window_id,
        )

    def bind(
            self,
            selected: WindowCandidate,
            hints: WindowMatchHints,
            *,
            stable_hint: StableWindowHint | None = None,
            monotonic: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep) -> "MacOSWindowTarget":
        # Selection and binding are deliberately separate user-visible steps.
        # Re-enumerate here so the target is built from current metadata rather
        # than the possibly stale object shown during selection.
        current_candidates = self.enumerate_candidates()
        current_selection = select_window_candidate(
            current_candidates,
            hints,
            stable_hint=stable_hint,
            manual_window_id=selected.window_id,
        )
        current = current_selection.selected
        if (
                current is None
                or current.runtime_identity != selected.runtime_identity
                or not self.system.process_exists(current.process_id)
                or not self.system.window_exists(
                    current.process_id, current.window_id)):
            raise WindowDiscoveryError(
                "selected macOS window disappeared before it could be bound")
        return MacOSWindowTarget(
            self,
            current,
            hints,
            stable_hint=stable_hint or current.stable_hint(),
            monotonic=monotonic,
            sleep=sleep,
        )


class MacOSWindowTarget(BaseDesktopWindowTarget):
    def __init__(
            self,
            discovery: MacOSWindowDiscovery,
            candidate: WindowCandidate,
            hints: WindowMatchHints,
            *,
            stable_hint: StableWindowHint,
            monotonic: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep):
        self.discovery = discovery
        self.hints = hints
        self.stable_hint = stable_hint
        self._monotonic = monotonic
        self._sleep = sleep
        self._state_lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        # Recovery metadata only: never expose this as usable capture geometry.
        self._last_bound_candidate = candidate
        self._process_exited = False
        self._unavailable_code = "MAC_TARGET_UNAVAILABLE"
        self._exit_samples = 0
        self._last_exit_sample = None
        super().__init__(candidate)

    @property
    def snapshot(self) -> WindowTargetSnapshot:
        with self._state_lock:
            return super().snapshot

    def _candidate_exists(self, candidate: WindowCandidate) -> bool:
        return bool(
            self.discovery.system.process_exists(candidate.process_id)
            and self.discovery.system.window_exists(
                candidate.process_id, candidate.window_id)
        )

    @property
    def unavailable_code(self) -> str:
        with self._state_lock:
            return self._unavailable_code

    def _mark_unavailable(self, *, process_exited=False):
        self._process_exited = self._process_exited or process_exited
        self._unavailable_code = (
            "MAC_TARGET_EXITED" if self._process_exited else "MAC_TARGET_UNAVAILABLE")
        self._update_candidate(None, exists=False)

    def _observe_process(self, process_id, *, bound_candidate=None):
        # Never sleep or enumerate SCK on the input path. A negative AppKit
        # sample may be contradicted only for the currently valid exact binding.
        # Lost bindings still require explicit refresh and a new capture epoch.
        try:
            alive = self.discovery.system.process_exists(process_id)
        except Exception:
            alive = None
        with self._state_lock:
            if alive is True:
                self._exit_samples = 0
                self._last_exit_sample = None
                return True
            current = super().snapshot
            if (alive is False and current.exists and bound_candidate is not None
                    and current.candidate == bound_candidate):
                posix_alive = window_alive = geometry = frontmost = None
                try:
                    posix_alive, window_alive = self.discovery.system.process_exit_evidence(process_id)
                    geometry = self.discovery.system.window_geometry(
                        process_id, bound_candidate.window_id)
                    frontmost = self.discovery.system.frontmost_process_id()
                except Exception:
                    # Partial/unknown observations cannot keep a binding usable.
                    geometry = None
                corroborated = (posix_alive is True and window_alive is True
                                and geometry == bound_candidate.outer_geometry
                                and frontmost == process_id)
                logger.warning(
                    'macOS liveness appkit=%s posix=%s cgwindow_pid=%s bound_window=%s '
                    'geometry_unchanged=%s frontmost_matches=%s target_generation=%s decision=%s',
                    alive, posix_alive, window_alive, geometry is not None,
                    geometry == bound_candidate.outer_geometry, frontmost == process_id,
                    current.generation, 'corroborated-bound-window' if corroborated else 'unavailable')
                if corroborated:
                    self._exit_samples = 0
                    self._last_exit_sample = None
                    return True
            was_available = super().snapshot.exists
            self._mark_unavailable()
            now = self._monotonic()
            if was_available:
                # Let the guard release held input before doing extra queries.
                self._exit_samples = 0
                self._last_exit_sample = now
                logger.warning("macOS liveness pid=%s appkit=%s state=unavailable", process_id, alive)
                return False
            if self._last_exit_sample is not None and now - self._last_exit_sample < 0.5:
                if alive is None:
                    self._exit_samples = 0
                return False
            self._last_exit_sample = now
            try:
                posix_alive, window_alive = self.discovery.system.process_exit_evidence(process_id)
            except Exception:
                posix_alive = window_alive = None
            negative = alive is False and posix_alive is False and window_alive is False
            self._exit_samples = self._exit_samples + 1 if negative else 0
            logger.warning(
                "macOS liveness pid=%s appkit=%s posix=%s cgwindow=%s negative_samples=%s time=%.3f",
                process_id, alive, posix_alive, window_alive, self._exit_samples, now)
            if self._exit_samples >= 3:
                self._mark_unavailable(process_exited=True)
            return False

    def _recovery_candidates(self, candidates, remembered):
        # A different process requires a new explicit binding, not a recovery.
        return tuple(candidate for candidate in candidates
                     if candidate.process_id == remembered.process_id
                     and candidate.bundle_identifier == remembered.bundle_identifier
                     and candidate.application_name == remembered.application_name
                     and candidate.layer in self.hints.allowed_layers
                     and candidate.outer_geometry.width >= self.hints.minimum_width
                     and candidate.outer_geometry.height >= self.hints.minimum_height)

    def refresh(self) -> WindowRefreshResult:
        with self._refresh_lock:
            with self._state_lock:
                previous = super().snapshot
                remembered = self._last_bound_candidate
                if self._process_exited:
                    return WindowRefreshResult(WindowRefreshStatus.LOST, previous, previous)
                refresh_generation = previous.generation + 1
                self._snapshot = WindowTargetSnapshot(
                    candidate=None,
                    generation=refresh_generation,
                    exists=False,
                )
            try:
                if not self._observe_process(remembered.process_id):
                    with self._state_lock:
                        return WindowRefreshResult(
                            WindowRefreshStatus.LOST, previous, super().snapshot)
                candidates = self.discovery.enumerate_candidates()
                current_identity = (
                    previous.candidate.runtime_identity
                    if previous.candidate else None)
                exact = next(
                    (candidate for candidate in candidates
                     if candidate.runtime_identity == current_identity),
                    None,
                )
                eligible = self._recovery_candidates(candidates, remembered)
                if exact in eligible and exact is not None and self._candidate_exists(exact):
                    with self._state_lock:
                        if self._process_exited:
                            return WindowRefreshResult(WindowRefreshStatus.LOST, previous, super().snapshot)
                        changed = (
                            previous.candidate is None
                            or previous.candidate.binding_signature
                            != exact.binding_signature
                        )
                        self._snapshot = WindowTargetSnapshot(
                            exact, refresh_generation, True)
                        self._last_bound_candidate = exact
                        status = (
                            WindowRefreshStatus.REBOUND
                            if not previous.exists
                            else (
                                WindowRefreshStatus.UPDATED
                                if changed else WindowRefreshStatus.UNCHANGED
                            )
                        )
                        return WindowRefreshResult(
                            status, previous, super().snapshot, candidates)

                # Even an old ID/title returning is ambiguous when there are
                # multiple credible windows after loss. Never guess a surface.
                if len(eligible) > 1:
                    with self._state_lock:
                        return WindowRefreshResult(
                            WindowRefreshStatus.MANUAL_SELECTION_REQUIRED,
                            previous, super().snapshot, eligible)
                selection = select_window_candidate(
                    eligible,
                    self.hints,
                    stable_hint=self.stable_hint,
                )
                selected = selection.selected
                if selected is not None and self._candidate_exists(selected):
                    with self._state_lock:
                        if self._process_exited:
                            return WindowRefreshResult(WindowRefreshStatus.LOST, previous, super().snapshot)
                        self._snapshot = WindowTargetSnapshot(
                            selected, refresh_generation, True)
                        self._last_bound_candidate = selected
                        return WindowRefreshResult(
                            WindowRefreshStatus.REBOUND,
                            previous,
                            super().snapshot,
                            selection.candidates,
                        )

                with self._state_lock:
                    status = (
                        WindowRefreshStatus.MANUAL_SELECTION_REQUIRED
                        if selection.status
                        is WindowSelectionStatus.MANUAL_SELECTION_REQUIRED
                        else WindowRefreshStatus.LOST
                    )
                    return WindowRefreshResult(
                        status, previous, super().snapshot,
                        selection.candidates)
            except Exception:
                raise

    def exists(self) -> bool:
        snapshot = self.snapshot
        candidate = snapshot.candidate
        if not snapshot.exists or candidate is None:
            # Keep the public snapshot invalid until explicit refresh, even if
            # this process/window comes back. Do not revive old generations.
            with self._state_lock:
                if self._process_exited:
                    return False
                remembered = self._last_bound_candidate
            self._observe_process(remembered.process_id)
            return False
        try:
            process_exists = self._observe_process(
                candidate.process_id, bound_candidate=candidate)
            live_geometry = (
                self.discovery.system.window_geometry(
                    candidate.process_id, candidate.window_id)
                if process_exists else None
            )
            exists = live_geometry is not None
        except Exception as error:
            with self._state_lock:
                current = super().snapshot
                if (
                        current.generation == snapshot.generation
                        and current.candidate is not None
                        and current.candidate.runtime_identity
                        == candidate.runtime_identity):
                    self._mark_unavailable()
            raise WindowDiscoveryError(
                "failed to verify macOS window liveness") from error
        with self._state_lock:
            current = super().snapshot
            if (
                    current.generation != snapshot.generation
                    or current.candidate is None
                    or current.candidate.runtime_identity
                    != candidate.runtime_identity):
                return current.exists
            if not exists:
                self._mark_unavailable()
            elif live_geometry is not None and any(
                    abs(left - right) > 0.5 for left, right in (
                        (candidate.outer_geometry.x, live_geometry.x),
                        (candidate.outer_geometry.y, live_geometry.y),
                        (candidate.outer_geometry.width, live_geometry.width),
                        (candidate.outer_geometry.height, live_geometry.height),
                    )):
                # CGWindow bounds are only a live invalidation probe. The next
                # capture rebind still derives content geometry from the unique
                # AXStandardWindow and SCWindow metadata.
                self._update_candidate(
                    replace(candidate, outer_geometry=live_geometry), exists=True)
            return super().snapshot.exists

    def is_foreground(self) -> bool:
        return bool(
            self.exists()
            and self.discovery.system.frontmost_process_id() == self.process_id
        )

    def request_activation(self) -> bool:
        if not self.exists():
            return False
        # Returning True means only that the request was accepted.  Callers must
        # still wait for observed frontmost state.
        return self.discovery.system.request_activation(self.process_id)

    def wait_for_observed_activation(
            self, timeout: float, poll_interval: float = 0.05) -> bool:
        if timeout < 0 or poll_interval <= 0:
            raise ValueError("timeout must be non-negative and poll_interval positive")
        deadline = self._monotonic() + timeout
        while True:
            if self.is_foreground():
                return True
            if not self.exists() or self._monotonic() >= deadline:
                return False
            self._sleep(min(poll_interval, max(0, deadline - self._monotonic())))
