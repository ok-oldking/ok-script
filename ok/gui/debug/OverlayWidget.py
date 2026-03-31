import win32api
from PySide6.QtCore import Qt, QPoint, QTimer, QRectF, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication, QBrush
from PySide6.QtWidgets import QWidget

from ok import Logger
from ok import og
from ok.gui.Communicate import communicate

logger = Logger.get_logger(__name__)


class OverlayWidget(QWidget):
    log_levels = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR"}
    color_codes = {
        "INFO": QColor(135, 206, 250),
        "DEBUG": QColor(85, 255, 85),
        "WARNING": QColor(255, 255, 85),
        "ERROR": QColor(255, 85, 85),
    }
    black_list_logs = ['A new release of pip', 'does not currently take into account all the packages']

    def __init__(self):
        super(OverlayWidget, self).__init__()
        self._mouse_position = QPoint(0, 0)
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_mouse_position)
        self.timer.start(1000)
        self.mouse_font = QFont()
        self.mouse_font.setPointSize(10)
        self.log_font = QFont()
        self.log_font.setPointSize(10)
        screen = QGuiApplication.primaryScreen()
        self.scaling = screen.devicePixelRatio()
        self.logs = []
        communicate.log.connect(self.add_log)

    def add_log(self, level_no, message):
        for log in self.black_list_logs:
            if log in message:
                return
        
        parts = message.split(':', 3)
        if len(parts) > 3:
            message = parts[3]

        level = self.log_levels.get(level_no, 'DEBUG')
        self.logs.append((level, message))
        if len(self.logs) > 50:
            self.logs.pop(0)
        self.update()

    def paint_logs(self, painter):
        if not og.app.ok_config.get('show_overlay_logs', True):
            return
        if not self.logs:
            return

        painter.setFont(self.log_font)
        fm = painter.fontMetrics()

        width = self.width() / 3.0
        height = self.height() / 2.0
        x = 0
        y = self.height() - height

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRect(x, y, width, height)

        painter.save()
        painter.setClipRect(x, y, width, height)

        padding_left = 2
        padding_bottom = 2
        
        flags = Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop
        
        available_width = width - (padding_left * 2)

        # Start text_y slightly higher to account for potential Qt alignment/descent clipping
        text_y = self.height() - padding_bottom - fm.descent()

        for level, msg in reversed(self.logs):
            text = msg
            rect = fm.boundingRect(QRect(0, 0, int(available_width), 10000), flags, text)
            
            # we subtract the exact bounding rect height to stack them perfectly
            text_y -= rect.height()
            
            color = self.color_codes.get(level, QColor(255, 255, 255))
            painter.setPen(color)
            
            # draw with an allowed massive height so that Qt's internal QRect clipping doesn't chop descenders
            painter.drawText(QRectF(x + padding_left, text_y, available_width, 10000), flags, text)
            
            if text_y <= y:
                break
                
        painter.restore()

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
        self.paint_logs(painter)
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
        
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()
        padding = 5
        
        bg_x = 16 - padding
        bg_y = 16 - fm.ascent() - padding
        bg_width = text_width + 2 * padding
        bg_height = text_height + 2 * padding
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRect(bg_x, bg_y, bg_width, bg_height)
        
        painter.setPen(QPen(QColor(255, 0, 0, 255), 1))
        painter.drawText(16, 16, text)
