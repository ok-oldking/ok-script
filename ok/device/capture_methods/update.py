import time

from ok.util.logger import Logger
from ok.util.window import windows_graphics_available

from ok.device.capture_methods import bitblt
from ok.device.capture_methods.bitblt import BitBltCaptureMethod, ForegroundBitBltCaptureMethod
from ok.device.capture_methods.desktop_duplication import DesktopDuplicationCaptureMethod
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod
from ok.task.exceptions import CaptureBusyException

logger = Logger.get_logger(__name__)

WGC_FIRST_FRAME_TIMEOUT = 1.5


def update_capture_method(config, capture_method, hwnd, exit_event=None, selected_method=None):
    try:
        method_preferences = config.get('capture_method', [])
        if selected_method and selected_method in method_preferences:
            method_preferences = [selected_method] + [m for m in method_preferences if m != selected_method]

        for method_name in method_preferences:
            if method_name == 'WGC':
                if win_graphic := get_win_graphics_capture(capture_method, hwnd, exit_event):
                    logger.info(f'use WGC capture')
                    return win_graphic
            elif method_name in ('BitBlt', 'BitBlt_RenderFull'):
                bitblt.render_full = (method_name == 'BitBlt_RenderFull')
                logger.info(f'use {method_name} capture render_full: {bitblt.render_full}')

                if bitblt_capture := get_capture(capture_method, BitBltCaptureMethod, hwnd, exit_event):
                    return bitblt_capture
            elif method_name in ('ForegroundBitBlt', 'Foreground BitBlt', 'Foreground', 'LosslessScaling', 'Lossless Scaling'):
                if foreground_capture := get_capture(capture_method, ForegroundBitBltCaptureMethod, hwnd, exit_event):
                    logger.info(f'use {method_name} capture')
                    return foreground_capture
            elif method_name == 'DXGI':
                if dxgi_capture := get_capture(capture_method, DesktopDuplicationCaptureMethod, hwnd, exit_event):
                    return dxgi_capture

        return None
    except Exception as e:
        logger.error(f'update_capture_method exception, return None: {e}')
        return None

def get_win_graphics_capture(capture_method, hwnd, exit_event):
    if not windows_graphics_available():
        return None

    target_method = WindowsGraphicsCaptureMethod
    capture_method = get_capture(capture_method, target_method, hwnd, exit_event)

    try:
        started = capture_method.start_or_stop()
    except CaptureBusyException:
        # A concurrent request already owns this WGC instance. That is evidence
        # of active use, not a startup failure. Keep WGC selected and let the
        # normal caller retry.
        logger.debug('WGC startup validation deferred because capture is busy')
        return capture_method

    if started:
        try:
            if _capture_can_produce_frame(capture_method, WGC_FIRST_FRAME_TIMEOUT):
                return capture_method
        except CaptureBusyException:
            # Do not close or cache a WGC instance merely because another
            # caller occupied its request lock for the probe interval.
            logger.debug('WGC first-frame probe deferred because capture is busy')
            return capture_method

    # Only genuine startup failure, or an acquired probe that produced no
    # frame, reaches this point.
    if isinstance(capture_method, WindowsGraphicsCaptureMethod):
        capture_hwnd = capture_method.get_capture_hwnd()
        if capture_hwnd:
            capture_method.last_start_failure_key = capture_hwnd
            capture_method.last_start_failure_time = time.time()
        capture_method.close()

    return None


def _capture_can_produce_frame(capture_method, timeout):
    deadline = time.monotonic() + max(0.0, float(timeout))

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning(f'{capture_method.get_name()} did not produce a frame within {timeout}s')
            return False

        try:
            frame = capture_method.get_frame_for_probe(remaining)
        except CaptureBusyException:
            # Preserve the distinction for get_win_graphics_capture(): a busy
            # WGC must not be closed, cached as failed, or replaced by BitBlt.
            raise
        except Exception as e:
            logger.warning(f'{capture_method.get_name()} did not produce a frame: {e}')
            return False

        if frame is not None:
            return True

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning(f'{capture_method.get_name()} did not produce a frame within {timeout}s')
            return False

        time.sleep(min(0.05, remaining))

def get_capture(capture_method, target_method, hwnd, exit_event):
    if not isinstance(capture_method, target_method):
        if capture_method is not None:
            capture_method.close()
        capture_method = target_method(hwnd)
    capture_method.hwnd_window = hwnd
    capture_method.exit_event = exit_event
    return capture_method
