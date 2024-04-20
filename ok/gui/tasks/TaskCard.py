from PySide6.QtCore import Qt
from qfluentwidgets import FluentIcon, PushButton, ExpandSettingCard

import ok
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.task.BaseTask import BaseTask


class TaskCard(ExpandSettingCard):
    def __init__(self, task: BaseTask):
        super().__init__(FluentIcon.INFO, task.name, task.description)
        self.button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.addWidget(self.button)
        self.button.clicked.connect(self.clicked)
        self.task = task
        self.__initWidget()
        # StyleSheet.CARD.apply(self)

    def __initWidget(self):
        # initialize layout
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        for key, value in self.task.config.items():
            self.__addConfig(key, value)

    def __addConfig(self, key: str, value):
        self.viewLayout.addWidget(config_widget(self.task.config, key, value))
        self._adjustViewSize()

    def clicked(self):
        if ok.gui.executor.paused:
            ok.gui.executor.start()
            self.button.setText(self.tr("Pause"))
            self.button.setIcon(FluentIcon.PAUSE)
        else:
            ok.gui.executor.pause()
            self.button.setText(self.tr("Start"))
            self.button.setIcon(FluentIcon.PLAY)
