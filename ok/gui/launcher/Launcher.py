import os
import sys

from ok.gui.launcher.LauncherWindow import LauncherWindow
from ok.gui.util.app import init_app_config, center_window
from ok.logging.Logger import get_logger, config_logger
from ok.update.GitUpdater import GitUpdater
from ok.util.exit_event import ExitEvent

logger = get_logger(__name__)


class Launcher:

    def __init__(self, config):
        self.app = None
        self.locale = None
        self.config = config
        self.exit_event = ExitEvent()
        config_logger(self.config, name='launcher')
        self.app = None
        self.locale = None
        self.updater = None
        logger.info(f'Launcher__init__ app_config = {config}')

    def start(self):
        try:
            self.app, self.locale = init_app_config()
            self.updater = GitUpdater(self.config, self.exit_event)
            self.updater.list_all_versions()
            logger.info(f'launcher start pid {os.getpid()} {self.locale}')
            w = LauncherWindow(self.config, self.updater, self.exit_event)
            center_window(self.app, w)
            w.show()
            self.app.exec_()
        except Exception as e:
            logger.error('launcher start error', e)
            self.exit_event.set()
            sys.exit(0)
