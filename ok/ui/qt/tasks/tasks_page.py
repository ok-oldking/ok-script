"""The Tasks page: a task list beside the selected task's details.

The list groups one-time ("On-demand") tasks and trigger tasks into
sections, each scrolling on its own; they collapse only in the All view.
Every one-time row has its own run button and every trigger row its own
switch, so nothing needs a select-then-start double click; clicking a row
opens its settings. Tabs above the list filter by kind and by the tasks'
``group_name``; the last selected tab is remembered across starts.
"""

import threading
import time

from PySide6.QtCore import QCoreApplication, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QMenu, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ok import Logger, og
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.dialogs import Dialog
from ok.ui.qt.kit.feedback import Pill
from ok.ui.qt.kit.icons import icon as kit_icon, tinted_icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.kit.tabs import TabStrip
from ok.ui.qt.kit.theme import set_style_property, theme
from ok.ui.qt.shell.nav_icons import FALLBACK, nav_icon
from ok.ui.qt.shell.run_bar import format_elapsed
from ok.ui.qt.tasks.config_form import ConfigForm
from ok.ui.qt.widget.UpdateConfigWidgetItem import value_to_string
from ok.util.config import Config

logger = Logger.get_logger(__name__)

LIST_WIDTH = 372
ROW_HEIGHT = 58
TRIGGER_LIST_MAX_HEIGHT = 4 * ROW_HEIGHT

KIND_ALL = "all"
KIND_ONETIME = "onetime"
KIND_TRIGGER = "trigger"
GROUP_PREFIX = "group:"


def _t(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def _app_tr(text):
    return og.app.tr(text) if og.app is not None and text else (text or "")


# --- task actions -----------------------------------------------------------------

def start_task(task, parent: QWidget) -> None:
    """Run (or resume) a one-time task, confirming its first-run alert once."""

    if task.enabled and task.paused:
        logger.info(f"resume paused task {task}")
        task.unpause()
        return
    if task.first_run_alert and not task.config.get('_first_run_alert'):
        dialog = Dialog(parent, _app_tr('Alert'), _app_tr(task.first_run_alert), ok_text=_app_tr('Confirm'),
                        cancel_text=_app_tr('Cancel'))
        dialog.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        accepted = dialog.exec()
        dialog.deleteLater()
        if not accepted:
            return
        task.config['_first_run_alert'] = task.first_run_alert
    og.app.start_controller.start(task)


def stop_task(task) -> None:
    task.disable()
    task.unpause()


def set_trigger_enabled(task, enabled: bool) -> None:
    if enabled:
        threading.Thread(target=task.enable, name="TaskEnable", daemon=True).start()
    else:
        task.disable()


def task_status(task, executor):
    """``(text, tone, tooltip)`` for a one-time task's status pill, or ``None`` when idle."""

    if not task.enabled:
        return None
    if task.paused:
        return _t("TasksPage", "Paused"), "warning", ""
    if task.running:
        return _t("TaskTab", "Running"), "success", ""
    tooltip = ""
    if waiting_for := executor.waiting_for_task(task):
        tooltip = _t("TaskCard", "Waiting for {task_name} task to be completed").format(
            task_name=_app_tr(waiting_for.name))
    return _t("TasksPage", "Queued"), "accent", tooltip


def _category_tint(source, key, fallback=None):
    config = getattr(og, 'config', None) or {}
    colors = config.get('task_category_colors', {})
    color = colors.get(key, colors.get(fallback))
    if source is None or color is None:
        return source
    qicon = kit_icon(source) if isinstance(source, str) else source
    return tinted_icon(qicon, color)


def task_icon(task, is_trigger=False):
    """A QIcon or bundled icon name for the task, or ``None`` for a monogram."""

    source = getattr(task, 'icon', None)
    if source is None:
        return None
    resolved = nav_icon(source, trim_transparent=True)
    if resolved == FALLBACK:
        return None
    kind = KIND_TRIGGER if is_trigger else KIND_ONETIME
    group = getattr(task, 'group_name', None)
    return _category_tint(resolved, GROUP_PREFIX + group if group else kind, kind)


def task_category_icon(key, fallback=None):
    """Resolve app-provided category artwork, keeping the default kit icons."""

    config = getattr(og, 'config', None) or {}
    if key.startswith(GROUP_PREFIX):
        source = fallback
    else:
        source = config.get('task_category_icons', {}).get(key, fallback)
    resolved = nav_icon(source, trim_transparent=True) if source is not None else None
    return _category_tint(resolved, key)


def split_leading_symbol(name: str):
    """Split a leading emoji or symbol off a task name: ``("📅", "Daily Task")``.

    Apps often prefix task names with an emoji; it becomes the row's tile.
    """

    name = name.strip()
    head, _, rest = name.partition(" ")
    if head and rest and not any(char.isalnum() for char in head):
        return head, rest.strip()
    return None, name


def display_name(task) -> str:
    return split_leading_symbol(_app_tr(task.name))[1]


def monogram(name: str) -> str:
    words = [word for word in name.replace('_', ' ').split() if word]
    if not words:
        return "?"
    if len(words) == 1 or not words[0][:1].isascii():
        return words[0][:2].upper() if words[0][:1].isascii() else words[0][:1]
    return (words[0][0] + words[1][0]).upper()


def visible_tasks(executor, task_manager=None):
    """``(onetime, triggers)`` shown on the page; imported scripts keep their own pages."""

    imported = set()
    if task_manager is not None:
        imported = {entry.get('script_name') for entry in task_manager.imported_scripts.values()}

    def shown(task):
        return getattr(task, 'visible', True) and getattr(task, 'group_name', None) not in imported - {None}

    return [t for t in executor.onetime_tasks if shown(t)], [t for t in executor.trigger_tasks if shown(t)]


def task_groups(tasks):
    """Ordered ``{group_name: group_icon}`` for tasks that declare a group."""

    groups = {}
    for task in tasks:
        name = getattr(task, 'group_name', None)
        if name and name not in groups:
            groups[name] = getattr(task, 'group_icon', None)
    return groups


def matches_filter(task, key: str, is_trigger: bool) -> bool:
    if key == KIND_ALL:
        return True
    if key == KIND_ONETIME:
        return not is_trigger
    if key == KIND_TRIGGER:
        return is_trigger
    if key.startswith(GROUP_PREFIX):
        return getattr(task, 'group_name', None) == key[len(GROUP_PREFIX):]
    return True


# --- list -------------------------------------------------------------------------

class TaskIconTile(QLabel):
    """The task's own icon or monogram, without a background tile."""

    def __init__(self, task, size: int = 36, parent=None, *, is_trigger=False):
        super().__init__(parent)
        self.setObjectName("taskTile")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._task = task
        self._is_trigger = is_trigger
        self._glyph = round(size * 0.78)
        theme.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        source = task_icon(self._task, self._is_trigger)
        if source is None:
            symbol, name = split_leading_symbol(_app_tr(self._task.name))
            if symbol:
                font = self.font()
                font.setPixelSize(int(self._glyph * 0.85))
                self.setFont(font)
            self.setText(symbol or monogram(name))
            return
        qicon = source if not isinstance(source, str) else kit_icon(source, "text_secondary")
        self.setPixmap(qicon.pixmap(QSize(self._glyph, self._glyph), self.devicePixelRatioF()))


class TaskRow(QFrame):
    """One task: tile, name, description, status and its run button or switch."""

    picked = Signal(object)

    def __init__(self, task, is_trigger: bool, parent=None):
        super().__init__(parent)
        self.task = task
        self.is_trigger = is_trigger
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)

        self.tile = TaskIconTile(task, is_trigger=is_trigger)
        self._name = display_name(task)
        self._description = _app_tr(getattr(task, 'description', '') or '')
        self.name_label = Label(self._name, "strong")
        self.description_label = Label("", "caption")
        # Only hide: showing a widget before it has a parent opens it as a
        # top-level window, which flashes on screen while the page is built.
        if not self._description:
            self.description_label.hide()
        # Elided labels must not ask for their full text width, or the row's
        # button or switch is pushed out of view.
        for label in (self.name_label, self.description_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            label.setMinimumWidth(1)
        self.status_pill = Pill("", "neutral")
        self.status_pill.hide()
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addStretch(1)
        text.addWidget(self.name_label)
        text.addWidget(self.description_label)
        text.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(12)
        layout.addWidget(self.tile)
        layout.addLayout(text, 1)
        layout.addWidget(self.status_pill)

        if is_trigger:
            self.switch = Switch()
            self.switch.setToolTip(_app_tr(task.name))
            self.switch.toggled.connect(lambda on: set_trigger_enabled(self.task, on))
            layout.addWidget(self.switch)
            self.action_button = None
        else:
            self.switch = None
            self.action_button = Button(icon="play", variant="secondary", size="small")
            self.action_button.setFixedSize(32, 32)
            self.action_button.clicked.connect(self._on_action)
            layout.addWidget(self.action_button)
        self.refresh()

    def set_selected(self, selected: bool) -> None:
        set_style_property(self, "selected", selected)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide_description()

    def _elide_description(self) -> None:
        for label, text in ((self.name_label, self._name), (self.description_label, self._description)):
            width = max(40, label.width())
            label.setText(QFontMetrics(label.font()).elidedText(text, Qt.TextElideMode.ElideRight, width))
            label.setToolTip(text)

    def refresh(self) -> None:
        task = self.task
        if self.is_trigger:
            if self.switch.isChecked() != bool(task.enabled):
                self.switch.blockSignals(True)
                self.switch.setChecked(bool(task.enabled))
                self.switch.blockSignals(False)
            return
        status = task_status(task, og.executor)
        self.status_pill.setVisible(status is not None)
        if status is not None:
            text, tone, tooltip = status
            self.status_pill.setText(text)
            self.status_pill.set_tone(tone)
            self.status_pill.setToolTip(tooltip)
        running = task.enabled and not task.paused
        self.action_button.set_icon("stop" if running else "play")
        self.action_button.set_variant("secondary")
        if running:
            self.action_button.setToolTip(_t("TaskCard", "Stop"))
        elif task.enabled and task.paused:
            self.action_button.setToolTip(_t("TaskCard", "Resume"))
        else:
            self.action_button.setToolTip(_t("TaskCard", "Start"))

    def _on_action(self) -> None:
        task = self.task
        if task.enabled and not task.paused:
            stop_task(task)
        else:
            start_task(task, self)
        self.refresh()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.picked.emit(self.task)
        super().mouseReleaseEvent(event)


class TaskSection(Card):
    """A collapsible card listing task rows; the rows scroll inside it."""

    toggled = Signal(bool)

    def __init__(self, title: str, icon_name, parent=None):
        super().__init__(parent)
        self.rows = []
        self._expanded = True
        self._collapsible = True
        self._icon_name = icon_name
        self.header = QPushButton(self)
        self.header.setObjectName("sectionHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFixedHeight(46)
        self.header.clicked.connect(self._on_header_clicked)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.title_label = Label(title, "strong")
        self.count_label = Label("", "chip")
        self.chevron = QLabel()
        self.chevron.setFixedSize(14, 14)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setSpacing(10)
        for widget in (self.icon_label, self.title_label, self.count_label):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            header_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch(1)
        self.chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self.chevron)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        self.rows_layout = QVBoxLayout(contents)
        self.rows_layout.setContentsMargins(6, 6, 6, 6)
        self.rows_layout.setSpacing(2)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(contents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.scroll, 1)
        theme.changed.connect(self._refresh_icons)
        self._refresh_icons()

    def set_rows(self, rows) -> None:
        for row in self.rows:
            self.rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self.rows = list(rows)
        for row in self.rows:
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self.count_label.setText(str(len(self.rows)))

    def set_count_text(self, text: str) -> None:
        self.count_label.setText(text)

    def set_title(self, title: str, icon_name) -> None:
        self.title_label.setText(title)
        self._icon_name = icon_name
        self._refresh_icons()

    def is_expanded(self) -> bool:
        return self._expanded or not self._collapsible

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.scroll.setVisible(self.is_expanded())
        self._refresh_icons()
        self.toggled.emit(expanded)

    def set_collapsible(self, collapsible: bool) -> None:
        """A section that cannot collapse stays open and hides its chevron;
        its own collapsed state returns when it becomes collapsible again."""

        self._collapsible = collapsible
        self.header.setCursor(Qt.CursorShape.PointingHandCursor if collapsible else Qt.CursorShape.ArrowCursor)
        self.chevron.setVisible(collapsible)
        self.scroll.setVisible(self.is_expanded())
        self._refresh_icons()

    def _on_header_clicked(self) -> None:
        if self._collapsible:
            self.set_expanded(not self._expanded)

    def content_height(self) -> int:
        return sum(row.height() for row in self.rows if not row.isHidden()) + 12 + 2 * max(0, len(self.rows) - 1)

    def _refresh_icons(self) -> None:
        dpr = self.devicePixelRatioF()
        source = nav_icon(self._icon_name, trim_transparent=True)
        icon = kit_icon(source, "text", 1.8) if isinstance(source, str) else source
        self.icon_label.setPixmap(icon.pixmap(QSize(20, 20), dpr))
        chevron = "chevron-up" if self.is_expanded() else "chevron-down"
        self.chevron.setPixmap(kit_icon(chevron, "text_tertiary", 2).pixmap(QSize(14, 14), dpr))


# --- detail -----------------------------------------------------------------------

class TaskDetail(QWidget):
    """The selected task: header, status, actions, settings and live info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task = None
        self.is_trigger = False
        self.form = None
        self._was_running = False

        self.card = Card()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        self.title_label = Label("", "title")
        self.title_label.setWordWrap(True)
        self.description_label = Label("", "secondary", word_wrap=True)
        self.status_label = Label("", "caption")
        self.status_label.hide()
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addWidget(self.title_label)
        text.addWidget(self.description_label)
        text.addWidget(self.status_label)

        self.instructions_button = Button(_t("TaskCard", "Instructions"), "info")
        self.instructions_button.clicked.connect(self.show_instructions)
        self.edit_button = Button(_t("TaskCard", "Edit"), "pen")
        self.edit_button.clicked.connect(self.edit_task)
        self.reset_button = Button(_t("ConfigCard", "Reset Config"), "reset", "subtle", "small")
        self.reset_button.clicked.connect(self.reset_config)
        self.more_button = Button(icon="chevron-down")
        self.more_button.setToolTip(_t("TasksPage", "More actions"))
        self.more_menu = QMenu(self.more_button)
        self.more_menu.addAction(_t("ConfigCard", "Add Start Menu Shortcut"), self._create_shortcut)
        self.more_button.clicked.connect(lambda: self.more_menu.exec(
            self.more_button.mapToGlobal(self.more_button.rect().bottomLeft())))
        self.pause_button = Button(_t("TaskCard", "Pause"), "pause")
        self.pause_button.clicked.connect(lambda: self.task and self.task.pause())
        self.stop_button = Button(_t("TaskCard", "Stop"), "stop", "danger")
        self.stop_button.clicked.connect(lambda: self.task and stop_task(self.task))
        self.run_button = Button(_t("TasksPage", "Run task"), "play", "primary")
        self.run_button.clicked.connect(lambda: self.task and start_task(self.task, self))
        self.trigger_label = Label(_t("TaskCard", "Enabled"), "secondary")
        self.trigger_switch = Switch()
        self.trigger_switch.toggled.connect(lambda on: self.task and set_trigger_enabled(self.task, on))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        for widget in (self.instructions_button, self.edit_button, self.more_button,
                       self.pause_button, self.stop_button, self.run_button, self.trigger_label,
                       self.trigger_switch):
            actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

        header = QHBoxLayout()
        header.setSpacing(16)
        header.addLayout(text, 1)
        header.addLayout(actions)

        self.tabs = TabStrip("underline")
        self.tabs.add_tab("settings", _t("TasksPage", "Settings"), icon="gear")
        self.tabs.add_tab("info", _t("TaskTab", "Info"), icon="file")
        self.tabs.current_changed.connect(self._show_tab)
        # Reset belongs to the settings it resets, so it sits on the tab row.
        self.tabs.layout().addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.info_table = QTableWidget(0, 2)
        self.info_table.setHorizontalHeaderLabels([_t("TaskTab", "Info"), _t("TaskTab", "Value")])
        self.info_table.verticalHeader().hide()
        self.info_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.info_table.horizontalHeader().setStretchLastSection(True)
        # Left-aligned headers line up with the padded cell text below them.
        self.info_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_table.verticalHeader().setDefaultSectionSize(40)
        self.info_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.info_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.form_scroll)
        self.pages.addWidget(self.info_table)

        self.placeholder = Label(_t("TasksPage", "Select a task to see its settings."), "secondary")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(self.tabs)
        layout.addWidget(self.pages, 1)
        layout.addWidget(self.placeholder, 1)
        self._set_has_task(False)

    def _set_has_task(self, has_task: bool) -> None:
        for widget in (self.title_label, self.description_label, self.tabs, self.pages):
            widget.setVisible(has_task)
        self.placeholder.setVisible(not has_task)
        if not has_task:
            for widget in (self.instructions_button, self.edit_button, self.reset_button, self.more_button,
                           self.pause_button, self.stop_button, self.run_button, self.trigger_label,
                           self.trigger_switch, self.status_label):
                widget.hide()

    def show_task(self, task, is_trigger: bool) -> None:
        self.task = task
        self.is_trigger = is_trigger
        self._set_has_task(task is not None)
        if task is None:
            return
        self.title_label.setText(display_name(task))
        description = _app_tr(getattr(task, 'description', '') or '')
        self.description_label.setText(description)
        self.description_label.setVisible(bool(description))
        if self.form is not None:
            self.form.setParent(None)
            self.form.deleteLater()
        self.form = ConfigForm(task, task.config, task.default_config, task.config_description, task.config_type)
        self.form_scroll.setWidget(self.form)
        self.instructions_button.setVisible(bool(getattr(task, 'instructions', None)))
        self.edit_button.setVisible(bool(getattr(task, 'is_custom', False)))
        self.more_button.setVisible(bool(getattr(task, 'show_create_shortcut', False)))
        # A running task opens on its live info; otherwise on its settings.
        self._was_running = self._is_running(task)
        self._open_tab("info" if self._was_running else "settings")
        self.refresh()

    def _is_running(self, task) -> bool:
        return bool(task is not None and not self.is_trigger and task.enabled and task.running)

    def _open_tab(self, key: str) -> None:
        self.tabs.item("info").setVisible(key == "info" or self._has_info())
        self.tabs.set_current(key)
        self._show_tab(key)

    def _has_info(self) -> bool:
        return self.task is not None and (bool(self.task.info) or self._is_running(self.task))

    def refresh(self) -> None:
        task = self.task
        if task is None:
            return
        running = self._is_running(task)
        if running and not self._was_running:
            # The selected task just started: follow it on the Info tab.
            self._open_tab("info")
        self._was_running = running
        has_info = self._has_info()
        self.tabs.item("info").setVisible(has_info)
        if not has_info and self.tabs.current_key() == "info":
            self._open_tab("settings")
        self.reset_button.setVisible(self.tabs.current_key() == "settings" and bool(task.default_config)
                                     and self.form is not None and not self.form.is_empty)
        if self.pages.currentWidget() is self.info_table:
            self._fill_info()

        if self.is_trigger:
            for widget in (self.pause_button, self.stop_button, self.run_button):
                widget.hide()
            self.trigger_label.show()
            self.trigger_switch.show()
            if self.trigger_switch.isChecked() != bool(task.enabled):
                self.trigger_switch.blockSignals(True)
                self.trigger_switch.setChecked(bool(task.enabled))
                self.trigger_switch.blockSignals(False)
            self.status_label.hide()
            return

        self.trigger_label.hide()
        self.trigger_switch.hide()
        running = task.enabled and task.running and not task.paused
        self.pause_button.setVisible(running)
        self.stop_button.setVisible(bool(task.enabled))
        self.run_button.setVisible(not task.enabled or task.paused)
        self.run_button.setText(_t("TaskCard", "Resume") if task.enabled and task.paused
                                else _t("TasksPage", "Run task"))
        status = task_status(task, og.executor)
        if status is None:
            self.status_label.hide()
            return
        text, tone, tooltip = status
        if running and getattr(task, 'start_time', 0):
            text = f"{text} · {_t('TaskTab', 'Time Elapsed')} {format_elapsed(time.time() - task.start_time)}"
        elif tooltip:
            text = f"{text} · {tooltip}"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {theme.color(tone).name()};")
        self.status_label.show()

    def _show_tab(self, key: str) -> None:
        if key == "info":
            self.pages.setCurrentWidget(self.info_table)
            self._fill_info()
        else:
            self.pages.setCurrentWidget(self.form_scroll)
        if self.task is not None:
            self.reset_button.setVisible(key == "settings" and bool(self.task.default_config)
                                         and self.form is not None and not self.form.is_empty)

    def _fill_info(self) -> None:
        info = self.task.info if self.task is not None else {}
        self.info_table.setRowCount(len(info))
        for row, (key, value) in enumerate(info.items()):
            for column, text in enumerate((_app_tr(key), _app_tr(value_to_string(value)))):
                item = self.info_table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.info_table.setItem(row, column, item)
                item.setText(text)
                item.setToolTip(text)

    def reset_config(self) -> None:
        if self.task is None:
            return
        self.task.config.reset_to_default()
        if self.form is not None:
            self.form.update_config()

    def _create_shortcut(self) -> None:
        if self.task is not None:
            self.task.create_shortcut()

    def edit_task(self) -> None:
        if self.task is None:
            return
        og.main_window.edit_task_tab.load_task(self.task)
        og.main_window.switch_to(og.main_window.edit_task_tab)

    def show_instructions(self) -> None:
        instructions = getattr(self.task, 'instructions', None) if self.task is not None else None
        if not instructions:
            return
        import re
        # Auto-link plain URLs while preserving existing <a> tags.
        parts = re.split(r'(<a\s[^>]*>.*?</a>)', instructions, flags=re.DOTALL)
        for i, part in enumerate(parts):
            if not part.startswith('<a '):
                parts[i] = re.sub(r'(https?://[^\s<>"]+)', r'<a href="\1">\1</a>', part)
        dialog = Dialog(self, _app_tr(self.task.name), width=560)
        dialog.set_cancel_visible(False)
        label = dialog.message_label
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setText(''.join(parts).replace('\n', '<br>'))
        label.show()
        dialog.exec()
        dialog.deleteLater()


# --- page -------------------------------------------------------------------------

class TasksPage(QWidget):
    """All visible tasks with filter tabs, a sectioned list and a detail pane.

    Subclasses show another task set by overriding :meth:`collect_tasks`.
    """

    state_name = "tasks_page"
    """Config file remembering the last selected filter tab."""

    def __init__(self, parent=None, title: str = None):
        super().__init__(parent)
        self.setObjectName("TasksPage")
        self.onetime_tasks = []
        self.trigger_tasks = []
        self.rows = {}
        self.groups = {}
        self.selected_task = None

        self.state = Config(self.state_name, {"filter": KIND_ALL})
        self.title_label = Label(title or _t("MainWindow", "Tasks"), "display")
        self.filter_tabs = TabStrip()
        self.filter_tabs.current_changed.connect(self._on_filter_changed)
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self.title_label)
        top.addWidget(self.filter_tabs)
        top.addStretch(1)

        self.onetime_section = TaskSection(_t("TasksPage", "On-demand"), task_category_icon(KIND_ONETIME, "bolt"))
        self.trigger_section = TaskSection(_t("TasksPage", "Triggers"), task_category_icon(KIND_TRIGGER, "timer"))
        self.onetime_section.toggled.connect(lambda _on: self._layout_sections())
        self.trigger_section.toggled.connect(lambda _on: self._layout_sections())
        self.list_column = QVBoxLayout()
        self.list_column.setSpacing(12)
        self.list_column.addWidget(self.onetime_section, 1)
        self.list_column.addWidget(self.trigger_section, 0)
        # Takes the free height when no section does, keeping collapsed headers on top.
        self.list_column.addStretch(0)
        list_holder = QWidget()
        list_holder.setFixedWidth(LIST_WIDTH)
        list_holder.setLayout(self.list_column)
        self.list_column.setContentsMargins(0, 0, 0, 0)

        self.detail = TaskDetail()
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(list_holder)
        body.addWidget(self.detail, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(16)
        layout.addLayout(top)
        layout.addLayout(body, 1)
        theme.install(self)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        communicate.task.connect(self._on_task_event)
        communicate.task_list_updated.connect(self.refresh_tasks)
        self.refresh_tasks()

    # --- building -------------------------------------------------------------

    def has_tasks(self) -> bool:
        return bool(self.onetime_tasks or self.trigger_tasks)

    def has_task(self, task) -> bool:
        return task in self.rows

    def collect_tasks(self):
        """``(onetime, triggers)`` this page lists."""
        return visible_tasks(og.executor, getattr(og, 'task_manager', None))

    def refresh_tasks(self) -> None:
        self.onetime_tasks, self.trigger_tasks = self.collect_tasks()
        self.rows = {}
        onetime_rows = [self._make_row(task, False) for task in self.onetime_tasks]
        trigger_rows = [self._make_row(task, True) for task in self.trigger_tasks]
        self.onetime_section.set_rows(onetime_rows)
        self.trigger_section.set_rows(trigger_rows)
        self._build_filters()
        selected = self.selected_task if self.selected_task in self.rows else None
        if selected is None and (self.onetime_tasks or self.trigger_tasks):
            selected = (self.onetime_tasks or self.trigger_tasks)[0]
        self.select_task(selected)
        self._apply_filter()

    def _make_row(self, task, is_trigger: bool) -> TaskRow:
        row = TaskRow(task, is_trigger)
        row.picked.connect(self.select_task)
        self.rows[task] = row
        return row

    def _build_filters(self) -> None:
        current = self.filter_tabs.current_key() or self.state.get("filter") or KIND_ALL
        self.filter_tabs.blockSignals(True)
        self.filter_tabs.clear()

        both_kinds = bool(self.onetime_tasks) and bool(self.trigger_tasks)
        groups = task_groups(self.onetime_tasks + self.trigger_tasks)
        self.groups = groups
        self.filter_tabs.add_tab(KIND_ALL, _t("TasksPage", "All"), len(self.onetime_tasks) + len(self.trigger_tasks),
                                 task_category_icon(KIND_ALL))
        if both_kinds:
            self.filter_tabs.add_tab(KIND_ONETIME, _t("TasksPage", "On-demand"), len(self.onetime_tasks),
                                     task_category_icon(KIND_ONETIME, "bolt"))
            self.filter_tabs.add_tab(KIND_TRIGGER, _t("TasksPage", "Triggers"), len(self.trigger_tasks),
                                     task_category_icon(KIND_TRIGGER, "timer"))
        if groups:
            self.filter_tabs.add_separator()
            for name, group_icon in groups.items():
                count = len([t for t in self.onetime_tasks + self.trigger_tasks
                             if getattr(t, 'group_name', None) == name])
                resolved = task_category_icon(GROUP_PREFIX + name, group_icon)
                self.filter_tabs.add_tab(GROUP_PREFIX + name, _app_tr(name), count, resolved)
        self.filter_tabs.setVisible(both_kinds or bool(groups))
        keys = self.filter_tabs.keys()
        self.filter_tabs.set_current(current if current in keys else KIND_ALL)
        self.filter_tabs.blockSignals(False)

    # --- filtering and layout -------------------------------------------------

    def current_filter(self) -> str:
        return self.filter_tabs.current_key() or KIND_ALL

    def set_filter(self, key: str) -> None:
        if key in self.filter_tabs.keys():
            self.filter_tabs.set_current(key)

    def _on_filter_changed(self, key: str) -> None:
        self.state["filter"] = key
        self._apply_filter()

    def _apply_filter(self) -> None:
        key = self.current_filter()
        sections = (self.onetime_section, self.trigger_section)
        for section in sections:
            shown = 0
            for row in section.rows:
                visible = matches_filter(row.task, key, row.is_trigger)
                row.setVisible(visible)
                shown += visible
            section.setVisible(shown > 0)
            section.set_count_text(str(shown))
            # Sections collapse only in the All view; a single category is one list.
            section.set_collapsible(key == KIND_ALL)
        self._title_sections(key)
        if self.selected_task in self.rows and self.rows[self.selected_task].isHidden():
            first = next((row.task for section in (self.onetime_section, self.trigger_section)
                          for row in section.rows if not row.isHidden()), None)
            self.select_task(first)
        self._layout_sections()

    def _title_sections(self, key: str) -> None:
        """A category shown as one section takes the category's name and icon."""

        self.onetime_section.set_title(_t("TasksPage", "On-demand"), task_category_icon(KIND_ONETIME, "bolt"))
        self.trigger_section.set_title(_t("TasksPage", "Triggers"), task_category_icon(KIND_TRIGGER, "timer"))
        if not key.startswith(GROUP_PREFIX):
            return
        shown = [section for section in (self.onetime_section, self.trigger_section) if not section.isHidden()]
        if len(shown) == 1:
            name = key[len(GROUP_PREFIX):]
            shown[0].set_title(_app_tr(name), task_category_icon(key, self.groups.get(name)))

    def _layout_sections(self) -> None:
        # One-time tasks take the free height; triggers keep a short scrolling list
        # unless they are the only section or the one-time section is collapsed.
        onetime, trigger = self.onetime_section, self.trigger_section
        trigger_alone = onetime.isHidden() or not onetime.is_expanded()
        for section in (onetime, trigger):
            section.setMaximumHeight(16777215)
        if not trigger.is_expanded():
            trigger.setMaximumHeight(trigger.header.height() + 2)
        elif not trigger_alone:
            trigger.setMaximumHeight(min(TRIGGER_LIST_MAX_HEIGHT, trigger.content_height()) + trigger.header.height()
                                     + 2)
        if not onetime.is_expanded():
            onetime.setMaximumHeight(onetime.header.height() + 2)
        onetime_grows = not onetime.isHidden() and onetime.is_expanded()
        trigger_grows = not trigger.isHidden() and trigger_alone and trigger.is_expanded()
        self.list_column.setStretchFactor(onetime, 1 if onetime_grows else 0)
        self.list_column.setStretchFactor(trigger, 1 if trigger_grows else 0)
        self.list_column.setStretch(2, 0 if onetime_grows or trigger_grows else 1)

    # --- selection and updates ------------------------------------------------

    def select_task(self, task) -> None:
        if self.selected_task in self.rows:
            self.rows[self.selected_task].set_selected(False)
        self.selected_task = task
        row = self.rows.get(task)
        if row is not None:
            row.set_selected(True)
            section = self.trigger_section if row.is_trigger else self.onetime_section
            # After a filter change the section still has its old height; scroll
            # once the layout has settled, or the list jumps and springs back.
            QTimer.singleShot(0, row, lambda: section.scroll.ensureWidgetVisible(row))
        self.detail.show_task(task, row.is_trigger if row is not None else False)

    def _on_task_event(self, task=None) -> None:
        if task is not None and task in self.rows:
            self.rows[task].refresh()
        else:
            for row in self.rows.values():
                row.refresh()
        self.detail.refresh()

    def dispose(self) -> None:
        """Unsubscribe from app events before the page is deleted."""

        communicate.task.disconnect(self._on_task_event)
        communicate.task_list_updated.disconnect(self.refresh_tasks)
        self.timer.stop()

    def _tick(self) -> None:
        if not self.isVisible():
            return
        for row in self.rows.values():
            row.refresh()
        self.detail.refresh()
