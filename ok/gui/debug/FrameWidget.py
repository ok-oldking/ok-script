import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

import ok.gui
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class FrameWidget(QWidget):
    def __init__(self):
        super(FrameWidget, self).__init__()

        self._visible = True
        communicate.update_overlay.connect(self.update)

    def frame_ratio(self):
        if ok.gui.device_manager.width == 0:
            return 1
        return self.width() / ok.gui.device_manager.width

    def paintEvent(self, event):
        if not self._visible:
            return
        painter = QPainter(self)
        self.paint_border(painter)
        self.paint_boxes(painter)

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
