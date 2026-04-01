from ok import Logger, og

from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TaskTab import TaskTab

logger = Logger.get_logger(__name__)


class OneTimeTaskTab(TaskTab):
    def __init__(self, is_standalone=True, group_name=None):
        super().__init__()
        self.is_standalone = is_standalone
        self.group_name = group_name
        self.card_widgets = []
        self.keep_info_when_done = True
        
        from ok.gui.Communicate import communicate
        communicate.task_list_updated.connect(self.refresh_ui)
        self.refresh_ui()

    def refresh_ui(self):
        # Remove old cards
        for w in self.card_widgets:
            self.removeWidget(w)
            w.deleteLater()
        self.card_widgets.clear()
        
        self.tasks = []
        for task in og.executor.onetime_tasks:
            task_group = getattr(task, 'group_name', None)
            if self.is_standalone and not task_group:
                self.tasks.append(task)
            elif self.group_name and task_group == self.group_name:
                self.tasks.append(task)
                
        for task in self.tasks:
            task_card = TaskCard(task, True)
            self.card_widgets.append(task_card)
            # Insert right before the task_info_container
            index = self.vBoxLayout.indexOf(self.task_info_container)
            self.vBoxLayout.insertWidget(index, task_card)

    def in_current_list(self, task):
        return getattr(self, 'tasks', None) and task in self.tasks
