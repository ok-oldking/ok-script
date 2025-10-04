# coding:utf-8
import sys

from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QApplication
from qfluentwidgets import qconfig, isDarkTheme
from qfluentwidgets.common.animation import BackgroundAnimationWidget
from qfluentwidgets.components.widgets.frameless_window import FramelessWindow

from ok import og

from ok.gui.widget.BaseLoading import BaseLoading


class BaseWindow(BackgroundAnimationWidget, FramelessWindow, BaseLoading):
    """ Fluent window base class """

    def __init__(self, parent=None):
        self._isMicaEnabled = False
        self._lightBackgroundColor = QColor(240, 244, 249)
        self._darkBackgroundColor = QColor(32, 32, 32)

        super().__init__(parent=parent)
        self.setWindowIcon(og.app.icon)

        qconfig.themeChangedFinished.connect(self._onThemeChangedFinished)

    def _updateStackedBackground(self):
        isTransparent = self.stackedWidget.currentWidget().property("isStackedTransparent")
        if bool(self.stackedWidget.property("isTransparent")) == isTransparent:
            return

        self.stackedWidget.setProperty("isTransparent", isTransparent)
        self.stackedWidget.setStyle(QApplication.style())

    def setCustomBackgroundColor(self, light, dark):
        """ set custom background color

        Parameters
        ----------
        light, dark: QColor | Qt.GlobalColor | str
            background color in light/dark theme mode
        """
        self._lightBackgroundColor = QColor(light)
        self._darkBackgroundColor = QColor(dark)
        self._updateBackgroundColor()

    def _normalBackgroundColor(self):
        return self._darkBackgroundColor if isDarkTheme() else self._lightBackgroundColor

    def _onThemeChangedFinished(self):
        pass

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.backgroundColor)
        painter.drawRect(self.rect())

    def systemTitleBarRect(self, size: QSize) -> QRect:
        """ Returns the system title bar rect, only works for macOS

        Parameters
        ----------
        size: QSize
            original system title bar rect
        """
        return QRect(size.width() - 75, 0 if self.isFullScreen() else 9, 75, size.height())


