import win32api
from PySide6.QtCore import Qt, QPoint, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication, QBrush
from PySide6.QtWidgets import QWidget

from ok import Logger
from ok import og

logger = Logger.get_logger(__name__)


class FrameWidget(QWidget):
    def __init__(self):
        super(FrameWidget, self).__init__()
        self._mouse_position = QPoint(0, 0)
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_mouse_position)
        self.timer.start(1000)
        self.mouse_font = QFont()
        self.mouse_font.setPointSize(10)
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
        if og.device_manager.width == 0:
            return 1
        return self.width() / og.device_manager.width

    def paintEvent(self, event):
        if not self.isVisible():
            return
        painter = QPainter(self)
        self.paint_border(painter)
        self.paint_boxes(painter)
        self.paint_mouse_position(painter)
        if og.config.get('debug_cover_uid'):
            self.paint_uid_cover(painter)

    def paint_boxes(self, painter):
        pen = QPen()
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        frame_ratio = self.frame_ratio()
        for key, value in og.ok.screenshot.ui_dict.items():
            boxes = value[0]
            pen.setColor(value[2])
            painter.setPen(pen)
            for box in boxes:
                width = box.width * frame_ratio
                height = box.height * frame_ratio
                x = box.x * frame_ratio
                y = box.y * frame_ratio
                painter.drawRect(x, y, width, height)
                text = f"{box.name or key}_{round(box.confidence * 100)}"
                text_x = x
                text_y = y + height + 12

                painter.save()
                painter.setPen(QColor("black"))
                # painter.drawText(text_x - 0.5, text_y, text)
                # painter.drawText(text_x + 0.5, text_y, text)
                # painter.drawText(text_x, text_y - 0.5, text)
                painter.drawText(text_x + 0.5, text_y + 0.5, text)

                painter.setPen(value[2])
                painter.drawText(text_x, text_y, text)
                painter.restore()

    def paint_uid_cover(self, painter):
        window_width = painter.window().width()
        window_height = painter.window().height()

        rect_width = window_width * 0.13
        rect_height = window_height * 0.025
        rect_x = window_width - rect_width
        rect_y = window_height - rect_height

        painter.setBrush(QBrush(Qt.black, Qt.SolidPattern))
        painter.setPen(Qt.NoPen)

        painter.drawRect(QRectF(rect_x, rect_y, rect_width, rect_height))

    def paint_border(self, painter):
        pen = QPen(QColor(255, 0, 0, 255))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def paint_mouse_position(self, painter):
        x_percent = self._mouse_position.x() / self.width()
        y_percent = self._mouse_position.y() / self.height()
        x, y = self._mouse_position.x() * 2, self._mouse_position.y() * 2
        text = f"({x}, {y}, {x_percent:.2f}, {y_percent:.2f})"
        painter.setFont(self.mouse_font)
        painter.setPen(QColor("black"))
        painter.drawText(16.5, 16.5, text)
        painter.setPen(QPen(QColor(255, 0, 0, 255), 1))
        painter.drawText(16, 16, text)
