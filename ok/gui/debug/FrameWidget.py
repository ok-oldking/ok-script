import os

import win32api
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget

import ok.gui
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class FrameWidget(QWidget):
    def __init__(self):
        super(FrameWidget, self).__init__()
        self._mouse_position = QPoint(0, 0)
        self.setMouseTracking(True)
        # Start a timer to update mouse position using Windows API
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_mouse_position)
        self.timer.start(1000)  # Update every 50 milliseconds
        self.mouse_font = QFont()
        self.mouse_font.setPointSize(10)  # Adjust the size as needed
        screen = QGuiApplication.primaryScreen()
        self.scaling = screen.devicePixelRatio()

    def update_mouse_position(self):
        try:
            if not self.isVisible():
                return
            x, y = win32api.GetCursorPos()
            relative = self.mapFromGlobal(QPoint(x / self.scaling, y / self.scaling))
            if self._mouse_position != relative and relative.x() > 0 and relative.y() > 0:
                self._mouse_position = relative
            self.update()
        except Exception as e:
            logger.warning(f'GetCursorPos exception {e}')

    def frame_ratio(self):
        if ok.gui.device_manager.width == 0:
            return 1
        return self.width() / ok.gui.device_manager.width

    def paintEvent(self, event):
        if not self.isVisible():
            return
        painter = QPainter(self)
        self.paint_border(painter)
        self.paint_boxes(painter)
        self.paint_mouse_position(painter)

    def paint_boxes(self, painter):
        pen = QPen()  # Set the brush to red color
        pen.setWidth(2)  # Set the width of the pen (border thickness)
        painter.setPen(pen)  # Apply the pen to the painter
        painter.setBrush(Qt.NoBrush)  # Ensure no fill

        frame_ratio = self.frame_ratio()
        for key, value in ok.gui.ok.screenshot.ui_dict.items():
            boxes = value[0]
            pen.setColor(value[2])
            painter.setPen(pen)
            for box in boxes:
                width = box.width * frame_ratio
                height = box.height * frame_ratio
                x = box.x * frame_ratio
                y = box.y * frame_ratio
                painter.drawRect(x, y, width, height)
                painter.drawText(x, y + height + 12, f"{box.name or key}_{round(box.confidence * 100)}")

    def paint_border(self, painter):
        pen = QPen(QColor(255, 0, 0, 255))  # Solid red color for the border
        pen.setWidth(1)  # Set the border width
        painter.setPen(pen)
        # Draw the border around the widget
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def paint_mouse_position(self, painter):
        x_percent = self._mouse_position.x() / self.width()
        y_percent = self._mouse_position.y() / self.height()
        x, y = self._mouse_position.x() * 2, self._mouse_position.y() * 2
        text = f"({x}, {y}, {x_percent:.2f}, {y_percent:.2f})"
        painter.setFont(self.mouse_font)

        painter.setPen(QPen(QColor(255, 0, 0, 255), 1))
        painter.drawText(20, 20, text)
        #
        # # Draw the black text
        # painter.setPen(QPen(QColor(0, 0, 0), 2))
        # painter.drawText(10, 10, text)
