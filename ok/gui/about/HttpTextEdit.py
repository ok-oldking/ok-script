from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import TextEdit


class VersionCard(TextEdit):
    """ Sample card """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.anchor = None

    def mousePressEvent(self, e):
        self.anchor = self.anchorAt(e.pos())
        if self.anchor:
            QApplication.setOverrideCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if self.anchor:
            QDesktopServices.openUrl(QUrl(self.anchor))
            QApplication.setOverrideCursor(Qt.ArrowCursor)
        self.anchor = None
