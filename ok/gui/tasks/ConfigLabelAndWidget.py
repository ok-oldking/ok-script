from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigLabelAndWidget(LabelAndWidget):

    def __init__(self, task, key: str):
        desc = None
        self.key = key
        self.task = task
        self.config = task.config
        if task.config_description is not None:
            desc = task.config_description.get(key)
        super().__init__(key, desc)

    def update_config(self, value):
        self.config[self.key] = value
