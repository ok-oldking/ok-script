from PySide6.QtCore import Qt
from qfluentwidgets import FluentIcon, SettingCard, PushButton

import ok


class StartCard(SettingCard):
    def __init__(self):
        super().__init__(FluentIcon.PLAY, f'{self.tr("Start")} {ok.gui.app.title}', ok.gui.app.title)
        self.button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.button.clicked.connect(self.clicked)

    def clicked(self):
        if ok.gui.executor.paused:
            ok.gui.executor.start()
            self.button.setText(self.tr("Pause"))
            self.button.setIcon(FluentIcon.PAUSE)
        else:
            ok.gui.executor.pause()
            self.button.setText(self.tr("Start"))
            self.button.setIcon(FluentIcon.PLAY)
