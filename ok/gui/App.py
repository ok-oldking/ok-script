import os
import sys

from PySide6.QtCore import QSize, QCoreApplication, QLocale, QTranslator, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from qfluentwidgets import FluentTranslator, qconfig, Theme

import ok
import ok.gui.resources
from ok.gui.Communicate import communicate
from ok.gui.MainWindow import MainWindow
from ok.gui.i18n.path import i18n_path
from ok.gui.overlay.OverlayWindow import OverlayWindow
from ok.gui.start.StartTab import StartTab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class App:
    def __init__(self, config,
                 exit_event=None):
        super().__init__()
        self.config = config

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

        self.app = QApplication(sys.argv)
        self.app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
        locale = QLocale()
        qconfig.theme = Theme.AUTO
        translator = FluentTranslator(locale)
        self.app.installTranslator(translator)

        self.about = self.config.get('about')
        self.title = self.config.get('gui_title')
        self.overlay = self.config.get('debug')
        self.loading_window = None
        self.overlay_window = None
        self.main_window = None
        self.exit_event = exit_event
        self.icon = QIcon(self.config.get('gui_icon') or ":/icon/icon.ico")
        self.tray = QSystemTrayIcon(self.icon)

        translator = QTranslator(self.app)
        full_path = os.path.join(i18n_path, f"{QLocale().name()}")
        if translator.load(locale.name(), ":/i18n"):
            translator.setParent(self.app)
            self.app.installTranslator(translator)
            QCoreApplication.installTranslator(translator)
            logger.debug(f"translator install success {QCoreApplication.translate('MainWindow', 'Debug')}")
        else:
            logger.debug(f"No translation available for {locale}, falling back to English/default. {full_path}")

        # Create a context menu for the tray
        menu = QMenu()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.quit)

        # Set the context menu and show the tray icon
        self.tray.setContextMenu(menu)
        self.tray.show()

        communicate.notification.connect(self.show_notification)

    def show_notification(self, title, message):
        if title is None:
            title = self.title
        self.tray.showMessage(title, message)

    def show(self):
        self.loading_window = StartTab(self, self.exit_event)
        size = self.size_relative_to_screen(width=0.6, height=0.4)
        self.loading_window.resize(size)
        self.loading_window.setMinimumSize(size)
        self.center_window(self.loading_window)
        self.loading_window.show()

    def center_window(self, window):
        screen = self.app.primaryScreen()
        size = screen.size()
        # Calculate half the screen size
        half_screen_width = size.width() / 2
        half_screen_height = size.height() / 2

        window.move(half_screen_width / 2, half_screen_height / 2)

    def show_main_window(self):
        self.main_window = MainWindow(self.overlay, self.about, exit_event=self.exit_event)
        self.main_window.setWindowTitle(self.title)  # Set the window title here
        self.main_window.setWindowIcon(self.icon)
        if self.overlay and ok.gui.device_manager.hwnd is not None:
            self.overlay_window = OverlayWindow(ok.gui.device_manager.hwnd)

        size = self.size_relative_to_screen(width=0.5, height=0.6)
        self.main_window.resize(size)
        self.main_window.setMinimumSize(size)

        # Optional: Move the window to the center of the screen

        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

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

    def quit(self):
        self.exit_event.set()
        self.app.quit()
