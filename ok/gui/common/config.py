# coding:utf-8
import sys
from enum import Enum

from PySide6.QtCore import QLocale
from qfluentwidgets import (qconfig, QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            OptionsValidator, RangeConfigItem, RangeValidator,
                            ConfigSerializer)

from ok import get_relative_path


class Language(Enum):
    """ Language enumeration """

    CHINESE_SIMPLIFIED = QLocale(QLocale.Chinese, QLocale.SimplifiedChineseScript)
    CHINESE_TRADITIONAL = QLocale(QLocale.Chinese, QLocale.TraditionalChineseScript)
    ENGLISH = QLocale(QLocale.English)
    SPANISH = QLocale(QLocale.Spanish)
    JAPANESE = QLocale(QLocale.Japanese)
    KOREAN = QLocale(QLocale.Korean)
    AUTO = QLocale()


class LanguageSerializer(ConfigSerializer):
    """ Language serializer """

    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


def isWin11():
    return sys.platform == 'win32' and sys.getwindowsversion().build >= 22000


class AppConfig(QConfig):
    """ Config of application """

    # main window
    micaEnabled = ConfigItem("MainWindow", "MicaEnabled", isWin11(), BoolValidator())
    dpiScale = OptionsConfigItem(
        "MainWindow", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)
    language = OptionsConfigItem(
        "MainWindow", "Language", Language.AUTO, OptionsValidator(Language), LanguageSerializer(), restart=True)

    # Material
    blurRadius = RangeConfigItem("Material", "AcrylicBlurRadius", 15, RangeValidator(0, 40))

    # software update
    checkUpdateAtStartUp = ConfigItem("Update", "CheckUpdateAtStartUp", True, BoolValidator())
    # themeMode = OptionsConfigItem(
    #     "QFluentWidgets", "ThemeMode", Theme.DARK, OptionsValidator(Theme), EnumSerializer(Theme))


cfg = AppConfig()
qconfig.load(get_relative_path('configs', f"ui_config.json"), cfg)

if __name__ == '__main__':
    locale = Language.ENGLISH
    print(locale.name)
    print(locale.value.name())
    print(locale.value.language())
    print(QLocale.languageToString(locale.value.language()))
