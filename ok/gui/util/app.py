import os
import sys

from PySide6.QtCore import Qt, QTranslator, QCoreApplication
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, qconfig

from ok.gui.common.config import cfg
from ok.gui.i18n.path import i18n_path
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


def init_app_config():
    locale = cfg.get(cfg.language).value
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    translator = FluentTranslator(locale)
    app.installTranslator(translator)
    translator = QTranslator(app)
    full_path = os.path.join(i18n_path, f"{locale.name()}")
    if translator.load(locale.name(), ":/i18n"):
        translator.setParent(app)
        app.installTranslator(translator)
        QCoreApplication.installTranslator(translator)
        logger.debug(f"translator install success {QCoreApplication.translate('MainWindow', 'Debug')}")
    else:
        logger.debug(f"No translation available for {locale}, falling back to English/default. {full_path}")
    qconfig.theme = cfg.themeMode.value
    return app, locale


def center_window(app, window):
    screen = app.primaryScreen()
    size = screen.size()
    # Calculate half the screen size
    half_screen_width = size.width() / 2
    half_screen_height = size.height() / 2
    window.move(half_screen_width / 2, half_screen_height / 2)
