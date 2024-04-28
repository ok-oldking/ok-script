from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigLabelAndWidget(LabelAndWidget):

    def __init__(self, config_desc, key: str):
        desc = None
        if config_desc is not None:
            desc = config_desc.get(key)
        super().__init__(key, desc)
