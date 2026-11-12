import inspect
import os
import threading

from PySide6.QtCore import QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ok.core.events import communicate
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.feedback import ProgressRing
from ok.ui.qt.kit.inputs import ComboBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme
from ok.util.logger import Logger


logger = Logger.get_logger(__name__)


def _is_numeric_version(version):
    try:
        return bool(version) and all(part.isdigit() for part in version.lstrip("v").split("."))
    except AttributeError:
        return False


def _accepts_language(function):
    """Whether ``function`` takes a ``language`` argument (newer pyappify versions)."""
    try:
        return "language" in inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False


def _ui_locale():
    """The app's UI locale, such as ``zh_CN``, for update notes from the app's changelogs."""
    try:
        from ok.ui.qt.common.config import cfg

        return cfg.language.value.name()
    except Exception as error:
        logger.warning(f"could not read the UI language for update notes: {error}")
        return None


def _is_local_checkout(pyappify_module):
    """Whether the app runs from a plain git clone instead of the PyAppify launcher."""
    is_local_checkout = getattr(pyappify_module, "is_local_checkout", None)
    if not callable(is_local_checkout):
        return False
    try:
        return bool(is_local_checkout())
    except Exception as error:
        logger.warning(f"pyappify.is_local_checkout failed: {error}")
        return False


# A checkout's versions say how they relate to the checked-out commit, since a
# branch or pull request has no version number to compare. None is a switch to
# a commit that is neither newer nor older.
_RELATION_DIRECTIONS = {"current": 0, "newer": 1, "older": -1, "other": None}
_TAG_KINDS = (None, "tag")
# Kinds whose newer version is announced as an update: not a local branch or a
# pull request, which are only ever switched to on purpose.
_UPDATE_KINDS = (None, "tag", "branch")


class ChangeLogView(Label):
    """A non-interactive, word-wrapped changelog that follows its text height."""

    def __init__(self, text="", parent=None):
        super().__init__("", "body", parent, word_wrap=True)
        self.setText(text)
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
    new_version_available = Signal(str)
    check_started = Signal()
    _versions_loaded = Signal(object)
    _update_finished = Signal(object)
    VERSION_COMBO_MIN_WIDTH = 120
    VERSION_COMBO_MAX_WIDTH = 240

    def __init__(self, current_version, pyappify_module, parent=None, exit_event=None, download_url=None):
        super().__init__(parent)
        self.current_version = current_version or getattr(pyappify_module, "app_version", None) or ""
        if "PYAPPIFY_PYTHON_TEST" in os.environ and not _is_numeric_version(self.current_version):
            logger.info(f"using v0.0.0 for nonnumeric test version {self.current_version!r}")
            self.current_version = "v0.0.0"
        self.pyappify_module = pyappify_module
        self.local_checkout = _is_local_checkout(pyappify_module)
        self.exit_event = exit_event
        self.download_url = download_url
        self.versions = []
        self._busy = False
        self._automatic_check = False
        logger.info(
            f"initialized current_version={self.current_version!r}, "
            f"pyappify_module={getattr(pyappify_module, '__file__', type(pyappify_module).__name__)!r}, "
            f"pyappify_app_version={getattr(pyappify_module, 'app_version', None)!r}, "
            f"test_mode={'PYAPPIFY_PYTHON_TEST' in os.environ}, local_checkout={self.local_checkout}"
        )

        self.version_label = Label(self.tr("Version"), "secondary", self)
        self.version_combo = ComboBox(parent=self)
        self.version_combo.setFixedWidth(self.VERSION_COMBO_MIN_WIDTH)
        self.version_combo.currentIndexChanged.connect(self._selection_changed)
        self.status_label = Label(self.tr("Click to check for updates"), "secondary", self, word_wrap=True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setMinimumWidth(0)
        status_size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_size_policy.setHeightForWidth(True)
        self.status_label.setSizePolicy(status_size_policy)

        self.download_button = Button(self.tr("Download"), "download", "primary", parent=self)
        self.download_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.download_url)))
        self.download_button.hide()
        self.test_version_checkbox = QCheckBox(self.tr("Check Test Version"), self)
        # A checkout's test versions include its branches and pull requests,
        # which is what someone running the code from git wants to see.
        self.test_version_checkbox.setChecked(self.local_checkout)
        self.check_progress = ProgressRing(16, parent=self)
        self.check_progress.hide()
        self.check_button = Button(self.tr("Check for updates"), "refresh", parent=self)
        self.check_button.clicked.connect(lambda _checked=False: self.check_for_updates())
        self.update_button = Button(self.tr("Update"), "download", "primary", parent=self)
        self.update_button.clicked.connect(self.update_to_selected_version)
        self.update_button.setEnabled(False)

        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(10)
        self.controls_layout.addWidget(self.version_label)
        self.controls_layout.addWidget(self.version_combo)
        self.controls_layout.addWidget(self.status_label, 1)
        self.controls_layout.addWidget(self.download_button)
        self.controls_layout.addWidget(self.test_version_checkbox)
        self.controls_layout.addWidget(self.check_progress)
        self.controls_layout.addWidget(self.check_button)
        self.controls_layout.addWidget(self.update_button)
        self._set_version_controls_visible(False)

        self.notes_edit = ChangeLogView("", self)
        self.notes_edit.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(self.controls_layout)
        layout.addWidget(self.notes_edit)

        self._versions_loaded.connect(self._apply_versions)
        self._update_finished.connect(self._apply_update_result)

    def check_for_updates(self, automatic=False):
        """Load the version list; ``automatic`` checks announce a newer version."""
        if self._busy:
            return
        get_versions = getattr(self.pyappify_module, "get_version_list", None)
        if not callable(get_versions):
            self._show_error(self.tr("Update checking is not supported by this PyAppify version."))
            return
        self._automatic_check = automatic
        self._set_busy(True, checking=True)
        self.check_started.emit()
        self._set_status(self.tr("Checking for updates…"))
        release_only = not self.test_version_checkbox.isChecked()
        self._run_in_background(
            lambda: get_versions(release_only=release_only, exit_event=self.exit_event),
            self._versions_loaded,
            f"pyappify.get_version_list(release_only={release_only})",
        )

    def update_to_version(self, version):
        """Select ``version`` in the picker and start changing to it."""
        index = next(
            (index for index, item in enumerate(self.versions) if str(item["version"]) == str(version)),
            -1,
        )
        if index < 0:
            logger.error(f"update_to_version: {version!r} is not in the loaded version list")
            return
        self.version_combo.setCurrentIndex(index)
        self.update_to_selected_version()

    def update_to_selected_version(self):
        index = self.version_combo.currentIndex()
        if self._busy or index < 0 or index >= len(self.versions):
            return
        update_to_version = getattr(self.pyappify_module, "update_to_version", None)
        if not callable(update_to_version):
            self._show_error(self.tr("Updating is not supported by this PyAppify version."))
            return
        version = str(self.versions[index]["version"])
        self._set_busy(True)
        self._set_status(
            self.tr("Starting change to {version}…").format(version=self._title(self.versions[index]))
        )
        kwargs = {"exit_event": self.exit_event}
        if _accepts_language(update_to_version):
            kwargs["language"] = _ui_locale()
        self._run_in_background(
            lambda: update_to_version(version, **kwargs),
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
        automatic, self._automatic_check = self._automatic_check, False
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
        self.version_combo.addItems([self._title(item) for item in self.versions])
        self.version_combo.blockSignals(False)
        self._resize_version_combo()
        logger.info(
            f"loaded {len(self.versions)} valid versions into selector: "
            f"{[item['version'] for item in self.versions]!r}"
        )

        newest_update = next(
            (index for index, item in enumerate(self.versions)
             if item.get("kind") in _UPDATE_KINDS and (self._direction(item) or 0) > 0),
            None,
        )
        self.update_available_changed.emit(newest_update is not None)
        if automatic and newest_update is not None:
            self.new_version_available.emit(str(self.versions[newest_update]["version"]))
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
        direction = self._direction(selected)
        logger.debug(
            f"selected version={target!r}, current_version={self.current_version!r}, direction={direction}"
        )
        self.update_button.setEnabled(direction != 0 and not self._busy)
        if direction is None:
            self.update_button.setText(self.tr("Switch"))
        elif direction == 0:
            self.update_button.setText(self.tr("Current version"))
        else:
            self.update_button.setText(self.tr("Update") if direction > 0 else self.tr("Downgrade"))

        if selected.get("kind") not in _TAG_KINDS:
            # A branch or pull request carries its own notes: what it adds to
            # the checked-out commit. Notes between versions are for tags.
            notes = self._entry_notes(selected)
            self._set_notes("\n".join(f"• {note}" for note in notes) or self.tr("No release notes."))
            return

        calculate_notes = getattr(self.pyappify_module, "calculate_update_notes", None)
        if not callable(calculate_notes):
            self._set_notes("")
            self._set_status(self.tr("Update-note calculation is not supported."), error=True)
            return
        try:
            tagged = [item for item in self.versions if item.get("kind") in _TAG_KINDS]
            if _accepts_language(calculate_notes):
                notes = calculate_notes(tagged, self.current_version, target, language=_ui_locale())
            else:
                notes = calculate_notes(tagged, self.current_version, target)
            self._set_notes(
                "\n".join(f"• {note}" for note in notes) or self.tr("No release notes.")
            )
        except Exception as error:
            logger.error(f"pyappify.calculate_update_notes failed: {error}", error)
            self._set_notes("")
            self._set_status(self.tr("Failed to calculate update notes: {error}").format(error=error), error=True)

    def _entry_notes(self, entry):
        """``entry``'s notes in the UI language when the app's changelogs have them."""
        entry_notes = getattr(self.pyappify_module, "entry_notes", None)
        if callable(entry_notes):
            try:
                return entry_notes(entry, _ui_locale())
            except Exception as error:
                logger.error(f"pyappify.entry_notes failed: {error}", error)
        notes = entry.get("update_note") or []
        return notes if isinstance(notes, list) else [notes]

    def _resize_version_combo(self):
        font_metrics = QFontMetrics(self.version_combo.font())
        text_width = max(
            (font_metrics.horizontalAdvance(self._title(item)) for item in self.versions),
            default=0,
        )
        content_width = text_width + 56
        width = max(self.VERSION_COMBO_MIN_WIDTH, min(self.VERSION_COMBO_MAX_WIDTH, content_width))
        self.version_combo.setFixedWidth(width)

    def _set_version_controls_visible(self, visible):
        self.version_label.setVisible(visible)
        self.version_combo.setVisible(visible)

    def _set_notes(self, text):
        self.notes_edit.setPlainText(text)
        self.notes_edit.setVisible(bool(text))

    def _set_check_loading(self, loading):
        self.check_progress.setVisible(loading)

    def _apply_update_result(self, result):
        self._set_busy(False)
        successful, value = result
        if successful:
            self._set_status(self.tr("Update request accepted. The app will restart to apply it."))
            if (isinstance(value, dict) and value.get("updated")
                    and value.get("restart_required") and not value.get("mocked")):
                # The standalone updater waits for us to exit before applying
                # the update. Use normal cleanup from this GUI-thread slot.
                logger.info("Update prepared; requesting app shutdown to apply it")
                communicate.quit.emit()
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
        self.status_label.setToolTip(message if error else "")
        self.status_label.setStyleSheet(f"color: {theme.color('danger').name()};" if error else "")
        self.download_button.setVisible(error and bool(self.download_url))

    @staticmethod
    def _title(item):
        """What the picker shows: a checkout names its branches and pull requests."""
        return str(item.get("title") or item["version"])

    def _direction(self, item):
        """1 for an update, -1 for a downgrade, 0 for the running version, None for a switch."""
        relation = item.get("relation")
        if relation in _RELATION_DIRECTIONS:
            return _RELATION_DIRECTIONS[relation]
        return self._compare_versions(str(item["version"]), self.current_version)

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
