import gettext
import os
import sys

from PySide6.QtCore import QSize, QCoreApplication, QTranslator, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, qconfig

import ok
from ok.firebase.Analytics import Analytics
from ok.gui import resources
from ok.gui.Communicate import communicate
from ok.gui.MainWindow import MainWindow
from ok.gui.MessageWindow import MessageWindow
from ok.gui.StartController import StartController
from ok.gui.common.config import cfg, Language
from ok.gui.i18n.GettextTranslator import get_translations
from ok.gui.i18n.path import i18n_path
from ok.gui.overlay.OverlayWindow import OverlayWindow
from ok.logging.Logger import get_logger
from ok.update.Updater import Updater

logger = get_logger(__name__)


class App:
    def __init__(self, config,
                 exit_event=None):
        super().__init__()
        self.config = config
        logger.debug(
            f'resources.qt_resource_name {resources.qt_resource_name} cfg.themeMode {cfg.themeMode.value}')
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

        self.app = QApplication(sys.argv)
        communicate.quit.connect(self.app.quit)
        self.app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
        qconfig.theme = cfg.themeMode.value

        self.about = self.config.get('about')
        self.title = self.config.get('gui_title')
        self.version = self.config.get('version')
        self.overlay = self.config.get('debug')
        self.locale = cfg.get(cfg.language).value
        logger.debug(f'locale name {self.locale.name()}')
        translator = FluentTranslator(self.locale)
        self.app.installTranslator(translator)
        self.loading_window = None
        self.overlay_window = None
        self.main_window = None
        self.exit_event = exit_event
        self.icon = QIcon(self.config.get('gui_icon') or ":/icon/icon.ico")
        if self.config.get('analytics'):
            self.fire_base_analytics = Analytics(self.config, self.exit_event)

        translator = QTranslator(self.app)
        full_path = os.path.join(i18n_path, f"{self.locale.name()}")
        if translator.load(self.locale.name(), ":/i18n"):
            translator.setParent(self.app)
            self.app.installTranslator(translator)
            QCoreApplication.installTranslator(translator)
            logger.debug(f"translator install success {QCoreApplication.translate('MainWindow', 'Debug')}")
        else:
            logger.debug(f"No translation available for {self.locale}, falling back to English/default. {full_path}")
        if self.config.get('update'):
            self.updater = Updater(self.config, exit_event)
        else:
            self.updater = None
        self.start_controller = StartController(self.config, exit_event)
        if self.config.get('debug'):
            self.to_translate = set()
        else:
            self.to_translate = None
        self.po_translation = None
        ok.gui.app = self

    def tr(self, key):
        if not key:
            return key
        if self.to_translate is not None:
            self.to_translate.add(key)
        if self.po_translation is None:
            try:
                self.po_translation = get_translations(self.locale.name())
                self.po_translation.install()
                logger.info(f'translation installed for {self.locale.name()}')
            except Exception as e:
                logger.error(f'install translations error for {self.locale.name()}', e)
                self.po_translation = "Failed"
        if self.po_translation != 'Failed':
            return self.po_translation.gettext(key)
        else:
            return key

    def gen_tr_po_files(self):
        folder = ""
        for locale in Language:
            from ok.gui.i18n.GettextTranslator import update_po_file
            folder = update_po_file(self.to_translate, locale.value.name())
        return folder

    def center_window(self, window):
        screen = self.app.primaryScreen()
        size = screen.size()
        # Calculate half the screen size
        half_screen_width = size.width() / 2
        half_screen_height = size.height() / 2
        window.move(half_screen_width / 2, half_screen_height / 2)

    def show_message_window(self, title, message):
        message_window = MessageWindow(self.icon, title, message, exit_event=self.exit_event)
        message_window.show()

    def show_already_running_error(self):
        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Another instance is already running")
        self.show_message_window(title, content)

    def show_path_ascii_error(self, path):
        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Install dir {path} must be an English path, move to another path.").format(
            path=path)
        self.show_message_window(title, content)

    def update_overlay(self, visible, x, y, window_width, window_height, width, height, scaling):
        if self.overlay_window is None:
            self.overlay_window = OverlayWindow(ok.gui.device_manager.hwnd)
        self.overlay_window.update_overlay(visible, x, y, window_width, window_height, width, height, scaling)

    def show_main_window(self):

        if self.overlay and ok.gui.device_manager.hwnd is not None:
            communicate.window.connect(self.update_overlay)

        self.main_window = MainWindow(self.config, self.icon, self.title, self.version, self.overlay, self.about,
                                      self.exit_event)
        # Set the window title here
        self.main_window.setWindowIcon(self.icon)

        size = self.size_relative_to_screen(width=0.5, height=0.6)
        self.main_window.resize(size)
        self.main_window.setMinimumSize(size)

        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        logger.debug(f'show_main_window end')

    def size_relative_to_screen(self, width, height):
        screen = self.app.primaryScreen()
        size = screen.size()
        # Calculate half the screen size
        half_screen_width = size.width() * width
        half_screen_height = size.height() * height
        # Resize the window to half the screen size
        size = QSize(half_screen_width, half_screen_height)
        return size

    def exec(self):
        sys.exit(self.app.exec())

    @staticmethod
    def quit():
        communicate.quit.emit()
