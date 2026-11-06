# coding:utf-8
"""UI preferences stored in ``configs/ui_config.json``: language, theme and window backdrop."""

import json
import os
from enum import Enum

from PySide6.QtCore import QLocale, QObject, Signal

from ok.util.file import get_relative_path
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

BACKDROPS = ("mica", "acrylic", "none")
DEFAULT_BACKDROP = "acrylic"


class Language(Enum):
    """ Language enumeration """

    CHINESE_SIMPLIFIED = QLocale(QLocale.Chinese, QLocale.SimplifiedChineseScript)
    CHINESE_TRADITIONAL = QLocale(QLocale.Chinese, QLocale.TraditionalChineseScript)
    ENGLISH = QLocale(QLocale.English)
    SPANISH = QLocale(QLocale.Spanish)
    JAPANESE = QLocale(QLocale.Japanese)
    KOREAN = QLocale(QLocale.Korean)
    AUTO = QLocale()


def serialize_language(language: Language) -> str:
    return language.value.name() if language != Language.AUTO else "Auto"


def deserialize_language(value) -> Language:
    if not value or value == "Auto":
        return Language.AUTO
    try:
        return Language(QLocale(value))
    except ValueError:
        return Language.AUTO


class UiConfig(QObject):
    """The language, the theme mode and the window backdrop, all applied live.

    The file also accepts the older qfluentwidgets layout
    (``MainWindow.Language`` and ``QFluentWidgets.ThemeMode``).
    """

    language_changed = Signal()
    theme_changed = Signal()

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        data = self._read()
        legacy_language = (data.get("MainWindow") or {}).get("Language")
        legacy_theme = (data.get("QFluentWidgets") or {}).get("ThemeMode")
        self.language = deserialize_language(data.get("language", legacy_language))
        self.theme_mode = str(data.get("theme", legacy_theme or "auto")).lower()
        if self.theme_mode not in ("light", "dark", "auto"):
            self.theme_mode = "auto"
        # Older files store only whether the effect is on ("mica", or qfluentwidgets'
        # MicaEnabled, which was on by default); on maps to the current default.
        legacy_on = data.get("mica", (data.get("MainWindow") or {}).get("MicaEnabled", True))
        self.backdrop = str(data.get("backdrop", DEFAULT_BACKDROP if legacy_on else "none")).lower()
        if self.backdrop not in BACKDROPS:
            self.backdrop = DEFAULT_BACKDROP

    def _read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            logger.error(f"Failed to read {self.path}", error)
            return {}

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as file:
                json.dump({"language": serialize_language(self.language), "theme": self.theme_mode,
                           "backdrop": self.backdrop}, file, indent=4)
        except OSError as error:
            logger.error(f"Failed to save {self.path}", error)

    def set_language(self, language: Language) -> None:
        if language == self.language:
            return
        self.language = language
        self.save()
        self.language_changed.emit()

    def set_theme_mode(self, mode: str) -> None:
        mode = getattr(mode, "value", mode)
        if mode == self.theme_mode:
            return
        self.theme_mode = mode
        self.save()
        self.theme_changed.emit()

    def set_backdrop(self, backdrop: str) -> None:
        backdrop = getattr(backdrop, "value", backdrop)
        if backdrop == self.backdrop or backdrop not in BACKDROPS:
            return
        self.backdrop = backdrop
        self.save()
        self.theme_changed.emit()


cfg = UiConfig(get_relative_path('configs', "ui_config.json"))
