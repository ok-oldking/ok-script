from typing import List

import ok.gui
from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TaskTab import TaskTab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class TriggerTaskTab(TaskTab):
    def __init__(self):
        super().__init__()

        for task in ok.gui.executor.trigger_tasks:
            task_card = TaskCard(task, False)
            self.addWidget(task_card)

    def in_current_list(self, task):
        return task in ok.gui.executor.trigger_tasks
