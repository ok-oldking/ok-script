from qfluentwidgets import FluentIcon

from ok.core.icons import Icon


_ICONS = {
    Icon.APPLICATION: FluentIcon.APPLICATION,
    Icon.GAME: FluentIcon.GAME,
    Icon.PEOPLE: FluentIcon.PEOPLE,
    Icon.RINGER: FluentIcon.RINGER,
    Icon.SYNC: FluentIcon.SYNC,
    Icon.UPDATE: FluentIcon.UPDATE,
}


def resolve_icon(icon, fallback=FluentIcon.INFO):
    try:
        return _ICONS.get(Icon(icon), icon)
    except (TypeError, ValueError):
        return icon or fallback
