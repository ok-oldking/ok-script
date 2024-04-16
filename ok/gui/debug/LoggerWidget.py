import logging

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit, QTextEdit)

from ok.gui.Communicate import communicate

level_map = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING, 'ERROR': logging.ERROR,
             'CRITICAL': logging.CRITICAL}


def get_colored_message(level, message):
    if level >= logging.ERROR:
        color = "red"
    elif level == logging.WARNING:
        color = "darkorange"  # Dark yellow can be represented as 'darkorange' for better visibility
    else:
        return message
    return f'<span style="color: {color};">{message}</span>'


class LoggerWidget(QWidget):
    # Define log levels

    def __init__(self, parent=None):
        super(LoggerWidget, self).__init__(parent)
        self.max_length = 1000
        self.init_ui()
        self.logs = []  # Store logs as tuples (level, message)
        communicate.log.connect(self.add_log)

    def init_ui(self):
        self.layout = QVBoxLayout(self)

        # Filter controls
        controls_layout = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItems(level_map.keys())
        self.level_filter.currentTextChanged.connect(self.update_display)

        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText("Filter logs by text...")
        self.text_filter.textChanged.connect(self.update_display)

        controls_layout.addWidget(self.level_filter)
        controls_layout.addWidget(self.text_filter)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("line-height:120%;")

        # Add widgets to layout
        self.layout.addLayout(controls_layout)
        self.layout.addWidget(self.log_display)

    def add_log(self, level, message):
        self.logs.append((level, message))
        if len(self.logs) > self.max_length:
            # Calculate how many elements to remove
            excess_length = len(self.logs) - self.max_length
            # Remove the oldest elements
            del self.logs[:excess_length]
        self.update_display()

    def update_display(self):
        filtered_logs = self.filter_logs()
        self.log_display.clear()
        for level, message in filtered_logs:
            colored_message = get_colored_message(level, message)
            self.log_display.append(colored_message)

    def filter_logs(self):
        level = level_map[self.level_filter.currentText()]
        text = self.text_filter.text().lower()
        return [(lvl, msg) for lvl, msg in self.logs if (lvl >= level) and text in msg.lower()]
