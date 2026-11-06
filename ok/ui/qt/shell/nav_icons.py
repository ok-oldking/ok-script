"""Turn the icon values pages and apps pass into something the sidebar can draw."""

from pathlib import Path, PurePath

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

FALLBACK = "grid"


def nav_icon(source, base_dir=None, *, trim_transparent: bool = False):
    """A bundled icon name or a QIcon for ``source``.

    Accepts ``None``, a bundled icon name, an ``ok.core.icons.Icon``, a path to
    an SVG/PNG, a QIcon, or an object whose ``icon()`` returns a QIcon.
    """

    if source is None:
        return FALLBACK
    if isinstance(source, QIcon):
        return source
    if isinstance(source, Icon):
        return _SEMANTIC.get(source, FALLBACK)
    if isinstance(source, PurePath):
        source = str(source)
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
                return load_icon(source, base_dir, trim_transparent=trim_transparent)
            except (OSError, ValueError):
                return FALLBACK
        return FALLBACK
    if callable(getattr(source, "icon", None)):
        try:
            result = source.icon()
            if isinstance(result, QIcon) and not result.isNull():
                return result
        except Exception:
            pass
    return FALLBACK
