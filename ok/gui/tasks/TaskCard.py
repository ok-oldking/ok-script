from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PushButton, ExpandSettingCard, InfoBar, InfoBarPosition, SwitchButton

import ok.gui
from ok.gui.Communicate import communicate
from ok.gui.common.OKIcon import OKIcon
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.task.BaseTask import BaseTask
from ok.task.OneTimeTask import OneTimeTask


class TaskCard(ExpandSettingCard):
    def __init__(self, task: BaseTask):
        super().__init__(FluentIcon.INFO, task.name, task.description)
        self.task = task
        if task.default_config:
            self.reset_config = PushButton(FluentIcon.CANCEL, self.tr("Reset Config"), self)
            self.addWidget(self.reset_config)
            self.reset_config.clicked.connect(self.reset_clicked)

        if isinstance(task, OneTimeTask):
            self.task_buttons = TaskButtons(self.task)
            self.addWidget(self.task_buttons)
        else:
            self.enable_button = SwitchButton()
            self.enable_button.setOnText(self.tr('Enabled'))
            self.enable_button.setOffText(self.tr('Disabled'))
            self.enable_button.checkedChanged.connect(self.check_changed)
            self.addWidget(self.enable_button)

        self.update_buttons(self.task)

        communicate.task.connect(self.update_buttons)

        self.config_widgets = []
        self.__initWidget()

    def __initWidget(self):
        # initialize layout
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        if not self.task.default_config:
            self.card.expandButton.hide()
        for key, value in self.task.config.items():
            if not key.startswith('_'):
                self.__addConfig(key, value)

    def update_buttons(self, task):
        if task == self.task:
            if isinstance(task, OneTimeTask):
                self.task_buttons.update_buttons()
            else:
                self.enable_button.setChecked(task.enabled)

    def check_changed(self, checked):
        if checked:
            self.task.enable()
        else:
            self.task.disable()

    def __addConfig(self, key: str, value):
        widget = config_widget(self.task, key, value)
        self.config_widgets.append(widget)
        self.viewLayout.addWidget(widget)
        self._adjustViewSize()

    def __updateConfig(self):
        for widget in self.config_widgets:
            widget.update_value()

    def reset_clicked(self):
        self.task.config.reset_to_default()
        self.__updateConfig()


class TaskButtons(QWidget):
    def __init__(self, task):
        super().__init__()
        self.task = task
        self.init_ui()

    def init_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(18)  # Set the spacing between widgets

        self.start_button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.start_button.clicked.connect(self.start_clicked)

        self.stop_button = PushButton(OKIcon.STOP, self.tr("Stop"), self)
        self.stop_button.clicked.connect(self.stop_clicked)

        self.pause_button = PushButton(FluentIcon.PAUSE, self.tr("Pause"), self)
        self.pause_button.clicked.connect(self.pause_clicked)
        # Add buttons to the layout
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)
        self.layout.addWidget(self.pause_button)

    def toggle_button_visibility(self, button, visible):
        button.setVisible(visible)
        self.adjust_spacing()

    def adjust_spacing(self):
        # Calculate the number of visible widgets
        visible_widgets = sum(
            1 for button in (self.start_button, self.stop_button, self.pause_button) if button.isVisible())
        # Adjust spacing based on the number of visible widgets
        new_spacing = 18 if visible_widgets > 1 else 0
        self.layout.setSpacing(new_spacing)

    def update_buttons(self):
        if self.task.enabled:
            if self.task.paused:
                self.start_button.setText(self.tr("Resume"))
                self.start_button.show()
                self.pause_button.hide()
                self.stop_button.show()
            elif self.task.running:
                self.start_button.hide()
                self.stop_button.show()
                self.pause_button.show()
            else:
                self.start_button.hide()
                self.stop_button.show()
                self.pause_button.hide()
        else:
            self.start_button.setText(self.tr("Start"))
            self.start_button.show()
            self.pause_button.hide()
            self.stop_button.hide()
        self.adjust_spacing()

    def start_clicked(self):
        if not ok.gui.executor.connected():
            InfoBar.error(
                title=self.tr('Error'),
                content=self.tr(
                    "Game window is not connected, please select the game window and capture method."),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,  # won't disappear automatically
                parent=self.window()
            )
            communicate.tab.emit("start")
            return
        else:
            self.task.enable()
            self.task.unpause()
            ok.gui.executor.start()

    def stop_clicked(self):
        self.task.disable()
        self.task.unpause()

    def pause_clicked(self):
        self.task.pause()
