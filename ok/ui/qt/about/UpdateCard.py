import os
import threading

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtGui import QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CheckBox, ComboBox, FluentIcon, IndeterminateProgressRing, \
    PrimaryPushButton, PushButton

from ok.util.logger import Logger


logger = Logger.get_logger(__name__)


def _is_numeric_version(version):
    try:
        return bool(version) and all(part.isdigit() for part in version.lstrip("v").split("."))
    except AttributeError:
        return False


class ChangeLogView(BodyLabel):
    """A non-interactive, word-wrapped changelog that follows its text height."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)

    def setPlainText(self, text):
        self.setText(text)

    def toPlainText(self):
        return self.text()


class UpdateCard(QWidget):
    """Version picker and release-note viewer backed by the PyAppify launcher API."""

    update_available_changed = Signal(bool)
    check_started = Signal()
    _versions_loaded = Signal(object)
    _update_finished = Signal(object)
    VERSION_COMBO_MIN_WIDTH = 100
    VERSION_COMBO_MAX_WIDTH = 240

    def __init__(self, current_version, pyappify_module, parent=None, exit_event=None):
        super().__init__(parent)
        self.current_version = current_version or getattr(pyappify_module, "app_version", None) or ""
        if "PYAPPIFY_PYTHON_TEST" in os.environ and not _is_numeric_version(self.current_version):
            logger.info(f"using v0.0.0 for nonnumeric test version {self.current_version!r}")
            self.current_version = "v0.0.0"
        self.pyappify_module = pyappify_module
        self.exit_event = exit_event
        self.versions = []
        self._busy = False
        logger.info(
            f"initialized current_version={self.current_version!r}, "
            f"pyappify_module={getattr(pyappify_module, '__file__', type(pyappify_module).__name__)!r}, "
            f"pyappify_app_version={getattr(pyappify_module, 'app_version', None)!r}, "
            f"test_mode={'PYAPPIFY_PYTHON_TEST' in os.environ}"
        )

        self.version_combo = ComboBox(self)
        self.version_combo.setFixedWidth(self.VERSION_COMBO_MIN_WIDTH)
        self.version_combo.currentIndexChanged.connect(self._selection_changed)

        self.test_version_checkbox = CheckBox(self.tr("Check Test Version"), self)
        self.test_version_checkbox.setChecked(False)
        self.check_button = PushButton(FluentIcon.SYNC, self.tr("Check for updates"), self)
        loading_icon_pixmap = QPixmap(16, 16)
        loading_icon_pixmap.fill(Qt.GlobalColor.transparent)
        self._loading_placeholder_icon = QIcon(loading_icon_pixmap)
        self.check_progress = IndeterminateProgressRing(self.check_button, start=False)
        self.check_progress.setFixedSize(16, 16)
        self.check_progress.setStrokeWidth(2)
        self.check_progress.hide()
        self.check_button.setMinimumWidth(self.check_button.sizeHint().width())
        self.check_button.installEventFilter(self)
        self.check_button.clicked.connect(self.check_for_updates)
        self.update_button = PrimaryPushButton(FluentIcon.UPDATE, self.tr("Update"), self)
        self.update_button.clicked.connect(self.update_to_selected_version)
        self.update_button.setEnabled(False)

        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.version_label = BodyLabel(self.tr("Version"), self)
        self.status_label = BodyLabel(self.tr("Click to check for updates"), self)
        self.controls_layout.addWidget(self.version_label)
        self.controls_layout.addWidget(self.version_combo)
        self.controls_layout.addWidget(self.status_label)
        self.controls_layout.addStretch(1)
        self.controls_layout.addWidget(self.test_version_checkbox)
        self.controls_layout.addWidget(self.check_button)
        self.controls_layout.addWidget(self.update_button)
        self._set_version_controls_visible(False)

        self.notes_edit = ChangeLogView("", self)
        self.notes_edit.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(self.controls_layout)
        layout.addWidget(self.notes_edit)

        self._versions_loaded.connect(self._apply_versions)
        self._update_finished.connect(self._apply_update_result)

    def check_for_updates(self):
        if self._busy:
            return
        get_versions = getattr(self.pyappify_module, "get_version_list", None)
        if not callable(get_versions):
            self._show_error(self.tr("Update checking is not supported by this PyAppify version."))
            return
        self._set_busy(True, checking=True)
        self.check_started.emit()
        self._set_status(self.tr("Checking for updates…"))
        release_only = not self.test_version_checkbox.isChecked()
        self._run_in_background(
            lambda: get_versions(release_only=release_only, exit_event=self.exit_event),
            self._versions_loaded,
            f"pyappify.get_version_list(release_only={release_only})",
        )

    def update_to_selected_version(self):
        if self._busy or self.version_combo.currentIndex() < 0:
            return
        update_to_version = getattr(self.pyappify_module, "update_to_version", None)
        if not callable(update_to_version):
            self._show_error(self.tr("Updating is not supported by this PyAppify version."))
            return
        version = self.version_combo.currentText()
        self._set_busy(True)
        self._set_status(self.tr("Starting change to {version}…").format(version=version))
        self._run_in_background(
            lambda: update_to_version(version, exit_event=self.exit_event),
            self._update_finished,
            f"pyappify.update_to_version({version!r})",
        )

    def _run_in_background(self, operation, signal, operation_name):
        def run():
            logger.info(f"calling {operation_name}")
            try:
                result = operation()
                logger.info(f"{operation_name} result={result!r}")
                signal.emit((True, result))
            except Exception as error:
                logger.error(f"{operation_name} failed: {error}", error)
                signal.emit((False, str(error)))

        threading.Thread(target=run, daemon=True, name="pyappify-update").start()

    def _apply_versions(self, result):
        self._set_busy(False, refresh_selection=False)
        successful, value = result
        if not successful:
            self.versions = []
            self.version_combo.clear()
            self._set_version_controls_visible(False)
            self.update_available_changed.emit(False)
            self._show_error(self.tr("Failed to check for updates: {error}").format(error=value))
            return

        self.versions = [item for item in value if isinstance(item, dict) and item.get("version")]
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItems([str(item["version"]) for item in self.versions])
        self.version_combo.blockSignals(False)
        self._resize_version_combo()
        logger.info(
            f"loaded {len(self.versions)} valid versions into selector: "
            f"{[item['version'] for item in self.versions]!r}"
        )

        newest_update = next(
            (index for index, item in enumerate(self.versions)
             if self._compare_versions(str(item["version"]), self.current_version) > 0),
            None,
        )
        self.update_available_changed.emit(newest_update is not None)
        logger.info(
            f"update_available={newest_update is not None}, current_version={self.current_version!r}, "
            f"newest_update_index={newest_update!r}"
        )
        if not self.versions:
            self._set_version_controls_visible(False)
            self._set_notes("")
            self._set_status(self.tr("No versions are available."))
            self.update_button.setEnabled(False)
            return
        self._set_version_controls_visible(True)
        self._set_status("" if newest_update is not None else self.tr("No updates available."))
        self.version_combo.setCurrentIndex(0)
        self._selection_changed()

    def _selection_changed(self, _index=None):
        index = self.version_combo.currentIndex()
        if index < 0 or index >= len(self.versions):
            self.update_button.setEnabled(False)
            return
        selected = self.versions[index]
        target = str(selected["version"])
        direction = self._compare_versions(target, self.current_version)
        logger.debug(
            f"selected version={target!r}, current_version={self.current_version!r}, direction={direction}"
        )
        self.update_button.setEnabled(direction != 0 and not self._busy)
        self.update_button.setText(self.tr("Update") if direction > 0 else self.tr("Downgrade"))

        if direction == 0:
            self.update_button.setText(self.tr("Current version"))

        calculate_notes = getattr(self.pyappify_module, "calculate_update_notes", None)
        if not callable(calculate_notes):
            self._set_notes("")
            self._set_status(self.tr("Update-note calculation is not supported."), error=True)
            return
        try:
            notes = calculate_notes(self.versions, self.current_version, target)
            self._set_notes(
                "\n".join(f"• {note}" for note in notes) or self.tr("No release notes.")
            )
        except Exception as error:
            logger.error(f"pyappify.calculate_update_notes failed: {error}", error)
            self._set_notes("")
            self._set_status(self.tr("Failed to calculate update notes: {error}").format(error=error), error=True)

    def _resize_version_combo(self):
        font_metrics = QFontMetrics(self.version_combo.font())
        text_width = max(
            (font_metrics.horizontalAdvance(str(item["version"])) for item in self.versions),
            default=0,
        )
        content_width = text_width + 48
        width = max(self.VERSION_COMBO_MIN_WIDTH, min(self.VERSION_COMBO_MAX_WIDTH, content_width))
        self.version_combo.setFixedWidth(width)

    def _set_version_controls_visible(self, visible):
        self.version_label.setVisible(visible)
        self.version_combo.setVisible(visible)

    def _set_notes(self, text):
        self.notes_edit.setPlainText(text)
        self.notes_edit.setVisible(bool(text))

    def _set_check_loading(self, loading):
        if loading:
            self.check_button.setIcon(self._loading_placeholder_icon)
            self.check_progress.show()
            self.check_progress.start()
        else:
            self.check_progress.stop()
            self.check_progress.hide()
            self.check_button.setIcon(FluentIcon.SYNC)
        self._position_check_progress()

    def _position_check_progress(self):
        minimum_width = self.check_button.minimumSizeHint().width()
        x = 12 + max(0, (self.check_button.width() - minimum_width) // 2)
        self.check_progress.move(x, (self.check_button.height() - self.check_progress.height()) // 2)

    def eventFilter(self, watched, event):
        if watched is self.check_button and event.type() == QEvent.Type.Resize:
            self._position_check_progress()
        return super().eventFilter(watched, event)

    def _apply_update_result(self, result):
        self._set_busy(False)
        successful, value = result
        if successful:
            self._set_status(self.tr("Update request accepted. The app will restart to apply it."))
        else:
            self._show_error(self.tr("Failed to change version: {error}").format(error=value))

    def _set_busy(self, busy, checking=False, refresh_selection=True):
        self._busy = busy
        self.check_button.setEnabled(not busy)
        self._set_check_loading(busy and checking)
        self.test_version_checkbox.setEnabled(not busy)
        self.version_combo.setEnabled(not busy)
        if busy:
            self.update_button.setEnabled(False)
        elif refresh_selection:
            self._selection_changed()

    def _show_error(self, message):
        self._set_busy(False, refresh_selection=False)
        self._set_notes("")
        self._set_status(message, error=True)

    def _set_status(self, message, error=False):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #d13438;" if error else "")

    def _compare_versions(self, left, right):
        if left == right:
            return 0
        is_greater = getattr(self.pyappify_module, "is_greater_version", None)
        if callable(is_greater):
            if is_greater(left, right):
                return 1
            if is_greater(right, left):
                return -1
        return 0
