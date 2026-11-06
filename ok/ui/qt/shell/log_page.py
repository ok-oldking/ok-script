"""The Log page: a live, filterable tail of ``logs/ok-script.log``.

Lines live in a ``QPlainTextEdit``, which lays out only what is on screen,
and a syntax highlighter colors them by level. Appends are incremental,
``setMaximumBlockCount`` trims old lines without a rebuild, and filtering is
debounced and rebuilds plain text only. (The previous log window rebuilt
50,000 lines of rich HTML on every change.)
"""

import codecs
import os
import re
from collections import deque
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.inputs import ComboBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme
from ok.util.config import Config

LOG_LINE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
)
LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LEVELS = {"ALL": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

MAX_LINES = 50000
TAIL_CHUNK_BYTES = 1024 * 1024
POLL_INTERVAL_MS = 250
FILTER_DELAY_MS = 180


def _t(text: str) -> str:
    # Strings keep the old log window's translation context.
    return QCoreApplication.translate("LogWindow", text)


def line_level(line: str):
    """The level a log line starts a record with, or ``None`` for a continuation line."""

    match = LOG_LINE_PATTERN.match(line)
    return LEVELS[match.group("level")] if match else None


class LogBuffer:
    """The last ``max_lines`` log lines, each tagged with its record's level and id.

    Continuation lines (tracebacks) belong to the record above them, so level
    and text filters keep whole records together.
    """

    def __init__(self, max_lines: int = MAX_LINES):
        self.lines = deque(maxlen=max_lines)  # (record_id, level, text)
        self._record_id = 0
        self._record_level = LEVELS["INFO"]

    def __len__(self):
        return len(self.lines)

    def clear(self) -> None:
        self.lines.clear()

    def append(self, line: str):
        level = line_level(line)
        if level is not None or not self.lines:
            self._record_id += 1
            self._record_level = level if level is not None else LEVELS["INFO"]
        entry = (self._record_id, self._record_level, line)
        self.lines.append(entry)
        return entry

    def matching_records(self, min_level: int, text: str):
        """Ids of records at or above ``min_level`` whose text contains ``text``."""

        text = text.lower()
        matched = set()
        for record_id, level, line in self.lines:
            if level >= min_level and (not text or text in line.lower()):
                matched.add(record_id)
        return matched

    def filtered_text(self, min_level: int, text: str) -> str:
        if min_level <= 0 and not text:
            return "\n".join(line for _id, _level, line in self.lines)
        matched = self.matching_records(min_level, text)
        return "\n".join(line for record_id, _level, line in self.lines if record_id in matched)


class LogHighlighter(QSyntaxHighlighter):
    """Colors each line by its record's level; continuation lines inherit it."""

    def __init__(self, document):
        super().__init__(document)
        self.formats = {}
        self.refresh_colors()

    def refresh_colors(self) -> None:
        colors = {
            LEVELS["DEBUG"]: theme.color("text_tertiary"),
            LEVELS["INFO"]: theme.color("text"),
            LEVELS["WARNING"]: theme.color("warning"),
            LEVELS["ERROR"]: theme.color("danger"),
            LEVELS["CRITICAL"]: theme.color("danger"),
        }
        self.formats = {}
        for level, color in colors.items():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if level == LEVELS["CRITICAL"]:
                fmt.setFontWeight(QFont.Weight.Bold)
            self.formats[level] = fmt
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        level = line_level(text)
        if level is None:
            level = max(self.previousBlockState(), LEVELS["INFO"]) if self.previousBlockState() > 0 \
                else LEVELS["INFO"]
        self.setCurrentBlockState(level)
        self.setFormat(0, len(text), self.formats.get(level, self.formats[LEVELS["INFO"]]))


class LogPage(QWidget):
    def __init__(self, log_file=None, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPage")
        self.config = Config("log_window", {"level": "ALL", "filter_text": ""})
        self.log_file = Path(log_file or Path.cwd() / "logs" / "ok-script.log")
        self.buffer = LogBuffer(MAX_LINES)
        self._position = 0
        self._file_id = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._pending = ""
        self._paused = False
        self._loaded = False

        self.level_combo = ComboBox([_t("All Levels"), *LEVEL_NAMES])
        self.level_combo.setFixedWidth(150)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(_t("Filter logs..."))
        self.filter_edit.setClearButtonEnabled(True)
        self.pause_button = Button(_t("Pause"), "pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.clear_button = Button(_t("Clear"), "x", "subtle")
        self.clear_button.clicked.connect(self.clear)
        self.tail_button = Button(QCoreApplication.translate("LogPage", "Jump to latest"), "chevron-down", "subtle")
        self.tail_button.clicked.connect(self.scroll_to_tail)
        self.tail_button.hide()

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(Label(QCoreApplication.translate("MainWindow", "Log"), "display", self))
        toolbar.addSpacing(12)
        toolbar.addWidget(self.level_combo)
        toolbar.addWidget(self.filter_edit, 1)
        toolbar.addWidget(self.tail_button)
        toolbar.addWidget(self.pause_button)
        toolbar.addWidget(self.clear_button)

        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setUndoRedoEnabled(False)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setMaximumBlockCount(MAX_LINES)
        self.view.setCenterOnScroll(False)
        # The monospace font comes from the kit stylesheet (QPlainTextEdit#logView).
        self.highlighter = LogHighlighter(self.view.document())
        self.view.verticalScrollBar().valueChanged.connect(self._sync_tail_button)

        self.status_label = Label("", "caption", self)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(12)
        layout.addLayout(toolbar)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.status_label)
        theme.install(self)
        theme.changed.connect(self.highlighter.refresh_colors)

        level = self.config.get("level", "ALL")
        self.level_combo.setCurrentIndex(0 if level not in LEVEL_NAMES else LEVEL_NAMES.index(level) + 1)
        self.filter_edit.setText(self.config.get("filter_text", ""))
        self.level_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(FILTER_DELAY_MS)
        self._filter_timer.timeout.connect(self._apply_filter)
        self.filter_edit.textChanged.connect(lambda _text: self._filter_timer.start())

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.poll)

    # --- lifecycle --------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load_tail()
            self._apply_filter()
        else:
            self.poll()
        self.timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # Nothing to draw while hidden; catch up from the file when shown again.
        self.timer.stop()

    # --- filters ----------------------------------------------------------------

    def min_level(self) -> int:
        index = self.level_combo.currentIndex()
        return 0 if index <= 0 else LEVELS[LEVEL_NAMES[index - 1]]

    def filter_text(self) -> str:
        return self.filter_edit.text().strip()

    def is_filtered(self) -> bool:
        return self.min_level() > 0 or bool(self.filter_text())

    def _on_filter_changed(self, *_args) -> None:
        self._filter_timer.start()

    def _apply_filter(self) -> None:
        index = self.level_combo.currentIndex()
        self.config["level"] = "ALL" if index <= 0 else LEVEL_NAMES[index - 1]
        self.config["filter_text"] = self.filter_edit.text()
        text = self.buffer.filtered_text(self.min_level(), self.filter_text())
        self.view.setPlainText(text)
        self.scroll_to_tail()
        self._update_status()

    # --- reading ----------------------------------------------------------------

    @staticmethod
    def _file_identity(file):
        stat = os.fstat(file.fileno())
        return stat.st_dev, getattr(stat, "st_ino", 0) or getattr(stat, "st_ctime_ns", stat.st_ctime)

    def _load_tail(self) -> None:
        if not self.log_file.exists():
            return
        chunks, line_count = [], 0
        with self.log_file.open("rb") as file:
            file.seek(0, 2)
            end = position = file.tell()
            self._file_id = self._file_identity(file)
            while position > 0 and line_count <= MAX_LINES:
                size = min(TAIL_CHUNK_BYTES, position)
                position -= size
                file.seek(position)
                chunk = file.read(size)
                chunks.insert(0, chunk)
                line_count += chunk.count(b"\n")
        self._position = end
        lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()[-MAX_LINES:]
        for line in lines:
            self.buffer.append(line)

    def _read_new_text(self) -> str:
        try:
            with self.log_file.open("rb") as file:
                file_id = self._file_identity(file)
                file.seek(0, 2)
                size = file.tell()
                if file_id != self._file_id or size < self._position:
                    # The log rotated: start from the top of the new file.
                    self._position, self._file_id = 0, file_id
                    self._decoder.reset()
                    self._pending = ""
                if size == self._position:
                    return ""
                file.seek(self._position)
                data = file.read()
                self._position = file.tell()
        except OSError:
            # Rotation can briefly remove or lock the active log on Windows.
            return ""
        return self._decoder.decode(data, final=False)

    def poll(self) -> None:
        if self._paused:
            return
        if not self.log_file.exists():
            self.status_label.setText(_t("Waiting for ok-script.log"))
            return
        text = self._read_new_text()
        if not text:
            return
        text = self._pending + text
        lines = text.split("\n")
        self._pending = lines.pop()
        lines = [line.rstrip("\r") for line in lines]
        self.append_lines(lines)

    def append_lines(self, lines) -> None:
        if not lines:
            return
        follow = self._at_tail()
        min_level, text = self.min_level(), self.filter_text().lower()
        shown = []
        for line in lines:
            _record, level, line = self.buffer.append(line)
            if not self.is_filtered() or (level >= min_level and (not text or text in line.lower())):
                shown.append(line)
        if shown:
            # One appendPlainText call per poll: a single layout update for the batch.
            self.view.appendPlainText("\n".join(shown))
        if follow:
            self.scroll_to_tail()
        self._update_status()

    # --- view state ---------------------------------------------------------------

    def _at_tail(self) -> bool:
        bar = self.view.verticalScrollBar()
        return bar.value() >= bar.maximum() - 2

    def scroll_to_tail(self) -> None:
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self.view.horizontalScrollBar().setValue(0)

    def _sync_tail_button(self, *_args) -> None:
        self.tail_button.setVisible(not self._at_tail())

    def _update_status(self) -> None:
        self.status_label.setText(
            f"{self.log_file}  ·  {self.view.blockCount()}/{len(self.buffer)} "
            f"{QCoreApplication.translate('LogPage', 'lines')}")

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText(_t("Resume") if self._paused else _t("Pause"))
        self.pause_button.set_icon("play" if self._paused else "pause")
        if not self._paused:
            self.poll()

    def clear(self) -> None:
        self.buffer.clear()
        self._pending = ""
        self.view.clear()
        self._update_status()
