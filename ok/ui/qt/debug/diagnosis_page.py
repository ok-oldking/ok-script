"""The Diagnosis page: capture, OCR and thread dumps, plus a screenshot viewer.

Every build shows it. Developer tools (reloading tasks, i18n files) and the
Ctrl+Alt+D / Ctrl+Alt+S hotkeys are added only in debug mode.
"""

import os
import re
import threading
import time
from ctypes import byref, windll, wintypes
from dataclasses import dataclass, field

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QSizePolicy, QVBoxLayout,
                               QWidget)

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.feedback import show_toast
from ok.ui.qt.kit.icons import icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.tabs import TabStrip
from ok.ui.qt.kit.theme import theme
from ok.ui.qt.shell import diagnostics
from ok.util.explorer import open_explorer_folder, reveal_in_explorer
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

MAX_SHOTS = 200
REFRESH_MS = 2000
RESULT_TOAST_LENGTH = 200
SUFFIXES = ("_original", "_boxed")
TIME_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})(?:-\d+)?_?")

HOTKEY_DUMP, HOTKEY_CAPTURE = 1, 2


def _t(text: str) -> str:
    # Strings keep the old Debug tab's translation context until i18n is regenerated.
    return QCoreApplication.translate("DebugTab", text)


def _tr(text: str) -> str:
    return QCoreApplication.translate("DiagnosisPage", text)


@dataclass
class Shot:
    """One saved screenshot: its ``_original`` file and, when boxes were drawn, ``_boxed``."""

    stem: str
    mtime: float
    files: dict = field(default_factory=dict)  # "original" / "boxed" -> path

    @property
    def title(self) -> str:
        name = TIME_PREFIX.sub("", self.stem)
        return name or self.stem

    @property
    def time_text(self) -> str:
        return time.strftime("%m-%d %H:%M:%S", time.localtime(self.mtime))

    def path(self, kind: str = "boxed") -> str:
        return self.files.get(kind) or self.files.get("original") or next(iter(self.files.values()))


def list_shots(folder, limit: int = MAX_SHOTS) -> list:
    """Screenshots in ``folder``, newest first, pairing ``_original`` and ``_boxed`` files."""

    if not folder or not os.path.isdir(folder):
        return []
    shots = {}
    try:
        entries = [entry for entry in os.scandir(folder) if entry.is_file() and entry.name.lower().endswith(".png")]
    except OSError:
        return []
    for entry in entries:
        stem, kind = entry.name[:-4], "original"
        for suffix in SUFFIXES:
            if stem.endswith(suffix):
                stem, kind = stem[:-len(suffix)], suffix[1:]
                break
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        shot = shots.setdefault(stem, Shot(stem, mtime))
        shot.mtime = max(shot.mtime, mtime)
        shot.files[kind] = entry.path
    return sorted(shots.values(), key=lambda shot: shot.mtime, reverse=True)[:limit]


class ScreenshotView(QWidget):
    """Draws one image scaled to fit; double click opens the file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("screenshotView")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 200)
        self.path = None
        self._pixmap = None
        self._scaled = None
        self.placeholder = _tr("No screenshot yet. Capture one to see it here.")

    def image_size(self):
        return None if self._pixmap is None else self._pixmap.size()

    def set_image(self, path, image: QImage = None) -> None:
        self.path = path
        self._pixmap = QPixmap.fromImage(image) if image is not None and not image.isNull() else None
        self._scaled = None
        self.update()

    def _target_rect(self):
        if self._pixmap is None:
            return QRectF()
        size = self._pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                      size.width(), size.height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        if self._pixmap is None:
            painter.setPen(theme.color("text_tertiary"))
            painter.setOpacity(0.6)
            glyph = icon("image").pixmap(QSize(40, 40), self.devicePixelRatioF())
            painter.drawPixmap(int((self.width() - 40) / 2), int(self.height() / 2 - 44), glyph)
            painter.setOpacity(1)
            painter.drawText(self.rect().adjusted(0, 24, 0, 24), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            return
        target = self._target_rect()
        ratio = self.devicePixelRatioF()
        wanted = QSize(round(target.width() * ratio), round(target.height() * ratio))
        if self._scaled is None or self._scaled.size() != wanted:
            # Scale once per size; repainting a 5K frame every time would be slow.
            self._scaled = self._pixmap.scaled(wanted, Qt.AspectRatioMode.IgnoreAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            self._scaled.setDevicePixelRatio(ratio)
        painter.drawPixmap(target.topLeft(), self._scaled)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
        super().mouseDoubleClickEvent(event)


class DiagnosisPage(QWidget):
    image_loaded = Signal(str, QImage)
    capture_done = Signal(object)
    ocr_done = Signal(object, object)
    reload_done = Signal(object)

    def __init__(self, exit_event=None, debug: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("DiagnosisPage")
        self.debug = debug
        self.shots = []
        self._signature = None
        self._kind = "boxed"
        self._load_token = 0

        self.capture_button = Button(_t("Capture Screenshot"), "camera", "primary")
        self.capture_button.clicked.connect(self.capture)
        self.ocr_button = Button("OCR", "scan")
        self.ocr_button.setToolTip(_tr("Run OCR on the current frame and save a screenshot with the text boxes"))
        self.ocr_button.clicked.connect(self.run_ocr)
        self.dump_button = Button(_tr("Dump Threads"), "layers")
        self.dump_button.setToolTip(_tr("Write every thread's stack to logs/thread_dumps.txt"))
        self.dump_button.clicked.connect(self.dump_threads)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(Label(QCoreApplication.translate("MainWindow", "Diagnosis"), "display", self))
        header.addStretch(1)
        self.dev_button = None
        self.reload_action = None
        if debug:
            self.dev_button = Button(_tr("Developer"), "code", "subtle")
            menu = QMenu(self.dev_button)
            self.reload_action = menu.addAction(_t("Reload tasks"), self.reload_tasks)
            menu.addSeparator()
            menu.addAction(_t("Generate i18n files"), self.gen_tr)
            menu.addAction(_t("Convert i18n files"), self.convert_tr)
            self.dev_button.clicked.connect(lambda: menu.exec(
                self.dev_button.mapToGlobal(self.dev_button.rect().bottomLeft())))
            self.dev_menu = menu
            header.addWidget(self.dev_button)
        header.addWidget(self.dump_button)
        header.addWidget(self.ocr_button)
        header.addWidget(self.capture_button)

        # Viewer: file name and box toggle above the image.
        self.title_label = Label("", "strong", self)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.meta_label = Label("", "caption", self)
        self.kind_tabs = TabStrip("pill")
        self.kind_tabs.add_tab("boxed", _tr("Boxes"))
        self.kind_tabs.add_tab("original", _tr("Original"))
        self.kind_tabs.set_current("boxed")
        self.kind_tabs.current_changed.connect(self._on_kind_changed)
        self.open_button = Button(icon="export", variant="subtle")
        self.open_button.setToolTip(_tr("Open image"))
        self.open_button.clicked.connect(self.open_image)
        self.reveal_button = Button(icon="folder", variant="subtle")
        self.reveal_button.setToolTip(_tr("Show in folder"))
        self.reveal_button.clicked.connect(self.reveal_image)
        self.view = ScreenshotView()

        title_text = QVBoxLayout()
        title_text.setSpacing(2)
        title_text.addWidget(self.title_label)
        title_text.addWidget(self.meta_label)
        viewer_bar = QHBoxLayout()
        viewer_bar.setSpacing(6)
        viewer_bar.addLayout(title_text, 1)
        viewer_bar.addWidget(self.kind_tabs)
        viewer_bar.addSpacing(6)
        viewer_bar.addWidget(self.open_button)
        viewer_bar.addWidget(self.reveal_button)

        viewer = Card(self)
        viewer_layout = QVBoxLayout(viewer)
        viewer_layout.setContentsMargins(16, 12, 16, 16)
        viewer_layout.setSpacing(12)
        viewer_layout.addLayout(viewer_bar)
        viewer_layout.addWidget(self.view, 1)

        # Recent screenshots, newest first.
        self.count_label = Label("", "caption", self)
        folder_button = Button(icon="folder", variant="subtle", size="small")
        folder_button.setToolTip(_tr("Open screenshot folder"))
        folder_button.clicked.connect(diagnostics.open_screenshot_folder)
        list_header = QHBoxLayout()
        list_header.setSpacing(6)
        list_header.addWidget(Label(_tr("Recent"), "subtitle", self))
        list_header.addWidget(self.count_label)
        list_header.addStretch(1)
        list_header.addWidget(folder_button)
        self.shot_list = QListWidget()
        self.shot_list.setObjectName("shotList")
        self.shot_list.setUniformItemSizes(True)
        self.shot_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.shot_list.currentRowChanged.connect(self._on_row_changed)
        side = QWidget()
        side.setFixedWidth(320)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        side_layout.addLayout(list_header)
        side_layout.addWidget(self.shot_list, 1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(viewer, 1)
        body.addWidget(side)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addLayout(body, 1)
        theme.install(self)

        self.image_loaded.connect(self._on_image_loaded)
        self.capture_done.connect(self._on_capture_done)
        self.ocr_done.connect(self._on_ocr_done)
        self.reload_done.connect(self._on_reload_done)
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh)
        self._show_selection()

        self.hotkey_handler = None
        if debug and exit_event is not None:
            from ok import Handler
            # Hotkeys are registered to, and polled on, their own thread so that a
            # busy tool (capture waiting for WGC) cannot block Ctrl+Alt+D.
            self.hotkey_handler = Handler(exit_event, "DiagnosisHotkeys")
            self.hotkey_handler.post(self.bind_hot_keys)
            self.hotkey_handler.post(self.check_hotkey, 0.1)
            og.app.app.aboutToQuit.connect(self.unregister)

    # --- lifecycle --------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.timer.stop()

    # --- screenshot list ----------------------------------------------------------

    def current_shot(self):
        row = self.shot_list.currentRow()
        return self.shots[row] if 0 <= row < len(self.shots) else None

    def refresh(self) -> None:
        shots = list_shots(diagnostics.screenshot_folder())
        signature = [(shot.stem, shot.mtime, tuple(sorted(shot.files))) for shot in shots]
        if signature == self._signature:
            return
        self._signature = signature
        current = self.current_shot()
        # Follow new screenshots unless an older one was picked.
        follow = current is None or self.shot_list.currentRow() == 0
        self.shots = shots
        self.shot_list.blockSignals(True)
        self.shot_list.clear()
        for shot in shots:
            item = QListWidgetItem(f"{shot.title}\n{shot.time_text}")
            item.setToolTip(shot.path("original"))
            item.setSizeHint(QSize(0, 52))
            self.shot_list.addItem(item)
        row = 0 if follow or current is None else next(
            (i for i, shot in enumerate(shots) if shot.stem == current.stem), 0)
        if shots:
            self.shot_list.setCurrentRow(row)
        self.shot_list.blockSignals(False)
        self.count_label.setText(str(len(shots)) if shots else "")
        selected = shots[row] if shots else None
        # Reload when the file changed too: a refresh can catch a PNG mid-write.
        if selected is None or current is None or (selected.stem, selected.mtime, selected.files) != (
                current.stem, current.mtime, current.files):
            self._show_selection()

    def select_path(self, path) -> None:
        """Select the screenshot saved at ``path``."""

        self._signature = None
        self.refresh()
        for row, shot in enumerate(self.shots):
            if path in shot.files.values():
                self.shot_list.blockSignals(True)
                self.shot_list.setCurrentRow(row)
                self.shot_list.blockSignals(False)
                self._show_selection()
                return

    def _on_row_changed(self, _row) -> None:
        self._show_selection()

    def _on_kind_changed(self, kind) -> None:
        self._kind = kind
        self._show_selection()

    def _show_selection(self) -> None:
        shot = self.current_shot()
        has_shot = shot is not None
        self.open_button.setEnabled(has_shot)
        self.reveal_button.setEnabled(has_shot)
        self.kind_tabs.setVisible(has_shot and len(shot.files) > 1)
        if not has_shot:
            self.title_label.setText(_tr("Screenshots"))
            self.meta_label.setText(_tr("Captures, OCR results and task screenshots appear here."))
            self.view.set_image(None)
            return
        path = shot.path(self._kind)
        self.title_label.setText(shot.title)
        self.meta_label.setText(shot.time_text)
        self._load(path)

    def _load(self, path) -> None:
        # Decoding a 5K PNG takes a while; do it off the GUI thread.
        self._load_token += 1
        token = self._load_token

        def run():
            image = QImage(path)
            if token == self._load_token:
                self.image_loaded.emit(path, image)

        threading.Thread(target=run, name="ScreenshotLoad", daemon=True).start()

    def _on_image_loaded(self, path, image) -> None:
        shot = self.current_shot()
        if shot is None or path not in shot.files.values():
            return
        self.view.set_image(path, image)
        if not image.isNull():
            self.meta_label.setText(f"{shot.time_text}  ·  {image.width()}×{image.height()}")

    def open_image(self) -> None:
        if self.view.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.view.path))

    def reveal_image(self) -> None:
        if self.view.path:
            reveal_in_explorer(self.view.path)

    # --- tools --------------------------------------------------------------------

    def capture(self) -> None:
        self.capture_button.setEnabled(False)
        diagnostics.capture_screenshot(done=self.capture_done.emit)

    def _on_capture_done(self, path) -> None:
        self.capture_button.setEnabled(True)
        if path:
            self.select_path(path)

    def run_ocr(self) -> None:
        tasks = og.executor.get_all_tasks()
        if not tasks:
            return
        task = tasks[0]
        from ok.core.code_runner import submit_call
        from ok.task.exceptions import ExecutorBusyException
        try:
            # A job on the executor gets frames even while the executor is paused.
            job = submit_call(og.executor, lambda: task.ocr(log=True, screenshot=True), name='diagnosis_ocr')
        except ExecutorBusyException as e:
            show_toast(self, QCoreApplication.translate('JobControls', 'The app is controlled by {owner}').format(
                owner=e.owner), "OCR", tone="danger")
            return
        self.ocr_button.setEnabled(False)
        job.future.add_done_callback(lambda _: self.ocr_done.emit(job, None))

    def _on_ocr_done(self, job, _unused=None) -> None:
        from ok.core.code_runner import wait_result
        self.ocr_button.setEnabled(True)
        result = wait_result(job)
        if result.cancelled:
            return
        if result.error:
            logger.error(f'diagnosis ocr exception {result.error}')
            show_toast(self, result.error.strip().splitlines()[-1], "OCR", tone="danger")
            return
        texts = ", ".join(box.name for box in result.raw or [])
        show_toast(self, texts[:RESULT_TOAST_LENGTH] or _tr("No text found"), "OCR", tone="success")
        # The OCR screenshot is written by a background queue; pick it up shortly.
        QTimer.singleShot(800, self.refresh)

    def dump_threads(self) -> None:
        from ok.capture.windows.dump import dump_threads
        from ok.util.file import get_relative_path
        dump_threads()
        path = get_relative_path(os.path.join('logs', "thread_dumps.txt"))
        show_toast(self, _tr("Saved to {path}").format(path=path), _tr("Dump Threads"), tone="success",
                   action=(_tr("Open"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path))))

    def reload_tasks(self) -> None:
        try:
            job = og.task_manager.reload_tasks()
        except Exception as error:
            show_toast(self, str(error), tone="danger")
            return
        self.reload_action.setEnabled(False)
        job.future.add_done_callback(lambda _: self.reload_done.emit(job))

    def _on_reload_done(self, job) -> None:
        self.reload_action.setEnabled(True)
        try:
            tasks = job.future.result()
        except Exception as error:
            logger.error('Task reload failed', error)
            show_toast(self, str(error), tone="danger")
            return
        show_toast(self, _t('Reloaded {count} tasks').format(count=len(tasks)), tone="success")

    @staticmethod
    def gen_tr() -> None:
        reveal_in_explorer(og.app.gen_tr_po_files())

    @staticmethod
    def convert_tr() -> None:
        from ok.core.translation import convert_to_mo_files
        convert_to_mo_files()

    # --- debug hotkeys --------------------------------------------------------------

    def bind_hot_keys(self) -> None:
        mod_alt, mod_control, vk_d, vk_s = 0x0001, 0x0002, 0x44, 0x53
        if not windll.user32.RegisterHotKey(None, HOTKEY_DUMP, mod_alt | mod_control, vk_d):
            logger.debug("Failed to register hotkey for Alt+Ctrl+D")
        if not windll.user32.RegisterHotKey(None, HOTKEY_CAPTURE, mod_alt | mod_control, vk_s):
            logger.debug("Failed to register hotkey for Alt+Ctrl+S")

    def check_hotkey(self) -> None:
        msg = wintypes.MSG()
        if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1) and msg.message == 0x0312:  # WM_HOTKEY
            if msg.wParam == HOTKEY_DUMP:
                from ok.capture.windows.dump import dump_threads
                dump_threads()
            elif msg.wParam == HOTKEY_CAPTURE:
                diagnostics.capture_screenshot(done=self.capture_done.emit)
        self.hotkey_handler.post(self.check_hotkey, 0.1)

    @staticmethod
    def unregister() -> None:
        windll.user32.UnregisterHotKey(None, HOTKEY_DUMP)
        windll.user32.UnregisterHotKey(None, HOTKEY_CAPTURE)
