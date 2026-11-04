import sys

from PySide6.QtCore import Qt, QTranslator, QCoreApplication
from PySide6.QtWidgets import QApplication

from ok import Logger
from ok.ui.qt import resources
from ok.ui.qt.common.config import cfg

logger = Logger.get_logger(__name__)

_translator = None


def install_translator(app):
    """Replace the installed Qt translator with one for ``cfg.language``; returns the locale."""
    global _translator
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator.deleteLater()
        _translator = None
    locale = cfg.language.value
    translator = QTranslator(app)
    if translator.load(locale.name(), ":/i18n"):
        app.installTranslator(translator)
        _translator = translator
        logger.info(f"translator install success {locale}, {QCoreApplication.translate('MainWindow', 'Debug')}")
    else:
        translator.deleteLater()
        logger.info(f"No translation available for {locale}, falling back to English/default.")
    return locale


def init_app_config():
    logger.debug(f'resources.qt_resource_name {resources.qt_resource_name} theme {cfg.theme_mode}')

    app = QApplication(sys.argv)
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app.setAttribute(Qt.AA_EnableHighDpiScaling)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    locale = install_translator(app)

    from ok.ui.qt.kit import Theme, theme
    theme.set_theme(Theme(cfg.theme_mode))
    theme.set_backdrop(cfg.backdrop)
    return app, locale


def show_info_bar(window, message, title=None, error=False):
    """Show a toast in ``window``; errors stay a little longer."""
    from ok.ui.qt.kit.feedback import show_toast
    if title is not None:
        title = QCoreApplication.translate('app', title)
    message = QCoreApplication.translate('app', message)
    return show_toast(window, message, title, tone="danger" if error else "neutral",
                      duration=8000 if error else 5000)


def get_localized_app_config(config, key):
    locale = cfg.language.value.name()

    if config.get(locale):
        config_dict = config.get(locale)
    else:
        config_dict = config.get('default')
    if config_dict:
        return config_dict.get(key)
