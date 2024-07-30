from ok.logging.Logger import get_logger

logger = get_logger(__name__)


def update_capture_method(config, capture_method, hwnd, require_bg=False, use_bit_blt_only=False,
                          bit_blt_render_full=False):
    try:
        if config.get('can_bit_blt'):  # slow try win graphics first
            if bit_blt_render_full:
                if win_graphic := get_win_graphics_capture(capture_method, hwnd):
                    return win_graphic
                logger.debug(
                    f"try BitBlt method {config} {hwnd} current_type:{type(capture_method)}")
            from ok.capture.windows.BitBltCaptureMethod import BitBltCaptureMethod
            BitBltCaptureMethod.render_full = config.get('bit_blt_render_full', False)
            target_method = BitBltCaptureMethod
            capture_method = get_capture(capture_method, target_method, hwnd)
            if bit_blt_render_full or capture_method.test_is_not_pure_color():
                return capture_method
            else:
                logger.info("test_is_not_pure_color failed, can't use BitBlt")
        if use_bit_blt_only:
            return None
        if win_graphic := get_win_graphics_capture(capture_method, hwnd):
            return win_graphic

        if not require_bg:
            from ok.capture.windows.DesktopDuplicationCaptureMethod import DesktopDuplicationCaptureMethod
            target_method = DesktopDuplicationCaptureMethod
            capture_method = get_capture(capture_method, target_method, hwnd)
            return capture_method
    except Exception as e:
        logger.error(f'update_capture_method exception, return None: ', e)


def get_win_graphics_capture(capture_method, hwnd):
    from ok.capture.windows.WindowsGraphicsCaptureMethod import windows_graphics_available
    if windows_graphics_available():
        from ok.capture.windows.WindowsGraphicsCaptureMethod import WindowsGraphicsCaptureMethod
        target_method = WindowsGraphicsCaptureMethod
        capture_method = get_capture(capture_method, target_method, hwnd)
        if capture_method.start_or_stop():
            return capture_method


def get_capture(capture_method, target_method, hwnd):
    if not isinstance(capture_method, target_method):
        if capture_method is not None:
            capture_method.close()
        capture_method = target_method(hwnd)
    capture_method.hwnd_window = hwnd
    return capture_method
