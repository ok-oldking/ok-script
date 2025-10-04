from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, qconfig


class OKIcon(FluentIconBase, Enum):
    """ Fluent icon """

    STOP = "stop"
    DISCORD = "discord"
    HEART = "heart"

    def path(self, theme=Theme.DARK):
        theme = qconfig.theme if theme == Theme.AUTO else theme
        return f':/qss/{theme.value.lower()}/{self.value}.svg'
