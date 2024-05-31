from ok.gui.Communicate import communicate


class InfoDict(dict):

    def __delitem__(self, key):
        super().__delitem__(key)
        communicate.task_info.emit()

    def clear(self):
        super().clear()
        communicate.task_info.emit()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        communicate.task_info.emit()
