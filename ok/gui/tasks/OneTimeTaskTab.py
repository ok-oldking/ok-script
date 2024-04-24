from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

import ok.gui
from ok.gui.Communicate import communicate
from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TooltipTableWidget import TooltipTableWidget
from ok.gui.widget.Tab import Tab
from ok.gui.widget.UpdateConfigWidgetItem import value_to_string
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class OneTimeTaskTab(Tab):
    def __init__(self):
        super().__init__()

        self.task_info_table = TooltipTableWidget()
        self.task_info_container = self.addCard(self.tr("Choose Window"), self.task_info_table)
        self.addWidget(self.task_info_container)

        for task in ok.gui.executor.onetime_tasks:
            task_card = TaskCard(task)
            self.addWidget(task_card)

        self.task_info_labels = [self.tr('Info'), self.tr('Value')]
        self.task_info_table.setColumnCount(len(self.task_info_labels))  # Name and Value
        self.task_info_table.setHorizontalHeaderLabels(self.task_info_labels)
        self.update_info_table()

        communicate.task.connect(self.task_update)
        communicate.task_info.connect(self.update_info_table)

    def task_update(self, task):
        if task == ok.gui.executor.current_task:
            self.update_info_table()

    def update_info_table(self):
        task = ok.gui.executor.current_task
        if task is None:
            self.task_info_container.hide()
        else:
            self.task_info_container.show()
            info = task.info
            self.task_info_container.titleLabel.setText(f"{self.tr('Running')}: {task.name}")
            self.task_info_table.setRowCount(len(info))
            for row, (key, value) in enumerate(info.items()):
                if not self.task_info_table.item(row, 0):
                    item0 = self.uneditable_item()
                    self.task_info_table.setItem(row, 0, item0)
                self.task_info_table.item(row, 0).setText(key)
                if not self.task_info_table.item(row, 1):
                    item1 = self.uneditable_item()
                    self.task_info_table.setItem(row, 1, item1)
                self.task_info_table.item(row, 1).setText(value_to_string(value))

    def uneditable_item(self):
        item = QTableWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item
