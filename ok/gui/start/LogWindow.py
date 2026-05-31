import html
import re
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSizePolicy, QTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, FluentWindow, PushButton, SearchLineEdit, isDarkTheme, qconfig

from ok.util.config import Config


LOG_LINE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
)

LEVELS = {
    "ALL": 0,
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


class LogWindow(FluentWindow):
    max_lines = 50000
    tail_chunk_bytes = 1024 * 1024

    def __init__(self, log_file=None, parent=None):
        super().__init__(parent)
        self.config = Config("log_window", {
            "pinned": False,
            "level": "ALL",
            "filter_text": "",
        })
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._set_app_icon()
        self.log_file = Path(log_file or Path.cwd() / "logs" / "ok-script.log")
        self.records = []
        self.line_count = 0
        self._position = 0
        self._pending_text = ""
        self._paused = False

        self.setWindowTitle(self.tr("View Log"))
        self.resize(980, 640)
        self.setMinimumSize(720, 420)

        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("logContent")

        self.level_combo = ComboBox(self.content_widget)
        self.level_combo.addItems([self.tr("All Levels"), "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

        self.search_edit = SearchLineEdit(self.content_widget)
        self.search_edit.setPlaceholderText(self.tr("Filter logs..."))
        self.search_edit.setClearButtonEnabled(True)

        self.pause_button = PushButton(FluentIcon.PAUSE, self.tr("Pause"), self.content_widget)
        self.pause_button.clicked.connect(self._toggle_pause)

        self.pin_button = PushButton(FluentIcon.PIN, self.tr("Pin"), self.content_widget)
        self.pin_button.clicked.connect(self._toggle_pin)

        self.clear_button = PushButton(FluentIcon.DELETE, self.tr("Clear"), self.content_widget)
        self.clear_button.clicked.connect(self._clear_view)

        self.status_label = QLabel(self.content_widget)
        self.status_label.setObjectName("logStatusLabel")
        self.status_label.setText(str(self.log_file))
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        toolbar = QWidget(self.content_widget)
        toolbar.setObjectName("logToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self.level_combo)
        toolbar_layout.addWidget(self.search_edit, stretch=1)
        toolbar_layout.addWidget(self.pin_button)
        toolbar_layout.addWidget(self.pause_button)
        toolbar_layout.addWidget(self.clear_button)

        self.log_edit = QTextEdit(self.content_widget)
        self.log_edit.setObjectName("logConsole")
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_edit.setAcceptRichText(True)
        self.log_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.log_edit.setFont(font)

        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self.log_edit, stretch=1)
        layout.addWidget(self.status_label)
        self.addSubInterface(self.content_widget, FluentIcon.COMMAND_PROMPT, self.tr("View Log"))
        self._collapse_navigation_chrome()
        self._restore_config()

        self.level_combo.currentIndexChanged.connect(self._level_changed)
        self.search_edit.textChanged.connect(self._filter_text_changed)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._poll_log_file)
        self.watcher.directoryChanged.connect(self._poll_log_file)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll_log_file)
        self.timer.start()

        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self._watch_log_path()
        self._load_initial_tail()
        self._render_logs()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.titleBar.move(0, 0)
        self.titleBar.resize(self.width(), self.titleBar.height())

    def _collapse_navigation_chrome(self):
        self.navigationInterface.hide()
        self.navigationInterface.setFixedWidth(0)
        self.widgetLayout.setContentsMargins(0, 48, 0, 0)
        self.titleBar.hBoxLayout.setContentsMargins(12, 0, 0, 0)
        self.titleBar.move(0, 0)
        self.titleBar.resize(self.width(), self.titleBar.height())

    def _restore_config(self):
        level = self.config.get("level", "ALL")
        level_index = 0 if level == "ALL" else self.level_combo.findText(level)
        self.level_combo.setCurrentIndex(max(0, level_index))
        self.search_edit.setText(self.config.get("filter_text", ""))
        self._set_pinned(self.config.get("pinned", False), save=False)

    def _set_app_icon(self):
        try:
            from ok import og
            icon = getattr(getattr(og, "app", None), "icon", None)
            if icon and not icon.isNull():
                self.setWindowIcon(icon)
                return
        except Exception:
            icon = None

        app = QApplication.instance()
        if app:
            icon = app.windowIcon()
            if icon and not icon.isNull():
                self.setWindowIcon(icon)

    def _watch_log_path(self):
        log_dir = str(self.log_file.parent)
        if self.log_file.parent.exists() and log_dir not in self.watcher.directories():
            self.watcher.addPath(log_dir)

        log_path = str(self.log_file)
        if self.log_file.exists() and log_path not in self.watcher.files():
            self.watcher.addPath(log_path)

    def _load_initial_tail(self):
        if not self.log_file.exists():
            return

        text = self._read_recent_lines(self.log_file, self.max_lines)
        with self.log_file.open("rb") as file:
            file.seek(0, 2)
            self._position = file.tell()

        self._append_text(text)

    def _read_recent_lines(self, path, max_lines):
        chunks = []
        line_count = 0
        position = path.stat().st_size

        with path.open("rb") as file:
            while position > 0 and line_count <= max_lines:
                read_size = min(self.tail_chunk_bytes, position)
                position -= read_size
                file.seek(position)
                chunk = file.read(read_size)
                chunks.insert(0, chunk)
                line_count += chunk.count(b"\n")

        data = b"".join(chunks)
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return "\n".join(lines) + ("\n" if lines else "")

    def _poll_log_file(self, *_args):
        if self._paused:
            return

        self._watch_log_path()
        if not self.log_file.exists():
            self.status_label.setText(self.tr("Waiting for ok-script.log"))
            return

        size = self.log_file.stat().st_size
        if size < self._position:
            self._position = 0
            self._pending_text = ""

        if size == self._position:
            return

        with self.log_file.open("rb") as file:
            file.seek(self._position)
            text = file.read().decode("utf-8", errors="replace")
            self._position = file.tell()

        if self._append_text(text):
            self._render_logs()

    def _append_text(self, text):
        if not text:
            return False

        text = self._pending_text + text
        if text.endswith(("\n", "\r")):
            lines = text.splitlines()
            self._pending_text = ""
        else:
            lines = text.splitlines()
            self._pending_text = lines.pop() if lines else text

        for line in lines:
            self._append_line(line)

        self._trim_to_max_lines()

        return bool(lines)

    def _append_line(self, line):
        match = LOG_LINE_PATTERN.match(line)
        if match or not self.records:
            self.records.append({
                "level": match.group("level") if match else "INFO",
                "lines": [line],
            })
            self.line_count += 1
        else:
            self.records[-1]["lines"].append(line)
            self.line_count += 1

    def _trim_to_max_lines(self):
        while self.records and self.line_count - len(self.records[0]["lines"]) >= self.max_lines:
            self.line_count -= len(self.records.pop(0)["lines"])
        if self.records and self.line_count > self.max_lines:
            overflow = self.line_count - self.max_lines
            self.records[0]["lines"] = self.records[0]["lines"][overflow:]
            self.line_count -= overflow

    def _render_logs(self, *_args):
        level_name = self._selected_level()
        min_level = LEVELS[level_name]
        text_filter = self.search_edit.text().strip().lower()
        visible_records = []

        for record in self.records:
            if LEVELS.get(record["level"], 0) < min_level:
                continue
            block_text = "\n".join(record["lines"])
            if text_filter and text_filter not in block_text.lower():
                continue
            visible_records.append(record)

        self.status_label.setText(
            f"{self.log_file}  |  {len(visible_records)}/{len(self.records)} {self.tr('records')}"
        )
        self.log_edit.setHtml(self._build_html(visible_records))
        QTimer.singleShot(0, self._scroll_to_tail_left)

    def _selected_level(self):
        index = self.level_combo.currentIndex()
        if index <= 0:
            return "ALL"
        return self.level_combo.currentText()

    def _build_html(self, records):
        palette = self._palette()
        lines = []
        for record in records:
            color = palette.get(record["level"], palette["INFO"])
            for line in record["lines"]:
                lines.append(f'<span style="color:{color};">{html.escape(line)}</span>')
        body = "\n".join(lines)
        return (
            "<html><head><style>"
            "body { margin: 0; white-space: pre; font-family: Consolas, 'Cascadia Mono', monospace; "
            f"font-size: 10pt; background: {palette['background']}; color: {palette['text']}; }}"
            "::selection { background: #2f65ca; color: #ffffff; }"
            "</style></head><body>"
            f"{body}"
            "</body></html>"
        )

    @staticmethod
    def _palette():
        if isDarkTheme():
            return {
                "background": "#1e1f22",
                "surface": "#2b2d30",
                "border": "#3c3f41",
                "text": "#dfe1e5",
                "muted": "#9aa0a6",
                "DEBUG": "#8ab4f8",
                "INFO": "#dfe1e5",
                "WARNING": "#f5c16c",
                "ERROR": "#ff867f",
                "CRITICAL": "#ff5f56",
            }

        return {
            "background": "#ffffff",
            "surface": "#f3f4f7",
            "border": "#d6d9de",
            "text": "#202124",
            "muted": "#5f6368",
            "DEBUG": "#1a73e8",
            "INFO": "#202124",
            "WARNING": "#9a6700",
            "ERROR": "#d93025",
            "CRITICAL": "#b3261e",
        }

    def _apply_theme(self):
        palette = self._palette()
        self.setStyleSheet(f"""
            LogWindow {{
                background: {palette["surface"]};
            }}
            QWidget#logToolbar {{
                background: {palette["surface"]};
                border-bottom: 1px solid {palette["border"]};
            }}
            QTextEdit#logConsole {{
                background: {palette["background"]};
                color: {palette["text"]};
                border: none;
                padding: 8px 10px;
                selection-background-color: #2f65ca;
                selection-color: #ffffff;
            }}
            QLabel#logStatusLabel {{
                color: {palette["muted"]};
                background: {palette["surface"]};
                border-top: 1px solid {palette["border"]};
                padding: 4px 10px;
                font: 12px 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';
            }}
        """)
        self._render_logs()

    def _scroll_to_tail_left(self):
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
        self.log_edit.horizontalScrollBar().setValue(self.log_edit.horizontalScrollBar().minimum())

    def _level_changed(self, *_args):
        self.config["level"] = self._selected_level()
        self._render_logs()

    def _filter_text_changed(self, text):
        self.config["filter_text"] = text
        self._render_logs()

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self.pause_button.setIcon(FluentIcon.PLAY)
            self.pause_button.setText(self.tr("Resume"))
        else:
            self.pause_button.setIcon(FluentIcon.PAUSE)
            self.pause_button.setText(self.tr("Pause"))
            self._poll_log_file()

    def _toggle_pin(self):
        pinned = not bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self._set_pinned(pinned)

    def _set_pinned(self, pinned, save=True):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        if pinned:
            self.pin_button.setIcon(FluentIcon.UNPIN)
            self.pin_button.setText(self.tr("Unpin"))
        else:
            self.pin_button.setIcon(FluentIcon.PIN)
            self.pin_button.setText(self.tr("Pin"))
        if save:
            self.config["pinned"] = pinned
        if self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()

    def _clear_view(self):
        self.records.clear()
        self.line_count = 0
        self._pending_text = ""
        self._render_logs()
