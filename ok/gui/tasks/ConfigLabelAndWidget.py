from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigLabelAndWidget(LabelAndWidget):

    def __init__(self, config_desc, config, key: str):
        desc = None
        self.key = key
        self.config = config
        if config_desc is not None:
            desc = config_desc.get(key)
        super().__init__(key, desc)

    def update_config(self, value):
        self.config[self.key] = value
