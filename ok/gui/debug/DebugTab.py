from PySide6.QtWidgets import QSizePolicy

from ok.gui.debug.LoggerWidget import LoggerWidget
from ok.gui.widget.Tab import Tab


class DebugTab(Tab):
    def __init__(self):
        super().__init__()

        # Bottom row setup
        self.logger = LoggerWidget()

        p2 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.logger.setSizePolicy(p2)

        self.addWidget(self.logger, 1)
