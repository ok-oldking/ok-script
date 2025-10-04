from ok import Logger, og

from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TaskTab import TaskTab

logger = Logger.get_logger(__name__)


class OneTimeTaskTab(TaskTab):
    def __init__(self):
        super().__init__()

        for task in og.executor.onetime_tasks:
            task_card = TaskCard(task, True)
            self.add_widget(task_card)
        self.keep_info_when_done = True

    def in_current_list(self, task):
        return task in og.executor.onetime_tasks
