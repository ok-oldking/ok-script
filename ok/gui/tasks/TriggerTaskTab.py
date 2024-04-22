from typing import List

import ok.gui
from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.widget.Tab import Tab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class TriggerTaskTab(Tab):
    def __init__(self):
        super().__init__()

        for task in ok.gui.executor.trigger_tasks:
            task_card = TaskCard(task)
            self.addWidget(task_card)
