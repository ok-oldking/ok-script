"""Log, folder and OCR helpers offered from the connection popover."""

import os
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from ok.util.explorer import open_explorer_folder, reveal_in_explorer
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def _tr(text: str) -> str:
    # Strings keep their original translation context until i18n is regenerated.
    return QCoreApplication.translate("StartTab", text)


def open_install_folder() -> None:
    open_explorer_folder(os.getcwd())


def open_screenshot_folder() -> None:
    from ok import og
    screenshot = getattr(og.ok, 'screenshot', None)
    folder = getattr(screenshot, 'screenshot_folder', None)
    if folder is None:
        folder = Path.cwd() / "screenshots"
        logger.info(f'screenshot folder was not initialized; using fallback={str(folder)!r}')
    open_explorer_folder(folder)


def open_log_folder() -> None:
    open_explorer_folder(Path.cwd() / "logs")


def export_logs() -> None:
    from ok import og
    from ok.ui.qt.util.Alert import alert_error
    from ok.util.file import get_downloads_folder
    app_name = og.config.get('gui_title')
    downloads_path = Path(get_downloads_folder())
    zip_path = downloads_path / f"{app_name}-log.zip"
    try:
        downloads_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for folder in ("screenshots", "logs"):
                source_dir = Path.cwd() / folder
                if not source_dir.is_dir():
                    continue
                for file_path in source_dir.rglob("*"):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(Path.cwd()))
        reveal_in_explorer(zip_path)
    except Exception as e:
        alert_error(f"{og.app.tr('Export failed')}: {e}", tray=True)
        logger.error('export_logs exception', e)


def _ocr_log() -> None:
    from ok import og
    from ok.ui.qt.util.Alert import alert_error, alert_info
    try:
        if og.executor.paused:
            alert_error(_tr("Please Start First"))
            return
        result = og.executor.get_all_tasks()[0].ocr(log=True, screenshot=True)
        alert_info(_tr(f"OCR success (Logged): {result}"))
        folder = og.ok.screenshot.screenshot_folder
        if folder:
            folder_abs = os.path.abspath(folder)
            if result:
                with open(os.path.join(folder_abs, 'ocr_result.txt'), 'w', encoding='utf-8') as f:
                    for box in result:
                        f.write(f"{box.name}, {box}, {box.confidence}\n")
            open_explorer_folder(folder_abs)
    except Exception as e:
        logger.error('debug ocr_log exception', e)


def ocr_log() -> None:
    threading.Thread(target=_ocr_log, name="OcrLog", daemon=True).start()


def screenshot_folder():
    from ok import og
    screenshot = getattr(og.ok, 'screenshot', None)
    return getattr(screenshot, 'screenshot_folder', None)


def capture(processor=None):
    """Save the current frame, with task boxes, and return the original's path or ``None``."""

    from ok import og
    from ok.core.screenshot import screenshot_file_stem
    from ok.device.capture import CAPTURE_BUSY_WAIT
    from ok.ui.qt.util.Alert import alert_error
    capture_method = og.device_manager.capture_method
    if capture_method is None:
        alert_error(QCoreApplication.translate('DebugTab', 'No Capture Available or Selected'))
        return None
    logger.info(f'capture with {capture_method}')
    try:
        frame = capture_method.get_frame(busy_wait=CAPTURE_BUSY_WAIT)
        if frame is None:
            alert_error(QCoreApplication.translate('DebugTab', 'Capture returned None'))
            return None
        screenshot = og.ok.screenshot
        return screenshot.generate_screen_shot(frame, screenshot.ui_dict, screenshot.screenshot_folder,
                                               screenshot_file_stem(type(capture_method).__name__), True, None,
                                               processor=processor)
    except Exception as e:
        logger.error('capture failed', e)
        alert_error(str(e))
        return None


def capture_screenshot(done=None) -> None:
    """Save a screenshot off the GUI thread; capturing can wait for a running task.

    ``done`` gets the saved file's path, or ``None``.
    """

    from ok import og

    processor = og.config.get('screenshot_processor')

    def run():
        path = None
        try:
            path = capture(processor=processor)
        finally:
            if done is not None:
                done(path)

    threading.Thread(target=run, name="Screenshot", daemon=True).start()
