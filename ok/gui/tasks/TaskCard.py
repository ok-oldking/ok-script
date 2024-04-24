from PySide6.QtCore import Qt
from qfluentwidgets import FluentIcon, PushButton, ExpandSettingCard, InfoBar, InfoBarPosition

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
        self.button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.update_start_text(self.task)
        self.addWidget(self.button)
        communicate.task.connect(self.update_start_text)
        self.button.clicked.connect(self.start_clicked)
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
            self.__addConfig(key, value)

    def __addConfig(self, key: str, value):
        widget = config_widget(self.task.config, key, value)
        self.config_widgets.append(widget)
        self.viewLayout.addWidget(widget)
        self._adjustViewSize()

    def __updateConfig(self):
        for widget in self.config_widgets:
            widget.update_value()

    def reset_clicked(self):
        self.task.config.reset_to_default()
        self.__updateConfig()

    def update_start_text(self, task):
        if task != self.task:
            return
        if self.task.enabled:
            if isinstance(self.task, OneTimeTask):
                if self.task.paused:
                    self.button.setText(self.tr("Resume"))
                else:
                    self.button.setText(self.tr("Stop"))
            else:
                self.button.setText(self.tr("Disable"))
            self.button.setIcon(OKIcon.STOP)
        else:
            if isinstance(self.task, OneTimeTask):
                self.button.setText(self.tr("Start"))
            else:
                self.button.setText(self.tr("Enable"))
            self.button.setIcon(FluentIcon.PLAY)

    def start_clicked(self):
        if self.task.enabled:
            if self.task.paused:
                self.task.unpause()
            else:
                self.task.disable()
        else:
            if ok.gui.executor.paused:
                if not ok.gui.executor.connected():
                    InfoBar.error(
                        title=self.tr('Error'),
                        content=self.tr(
                            "Game window is not connected, please select the game window and capture method."),
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=5000,  # won't disappear automatically
                        parent=self
                    )
                    communicate.tab.emit("start")
                    return
                else:
                    ok.gui.executor.start()
            self.task.enable()
        self.update_start_text(self.task)
