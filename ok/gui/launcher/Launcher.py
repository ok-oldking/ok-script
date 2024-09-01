from ok.gui.launcher.LauncherWindow import LauncherWindow
from ok.gui.util.app import init_app_config, center_window


class Launcher:

    def __init__(self, config):
        self.app = None
        self.locale = None
        self.config = config

    def start(self):
        self.app, self.locale = init_app_config()

        w = LauncherWindow(self.config)
        center_window(self.app, w)
        w.show()
        self.app.exec_()
