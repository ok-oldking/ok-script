"""
Schedule Task Tab - 计划任务管理界面

提供以下功能：
1. 显示所有计划任务列表
2. 创建新的计划任务
3. 启用/禁用任务
4. 删除任务
5. 查看任务详情
6. 实时更新（基于缓存和信号通知）
"""

from typing import Optional, List, Callable
import re
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
    QHeaderView,
)
from qfluentwidgets import (
    PushButton,
    SwitchButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    TableWidget,
    MessageBoxBase,
    SubtitleLabel,
    ComboBox,
    SpinBox,
    CheckBox,
)

from ok import Logger, og
from ok.gui.widget.Tab import Tab
from ok.util.windows_schedule import WindowsScheduleManager, ScheduleTaskInfo, TriggerType

logger = Logger.get_logger(__name__)


def normalize_trigger_type(raw_type: str) -> TriggerType:
    """将 COM/schtasks 的触发器类型统一为 TriggerType"""
    value = (raw_type or "").strip()
    lowered = value.lower()

    if value in (TriggerType.DAILY.value, "2") or "daily" in lowered:
        return TriggerType.DAILY
    if value in (TriggerType.WEEKLY.value, "3") or "weekly" in lowered:
        return TriggerType.WEEKLY
    if value in (TriggerType.MONTHLY.value, "4", "5", "6") or "monthly" in lowered:
        return TriggerType.MONTHLY
    if value in (TriggerType.ONCE.value, "1") or "once" in lowered or "time" in lowered:
        return TriggerType.ONCE
    if value in (TriggerType.CUSTOM.value,) or "custom" in lowered:
        return TriggerType.CUSTOM

    return TriggerType.DAILY


def display_trigger_type(raw_type: str, tr_func: Optional[Callable[[str], str]] = None) -> str:
    """用于 UI 展示的触发类型文本"""
    trigger = normalize_trigger_type(raw_type)
    translator = tr_func or og.app.tr
    return translator(trigger.value)


def trigger_type_to_index(raw_type: str) -> int:
    """将触发类型映射为下拉框索引"""
    trigger = normalize_trigger_type(raw_type)
    mapping = {
        TriggerType.DAILY: 0,
        TriggerType.WEEKLY: 1,
        TriggerType.MONTHLY: 2,
        TriggerType.ONCE: 3,
        TriggerType.CUSTOM: 4,
    }
    return mapping.get(trigger, 0)


def infer_trigger_type(raw_type: str, xml_config: str = "", interval_days: int = 0,
                       interval_hours: int = 0) -> TriggerType:
    """综合 raw/xml/interval 推断触发类型，避免读取异常时回显错误"""
    if interval_hours > 0 or interval_days > 1:
        return TriggerType.CUSTOM

    trigger = normalize_trigger_type(raw_type)
    raw_value = (raw_type or "").strip()

    # raw 可识别且不是默认兜底值时直接用
    if raw_value and (raw_value.isdigit() or raw_value.lower() in {"daily", "weekly", "monthly", "once", "custom"}):
        return trigger

    xml = (xml_config or "").lower()
    if not xml:
        return trigger

    if "<repetition>" in xml and "<interval>pt" in xml and "h</interval>" in xml:
        return TriggerType.CUSTOM
    if "<schedulebyweek>" in xml:
        return TriggerType.WEEKLY
    if "<schedulebymonth>" in xml:
        return TriggerType.MONTHLY
    if "<timetrigger>" in xml and "<repetition>" not in xml:
        return TriggerType.ONCE
    if "<schedulebyday>" in xml:
        return TriggerType.DAILY

    return trigger


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
    mapping = {
        TriggerType.DAILY: 0,
        TriggerType.WEEKLY: 1,
        TriggerType.MONTHLY: 2,
        TriggerType.ONCE: 3,
        TriggerType.CUSTOM: 4,
    }
    return mapping.get(trigger, 0)


def format_next_run_time(next_run_time: str) -> str:
    """格式化下次运行时间，截取关键参数"""
    if not next_run_time:
        return "-"

    # 如果已经很短，直接返回
    if len(next_run_time) <= 16:  # 例如 "2026-03-06 14:30"
        return next_run_time

    # 尝试提取日期和时间部分，移除额外的信息
    # 优先保留 "YYYY-MM-DD HH:MM" 格式
    parts = next_run_time.split()
    if len(parts) >= 2:
        date_part = parts[0]
        time_part = parts[1]
        # 检查时间格式是否包含秒
        if len(time_part) > 5:  # "HH:MM:SS"
            time_part = time_part[:5]  # 只保留 "HH:MM"
        return f"{date_part} {time_part}"

    # 如果无法分割，就截取前16个字符
    return next_run_time[:16]


class ScheduleTaskTable(TableWidget):
    """计划任务表格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            [
                self.tr("Task Name"),
                self.tr("Status"),
                self.tr("Trigger Type"),
                self.tr("Next Run"),
                self.tr("Enabled"),
                self.tr("Actions"),
            ]
        )
        # 列宽策略：全动态（不固定任何列）
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 任务名称占用剩余空间
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 状态按内容
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 触发类型按内容
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 下次运行按内容
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 启用状态按内容
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 操作按内容
        header.setStretchLastSection(False)

        # 设置最小高度
        self.setMinimumHeight(300)
        # 自动调整行高
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # 回调字典
        self.delete_callbacks = {}
        self.view_callbacks = {}
        self.toggle_callbacks = {}

    def add_task_row(self, task_info: ScheduleTaskInfo, on_delete=None, on_view=None, on_toggle=None) -> int:
        """添加任务行"""
        row = self.rowCount()
        self.insertRow(row)

        # 任务名称
        name_item = QTableWidgetItem(og.app.tr(task_info.name))
        name_item.setData(Qt.UserRole, task_info.name)
        name_item.setToolTip(f"{og.app.tr(task_info.name)} ({task_info.name})")
        self.setItem(row, 0, name_item)

        # 状态
        status_item = QTableWidgetItem(self.tr(task_info.status))
        self.setItem(row, 1, status_item)

        # 触发类型
        trigger_item = QTableWidgetItem(display_trigger_type_for_task(task_info, self.tr))
        self.setItem(row, 2, trigger_item)

        # 下次运行时间
        next_run_item = QTableWidgetItem(format_next_run_time(task_info.next_run_time))
        self.setItem(row, 3, next_run_item)

        # 启用状态（开关按钮）
        enabled_widget = QWidget()
        enabled_layout = QHBoxLayout()
        enabled_layout.setContentsMargins(0, 0, 0, 0)
        enabled_switch = SwitchButton()
        enabled_switch.setChecked(task_info.enabled)
        # 隐藏 on/off 文本（如果组件支持）
        if hasattr(enabled_switch, "setOnText"):
            enabled_switch.setOnText("")
        if hasattr(enabled_switch, "setOffText"):
            enabled_switch.setOffText("")
        enabled_switch.checkedChanged.connect(lambda checked: on_toggle(task_info.name, checked) if on_toggle else None)
        enabled_layout.addWidget(enabled_switch, alignment=Qt.AlignCenter)
        enabled_widget.setLayout(enabled_layout)
        self.setCellWidget(row, 4, enabled_widget)

        # 操作按钮
        actions_widget = QWidget()
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(5)

        view_btn = PushButton(self.tr("Modify"))
        view_btn.clicked.connect(lambda: on_view(task_info.name) if on_view else None)
        delete_btn = PushButton(self.tr("Delete"))
        delete_btn.clicked.connect(lambda: on_delete(task_info.name) if on_delete else None)

        actions_layout.addWidget(view_btn)
        actions_layout.addWidget(delete_btn)
        actions_widget.setLayout(actions_layout)
        self.setCellWidget(row, 5, actions_widget)

        return row

    def update_task_row(self, task_info: ScheduleTaskInfo):
        """更新任务行"""
        for row in range(self.rowCount()):
            name_item = self.item(row, 0)
            if name_item and name_item.data(Qt.UserRole) == task_info.name:
                name_item.setText(og.app.tr(task_info.name))
                name_item.setToolTip(f"{og.app.tr(task_info.name)} ({task_info.name})")
                self.item(row, 1).setText(self.tr(task_info.status))
                self.item(row, 2).setText(display_trigger_type_for_task(task_info, self.tr))
                self.item(row, 3).setText(format_next_run_time(task_info.next_run_time))

                # 更新开关状态
                enabled_widget = self.cellWidget(row, 4)
                if enabled_widget:
                    switch = enabled_widget.findChild(SwitchButton)
                    if switch:
                        switch.setChecked(task_info.enabled)
                break

    def remove_task_row(self, task_name: str):
        """删除任务行"""
        for row in range(self.rowCount()):
            name_item = self.item(row, 0)
            if name_item and name_item.data(Qt.UserRole) == task_name:
                self.removeRow(row)
                break


class CreateScheduleTaskDialog(MessageBoxBase):
    """创建计划任务对话框"""

    task_created = Signal(
        str, int, TriggerType, int, int, int, bool, int, int
    )  # name, task_index, trigger_type, timeout_hours, start_hour, start_minute, auto_exit, interval_days, interval_hours

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("Create Schedule Task"), self)

        # 获取所有 onetime_tasks
        self.tasks = [task for task in (og.executor.onetime_tasks if og.executor.onetime_tasks else []) if task.support_schedule_task]
        self.task_names = [og.app.tr(task.name) for task in self.tasks]

        self.viewLayout.setSpacing(12)
        self.viewLayout.setContentsMargins(16, 12, 16, 12)

        # 任务选择
        task_label = QLabel(self.tr("Select Task"))
        task_label.setMinimumWidth(120)
        self.task_combo = ComboBox()
        self.task_combo.setFixedHeight(34)
        if self.task_names:
            self.task_combo.addItems(self.task_names)
            self.task_combo.setCurrentIndex(0)
        else:
            self.task_combo.addItem(self.tr("No tasks available"))
            self.task_combo.setEnabled(False)

        # 触发类型
        trigger_label = QLabel(self.tr("Trigger Type"))
        trigger_label.setMinimumWidth(120)
        self.trigger_combo = ComboBox()
        # 使用翻译后的触发类型文本
        self.trigger_combo.addItems(
            [
                self.tr(TriggerType.DAILY.value),
                self.tr(TriggerType.WEEKLY.value),
                self.tr(TriggerType.MONTHLY.value),
                self.tr(TriggerType.ONCE.value),
                self.tr(TriggerType.CUSTOM.value),
            ]
        )
        self.trigger_combo.setFixedHeight(34)
        # 不在这里连接信号，先不触发初始化
        self.trigger_combo.setCurrentIndex(0)

        # 开始时间（24小时制）
        start_time_label = QLabel(self.tr("Start Time"))
        start_time_label.setMinimumWidth(120)
        self.start_hour_spin = SpinBox()
        self.start_hour_spin.setRange(0, 23)
        self.start_hour_spin.setValue(9)
        self.start_hour_spin.setFixedWidth(120)
        self.start_hour_spin.setFixedHeight(34)

        self.start_minute_spin = SpinBox()
        self.start_minute_spin.setRange(0, 59)
        self.start_minute_spin.setValue(0)
        self.start_minute_spin.setFixedWidth(120)
        self.start_minute_spin.setFixedHeight(34)

        start_time_input_layout = QHBoxLayout()
        start_time_input_layout.setContentsMargins(0, 0, 0, 0)
        start_time_input_layout.setSpacing(8)
        start_time_input_layout.addWidget(QLabel(self.tr("Hour")), 0)
        start_time_input_layout.addWidget(self.start_hour_spin, 0)
        start_time_input_layout.addWidget(QLabel(":"), 0)
        start_time_input_layout.addWidget(QLabel(self.tr("Minute")), 0)
        start_time_input_layout.addWidget(self.start_minute_spin, 0)
        start_time_input_layout.addWidget(QLabel(self.tr("24h")), 0)
        start_time_input_layout.addStretch(1)

        start_time_input_widget = QWidget()
        start_time_input_widget.setLayout(start_time_input_layout)

        # 自定义间隔
        self.interval_label = QLabel(self.tr("Custom Interval"))
        self.interval_label.setMinimumWidth(120)

        self.interval_days_spin = SpinBox()
        self.interval_days_spin.setRange(0, 365)
        self.interval_days_spin.setValue(0)
        self.interval_days_spin.setFixedWidth(140)
        self.interval_days_spin.setFixedHeight(34)

        self.interval_hours_spin = SpinBox()
        self.interval_hours_spin.setRange(0, 23)
        self.interval_hours_spin.setValue(0)
        self.interval_hours_spin.setFixedWidth(140)
        self.interval_hours_spin.setFixedHeight(34)

        interval_input_layout = QHBoxLayout()
        interval_input_layout.setContentsMargins(0, 0, 0, 0)
        interval_input_layout.setSpacing(8)
        interval_input_layout.addWidget(QLabel(self.tr("Days")), 0)
        interval_input_layout.addWidget(self.interval_days_spin, 0)
        interval_input_layout.addWidget(QLabel(self.tr("Hours")), 0)
        interval_input_layout.addWidget(self.interval_hours_spin, 0)
        interval_input_layout.addWidget(QLabel(self.tr("(0 = disabled)")), 0)
        interval_input_layout.addStretch(1)

        self.interval_widget = QWidget()
        self.interval_widget.setLayout(interval_input_layout)

        # 现在连接信号和初始化显示状态
        self.trigger_combo.currentIndexChanged.connect(self._on_trigger_type_changed)
        self._on_trigger_type_changed()

        # 超时限制
        timeout_label = QLabel(self.tr("Timeout"))
        timeout_label.setMinimumWidth(120)
        self.timeout_spin = SpinBox()
        self.timeout_spin.setMinimum(0)
        self.timeout_spin.setMaximum(12)
        self.timeout_spin.setValue(0)
        self.timeout_spin.setFixedWidth(160)
        self.timeout_spin.setFixedHeight(34)

        timeout_input_layout = QHBoxLayout()
        timeout_input_layout.setContentsMargins(0, 0, 0, 0)
        timeout_input_layout.setSpacing(8)
        timeout_input_layout.addWidget(self.timeout_spin, 0)
        timeout_input_layout.addWidget(QLabel(self.tr("hours (0 = unlimited)")), 0)
        timeout_input_layout.addStretch(1)

        timeout_input_widget = QWidget()
        timeout_input_widget.setLayout(timeout_input_layout)

        # 启动参数选项
        self.auto_exit_check = CheckBox(self.tr("Auto exit after task done (-e)"))
        self.auto_exit_check.setChecked(True)

        form_widget = QWidget()
        form_layout = QGridLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(16)
        form_layout.setVerticalSpacing(10)
        form_layout.addWidget(task_label, 0, 0)
        form_layout.addWidget(self.task_combo, 0, 1)
        form_layout.addWidget(trigger_label, 1, 0)
        form_layout.addWidget(self.trigger_combo, 1, 1)
        form_layout.addWidget(start_time_label, 2, 0)
        form_layout.addWidget(start_time_input_widget, 2, 1)
        form_layout.addWidget(self.interval_label, 3, 0)
        form_layout.addWidget(self.interval_widget, 3, 1)
        form_layout.addWidget(timeout_label, 4, 0)
        form_layout.addWidget(timeout_input_widget, 4, 1)
        form_layout.addWidget(QLabel(self.tr("Startup Options")), 5, 0)
        form_layout.addWidget(self.auto_exit_check, 5, 1)
        form_layout.setColumnStretch(1, 1)

        # 默认隐藏 interval_label
        self.interval_label.hide()

        # 添加到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(form_widget)

        # 设置按钮文本
        self.yesButton.setText(self.tr("Create"))
        self.cancelButton.setText(self.tr("Cancel"))

        # 设置最小宽度
        self.widget.setMinimumWidth(620)

        # 连接信号
        self.yesButton.clicked.connect(self.on_create)

        # 如果没有可用任务，禁用创建按钮
        if not self.tasks:
            self.yesButton.setEnabled(False)

    def _on_trigger_type_changed(self):
        """触发类型改变时，控制自定义间隔输入的显示"""
        trigger_index = self.trigger_combo.currentIndex()
        # 第 5 个（索引 4）是 CUSTOM
        is_custom = trigger_index == 4
        self.interval_widget.setVisible(is_custom)
        self.interval_label.setVisible(is_custom)

    def on_create(self):
        """创建任务"""
        if not self.tasks:
            return

        selected_index = self.task_combo.currentIndex()
        if selected_index < 0 or selected_index >= len(self.tasks):
            return

        selected_task = self.tasks[selected_index]
        task_name = selected_task.name
        # -t N: N 为 onetime_tasks 的第 N 个（从 1 开始）
        task_index = og.executor.onetime_tasks.index(selected_task) + 1
        # 根据下拉框索引获取触发类型
        trigger_types = [
            TriggerType.DAILY,
            TriggerType.WEEKLY,
            TriggerType.MONTHLY,
            TriggerType.ONCE,
            TriggerType.CUSTOM,
        ]
        trigger_type = trigger_types[self.trigger_combo.currentIndex()]
        timeout_hours = self.timeout_spin.value()
        start_hour = self.start_hour_spin.value()
        start_minute = self.start_minute_spin.value()
        auto_exit = self.auto_exit_check.isChecked()
        interval_days = self.interval_days_spin.value()
        interval_hours = self.interval_hours_spin.value()

        self.task_created.emit(
            task_name,
            task_index,
            trigger_type,
            timeout_hours,
            start_hour,
            start_minute,
            auto_exit,
            interval_days,
            interval_hours,
        )


class ModifyScheduleTaskDialog(MessageBoxBase):
    """修改计划任务对话框"""

    task_modified = Signal(str, int, TriggerType, int, int, int, bool, int, int)

    # task_name, task_index, trigger_type, timeout_hours, start_hour, start_minute, auto_exit, interval_days, interval_hours

    def __init__(self, task_info: ScheduleTaskInfo, parent=None):
        super().__init__(parent)
        self.task_info = task_info

        try:
            self.titleLabel = SubtitleLabel(self.tr("Modify Schedule Task"), self)
            self.viewLayout.setSpacing(12)
            self.viewLayout.setContentsMargins(16, 12, 16, 12)

            self.task_index, auto_exit_default = self._parse_args(task_info.actions)
            timeout_default = self._parse_timeout(task_info.xml_config)
            start_hour_default, start_minute_default = self._parse_start_time(task_info.next_run_time)
            interval_days_default, interval_hours_default = self._parse_custom_interval(task_info)

            logger.debug(
                f"ModifyScheduleTaskDialog init - task: {task_info.name}, "
                f"trigger_type: {task_info.trigger_type}, "
                f"interval_days: {interval_days_default}, "
                f"interval_hours: {interval_hours_default}"
            )
        except Exception as e:
            logger.exception(f"Error parsing task info: {e}")
            self.task_index, auto_exit_default = 1, False
            timeout_default = 0
            start_hour_default, start_minute_default = 0, 0
            interval_days_default, interval_hours_default = 0, 0

        # 任务名称（显示，不可修改）
        task_name_label = QLabel(self.tr("Task Name"))
        task_name_label.setMinimumWidth(140)
        task_name_display = QLabel(og.app.tr(task_info.name))
        task_name_display.setToolTip(f"{og.app.tr(task_info.name)} ({task_info.name})")
        task_name_display.setMinimumWidth(260)

        # 任务索引（显示，不可修改）
        task_index_label = QLabel(self.tr("Task Index (-t)"))
        task_index_label.setMinimumWidth(140)
        task_index_display = QLabel(str(self.task_index))
        task_index_display.setMinimumWidth(260)

        # 触发类型
        trigger_label = QLabel(self.tr("Trigger Type"))
        trigger_label.setMinimumWidth(140)
        self.trigger_combo = ComboBox()
        # 使用翻译后的触发类型文本
        self.trigger_combo.addItems(
            [
                self.tr(TriggerType.DAILY.value),
                self.tr(TriggerType.WEEKLY.value),
                self.tr(TriggerType.MONTHLY.value),
                self.tr(TriggerType.ONCE.value),
                self.tr(TriggerType.CUSTOM.value),
            ]
        )
        try:
            trigger_index = trigger_type_to_index_for_task(task_info)
            logger.debug(f"Setting trigger combo index: {trigger_index}")
            if trigger_index < 0 or trigger_index > 4:
                logger.warning(f"Invalid trigger index {trigger_index}, defaulting to 0")
                trigger_index = 0
            self.trigger_combo.setCurrentIndex(trigger_index)
        except Exception as e:
            logger.exception(f"Error setting trigger combo index: {e}")
            self.trigger_combo.setCurrentIndex(0)
        self.trigger_combo.setFixedHeight(34)
        self.trigger_combo.currentIndexChanged.connect(self._on_trigger_type_changed)

        # 开始时间（24小时制）
        start_time_label = QLabel(self.tr("Start Time"))
        start_time_label.setMinimumWidth(140)
        self.start_hour_spin = SpinBox()
        self.start_hour_spin.setRange(0, 23)
        try:
            start_hour_default = max(0, min(23, start_hour_default))
            self.start_hour_spin.setValue(start_hour_default)
        except Exception as e:
            logger.debug(f"Error setting start hour: {e}, defaulting to 0")
            self.start_hour_spin.setValue(0)
        self.start_hour_spin.setFixedWidth(120)
        self.start_hour_spin.setFixedHeight(34)

        self.start_minute_spin = SpinBox()
        self.start_minute_spin.setRange(0, 59)
        try:
            start_minute_default = max(0, min(59, start_minute_default))
            self.start_minute_spin.setValue(start_minute_default)
        except Exception as e:
            logger.debug(f"Error setting start minute: {e}, defaulting to 0")
            self.start_minute_spin.setValue(0)
        self.start_minute_spin.setFixedWidth(120)
        self.start_minute_spin.setFixedHeight(34)

        start_time_input_layout = QHBoxLayout()
        start_time_input_layout.setContentsMargins(0, 0, 0, 0)
        start_time_input_layout.setSpacing(8)
        start_time_input_layout.addWidget(QLabel(self.tr("Hour")), 0)
        start_time_input_layout.addWidget(self.start_hour_spin, 0)
        start_time_input_layout.addWidget(QLabel(":"), 0)
        start_time_input_layout.addWidget(QLabel(self.tr("Minute")), 0)
        start_time_input_layout.addWidget(self.start_minute_spin, 0)
        start_time_input_layout.addWidget(QLabel(self.tr("24h")), 0)
        start_time_input_layout.addStretch(1)

        start_time_input_widget = QWidget()
        start_time_input_widget.setLayout(start_time_input_layout)

        # 超时限制
        timeout_label = QLabel(self.tr("Timeout"))
        timeout_label.setMinimumWidth(140)
        self.timeout_spin = SpinBox()
        self.timeout_spin.setMinimum(0)
        self.timeout_spin.setMaximum(12)
        try:
            timeout_default = max(0, min(12, timeout_default))
            self.timeout_spin.setValue(timeout_default)
        except Exception as e:
            logger.debug(f"Error setting timeout: {e}, defaulting to 0")
            self.timeout_spin.setValue(0)
        self.timeout_spin.setFixedWidth(160)
        self.timeout_spin.setFixedHeight(34)

        timeout_input_layout = QHBoxLayout()
        timeout_input_layout.setContentsMargins(0, 0, 0, 0)
        timeout_input_layout.setSpacing(8)
        timeout_input_layout.addWidget(self.timeout_spin, 0)
        timeout_input_layout.addWidget(QLabel(self.tr("hours (0 = unlimited)")), 0)
        timeout_input_layout.addStretch(1)

        timeout_input_widget = QWidget()
        timeout_input_widget.setLayout(timeout_input_layout)

        # 自定义间隔（仅当触发类型为 CUSTOM 时显示）
        self.interval_label = QLabel(self.tr("Custom Interval"))
        self.interval_label.setMinimumWidth(140)

        self.interval_days_spin = SpinBox()
        self.interval_days_spin.setMinimum(0)
        self.interval_days_spin.setMaximum(365)
        try:
            interval_days_default = max(0, min(365, interval_days_default))
            self.interval_days_spin.setValue(interval_days_default)
        except Exception as e:
            logger.debug(f"Error setting interval days: {e}, defaulting to 0")
            self.interval_days_spin.setValue(0)
        self.interval_days_spin.setFixedWidth(140)
        self.interval_days_spin.setFixedHeight(34)

        self.interval_hours_spin = SpinBox()
        self.interval_hours_spin.setMinimum(0)
        self.interval_hours_spin.setMaximum(23)
        try:
            interval_hours_default = max(0, min(23, interval_hours_default))
            self.interval_hours_spin.setValue(interval_hours_default)
        except Exception as e:
            logger.debug(f"Error setting interval hours: {e}, defaulting to 0")
            self.interval_hours_spin.setValue(0)
        self.interval_hours_spin.setFixedWidth(140)
        self.interval_hours_spin.setFixedHeight(34)

        self.interval_widget = QWidget()
        interval_layout = QHBoxLayout()
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.setSpacing(8)
        interval_layout.addWidget(QLabel(self.tr("Days")), 0)
        interval_layout.addWidget(self.interval_days_spin, 0)
        interval_layout.addWidget(QLabel(self.tr("Hours")), 0)
        interval_layout.addWidget(self.interval_hours_spin, 0)
        interval_layout.addWidget(QLabel(self.tr("(0 = disabled)")), 0)
        interval_layout.addStretch(1)
        self.interval_widget.setLayout(interval_layout)

        # 初始化时根据当前触发类型显示/隐藏间隔控件
        try:
            self._on_trigger_type_changed()
        except Exception as e:
            logger.exception(f"Error in _on_trigger_type_changed: {e}")
            self.interval_widget.setVisible(False)
            self.interval_label.setVisible(False)

        # 启动参数选项
        self.auto_exit_check = CheckBox(self.tr("Auto exit after task done (-e)"))
        try:
            self.auto_exit_check.setChecked(auto_exit_default)
        except Exception as e:
            logger.debug(f"Error setting auto_exit check: {e}")
            self.auto_exit_check.setChecked(False)

        try:
            form_widget = QWidget()
            form_layout = QGridLayout(form_widget)
            form_layout.setContentsMargins(0, 0, 0, 0)
            form_layout.setHorizontalSpacing(16)
            form_layout.setVerticalSpacing(10)
            form_layout.addWidget(task_name_label, 0, 0)
            form_layout.addWidget(task_name_display, 0, 1)
            form_layout.addWidget(task_index_label, 1, 0)
            form_layout.addWidget(task_index_display, 1, 1)
            form_layout.addWidget(trigger_label, 2, 0)
            form_layout.addWidget(self.trigger_combo, 2, 1)
            form_layout.addWidget(start_time_label, 3, 0)
            form_layout.addWidget(start_time_input_widget, 3, 1)
            form_layout.addWidget(timeout_label, 4, 0)
            form_layout.addWidget(timeout_input_widget, 4, 1)
            form_layout.addWidget(self.interval_label, 5, 0)
            form_layout.addWidget(self.interval_widget, 5, 1)
            form_layout.addWidget(QLabel(self.tr("Startup Options")), 6, 0)
            form_layout.addWidget(self.auto_exit_check, 6, 1)
            form_layout.setColumnStretch(1, 1)

            self.viewLayout.addWidget(self.titleLabel)
            self.viewLayout.addWidget(form_widget)

            self.yesButton.setText(self.tr("Modify"))
            self.cancelButton.setText(self.tr("Cancel"))
            self.widget.setMinimumWidth(640)

            self.yesButton.clicked.connect(self.on_modify)
        except Exception as e:
            logger.exception(f"Error setting up form layout: {e}")
            # 显示一个简单的错误消息而不是崩溃
            error_label = QLabel(f"Error initializing dialog: {str(e)[:100]}")
            self.viewLayout.addWidget(error_label)
            self.yesButton.clicked.connect(self.close)

    def _on_trigger_type_changed(self):
        """触发类型改变时，控制自定义间隔输入的显示"""
        trigger_index = self.trigger_combo.currentIndex()
        # 第 5 个（索引 4）是 CUSTOM
        is_custom = trigger_index == 4
        self.interval_widget.setVisible(is_custom)
        self.interval_label.setVisible(is_custom)

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
            logger.debug("XML config is empty")
            return 0

        # 匹配 <ExecutionTimeLimit>PT5H</ExecutionTimeLimit> 或 PT0S
        m = re.search(r"<ExecutionTimeLimit>PT(\d+)H</ExecutionTimeLimit>", xml_config)
        if m:
            timeout = int(m.group(1))
            logger.debug(f"Parsed timeout from XML: {timeout} hours")
            return timeout

        # PT0S 表示无限制
        if "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml_config:
            logger.debug("Timeout is unlimited (PT0S)")
            return 0

        logger.debug(f"Could not parse timeout from XML, length: {len(xml_config)}")
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
        # 根据下拉框索引获取触发类型
        trigger_types = [
            TriggerType.DAILY,
            TriggerType.WEEKLY,
            TriggerType.MONTHLY,
            TriggerType.ONCE,
            TriggerType.CUSTOM,
        ]
        trigger_type = trigger_types[self.trigger_combo.currentIndex()]
        timeout_hours = self.timeout_spin.value()
        start_hour = self.start_hour_spin.value()
        start_minute = self.start_minute_spin.value()
        auto_exit = self.auto_exit_check.isChecked()
        # 从 spin 控件获取间隔（支持修改）
        interval_days = self.interval_days_spin.value()
        interval_hours = self.interval_hours_spin.value()

        self.task_modified.emit(
            self.task_info.name,
            self.task_index,
            trigger_type,
            timeout_hours,
            start_hour,
            start_minute,
            auto_exit,
            interval_days,
            interval_hours,
        )


class ScheduleTaskTab(Tab):
    """
    计划任务管理标签页

    功能:
    - 显示所有计划任务列表（支持多语言）
    - 创建新任务（触发类型、时间、超时等配置）
    - 修改现有任务配置
    - 启用/禁用任务
    - 删除任务
    - 实时刷新任务状态

    任务名称从源代码类的 name 属性获取
    触发类型、状态等文本支持框架自动翻译
    """

    tasks_loaded = Signal(list)
    refresh_failed = Signal(str)
    task_updated_signal = Signal(object)

    def __init__(self, config=None):
        super().__init__()
        self.config = config
        self.schedule_manager: Optional[WindowsScheduleManager] = None
        self.task_table: Optional[ScheduleTaskTable] = None
        self.refreshing = False
        # 仅通过软件内操作与手动刷新管理任务，不启用自动轮询/后台同步
        self.enable_ui_polling = False
        self.enable_background_sync = False
        self.icon = FluentIcon.CALENDAR  # 设置侧边栏图标
        self.tasks_loaded.connect(self.on_tasks_loaded)
        self.refresh_failed.connect(self.on_refresh_failed)
        self.task_updated_signal.connect(self.on_task_updated_ui)
        self.init_ui()
        self.setup_manager()
        self.load_tasks()

    @property
    def name(self):
        """侧边栏显示的名称"""
        return self.tr("Task Schedule")

    def init_ui(self):
        """初始化 UI"""
        # 顶部工具栏
        toolbar_layout = QHBoxLayout()

        self.refresh_btn = PushButton(FluentIcon.SYNC, self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self.on_refresh)
        toolbar_layout.addWidget(self.refresh_btn)

        create_btn = PushButton(FluentIcon.ADD, self.tr("Create Task"))
        create_btn.clicked.connect(self.on_create_task)
        toolbar_layout.addWidget(create_btn)

        toolbar_layout.addStretch()
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar_layout)
        self.add_widget(toolbar_widget)

        # 任务表格
        self.task_table = ScheduleTaskTable()
        table_container = self.add_card(self.tr("Schedule Tasks"), self.task_table)
        self.add_widget(table_container)

        # 连接表格信号
        self.task_table.itemClicked.connect(self.on_table_item_clicked)

        # 可选：定时刷新表格（默认关闭，采用手动刷新 + 操作后更新）
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_table)
        if self.enable_ui_polling:
            self.timer.start(5000)  # 每 5 秒刷新一次

    def setup_manager(self):
        """设置管理器"""
        self.schedule_manager = WindowsScheduleManager(config=self.config)
        self.schedule_manager.register_update_callback(self.on_task_updated)

        # 可选：后台同步（默认关闭）
        if self.enable_background_sync:
            self.schedule_manager.start_background_sync(interval=30)

    def load_tasks(self):
        """加载任务列表"""
        try:
            tasks = self.schedule_manager.query_all_tasks(force_sync=True)
            self.render_tasks(tasks)
            logger.info(f"Loaded {len(tasks)} tasks")
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            self.show_error(self.tr("Failed to load tasks") + f": {e}")

    def render_tasks(self, tasks: List[ScheduleTaskInfo]):
        """渲染任务列表（智能更新，只在数据变化时重新渲染）"""
        # 构建新任务字典
        new_tasks_dict = {task.name: task for task in tasks}

        # 获取当前表格中的任务
        existing_tasks = set()
        rows_to_remove = []

        # 检查现有行，标记需要删除或更新的
        for row in range(self.task_table.rowCount()):
            name_item = self.task_table.item(row, 0)
            if name_item:
                task_name = name_item.data(Qt.UserRole) or name_item.text()
                existing_tasks.add(task_name)

                if task_name not in new_tasks_dict:
                    # 任务已被删除，标记行待删除
                    rows_to_remove.append(row)
                else:
                    # 任务存在，检查是否需要更新
                    new_task = new_tasks_dict[task_name]
                    if self._task_changed(row, new_task):
                        self.task_table.update_task_row(new_task)

        # 从后往前删除行（避免索引问题）
        for row in reversed(rows_to_remove):
            self.task_table.removeRow(row)

        # 添加新任务
        for task_info in tasks:
            if task_info.name not in existing_tasks:
                self.task_table.add_task_row(
                    task_info, on_delete=self.on_task_deleted, on_view=self.on_task_view, on_toggle=self.on_task_toggled
                )

    def _task_changed(self, row: int, new_task: ScheduleTaskInfo) -> bool:
        """检查任务是否有变化"""
        # 检查状态
        status_item = self.task_table.item(row, 1)
        if status_item and status_item.text() != self.tr(new_task.status):
            return True

        # 检查触发类型
        trigger_item = self.task_table.item(row, 2)
        if trigger_item and trigger_item.text() != display_trigger_type_for_task(new_task, self.tr):
            return True

        # 检查下次运行时间
        next_run_item = self.task_table.item(row, 3)
        if next_run_item and next_run_item.text() != format_next_run_time(new_task.next_run_time):
            return True

        # 检查启用状态
        enabled_widget = self.task_table.cellWidget(row, 4)
        if enabled_widget:
            switch = enabled_widget.findChild(SwitchButton)
            if switch and switch.isChecked() != new_task.enabled:
                return True

        return False

    def on_tasks_loaded(self, tasks: List[ScheduleTaskInfo]):
        """后台刷新完成后在主线程更新 UI"""
        self.refreshing = False
        self.refresh_btn.setEnabled(True)
        self.render_tasks(tasks)
        self.show_success(self.tr("Tasks refreshed"))

    def on_refresh_failed(self, error_message: str):
        """后台刷新失败处理"""
        self.refreshing = False
        self.refresh_btn.setEnabled(True)
        self.show_error(self.tr("Refresh failed") + f": {error_message}")

    def update_table(self):
        """更新表格（主要用于刷新状态）"""
        try:
            tasks = self.schedule_manager.cache.get_all()
            for task_info in tasks:
                self.task_table.update_task_row(task_info)
        except Exception as e:
            logger.error(f"Failed to update table: {e}")

    def on_table_item_clicked(self, item):
        """表格项点击处理"""
        # 此方法保留以防需要，但按钮已直接连接回调
        pass

    def on_task_view(self, task_name: str):
        """打开修改任务弹窗"""
        try:
            task_info = self.schedule_manager.cache.get(task_name)
            if not task_info:
                self.show_error(self.tr("Task not found in cache"))
                return

            dialog = ModifyScheduleTaskDialog(task_info, self)
            dialog.task_modified.connect(self.on_task_modified)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open modify dialog: {e}")
            self.show_error(self.tr("Failed to open modify dialog") + f": {e}")

    def on_task_modified(
            self,
            task_name: str,
            task_index: int,
            trigger_type: TriggerType,
            timeout_hours: int,
            start_hour: int,
            start_minute: int,
            auto_exit: bool,
            interval_days: int = 0,
            interval_hours: int = 0,
    ):
        """处理任务修改"""
        try:
            current = self.schedule_manager.cache.get(task_name)
            enabled = current.enabled if current else True

            deleted = self.schedule_manager.delete_task(task_name)
            if not deleted:
                self.show_error(self.tr("Failed to modify task: cannot delete old task"))
                return

            success = self.schedule_manager.create_task(
                task_name=task_name,
                task_index=task_index,
                trigger_type=trigger_type,
                timeout_hours=timeout_hours,
                start_hour=start_hour,
                start_minute=start_minute,
                auto_exit=auto_exit,
                enabled=enabled,
                interval_days=interval_days,
                interval_hours=interval_hours,
            )
            if success:
                self.load_tasks()
                self.show_success(self.tr("Task modified successfully"))
            else:
                self.show_error(self.tr("Failed to modify task"))
        except Exception as e:
            logger.error(f"Failed to modify task: {e}")
            self.show_error(self.tr("Failed to modify task") + f": {e}")

    def on_task_updated(self, task_info: ScheduleTaskInfo):
        """任务更新回调"""
        # 可能来自后台线程，转发到主线程更新 UI
        self.task_updated_signal.emit(task_info)

    def on_task_updated_ui(self, task_info: ScheduleTaskInfo):
        """在主线程中更新单行任务信息"""
        self.task_table.update_task_row(task_info)

    def on_refresh(self):
        """刷新任务列表"""
        if self.refreshing:
            return

        self.refreshing = True
        self.refresh_btn.setEnabled(False)

        def refresh():
            try:
                tasks = self.schedule_manager.query_all_tasks(force_sync=True)
                self.tasks_loaded.emit(tasks)
            except Exception as e:
                self.refresh_failed.emit(str(e))

        # 后台线程刷新
        import threading

        thread = threading.Thread(target=refresh, daemon=True)
        thread.start()

    def on_create_task(self):
        """创建任务"""
        dialog = CreateScheduleTaskDialog(self)
        dialog.task_created.connect(self.on_task_created)
        dialog.exec()

    def on_task_created(
            self,
            name: str,
            task_index: int,
            trigger_type: TriggerType,
            timeout_hours: int,
            start_hour: int,
            start_minute: int,
            auto_exit: bool,
            interval_days: int = 0,
            interval_hours: int = 0,
    ):
        """处理任务创建"""
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
        """删除任务"""
        from qfluentwidgets import BodyLabel

        dialog = MessageBoxBase(self)

        # 手动创建并添加标题
        title_label = SubtitleLabel(self.tr("Delete Task"), self)
        dialog.viewLayout.addWidget(title_label)

        display_name = og.app.tr(task_name)
        content = BodyLabel(
            self.tr("Are you sure you want to delete task") + f"\n{display_name}?"
        )
        content.setWordWrap(True)
        dialog.viewLayout.addWidget(content)

        dialog.yesButton.setText(self.tr("Delete"))
        dialog.cancelButton.setText(self.tr("Cancel"))

        if dialog.exec():
            try:
                success = self.schedule_manager.delete_task(task_name)
                if success:
                    self.task_table.remove_task_row(task_name)
                    self.show_success(self.tr("Task deleted successfully"))
                else:
                    self.show_error(self.tr("Failed to delete task"))
            except Exception as e:
                logger.error(f"Failed to delete task: {e}")
                self.show_error(self.tr("Failed to delete task") + f": {e}")

    def on_task_toggled(self, task_name: str, enabled: bool):
        """切换任务启用状态"""
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
        """显示成功消息"""
        InfoBar.success(
            title=self.tr("Success"),
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def show_error(self, message: str):
        """显示错误消息"""
        InfoBar.error(
            title=self.tr("Error"),
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def closeEvent(self, event):
        """关闭事件 - 停止后台同步"""
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
        if self.schedule_manager:
            self.schedule_manager.stop_background_sync()
        super().closeEvent(event)
