"""Turn the icon values pages and apps pass into something the sidebar can draw."""

from pathlib import Path

from PySide6.QtGui import QIcon

from ok.core.icons import Icon
from ok.ui.qt.kit.icons import ICON_NAMES, load_icon

_SEMANTIC = {
    Icon.APPLICATION: "grid",
    Icon.GAME: "gamepad",
    Icon.PEOPLE: "users",
    Icon.RINGER: "bell",
    Icon.SYNC: "refresh",
    Icon.UPDATE: "refresh",
}

# Old pages still pass Fluent icons until they are ported to the kit.
_FLUENT = {
    "PLAY": "play", "STOP_WATCH": "timer", "BOOK_SHELF": "tasks", "DEVELOPER_TOOLS": "bug",
    "COMMAND_PROMPT": "terminal", "EDIT": "pen", "PHOTO": "image", "CALENDAR": "calendar", "RINGER": "bell",
    "SETTING": "gear", "QUESTION": "info", "APPLICATION": "grid", "GAME": "gamepad", "PEOPLE": "users",
    "SYNC": "refresh", "UPDATE": "refresh", "CODE": "code", "FOLDER": "folder", "INFO": "info",
    "HISTORY": "history", "LINK": "link", "HEART": "heart", "ROBOT": "gamepad", "TAG": "layers",
    "LIBRARY": "layers", "DOCUMENT": "file", "CAMERA": "camera", "MESSAGE": "bell",
}

FALLBACK = "grid"


def nav_icon(source, base_dir=None):
    """A bundled icon name or a QIcon for ``source``.

    Accepts ``None``, a bundled icon name, an ``ok.core.icons.Icon``, a path to
    an SVG/PNG, a QIcon, or a Fluent icon from a page not yet ported.
    """

    if source is None:
        return FALLBACK
    if isinstance(source, QIcon):
        return source
    if isinstance(source, Icon):
        return _SEMANTIC.get(source, FALLBACK)
    if isinstance(source, str):
        if source in ICON_NAMES:
            return source
        try:
            semantic = Icon(source)
        except ValueError:
            semantic = None
        if semantic is not None:
            return _SEMANTIC[semantic]
        if Path(source).suffix.lower() in (".svg", ".png", ".jpg", ".jpeg", ".ico", ".bmp", ".webp"):
            try:
                return load_icon(source, base_dir)
            except (OSError, ValueError):
                return FALLBACK
        return FALLBACK
    name = getattr(source, "name", None)
    if isinstance(name, str) and name in _FLUENT:
        return _FLUENT[name]
    if callable(getattr(source, "icon", None)):
        try:
            result = source.icon()
            if isinstance(result, QIcon) and not result.isNull():
                return result
        except Exception:
            pass
    return FALLBACK
