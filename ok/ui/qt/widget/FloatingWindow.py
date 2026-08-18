# coding:utf-8
"""Compact always-on-top floating panel (悬浮窗) matching the app's fluent UI.

The panel floats above the game window so its buttons can be clicked without
switching away from the game. It reuses the app's own widgets (Card, TaskCard,
StatusBar) so the look matches the main window exactly. It is a frameless,
always-on-top, rectangular panel that can be resized from the bottom-right
corner. Every task card and button inside is clickable; a live progress card
shows the current task, elapsed time and task info while it runs.
"""

import ctypes
import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    IndeterminateProgressRing,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    ToolButton,
    qconfig,
)

from ok import Logger, og
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.common.design_system import configure_page_layout
from ok.ui.qt.tasks.TaskCard import TaskCard
from ok.ui.qt.widget.Card import Card
from ok.ui.qt.widget.ExpandCardLayout import ExpandCardLayout
from ok.ui.qt.widget.StatusBar import StatusBar

logger = Logger.get_logger(__name__)

WINDOW_WIDTH = 440
WINDOW_HEIGHT = 580
MIN_WIDTH = 300
MIN_HEIGHT = 360

class _DragBar(QWidget):
    """Fluent title bar used to drag the floating window."""

    def __init__(self, floating):
        super().__init__(floating)
        self._floating = floating
        self._drag_offset = None
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(20, 20)
        if og.app is not None and getattr(og.app, 'icon', None) is not None:
            self.icon_label.setPixmap(og.app.icon.pixmap(20, 20))
        layout.addWidget(self.icon_label)

        self.title_label = StrongBodyLabel(floating._window_title(), self)
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.close_button = ToolButton(FluentIcon.CLOSE, self)
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip(floating._tr("Close"))
        self.close_button.clicked.connect(floating._on_close)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.window().frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.window()._save_position()
            event.accept()


class _ResizeGrip(QWidget):
    """Bottom-right drag handle that resizes the floating panel."""

    SIZE = 18

    def __init__(self, floating):
        super().__init__(floating)
        self._floating = floating
        self._start_global = None
        self._start_size = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip(floating._tr("Resize"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_global = event.globalPosition().toPoint()
            self._start_size = (self._floating.width(), self._floating.height())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._start_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._start_global
            width = max(MIN_WIDTH, self._start_size[0] + delta.x())
            height = max(MIN_HEIGHT, self._start_size[1] + delta.y())
            self._floating.resize(width, height)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_global = None
            self._start_size = None
            self._floating._save_position()
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(150, 150, 150), 1)
        painter.setPen(pen)
        x = self.width() - 7
        y = self.height() - 7
        for i in range(3):
            painter.drawLine(x, y, x + 4, y + 4)
            x -= 4
            y -= 4


class FloatingWindow(QWidget):
    """Frameless always-on-top fluent panel that can be clicked over the game."""

    closed = Signal()

    def __init__(self, config, parent=None):
        flags = (Qt.WindowType.Tool
                 | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint)
        super().__init__(parent, flags)
        self._config = config
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(self._window_title())
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self._task_cards = []
        self._build_ui()
        self._load_geometry()
        self._update_theme()
        qconfig.themeChanged.connect(self._update_theme)
        communicate.executor_paused.connect(self._update_status)
        communicate.task.connect(self._update_status)
        communicate.window.connect(self._update_status)
        communicate.task_list_updated.connect(self._rebuild_task_lists)
        self._update_status()
        self._rebuild_task_lists()
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self._refresh_progress)
        self.progress_timer.start()
        logger.info('floating window created')

    def _tr(self, key):
        """Translate with the app gettext catalog, falling back to the key."""
        if og.app is not None and hasattr(og.app, 'tr'):
            try:
                return og.app.tr(key)
            except Exception:
                pass
        return key

    def _window_title(self):
        """Return the floating window title using the configured app name."""
        app_name = "OK-WW"
        if og.app is not None and getattr(og.app, 'title', None):
            app_name = og.app.title
        return app_name + " " + self._tr("Floating Window")

    # ---------- UI ----------

    def _build_ui(self):
        self.container = QFrame(self)
        self.container.setObjectName("floatingContainer")
        self.container.setGeometry(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        # transparent panel: let the game show through, keep the cards readable
        self.container.setStyleSheet(
            "QFrame#floatingContainer { background: transparent; border: none; }")

        root = QVBoxLayout(self.container)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(10)

        # drag bar
        self.drag_bar = _DragBar(self)
        root.addWidget(self.drag_bar)

        # live current-task progress card
        progress_widget = QWidget()
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(2)

        progress_header = QHBoxLayout()
        progress_header.setSpacing(8)
        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(26, 26)
        self.progress_ring.setStrokeWidth(3)
        progress_header.addWidget(self.progress_ring, 0, Qt.AlignmentFlag.AlignVCenter)
        self.progress_name_label = BodyLabel(self._tr("Idle"))
        progress_header.addWidget(self.progress_name_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.progress_time_label = CaptionLabel("")
        progress_header.addWidget(self.progress_time_label, 0, Qt.AlignmentFlag.AlignVCenter)
        progress_header.addStretch(1)
        progress_layout.addLayout(progress_header)

        self.progress_detail_label = CaptionLabel("")
        self.progress_detail_label.setWordWrap(True)
        self.progress_detail_label.setMaximumHeight(72)
        progress_layout.addWidget(self.progress_detail_label)

        self.progress_card = Card("", progress_widget)
        root.addWidget(self.progress_card)

        # status / start / stop card (same look as the main window StartCard)
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        self.status_bar = StatusBar(self._tr("Idle"), parent=status_widget)
        status_layout.addWidget(self.status_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        status_layout.addStretch(1)
        self.start_button = PrimaryPushButton(FluentIcon.PLAY, self._tr("Start"))
        self.start_button.clicked.connect(self._toggle_start)
        status_layout.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.stop_button = PushButton(FluentIcon.POWER_BUTTON, self._tr("Stop"))
        self.stop_button.clicked.connect(self._stop_current_task)
        status_layout.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status_card = Card("", status_widget)
        root.addWidget(self.status_card)

        # scrollable task list
        self.scroll = QScrollArea(self.container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        # keep the scroll area see-through so only the cards are visible
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll_view = QWidget()
        self.scroll_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.scroll_layout = QVBoxLayout(self.scroll_view)
        configure_page_layout(self.scroll_layout)
        self.scroll_layout.setContentsMargins(0, 0, 6, 0)
        self.scroll.setWidget(self.scroll_view)
        root.addWidget(self.scroll, 1)

        self.tasks_header = StrongBodyLabel(self._tr("Tasks"), self.scroll_view)
        self.scroll_layout.addWidget(self.tasks_header)
        self.tasks_view = QWidget(self.scroll_view)
        self.tasks_layout = ExpandCardLayout(self.tasks_view)
        self.scroll_layout.addWidget(self.tasks_view)

        self.triggers_header = StrongBodyLabel(self._tr("Triggers"), self.scroll_view)
        self.scroll_layout.addWidget(self.triggers_header)
        self.triggers_view = QWidget(self.scroll_view)
        self.triggers_layout = ExpandCardLayout(self.triggers_view)
        self.scroll_layout.addWidget(self.triggers_view)
        self.scroll_layout.addStretch(1)

        # footer
        footer = QHBoxLayout()
        self.main_button = PushButton(FluentIcon.HOME, self._tr("Main Window"))
        self.main_button.clicked.connect(self._open_main_window)
        footer.addStretch(1)
        footer.addWidget(self.main_button)
        root.addLayout(footer)

        # resize handle (bottom-right)
        self.resize_grip = _ResizeGrip(self)
        self.resize_grip.move(self.width() - _ResizeGrip.SIZE,
                              self.height() - _ResizeGrip.SIZE)

    def _update_theme(self, *_args):
        # keep the panel background transparent regardless of the active theme
        self.container.setStyleSheet(
            "QFrame#floatingContainer { background: transparent; border: none; }")

    def _rebuild_task_lists(self, *_args):
        if not self.isVisible():
            return
        for card in self._task_cards:
            self.tasks_layout.removeWidget(card)
            self.triggers_layout.removeWidget(card)
            card.deleteLater()
        self._task_cards = []
        if og.executor is None:
            return
        try:
            for task in og.executor.onetime_tasks:
                if not getattr(task, 'visible', True):
                    continue
                card = TaskCard(task, True)
                self._task_cards.append(card)
                self.tasks_layout.addWidget(card)
            for task in og.executor.trigger_tasks:
                if not getattr(task, 'visible', True):
                    continue
                card = TaskCard(task, False)
                self._task_cards.append(card)
                self.triggers_layout.addWidget(card)
            self.tasks_header.setVisible(bool(og.executor.onetime_tasks))
            self.triggers_header.setVisible(bool(og.executor.trigger_tasks))
        except Exception as e:
            logger.error(f'floating window rebuild task lists error: {e}')

    # ---------- native window behavior ----------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Guard against resize events that can arrive while __init__ is still
        # building the UI (before the container/grip widgets exist).
        container = getattr(self, 'container', None)
        if container is not None:
            container.setGeometry(0, 0, self.width(), self.height())
        grip = getattr(self, 'resize_grip', None)
        if grip is not None:
            grip.move(self.width() - _ResizeGrip.SIZE,
                      self.height() - _ResizeGrip.SIZE)

    def showEvent(self, event):
        super().showEvent(event)
        # The panel may have been hidden while the executor state changed;
        # refresh the status and task list now that it is visible again.
        self._update_status()
        self._rebuild_task_lists()

    # ---------- position ----------

    def _load_geometry(self):
        width = self._config.get('width', WINDOW_WIDTH)
        height = self._config.get('height', WINDOW_HEIGHT)
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            self.resize(max(MIN_WIDTH, int(width)), max(MIN_HEIGHT, int(height)))
        else:
            self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        x = self._config.get('x', -1)
        y = self._config.get('y', -1)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x >= 0 and y >= 0:
            self.move(int(x), int(y))
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 24, geo.top() + 24)

    def _save_position(self):
        self._config['x'] = int(self.x())
        self._config['y'] = int(self.y())
        self._config['width'] = self.width()
        self._config['height'] = self.height()

    def _clamp_to_screen(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = max(geo.left(), min(self.x(), geo.right() - self.width()))
        y = max(geo.top(), min(self.y(), geo.bottom() - self.height()))
        self.move(int(x), int(y))

    # ---------- progress ----------

    @staticmethod
    def _time_elapsed(start_time):
        if not start_time:
            return ""
        seconds = max(0, int(time.time() - start_time))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {secs:02d}s"

    @staticmethod
    def _format_task_info(task):
        info = getattr(task, "info", None)
        if not isinstance(info, dict) or not info:
            return ""
        skip = {"Log", "Error", "Warning", "Liberation Key", "Echo Key", "Chars",
                "Resonance Key", "Tool Key"}
        parts = []
        for key, value in info.items():
            if key in skip:
                continue
            text = str(value)
            if len(text) > 48:
                text = text[:48] + "..."
            parts.append(f"{str(key)}: {text}")
        return "\n".join(parts[-4:])

    def _refresh_progress(self):
        if og.executor is None or not self.isVisible():
            return
        try:
            task = og.executor.current_task
            if task is not None and getattr(task, "running", False):
                self.progress_ring.start()
                self.progress_name_label.setText(og.app.tr(task.name) if og.app else task.name)
                self.progress_time_label.setText(self._time_elapsed(task.start_time))
                self.progress_detail_label.setText(self._format_task_info(task))
            elif og.executor.paused:
                self.progress_ring.stop()
                self.progress_name_label.setText(self._tr("Paused"))
                self.progress_time_label.setText("")
                self.progress_detail_label.setText("")
            elif task is not None:
                self.progress_ring.stop()
                self.progress_name_label.setText(og.app.tr(task.name) if og.app else task.name)
                self.progress_time_label.setText("")
                self.progress_detail_label.setText("")
            else:
                self.progress_ring.stop()
                self.progress_name_label.setText(self._tr("Idle"))
                self.progress_time_label.setText("")
                self.progress_detail_label.setText("")
        except Exception as e:
            logger.debug(f'floating progress refresh failed: {e}')

    # ---------- actions ----------

    def _on_close(self):
        self.hide()
        self.closed.emit()

    def _toggle_start(self):
        if og.executor is None:
            return
        if not og.executor.paused:
            og.executor.pause()
        else:
            og.app.start_controller.start()

    def _stop_current_task(self):
        if og.executor is not None:
            og.executor.stop_current_task()
            if not og.executor.paused:
                og.executor.pause()

    def _open_main_window(self):
        if og.main_window is not None:
            og.main_window.bring_to_front()

    # ---------- status ----------

    def _update_status(self, *_args):
        if og.executor is None:
            return
        if not self.isVisible():
            # Hidden panels (e.g. after closing/collapsing) should not do GUI
            # work on every window/task signal from the executor thread.
            return
        try:
            if og.executor.paused:
                self.start_button.setText(self._tr("Start"))
                self.start_button.setIcon(FluentIcon.PLAY)
                self.status_bar.setTitle(self._tr("Paused"))
                self.status_bar.setState(True)
                self._refresh_progress()
                return
            self.start_button.setText(self._tr("Pause"))
            self.start_button.setIcon(FluentIcon.PAUSE)
            if not og.executor.connected():
                self.status_bar.setTitle(self._tr("Game Window Disconnected"))
                self.status_bar.setState(True)
            elif og.executor.active_trigger_task_count():
                if not og.executor.can_capture():
                    self.status_bar.setTitle(self._tr('Paused: Game Window Must Be in Front'))
                    self.status_bar.setState(True)
                else:
                    count = og.executor.active_trigger_task_count()
                    self.status_bar.setTitle(
                        self._tr("Running") + ": " + str(count) + " " + self._tr("Trigger Tasks"))
                    self.status_bar.setState(False)
            elif task := og.executor.current_task:
                if not og.executor.can_capture():
                    self.status_bar.setTitle(self._tr('Paused: Game Window Must Be in Front'))
                    self.status_bar.setState(True)
                elif task.enabled:
                    self.status_bar.setTitle(self._tr("Running") + ": " + task.name)
                    self.status_bar.setState(False)
                else:
                    self.status_bar.setTitle(self._tr("Waiting for task to be enabled"))
                    self.status_bar.setState(False)
            else:
                self.status_bar.setTitle(self._tr("Waiting for task to be enabled"))
                self.status_bar.setState(False)
            self._refresh_progress()
        except Exception as e:
            logger.debug(f'floating window update status failed: {e}')
