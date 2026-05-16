from ok.util.logger import Logger
from ok.util.window import windows_graphics_available

from ok.device.capture_methods import bitblt
from ok.device.capture_methods.bitblt import BitBltCaptureMethod, ForegroundBitBltCaptureMethod
from ok.device.capture_methods.desktop_duplication import DesktopDuplicationCaptureMethod
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod

logger = Logger.get_logger(__name__)

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
    if windows_graphics_available():
        target_method = WindowsGraphicsCaptureMethod
        capture_method = get_capture(capture_method, target_method, hwnd, exit_event)
        if capture_method.start_or_stop():
            return capture_method



def get_capture(capture_method, target_method, hwnd, exit_event):
    if not isinstance(capture_method, target_method):
        if capture_method is not None:
            capture_method.close()
        capture_method = target_method(hwnd)
    capture_method.hwnd_window = hwnd
    capture_method.exit_event = exit_event
    return capture_method
