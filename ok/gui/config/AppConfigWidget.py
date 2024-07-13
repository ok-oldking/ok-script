from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from qfluentwidgets import SwitchButton

from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class AppConfigWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.dark_theme_widget = LabelAndWidget(self.tr('Theme'))
        self.switch_button = SwitchButton()
        self.switch_button.setOnText(self.tr('Dark'))
        self.switch_button.setOffText(self.tr('Light'))

    def init_ui(self):
        self.scene_widget = QLabel()
        self.layout.addWidget(self.scene_widget)
        self.update_scene("None")

        self.fps_widget = QLabel()
        self.layout.addWidget(self.fps_widget)
        self.update_fps(0)

        self.frame_time_widget = QLabel()
        self.layout.addWidget(self.frame_time_widget)
        self.update_frame_time(0)

        self.layout.addStretch()

    def update_fps(self, fps):
        self.fps_widget.setText(f"FPS: {fps}")

    def update_frame_time(self, fps):
        self.frame_time_widget.setText(f"FrameTime: {fps}")

    def update_scene(self, scene):
        self.scene_widget.setText(f"Scene: {scene}")
