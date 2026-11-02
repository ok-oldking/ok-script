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


def capture_screenshot(done=None) -> None:
    """Save a screenshot off the GUI thread; capturing can wait for a running task."""

    from ok import og
    from ok.ui.qt.debug.DebugTab import capture

    processor = og.config.get('screenshot_processor')

    def run():
        try:
            capture(processor=processor)
        finally:
            if done is not None:
                done()

    threading.Thread(target=run, name="Screenshot", daemon=True).start()
