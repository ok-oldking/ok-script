from PySide6.QtCore import QTimer, QPropertyAnimation, Qt, QPoint, QRectF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QLabel, QGraphicsOpacityEffect
from qfluentwidgets import Theme, isDarkTheme, FluentIcon, StateToolTip

from ok.gui.common.style_sheet import StyleSheet


class StatusBar(QWidget):
    """ State tooltip """
    clicked = Signal()

    def __init__(self, title, running_icon=FluentIcon.SYNC, done_icon=FluentIcon.PAUSE, done=True, parent=None):
        """
        Parameters
        ----------
        title: str
            title of tooltip

        content: str
            content of tooltip

        parant:
            parent window
        """
        super().__init__(parent)
        self.title = title
        self.titleLabel = QLabel(self.title, self)
        self.rotateTimer = QTimer(self)

        self.opacityEffect = QGraphicsOpacityEffect(self)
        self.animation = QPropertyAnimation(self.opacityEffect, b"opacity")

        self.isDone = done
        self.rotateAngle = 0
        self.deltaAngle = 20
        self.running_icon: FluentIcon = running_icon
        self.done_icon = done_icon

        self.__initWidget()

    def __initWidget(self):
        """ initialize widgets """
        self.setAttribute(Qt.WA_StyledBackground)
        self.setGraphicsEffect(self.opacityEffect)
        self.opacityEffect.setOpacity(1)
        self.rotateTimer.setInterval(50)

        self.rotateTimer.timeout.connect(self.__rotateTimerFlowSlot)

        self.__setQss()
        self.__initLayout()

        self.rotateTimer.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Emit the 'clicked' signal
            self.clicked.emit()

    def __initLayout(self):
        """ initialize layout """
        self.__setSize()
        self.titleLabel.move(32, 8)

    def __setSize(self):
        self.setFixedSize(self.titleLabel.width() + 50, 34)

    def __setQss(self):
        """ set style sheet """
        self.titleLabel.setObjectName("titleLabel")

        StyleSheet.STATUS_BAR.apply(self)

        self.titleLabel.adjustSize()
        self.__setSize()

    def setTitle(self, title: str):
        """ set the title of tooltip """
        self.title = title
        self.titleLabel.setText(title)
        self.titleLabel.adjustSize()
        self.__setSize()

    def setState(self, isDone=False):
        """ set the state of tooltip """
        self.isDone = isDone
        self.update()
        # if isDone:
        #     QTimer.singleShot(1000, self.__fadeOut)

    def __fadeOut(self):
        """ fade out """
        self.rotateTimer.stop()
        self.animation.setDuration(200)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.start()

    def __rotateTimerFlowSlot(self):
        """ rotate timer time out slot """
        self.rotateAngle = (self.rotateAngle + self.deltaAngle) % 360
        self.update()

    def getSuitablePos(self):
        """ get suitable position in main window """
        for i in range(10):
            dy = i * (self.height() + 16)
            pos = QPoint(self.parent().width() - self.width() - 24, 50 + dy)
            widget = self.parent().childAt(pos + QPoint(2, 2))
            if isinstance(widget, StateToolTip):
                pos += QPoint(0, self.height() + 16)
            else:
                break

        return pos

    def paintEvent(self, e):
        """ paint state tooltip """
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        theme = Theme.DARK if not isDarkTheme() else Theme.LIGHT

        if not self.isDone:
            painter.translate(19, 18)
            painter.rotate(self.rotateAngle)
            self.running_icon.render(painter, QRectF(-8, -8, 16, 16), theme)
        else:
            self.done_icon.render(painter, QRectF(11, 10, 16, 16), theme)
