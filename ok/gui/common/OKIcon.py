from enum import Enum

from qfluentwidgets import FluentIconBase, Theme, qconfig


class OKIcon(FluentIconBase, Enum):
    """ Fluent icon """

    STOP = "stop"

    def path(self, theme=Theme.AUTO):
        theme = qconfig.theme if theme == Theme.AUTO else theme
        return f':/qss/{theme.value.lower()}/{self.value}.svg'
