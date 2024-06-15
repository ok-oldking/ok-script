from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex, QPoint, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QListView, QLineEdit, QHBoxLayout, QComboBox, QAbstractItemView, QWidget, \
    QPushButton, QLabel, QStyledItemDelegate

from ok.config.Config import Config
from ok.gui.Communicate import communicate

LOG_BG_TRANS = 80
color_codes = {
    "INFO": QColor(85, 85, 255, LOG_BG_TRANS),  # Light blue
    "DEBUG": QColor(85, 255, 85, LOG_BG_TRANS),  # Light green
    "WARNING": QColor(255, 255, 85, LOG_BG_TRANS),  # Yellow
    "ERROR": QColor(255, 85, 85, LOG_BG_TRANS),  # Red
}


class ColoredText:
    """
    Class to store colored text with its format code.
    """

    def __init__(self, text, format, level):
        self.text = text
        self.format = format
        self.level = level


class ColorDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(ColorDelegate, self).__init__(parent)

    def paint(self, painter, option, index):
        # Get the color from the model
        color = index.data(Qt.ForegroundRole)
        if color:
            painter.fillRect(option.rect, color)
        super(ColorDelegate, self).paint(painter, option, index)


class LogModel(QAbstractListModel):
    def __init__(self, log_list):
        super(LogModel, self).__init__()
        self.log_list = log_list
        self.logs = []
        self.filtered_logs = self.logs[:]
        self.current_level = "ALL"
        self.current_keyword = ""

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return self.filtered_logs[index.row()].text
        elif role == Qt.ForegroundRole:
            return self.filtered_logs[index.row()].format

    def rowCount(self, index):
        return len(self.filtered_logs)

    def add_log(self, level, message):
        # Create colored text based on level
        color_format = self.get_color_format(level)
        colored_text = ColoredText(message, color_format, level)
        self.logs.append(colored_text)
        if len(self.logs) >= 500:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self.logs.pop(0)
            self.endRemoveRows()

        self.beginInsertRows(QModelIndex(), self.rowCount(QModelIndex()), self.rowCount(QModelIndex()))
        self.do_filter_logs()
        self.endInsertRows()
        self.layoutChanged.emit()
        self.log_list.scrollToBottom()

    def do_filter_logs(self):

        keyword = self.current_keyword.lower()

        # Get the numeric severity for the current level
        current_level_severity = level_severity.get(self.current_level, 0)

        # Filter logs based on severity level and keyword
        if self.current_level == "ALL":
            self.filtered_logs = [log for log in self.logs if keyword in log.text.lower()]
        else:
            self.filtered_logs = [
                log for log in self.logs
                if level_severity.get(log.level, 0) >= current_level_severity
                   and keyword in log.text.lower()
            ]

    def filter_logs(self, level, keyword):
        self.current_level = level
        self.current_keyword = keyword
        self.do_filter_logs()
        self.layoutChanged.emit()
        self.log_list.scrollToBottom()

    def get_color_format(self, level):
        # Define color codes for different levels

        return color_codes.get(level, QColor())  # Return default color for unknown levels


log_levels = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR"}
level_severity = {v: k for k, v in log_levels.items()}


class LogWindow(QWidget):
    def __init__(self, app_config):
        super().__init__()
        self.setWindowTitle('Log Viewer')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.config = Config({'width': 800, 'height': 300, 'x': 0, 'y': 0,
                              'level': 'ALL'},
                             app_config.get('config_folder'), 'log_window')
        self.setGeometry(self.config['x'], self.config['y'], self.config['width'], self.config['height'])

        self.refresh_signal = Signal()

        self.old_pos = None

        # Layouts
        self.layout = QVBoxLayout()
        self.filter_layout = QHBoxLayout()

        # Widgets
        self.log_list = QListView()
        self.log_list.setStyleSheet("background:rgba(0,0,0,60);")
        self.log_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.log_list.setItemDelegate(ColorDelegate())

        self.level_filter = QComboBox()
        self.level_filter.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_filter.setCurrentText(self.config.get('level'))
        self.level_filter.currentIndexChanged.connect(self.filter_logs)

        self.keyword_filter = QLineEdit()
        self.keyword_filter.setPlaceholderText("Filter by keyword")
        self.keyword_filter.textChanged.connect(self.filter_logs)

        self.drag_button = QLabel(self.tr("Drag"))
        self.drag_button.setStyleSheet('background:rgba(0,0,0,255)')

        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.clicked.connect(self.close)

        # Adding widgets to layouts
        self.filter_layout.addWidget(self.level_filter)
        self.filter_layout.addWidget(self.keyword_filter, stretch=1)
        self.filter_layout.addWidget(self.drag_button)
        self.filter_layout.addWidget(self.close_button)

        self.layout.addLayout(self.filter_layout)
        self.layout.addWidget(self.log_list)

        self.setLayout(self.layout)

        self.log_model = LogModel(self.log_list)
        self.log_list.setModel(self.log_model)
        communicate.log.connect(self.add_log)

        self.logs = []
        self.filter_logs()

    def add_log(self, level_no, message):
        self.logs.append(message)
        self.log_model.add_log(log_levels.get(level_no, 'DEBUG'), message)

    def filter_logs(self):
        level = self.level_filter.currentText()
        self.config['level'] = level
        keyword = self.keyword_filter.text()
        self.log_model.filter_logs(level, keyword)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.config['x'] = self.x()
            self.config['y'] = self.y()
            self.old_pos = None
