from PySide6.QtCore import QRect, QPoint, Qt
from PySide6.QtWidgets import QTabBar, QStylePainter, QStyleOptionTab, QStyle, QWidget
from PySide6.QtWidgets import QTabWidget, QVBoxLayout
from qfluentwidgets import BodyLabel


class TabBar(QTabBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def tabSizeHint(self, index):
        s = QTabBar.tabSizeHint(self, index)
        if s.width() < s.height():
            s.transpose()
        s.scale(s.width() * 2, s.height() * 2, Qt.KeepAspectRatio)
        return s

    # Make text visible adequately
    def paintEvent(self, event):
        painter = QStylePainter(self)
        style_option = QStyleOptionTab()

        for i in range(self.count()):
            self.initStyleOption(style_option, i)
            painter.drawControl(QStyle.CE_TabBarTabShape, style_option)
            painter.save()

            s = style_option.rect.size()
            s.scale(s.width() * 2, s.height() * 2, Qt.KeepAspectRatio)
            rect = QRect(QPoint(), s)
            rect.moveCenter(style_option.rect.center())
            style_option.rect = rect

            center = self.tabRect(i).center()
            painter.translate(center)
            painter.rotate(90)
            painter.translate(center * -1)
            painter.drawControl(QStyle.CE_TabBarTabLabel, style_option)
            painter.restore()


class VerticalTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setTabBar(TabBar(self))
        self.setTabPosition(QTabWidget.West)

    # def setTabSize(self, width, height):


class TabContent(QWidget):
    def __init__(self, text):
        super().__init__()
        layout = QVBoxLayout()
        label = BodyLabel(text)
        layout.addWidget(label)
        self.setLayout(layout)
