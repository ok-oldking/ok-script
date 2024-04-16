from PySide6.QtWidgets import QWidget, QHBoxLayout, QSizePolicy

from ok.gui.debug.InfoWidget import InfoWidget
from ok.gui.debug.LoggerWidget import LoggerWidget


class DebugTab(QWidget):
    def __init__(self):
        super().__init__()

        self.mainLayout = QHBoxLayout()
        self.setLayout(self.mainLayout)

        self.info_widget = InfoWidget()
        self.info_widget.setFixedWidth(200)
        # self.frame_widget = FrameWidget(True)
        self.mainLayout.addWidget(self.info_widget)
        # self.topSplitter.addWidget(self.frame_widget)

        # Bottom row setup
        self.logger = LoggerWidget()

        self.mainLayout.addWidget(self.logger)

        p1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        p1.setHorizontalStretch(1)  # 33% of the layout
        self.info_widget.setSizePolicy(p1)

        p2 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        p2.setHorizontalStretch(2)  # 67% of the layout
        self.logger.setSizePolicy(p2)
