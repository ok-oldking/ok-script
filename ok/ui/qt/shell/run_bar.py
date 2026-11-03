"""The run bar under the main window's title bar.

Left: the game connection pill, which opens :class:`ConnectionPopover`.
Right: what the executor is doing and the one executor button, bound to the
Start/Stop hotkey (F11 by default). Running a single task happens from the
task pages; this bar never starts a specific task.
"""

import time
from ctypes import byref, windll, wintypes
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from ok import Handler
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.feedback import Pill, ProgressRing, StatusDot
from ok.ui.qt.kit.icons import icon as kit_icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import set_style_property, theme
from ok.ui.qt.shell.connection import ConnectionPopover
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

HOTKEY_ID = 999
HOTKEY_KEYS = {'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B}


def _t(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def game_display_name(config) -> str:
    """The translated ``game_name`` config, or a generic "Game"."""

    from ok import og

    name = (config or {}).get('game_name')
    if name:
        return og.app.tr(name) if og.app is not None else name
    return _t("RunBar", "Game")


@dataclass
class RunState:
    """What the right side of the run bar shows."""

    button: str  # "start", "pause", "cancel" or "disabled"
    button_text: str = ""
    message: str = ""
    tone: str = "neutral"  # tone of the message text
    task: object = None  # the one-time task being run, if any
    queued: int = 0
    starting: bool = False


def compute_run_state(executor, device_manager, starting: bool = False, game_name: str = "Game",
                      app_name: str = "") -> RunState:
    """The run bar state; the button text names what it acts on.

    Stopped with the game closed, Start launches the game, so it reads
    "Start <game>". Otherwise the button starts or pauses the app.
    """

    start_app = _t("RunBar", "Start {name}").format(name=app_name).strip()
    pause_app = _t("RunBar", "Pause {name}").format(name=app_name).strip()
    owner = getattr(executor, 'exclusive_owner', None)
    if owner is not None:
        return RunState("disabled", start_app,
                        _t("MainWindow", "{owner} is controlling the app. Other tasks are stopped.")
                        .format(owner=owner), "warning")
    if starting:
        return RunState("cancel", _t("RunBar", "Cancel"), _t("RunBar", "Launching {name}").format(name=game_name),
                        starting=True)
    if executor.paused:
        device = device_manager.get_preferred_device() if device_manager else None
        if device is not None and not device.get('connected'):
            return RunState("start", _t("RunBar", "Start {name}").format(name=game_name))
        return RunState("start", start_app)
    if not executor.connected():
        return RunState("pause", pause_app, _t("StartCard", "Game Window Disconnected"), "danger")
    task = executor.current_task
    if task is not None and task in executor.onetime_tasks and task.enabled:
        if not executor.can_capture():
            return RunState("pause", pause_app, _t("StartCard", "Paused: PC Game Window Must Be in Front!"), "danger")
        queued = len([t for t in executor.onetime_task_queue if t is not task and t.enabled])
        return RunState("pause", pause_app, task=task, queued=queued)
    if executor.active_trigger_task_count():
        if not executor.can_capture():
            return RunState("pause", pause_app, _t("StartCard", "Paused: PC Game Window Must Be in Front!"), "danger")
        return RunState("pause", pause_app)
    return RunState("pause", pause_app, _t("StartCard", "Waiting for task to be enabled"))


class ConnectionPill(QPushButton):
    """Status dot, game name, resolution and the capture/interaction methods."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.dot = StatusDot("neutral")
        self.name_label = Label("", "strong")
        self.resolution_label = Label("", "caption")
        self.capture_chip = Label("", "chip")
        self.interaction_chip = Label("", "chip")
        self.chevron = QLabel()
        self.chevron.setFixedSize(14, 14)
        for widget in (self.dot, self.name_label, self.resolution_label, self.capture_chip, self.interaction_chip,
                       self.chevron):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)
        layout.addWidget(self.dot)
        layout.addWidget(self.name_label)
        layout.addWidget(self.resolution_label)
        layout.addWidget(self.capture_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.interaction_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.chevron)
        theme.changed.connect(self._refresh_chevron)
        self.set_open(False)

    def set_open(self, open_: bool) -> None:
        set_style_property(self, "open", open_)
        self._refresh_chevron()

    def _refresh_chevron(self) -> None:
        # The popover opens downward from the toolbar.
        name = "chevron-up" if self.property("open") else "chevron-down"
        self.chevron.setPixmap(kit_icon(name, "text_tertiary", 2).pixmap(QSize(14, 14), self.devicePixelRatioF()))

    def sizeHint(self) -> QSize:
        return QSize(self.layout().sizeHint().width(), self.height())

    def update_from(self, device_manager) -> None:
        device = device_manager.get_preferred_device() if device_manager else None
        if device is None:
            self.dot.set_tone("neutral")
            self.name_label.setText(_t("RunBar", "No game selected"))
            for label in (self.resolution_label, self.capture_chip, self.interaction_chip):
                label.hide()
            return
        connected = bool(device.get('connected'))
        self.dot.set_tone("success" if connected else "neutral")
        self.name_label.setText(str(device.get('nick') or device.get('address') or ''))
        resolution = device.get('resolution') if connected else _t("StartTab", "Disconnected")
        self.resolution_label.setText(str(resolution or ''))
        self.resolution_label.setVisible(bool(resolution))
        capture = device_manager.get_preferred_capture() if device.get('device') == 'windows' else None
        interaction = device_manager.config.get('interaction') if device.get('device') == 'windows' else None
        self.capture_chip.setText(str(capture or ''))
        self.capture_chip.setVisible(bool(capture))
        self.interaction_chip.setText(str(interaction or ''))
        self.interaction_chip.setVisible(bool(interaction))


class RunBar(QFrame):
    """Connection pill, executor status and the executor button."""

    HEIGHT = 52
    toggle_requested = Signal()

    def __init__(self, exit_event, parent=None):
        super().__init__(parent)
        from ok import og
        self.setFixedHeight(self.HEIGHT)
        self._starting = False
        self._launch_deadline = 0.0
        self._state = None

        self.connection_pill = ConnectionPill(self)
        self.popover = ConnectionPopover(self)
        self.connection_pill.clicked.connect(self.toggle_popover)
        self.popover.closed.connect(lambda: self.connection_pill.set_open(False))
        self.popover.changed.connect(self.refresh)

        self.ring = ProgressRing(18)
        self.task_label = Label("", "strong")
        self.elapsed_label = Label("", "mono")
        self.cancel_task_button = Button(icon="x", variant="subtle", size="small")
        self.cancel_task_button.setToolTip(_t("RunBar", "Cancel this task"))
        self.cancel_task_button.clicked.connect(self._cancel_task)
        self.queue_pill = Pill("", "neutral")
        self.message_label = Label("", "secondary")
        self.executor_button = Button("", "power", "tonal")
        self.executor_button.clicked.connect(self.toggle_executor)
        self.toggle_requested.connect(self.toggle_executor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 12, 0)
        layout.setSpacing(12)
        layout.addWidget(self.connection_pill)
        layout.addStretch(1)
        for widget in (self.ring, self.task_label, self.elapsed_label, self.cancel_task_button, self.queue_pill,
                       self.message_label):
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.executor_button)
        theme.install(self)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        communicate.executor_paused.connect(self._on_event)
        communicate.window.connect(self._on_event)
        communicate.task.connect(self._on_event)
        communicate.executor_exclusive.connect(self._on_event)
        communicate.adb_devices.connect(self._on_devices)
        communicate.starting_emulator.connect(self._on_starting)

        self.basic_options = og.executor.basic_options
        self.current_hotkey = "UNINIT"
        self.handler = Handler(exit_event, "RunBarHotkey")
        self.handler.post(self._check_hotkey, 0.1)
        self.refresh()

    # --- state ----------------------------------------------------------------

    def hotkey(self) -> str:
        hotkey = self.basic_options.get('Start/Stop')
        return hotkey if hotkey and hotkey != 'None' else ""

    def _compute_state(self) -> RunState:
        from ok import og
        config = og.config or {}
        return compute_run_state(og.executor, og.device_manager, self._starting, game_display_name(config),
                                 config.get('gui_title') or "")

    def refresh(self) -> None:
        from ok import og
        state = self._compute_state()
        self._state = state
        self.connection_pill.update_from(og.device_manager)

        running_task = state.task is not None
        self.ring.setVisible(state.starting)
        self.task_label.setVisible(running_task)
        self.elapsed_label.setVisible(running_task or state.starting)
        self.cancel_task_button.setVisible(running_task)
        self.queue_pill.setVisible(running_task and state.queued > 0)
        self.message_label.setVisible(bool(state.message))
        self.message_label.setText(state.message)
        self.message_label.setStyleSheet(
            "" if state.tone == "neutral" else f"color: {theme.color(state.tone).name()};")
        if running_task:
            self.task_label.setText(og.app.tr(state.task.name))
            started = getattr(state.task, 'start_time', 0) or 0
            self.elapsed_label.setText(format_elapsed(time.time() - started) if started else "")
            self.queue_pill.setText(_t("RunBar", "+{count} queued").format(count=state.queued))
        elif state.starting:
            left = max(0, self._launch_deadline - time.time())
            self.elapsed_label.setText(format_elapsed(left))

        button = self.executor_button
        button.setEnabled(state.button != "disabled")
        button.setText(state.button_text)
        if state.button == "start":
            button.set_icon("power")
            button.set_variant("primary")
        elif state.button == "disabled":
            button.set_icon("power")
            button.set_variant("tonal")
        elif state.button == "pause":
            button.set_icon("pause")
            button.set_variant("secondary")
        else:
            button.set_icon("x")
            button.set_variant("secondary")
        button.set_hint(self.hotkey() if state.button != "cancel" else "")
        button.setToolTip(_t("RunBar", "Launches the game if needed, then runs triggers and queued tasks")
                          if state.button == "start" else "")

    def _on_event(self, *_args) -> None:
        self.refresh()

    def _on_devices(self, finished=True) -> None:
        if self.popover.isVisible():
            self.popover.refresh(finished)
        self.refresh()

    def _on_starting(self, done, error, seconds_left) -> None:
        self._starting = not done
        if not done:
            self._launch_deadline = time.time() + (seconds_left or 0)
        self.refresh()

    # --- actions --------------------------------------------------------------

    def toggle_popover(self) -> None:
        if not self.popover.isVisible():
            self.popover.refresh()
            self.connection_pill.set_open(True)
        self.popover.toggle(self.connection_pill, above=False)

    def open_popover(self) -> None:
        if not self.popover.isVisible():
            self.toggle_popover()

    def toggle_executor(self) -> None:
        from ok import og
        state = self._state or self._compute_state()
        if state.button == "disabled":
            return
        if state.button == "cancel":
            og.app.start_controller.cancel_start()
        elif state.button == "pause":
            og.executor.pause()
        else:
            og.app.start_controller.start()

    def _cancel_task(self) -> None:
        from ok import og
        og.executor.stop_current_task()
        self.refresh()

    # --- global hotkey (runs on the handler thread) ----------------------------

    def dispose(self) -> None:
        """Release the hotkey and stop polling so a replacement run bar can bind it."""
        self.timer.stop()
        self.handler.post(self._release_hotkey)
        self.handler.join(1)

    def _release_hotkey(self) -> None:
        # The hotkey belongs to the thread that registered it, so release it there.
        windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        self.handler.stop()

    def _check_hotkey(self) -> None:
        new_hotkey = self.basic_options.get('Start/Stop')
        if new_hotkey != self.current_hotkey:
            self._rebind_hotkey(new_hotkey)
            self.current_hotkey = new_hotkey
        msg = wintypes.MSG()
        if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:  # WM_HOTKEY
                logger.debug(f'hotkey pressed {msg}')
                self.toggle_requested.emit()
        self.handler.post(self._check_hotkey, 0.1)

    @staticmethod
    def _rebind_hotkey(hotkey) -> None:
        windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        if hotkey and hotkey != 'None' and hotkey in HOTKEY_KEYS:
            if not windll.user32.RegisterHotKey(None, HOTKEY_ID, 0, HOTKEY_KEYS[hotkey]):
                logger.error(f"Failed to register hotkey {hotkey}")
        else:
            logger.debug(f"Hotkey disabled or invalid: {hotkey}")
