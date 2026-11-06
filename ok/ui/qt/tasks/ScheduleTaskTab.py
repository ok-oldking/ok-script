"""
Schedule Task Tab - 计划任务管理界面

提供以下功能：
1. 显示所有计划任务列表（按应用分组）
2. 创建新的计划任务
3. 启用/禁用任务
4. 删除任务
5. 修改任务配置
6. 实时更新（基于缓存和信号通知）
"""

import re
import threading
from typing import Optional, List, Callable

from PySide6.QtCore import QCoreApplication, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QTimeEdit, QVBoxLayout, QWidget)

from ok import Logger, og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.dialogs import Dialog, confirm
from ok.ui.qt.kit.feedback import Pill, show_toast
from ok.ui.qt.kit.icons import icon
from ok.ui.qt.kit.inputs import ComboBox, NumberBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.kit.theme import theme
from ok.util.windows_schedule import (
    WindowsScheduleManager, ScheduleTaskInfo, TriggerType,
    resolve_schedule_task_index,
    format_next_run_time as core_format_next_run_time,
    infer_trigger_type as core_infer_trigger_type,
    normalize_trigger_type as core_normalize_trigger_type,
)

logger = Logger.get_logger(__name__)

PAGE_MARGINS = (28, 18, 28, 20)
TRIGGER_TYPES = [TriggerType.DAILY, TriggerType.WEEKLY, TriggerType.MONTHLY, TriggerType.ONCE, TriggerType.CUSTOM]
CUSTOM_INDEX = TRIGGER_TYPES.index(TriggerType.CUSTOM)


def normalize_trigger_type(raw_type: str) -> TriggerType:
    return core_normalize_trigger_type(raw_type)


def display_trigger_type(raw_type: str, tr_func: Optional[Callable[[str], str]] = None) -> str:
    """用于 UI 展示的触发类型文本"""
    trigger = normalize_trigger_type(raw_type)
    translator = tr_func or og.app.tr
    return translator(trigger.value)


def trigger_type_to_index(raw_type: str) -> int:
    """将触发类型映射为下拉框索引"""
    trigger = normalize_trigger_type(raw_type)
    return TRIGGER_TYPES.index(trigger) if trigger in TRIGGER_TYPES else 0


def infer_trigger_type(raw_type: str, xml_config: str = "", interval_days: int = 0,
                       interval_hours: int = 0) -> TriggerType:
    return core_infer_trigger_type(raw_type, xml_config, interval_days, interval_hours)


def display_trigger_type_for_task(
        task_info: ScheduleTaskInfo,
        tr_func: Optional[Callable[[str], str]] = None,
) -> str:
    trigger = infer_trigger_type(
        task_info.trigger_type,
        task_info.xml_config,
        task_info.interval_days,
        task_info.interval_hours,
    )
    translator = tr_func or og.app.tr
    return translator(trigger.value)


def trigger_type_to_index_for_task(task_info: ScheduleTaskInfo) -> int:
    trigger = infer_trigger_type(
        task_info.trigger_type,
        task_info.xml_config,
        task_info.interval_days,
        task_info.interval_hours,
    )
    return TRIGGER_TYPES.index(trigger) if trigger in TRIGGER_TYPES else 0


def format_next_run_time(next_run_time: str) -> str:
    return core_format_next_run_time(next_run_time)


def _tr(text: str) -> str:
    # Row and dialog strings keep the old table's translation context.
    return QCoreApplication.translate("ScheduleTaskTable", text)


def _dialog_tr(text: str) -> str:
    return QCoreApplication.translate("CreateScheduleTaskDialog", text)


def task_key(task_info: ScheduleTaskInfo) -> str:
    return task_info.path or task_info.name


def status_tone(status: str) -> str:
    status = (status or "").lower()
    if "running" in status:
        return "accent"
    if "disabled" in status:
        return "neutral"
    if "ready" in status:
        return "success"
    return "warning"


# --- list --------------------------------------------------------------------------

class ScheduleRow(QFrame):
    """One scheduled task: name, status, trigger and next run, enable switch and actions."""

    def __init__(self, task_info: ScheduleTaskInfo, on_delete=None, on_view=None, on_toggle=None, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleRow")
        self.task_key = task_key(task_info)
        self._on_toggle = on_toggle

        self.tile = QLabel(self)
        self.tile.setObjectName("taskTile")
        self.tile.setFixedSize(36, 36)
        self.tile.setAlignment(Qt.AlignCenter)
        self.tile.setPixmap(icon("calendar").pixmap(QSize(18, 18), self.devicePixelRatioF()))
        self.name_label = Label("", "strong", self)
        self.status_pill = Pill("", "neutral", self)
        self.detail_label = Label("", "secondary", self)

        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(self.name_label)
        title.addWidget(self.status_pill)
        title.addStretch(1)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addLayout(title)
        text.addWidget(self.detail_label)

        self.enabled_switch = Switch(parent=self)
        self.enabled_switch.toggled.connect(self._toggled)
        self.view_button = Button(icon="pen", variant="subtle", parent=self)
        self.view_button.setToolTip(_tr("Modify"))
        self.view_button.clicked.connect(lambda: on_view(self.task_key) if on_view else None)
        self.delete_button = Button(icon="trash", variant="subtle", parent=self)
        self.delete_button.setToolTip(_tr("Delete"))
        self.delete_button.clicked.connect(lambda: on_delete(self.task_key) if on_delete else None)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.tile)
        layout.addLayout(text, 1)
        layout.addWidget(self.enabled_switch)
        layout.addSpacing(6)
        layout.addWidget(self.view_button)
        layout.addWidget(self.delete_button)
        self.update_task(task_info)

    def _toggled(self, checked):
        if self._on_toggle is not None:
            self._on_toggle(self.task_key, checked)

    @staticmethod
    def detail_text(task_info: ScheduleTaskInfo) -> str:
        trigger = display_trigger_type_for_task(task_info, _tr)
        next_run = format_next_run_time(task_info.next_run_time)
        return f"{trigger}  ·  {_tr('Next Run')} {next_run}" if next_run else trigger

    def signature(self, task_info: ScheduleTaskInfo):
        return (og.app.tr(task_info.name), _tr(task_info.status), self.detail_text(task_info),
                task_info.enabled, task_info.read_only)

    def update_task(self, task_info: ScheduleTaskInfo):
        self.task_info = task_info
        # What the row shows now, to skip updates that would change nothing.
        self.shown = self.signature(task_info)
        self.name_label.setText(og.app.tr(task_info.name))
        self.name_label.setToolTip(task_info.path or f"{og.app.tr(task_info.name)} ({task_info.name})")
        self.status_pill.setText(_tr(task_info.status))
        self.status_pill.set_tone(status_tone(task_info.status))
        self.status_pill.setVisible(bool(task_info.status))
        self.detail_label.setText(self.detail_text(task_info))
        self.enabled_switch.blockSignals(True)
        self.enabled_switch.setChecked(task_info.enabled)
        self.enabled_switch.blockSignals(False)
        self.enabled_switch.update()
        for control in (self.enabled_switch, self.view_button, self.delete_button):
            control.setEnabled(not task_info.read_only)


class ScheduleGroup(QWidget):
    """Scheduled tasks of one app: a heading and a card of rows."""

    def __init__(self, app_name: str, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.rows: dict[str, ScheduleRow] = {}
        self.count_label = Label("", "caption", self)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(Label(app_name, "section", self))
        heading.addWidget(self.count_label)
        heading.addStretch(1)
        self.card = Card(self)
        self.rows_layout = QVBoxLayout(self.card)
        self.rows_layout.setContentsMargins(0, 4, 0, 4)
        self.rows_layout.setSpacing(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addWidget(self.card)

    def has_task(self, key: str) -> bool:
        return key in self.rows

    def add_task_row(self, task_info: ScheduleTaskInfo, on_delete=None, on_view=None, on_toggle=None) -> ScheduleRow:
        row = ScheduleRow(task_info, on_delete, on_view, on_toggle, self.card)
        self.rows[row.task_key] = row
        self.rows_layout.addWidget(row)
        self._sync()
        return row

    def update_task_row(self, task_info: ScheduleTaskInfo):
        row = self.rows.get(task_key(task_info))
        if row is not None:
            row.update_task(task_info)

    def remove_task_row(self, key: str):
        row = self.rows.pop(key, None)
        if row is not None:
            row.hide()
            row.deleteLater()
            self._sync()

    def _sync(self):
        self.count_label.setText(str(len(self.rows)))
        # Rows after the first draw a divider above them.
        for index, row in enumerate(self.rows.values()):
            row.setProperty("first", index == 0)
            row.style().unpolish(row)
            row.style().polish(row)


# --- dialogs -------------------------------------------------------------------------

class ScheduleForm:
    """The shared create/modify form: trigger, start time, interval, timeout and options."""

    def __init__(self, dialog: Dialog, trigger_index=0, start=(9, 0), interval=(0, 0), timeout=0, auto_exit=True,
                 leading_rows=()):
        panel = dialog.panel
        self.dialog = dialog
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(1, 1)
        self._row = 0

        self.trigger_combo = ComboBox([_dialog_tr(trigger.value) for trigger in TRIGGER_TYPES], panel)
        self.trigger_combo.setCurrentIndex(max(0, min(len(TRIGGER_TYPES) - 1, trigger_index)))

        self.start_time_edit = QTimeEdit(QTime(max(0, min(23, start[0])), max(0, min(59, start[1]))), panel)
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setFixedWidth(120)

        self.interval_days_spin = NumberBox(max(0, min(365, interval[0])), 0, 365, parent=panel)
        self.interval_hours_spin = NumberBox(max(0, min(23, interval[1])), 0, 23, parent=panel)
        self.interval_widget = QWidget(panel)
        interval_layout = QHBoxLayout(self.interval_widget)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.setSpacing(8)
        for spin, unit in ((self.interval_days_spin, _dialog_tr("Days")),
                           (self.interval_hours_spin, _dialog_tr("Hours"))):
            spin.setFixedWidth(130)
            interval_layout.addWidget(spin)
            interval_layout.addWidget(Label(unit, "secondary", self.interval_widget))
            interval_layout.addSpacing(6)
        interval_layout.addStretch(1)

        self.timeout_spin = NumberBox(max(0, min(12, timeout)), 0, 12, parent=panel)
        self.timeout_spin.setFixedWidth(130)
        timeout_row = QWidget(panel)
        timeout_layout = QHBoxLayout(timeout_row)
        timeout_layout.setContentsMargins(0, 0, 0, 0)
        timeout_layout.setSpacing(8)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addWidget(Label(_dialog_tr("hours (0 = unlimited)"), "secondary", timeout_row))
        timeout_layout.addStretch(1)

        self.auto_exit_check = QCheckBox(_dialog_tr("Auto exit after task done (-e)"), panel)
        self.auto_exit_check.setChecked(auto_exit)

        for label, widget in leading_rows:
            self.add_row(label, widget)
        self.add_row(_dialog_tr("Trigger Type"), self.trigger_combo)
        self.add_row(_dialog_tr("Start Time"), self.start_time_edit)
        self.interval_label = self.add_row(_dialog_tr("Custom Interval"), self.interval_widget)
        self.add_row(_dialog_tr("Timeout"), timeout_row)
        self.add_row(_dialog_tr("Startup Options"), self.auto_exit_check)
        dialog.body.addLayout(self.grid)

        self.trigger_combo.currentIndexChanged.connect(self._on_trigger_type_changed)
        self._on_trigger_type_changed()

    def add_row(self, label: str, widget: QWidget):
        caption = Label(label, "strong", self.dialog.panel)
        self.grid.addWidget(caption, self._row, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.grid.addWidget(widget, self._row, 1)
        self._row += 1
        return caption

    def _on_trigger_type_changed(self, *_args):
        is_custom = self.trigger_combo.currentIndex() == CUSTOM_INDEX
        self.interval_widget.setVisible(is_custom)
        self.interval_label.setVisible(is_custom)
        if self.dialog.isVisible():
            self.dialog._fit()

    def values(self):
        time = self.start_time_edit.time()
        return (TRIGGER_TYPES[self.trigger_combo.currentIndex()], self.timeout_spin.value(), time.hour(),
                time.minute(), self.auto_exit_check.isChecked(), self.interval_days_spin.value(),
                self.interval_hours_spin.value())


class CreateScheduleTaskDialog(Dialog):
    """创建计划任务对话框"""

    task_created = Signal(
        str, int, TriggerType, int, int, int, bool, int, int
    )  # name, task_index, trigger_type, timeout_hours, start_hour, start_minute, auto_exit, interval_days, interval_hours

    def __init__(self, parent=None):
        super().__init__(parent, _dialog_tr("Create Schedule Task"),
                         _dialog_tr("Windows runs the app with this task at the chosen time, even when it is closed."),
                         ok_text=_dialog_tr("Create"), cancel_text=_dialog_tr("Cancel"), width=600)
        self.titleLabel = self.title_label

        # 获取所有 onetime_tasks（不筛 visible，未显示在 GUI 的任务也可计划调度）
        self.tasks = [
            task for task in (og.executor.onetime_tasks if og.executor.onetime_tasks else [])
            if task.support_schedule_task
        ]
        self.task_names = [og.app.tr(task.name) for task in self.tasks]
        self.task_combo = ComboBox(parent=self.panel)
        if self.task_names:
            self.task_combo.addItems(self.task_names)
        else:
            self.task_combo.addItem(_dialog_tr("No tasks available"))
            self.task_combo.setEnabled(False)

        self.form = ScheduleForm(self, leading_rows=[(_dialog_tr("Select Task"), self.task_combo)])
        self.trigger_combo = self.form.trigger_combo
        self.auto_exit_check = self.form.auto_exit_check
        self.accepted.connect(self.on_create)

        # 如果没有可用任务，禁用创建按钮
        if not self.tasks:
            self.ok_button.setEnabled(False)

    def on_create(self):
        """创建任务"""
        if not self.tasks:
            return

        selected_index = self.task_combo.currentIndex()
        if selected_index < 0 or selected_index >= len(self.tasks):
            return

        selected_task = self.tasks[selected_index]
        # -t N: N 为 onetime_tasks 的第 N 个（从 1 开始）
        task_index = og.executor.onetime_tasks.index(selected_task) + 1
        trigger_type, timeout_hours, start_hour, start_minute, auto_exit, interval_days, interval_hours = \
            self.form.values()
        self.task_created.emit(selected_task.name, task_index, trigger_type, timeout_hours, start_hour, start_minute,
                               auto_exit, interval_days, interval_hours)


class ModifyScheduleTaskDialog(Dialog):
    """修改计划任务对话框"""

    task_modified = Signal(str, int, TriggerType, int, int, int, bool, int, int)

    # task_name, task_index, trigger_type, timeout_hours, start_hour, start_minute, auto_exit, interval_days, interval_hours

    def __init__(self, task_info: ScheduleTaskInfo, parent=None):
        super().__init__(parent, _dialog_tr("Modify Schedule Task"), ok_text=_dialog_tr("Modify"),
                         cancel_text=_dialog_tr("Cancel"), width=600)
        self.titleLabel = self.title_label
        self.task_info = task_info

        try:
            self.task_index, auto_exit_default = self._parse_args(task_info.actions)
            if task_info.task_identifier:
                self.task_index = resolve_schedule_task_index(
                    task_info.task_identifier, og.executor.onetime_tasks)
            timeout_default = self._parse_timeout(task_info.xml_config)
            start_default = self._parse_start_time(task_info.next_run_time)
            interval_default = self._parse_custom_interval(task_info)
            trigger_index = trigger_type_to_index_for_task(task_info)
        except Exception as e:
            logger.exception(f"Error parsing task info: {e}")
            self.task_index, auto_exit_default = 1, False
            timeout_default, start_default, interval_default, trigger_index = 0, (0, 0), (0, 0), 0

        name_value = Label(og.app.tr(task_info.name), "body", self.panel)
        name_value.setToolTip(f"{og.app.tr(task_info.name)} ({task_info.name})")
        index_value = Label(str(self.task_index), "mono", self.panel)

        self.form = ScheduleForm(self, trigger_index, start_default, interval_default, timeout_default,
                                 auto_exit_default, leading_rows=[(_dialog_tr("Task Name"), name_value),
                                                                  (_dialog_tr("Task Index (-t)"), index_value)])
        self.trigger_combo = self.form.trigger_combo
        self.auto_exit_check = self.form.auto_exit_check
        self.accepted.connect(self.on_modify)

    def _parse_args(self, actions: str) -> tuple[int, bool]:
        """从 Action 参数解析 -t 与 -e"""
        args = actions or ""
        task_index = 1
        auto_exit = False

        m = re.search(r"(?:^|\s)-t\s+(\d+)(?:\s|$)", args)
        if m:
            task_index = int(m.group(1))

        if re.search(r"(?:^|\s)-e(?:\s|$)", args):
            auto_exit = True

        return task_index, auto_exit

    def _parse_timeout(self, xml_config: str) -> int:
        """从 XML 配置解析 ExecutionTimeLimit（超时时间）

        格式: PT{hours}H 或 PT0S (无限制)
        返回: 超时小时数，0 表示无限制
        """
        if not xml_config:
            return 0
        m = re.search(r"<ExecutionTimeLimit>PT(\d+)H</ExecutionTimeLimit>", xml_config)
        if m:
            return int(m.group(1))
        return 0

    def _parse_start_time(self, next_run_time: str) -> tuple[int, int]:
        """从下一次运行时间解析小时和分钟"""
        text = (next_run_time or "").strip()
        m = re.search(r"(\d{1,2}):(\d{1,2})(?:\d{1,2})?", text)
        if m:
            hour = max(0, min(23, int(m.group(1))))
            minute = max(0, min(59, int(m.group(2))))
            return hour, minute
        return 9, 0

    def _parse_custom_interval(self, task_info: ScheduleTaskInfo) -> tuple[int, int]:
        """优先从 task_info 读取，自定义间隔为空时再从 XML 回填"""
        interval_days = task_info.interval_days or 0
        interval_hours = task_info.interval_hours or 0

        if interval_days > 0 or interval_hours > 0:
            return interval_days, interval_hours

        xml = task_info.xml_config or ""
        if not xml:
            return 0, 0

        days_match = re.search(r"<DaysInterval>(\d+)</DaysInterval>", xml)
        if days_match:
            interval_days = int(days_match.group(1))

        hours_match = re.search(r"<Interval>PT(\d+)H</Interval>", xml)
        if hours_match:
            interval_hours = int(hours_match.group(1))

        return interval_days, interval_hours

    def on_modify(self):
        """提交修改"""
        trigger_type, timeout_hours, start_hour, start_minute, auto_exit, interval_days, interval_hours = \
            self.form.values()
        self.task_modified.emit(task_key(self.task_info), self.task_index, trigger_type, timeout_hours, start_hour,
                                start_minute, auto_exit, interval_days, interval_hours)


# --- page ------------------------------------------------------------------------------

class ScheduleTaskTab(QWidget):
    """
    计划任务管理页

    功能:
    - 按应用分组显示所有计划任务（支持多语言）
    - 创建新任务（触发类型、时间、超时等配置）
    - 修改现有任务配置
    - 启用/禁用任务
    - 删除任务
    - 手动刷新任务状态
    """

    tasks_loaded = Signal(list)
    refresh_failed = Signal(str)
    task_updated_signal = Signal(object)

    def __init__(self, config=None):
        super().__init__()
        self.setObjectName("ScheduleTaskTab")
        self.config = config
        self.schedule_manager: Optional[WindowsScheduleManager] = None
        self.groups: dict[str, ScheduleGroup] = {}
        self.refreshing = False
        self._notify_refresh = False
        self.tasks_loaded.connect(self.on_tasks_loaded)
        self.refresh_failed.connect(self.on_refresh_failed)
        self.task_updated_signal.connect(self.on_task_updated_ui)
        self.init_ui()
        self.setup_manager()
        self.render_tasks(self.schedule_manager.cache.get_all())
        self.load_tasks()

    @property
    def name(self):
        """侧边栏显示的名称"""
        return self.tr("Task Schedule")

    def init_ui(self):
        self.refresh_btn = Button(self.tr("Refresh"), "refresh", "subtle")
        self.refresh_btn.clicked.connect(self.on_refresh)
        self.create_btn = Button(self.tr("Create Task"), "plus", "primary")
        self.create_btn.clicked.connect(self.on_create_task)

        title = QVBoxLayout()
        title.setSpacing(4)
        title.addWidget(Label(QCoreApplication.translate("MainWindow", "Schedule"), "display", self))
        title.addWidget(Label(self.tr("Windows Task Scheduler starts the app and runs these tasks, "
                                      "even when the app is closed."), "secondary", self))
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addLayout(title, 1)
        header.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        header.addWidget(self.create_btn, 0, Qt.AlignTop)

        self.groups_widget = QWidget()
        self.groups_widget.setObjectName("scrollContents")
        self.groups_layout = QVBoxLayout(self.groups_widget)
        self.groups_layout.setContentsMargins(0, 0, 0, 0)
        self.groups_layout.setSpacing(20)
        self.groups_layout.setAlignment(Qt.AlignTop)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.groups_widget)

        self.empty_widget = self._build_empty_state()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(18)
        layout.addLayout(header)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.empty_widget, 1)
        theme.install(self)

    def _build_empty_state(self):
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        glyph = QLabel(widget)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setPixmap(icon("calendar").pixmap(QSize(40, 40), self.devicePixelRatioF()))
        layout.addWidget(glyph)
        title = Label(self.tr("No scheduled tasks"), "subtitle", widget)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        hint = Label(self.tr("Run a task every day, week or month without opening the app."), "secondary", widget)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        layout.addSpacing(8)
        create = Button(self.tr("Create Task"), "plus", "primary", parent=widget)
        create.clicked.connect(self.on_create_task)
        layout.addWidget(create, 0, Qt.AlignCenter)
        widget.hide()
        return widget

    def setup_manager(self):
        self.schedule_manager = WindowsScheduleManager(config=self.config)
        self.schedule_manager.register_update_callback(self.on_task_updated)

    def load_tasks(self):
        """Load without blocking construction or the Qt event loop."""
        self.on_refresh(notify=False)

    # --- rendering -----------------------------------------------------------------

    def render_tasks(self, tasks: List[ScheduleTaskInfo]):
        """按应用分组渲染任务；只更新变化的行"""
        grouped_tasks: dict[str, List[ScheduleTaskInfo]] = {}
        for task_info in tasks:
            grouped_tasks.setdefault(self._app_name_from_task(task_info), []).append(task_info)
        own_app_name = self._own_app_name()
        ordered = sorted(grouped_tasks, key=lambda name: (name != own_app_name, name.lower()))

        for app_name in list(self.groups):
            if app_name not in grouped_tasks:
                group = self.groups.pop(app_name)
                group.hide()
                group.deleteLater()

        for index, app_name in enumerate(ordered):
            group = self.groups.get(app_name)
            if group is None:
                group = ScheduleGroup(app_name, self.groups_widget)
                self.groups[app_name] = group
            self.groups_layout.insertWidget(index, group)
            self._render_group(group, grouped_tasks[app_name])

        has_tasks = bool(tasks)
        self.scroll.setVisible(has_tasks)
        self.empty_widget.setVisible(not has_tasks)

    def _render_group(self, group: ScheduleGroup, tasks: List[ScheduleTaskInfo]):
        keys = {task_key(task) for task in tasks}
        for key in [key for key in group.rows if key not in keys]:
            group.remove_task_row(key)
        for task_info in tasks:
            row = group.rows.get(task_key(task_info))
            if row is None:
                group.add_task_row(task_info, on_delete=self.on_task_deleted, on_view=self.on_task_view,
                                   on_toggle=self.on_task_toggled)
            elif row.shown != row.signature(task_info):
                row.update_task(task_info)

    def _own_app_name(self) -> str:
        if self.schedule_manager:
            return self.schedule_manager.SCHEDULE_ROOT_PATH.strip("\\") or self.tr("Current App")
        return self.tr("Current App")

    def _app_name_from_task(self, task_info: ScheduleTaskInfo) -> str:
        normalized_path = (task_info.path or "").lstrip("\\")
        if normalized_path:
            return normalized_path.split("\\", 1)[0] or self._own_app_name()
        return self._own_app_name()

    def _find_group(self, key: str) -> Optional[ScheduleGroup]:
        return next((group for group in self.groups.values() if group.has_task(key)), None)

    # --- refresh -----------------------------------------------------------------------

    def on_tasks_loaded(self, tasks: List[ScheduleTaskInfo]):
        """后台刷新完成后在主线程更新 UI"""
        self.refreshing = False
        self.setEnabled(True)
        self.render_tasks(tasks)
        logger.info(f"Loaded {len(tasks)} tasks")
        if self._notify_refresh:
            self.show_success(self.tr("Tasks refreshed"))

    def on_refresh_failed(self, error_message: str):
        self.refreshing = False
        self.setEnabled(True)
        self.show_error(self.tr("Refresh failed") + f": {error_message}")

    def on_refresh(self, checked=False, *, notify=True):
        """刷新任务列表"""
        if self.refreshing:
            return

        self.refreshing = True
        self._notify_refresh = notify
        # Prevent scheduler mutations from waiting on the worker's lock in Qt.
        self.setEnabled(False)

        def refresh():
            try:
                from ok.ui.qt.tasks.schedule_index_sync import sync_schedule_task_indexes
                sync_schedule_task_indexes(rewrite_argv=False)
                self.schedule_manager.cache.load_cache()
                tasks = self.schedule_manager.query_all_tasks(force_sync=True)
                self.tasks_loaded.emit(tasks)
            except Exception as e:
                self.refresh_failed.emit(str(e))

        self.refresh_thread = threading.Thread(target=refresh, daemon=True, name="ScheduleRefresh")
        self.refresh_thread.start()

    def on_task_updated(self, task_info: ScheduleTaskInfo):
        # 可能来自后台线程，转发到主线程更新 UI
        self.task_updated_signal.emit(task_info)

    def on_task_updated_ui(self, task_info: ScheduleTaskInfo):
        group = self.groups.get(self._app_name_from_task(task_info))
        if group:
            group.update_task_row(task_info)

    # --- actions -----------------------------------------------------------------------

    @staticmethod
    def _task_identifier(task_index):
        """模块路径.类名 is stable across task reordering, unlike the index."""
        try:
            tasks = og.executor.onetime_tasks if og.executor.onetime_tasks else []
            if isinstance(task_index, int) and 1 <= task_index <= len(tasks):
                task = tasks[task_index - 1]
                return f"{task.__class__.__module__}.{task.__class__.__name__}"
        except Exception:
            logger.exception("Failed to resolve task_identifier")
        return None

    def on_task_view(self, task_name: str):
        """打开修改任务弹窗"""
        try:
            task_info = self.schedule_manager.cache.get(task_name)
            if not task_info:
                self.show_error(self.tr("Task not found in cache"))
                return
            dialog = ModifyScheduleTaskDialog(task_info, self)
            dialog.task_modified.connect(self.on_task_modified)
            try:
                dialog.exec()
            finally:
                dialog.deleteLater()
        except Exception as e:
            logger.error(f"Failed to open modify dialog: {e}")
            self.show_error(self.tr("Failed to open modify dialog") + f": {e}")

    def on_task_modified(self, task_name: str, task_index: int, trigger_type: TriggerType, timeout_hours: int,
                         start_hour: int, start_minute: int, auto_exit: bool, interval_days: int = 0,
                         interval_hours: int = 0):
        try:
            current = self.schedule_manager.cache.get(task_name)
            enabled = current.enabled if current else True
            # 优先沿用缓存的稳定标识；旧任务没有则按索引反查任务实例
            task_identifier = getattr(current, "task_identifier", None) if current else None
            task_identifier = task_identifier or self._task_identifier(task_index)

            if not self.schedule_manager.delete_task(task_name):
                self.show_error(self.tr("Failed to modify task: cannot delete old task"))
                return

            success = self.schedule_manager.create_task(
                task_name=current.name if current else task_name,
                task_index=task_index,
                trigger_type=trigger_type,
                timeout_hours=timeout_hours,
                start_hour=start_hour,
                start_minute=start_minute,
                auto_exit=auto_exit,
                enabled=enabled,
                interval_days=interval_days,
                interval_hours=interval_hours,
                task_identifier=task_identifier,
            )
            if success:
                self.load_tasks()
                self.show_success(self.tr("Task modified successfully"))
            else:
                self.show_error(self.tr("Failed to modify task"))
        except Exception as e:
            logger.error(f"Failed to modify task: {e}")
            self.show_error(self.tr("Failed to modify task") + f": {e}")

    def on_create_task(self):
        dialog = CreateScheduleTaskDialog(self)
        dialog.task_created.connect(self.on_task_created)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def on_task_created(self, name: str, task_index: int, trigger_type: TriggerType, timeout_hours: int,
                        start_hour: int, start_minute: int, auto_exit: bool, interval_days: int = 0,
                        interval_hours: int = 0):
        try:
            success = self.schedule_manager.create_task(
                task_name=name or f"AutoTask_{task_index}",
                task_index=task_index,
                trigger_type=trigger_type,
                timeout_hours=timeout_hours,
                start_hour=start_hour,
                start_minute=start_minute,
                auto_exit=auto_exit,
                enabled=True,
                interval_days=interval_days,
                interval_hours=interval_hours,
                task_identifier=self._task_identifier(task_index),
            )
            if success:
                self.load_tasks()
                self.show_success(self.tr("Task created successfully"))
            else:
                self.show_error(self.tr("Failed to create task"))
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            self.show_error(self.tr("Failed to create task") + f": {e}")

    def on_task_deleted(self, task_name: str):
        task_info = self.schedule_manager.cache.get(task_name)
        display_name = og.app.tr(task_info.name if task_info else task_name)
        if not confirm(self, self.tr("Delete Task"),
                       self.tr("Are you sure you want to delete task") + f"\n{display_name}?",
                       ok_text=self.tr("Delete"), danger=True):
            return
        try:
            if self.schedule_manager.delete_task(task_name):
                group = self._find_group(task_name)
                if group:
                    group.remove_task_row(task_name)
                self.show_success(self.tr("Task deleted successfully"))
                if not any(group.rows for group in self.groups.values()):
                    self.render_tasks([])
            else:
                self.show_error(self.tr("Failed to delete task"))
        except Exception as e:
            logger.error(f"Failed to delete task: {e}")
            self.show_error(self.tr("Failed to delete task") + f": {e}")

    def on_task_toggled(self, task_name: str, enabled: bool):
        try:
            if enabled:
                self.schedule_manager.enable_task(task_name)
                self.show_success(self.tr("Task enabled"))
            else:
                self.schedule_manager.disable_task(task_name)
                self.show_success(self.tr("Task disabled"))
        except Exception as e:
            logger.error(f"Failed to toggle task: {e}")
            self.show_error(self.tr("Failed to toggle task") + f": {e}")

    def show_success(self, message: str):
        show_toast(self, message, tone="success")

    def show_error(self, message: str):
        show_toast(self, message, self.tr("Error"), tone="danger", duration=6000)

    def closeEvent(self, event):
        if self.schedule_manager:
            self.schedule_manager.stop_background_sync()
        super().closeEvent(event)
