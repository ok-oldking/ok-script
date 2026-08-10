# coding:utf-8
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog


class BaseLoading():

    def __init__(self):
        super().__init__()
        self.loading_dialog = None

    def show_loading(self, message=""):
        if not self.loading_dialog:
            self.loading_dialog = StartLoadingDialog(-1,
                                                     self.window())
        self.loading_dialog.show()

    def close_loading(self):
        self.loading_dialog.close()
