from ok import Logger, og

from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TaskTab import TaskTab

logger = Logger.get_logger(__name__)


class TriggerTaskTab(TaskTab):
    def __init__(self):
        super().__init__()
        self.card_widgets = []
        from ok.gui.Communicate import communicate
        communicate.task_list_updated.connect(self.refresh_ui)
        self.refresh_ui()

    def refresh_ui(self):
        for w in self.card_widgets:
            self.removeWidget(w)
            w.deleteLater()
        self.card_widgets.clear()
        
        for task in og.executor.trigger_tasks:
            task_card = TaskCard(task, False)
            self.card_widgets.append(task_card)
            self.add_widget(task_card)

    def in_current_list(self, task):
        return task in og.executor.trigger_tasks
