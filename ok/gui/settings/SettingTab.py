# coding:utf-8
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import InfoBar
from qfluentwidgets import (SettingCardGroup, OptionsSettingCard, ComboBoxSettingCard, setTheme)

from ok.gui.common.config import cfg
from ok.gui.widget.Tab import Tab


class SettingTab(Tab):
    """ Setting interface """

    def __init__(self):
        super().__init__()
        # self.scrollWidget = QWidget()
        # self.scrollWidget.setObjectName('scrollWidget')
        # self.expandLayout = ExpandLayout(self.scrollWidget)
        # self.expandLayout.setObjectName('SettingInterface')

        # personalization
        self.personalGroup = SettingCardGroup(
            self.tr('Personalization'))
        self.vBoxLayout.addWidget(self.personalGroup)

        self.themeCard = OptionsSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            self.tr('Application theme'),
            self.tr("Change the appearance of your application"),
            texts=[
                self.tr('Light'), self.tr('Dark'),
                self.tr('Use system setting')
            ],
            parent=self.personalGroup
        )

        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            FIF.LANGUAGE,
            self.tr('Language'),
            self.tr('Set your preferred language'),
            texts=['简体中文', 'English', self.tr('Use system setting')],
            parent=self.personalGroup
        )

        self.__initWidget()

        # StyleSheet.SETTING_INTERFACE.apply(self)

    def __initWidget(self):
        # self.resize(1000, 800)
        # self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # # self.setViewportMargins(0, 80, 0, 20)
        # self.vBoxLayout.addWidget(self.scrollWidget)
        # # self.setWidget(self.scrollWidget)
        # self.setWidgetResizable(True)
        # self.setObjectName('settingInterface')

        # initialize style sheet
        # self.scrollWidget.setObjectName('scrollWidget')

        # initialize layout
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initLayout(self):
        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.languageCard)
        # add setting card group to layout
        # self.expandLayout.setSpacing(28)
        # self.expandLayout.setContentsMargins(36, 10, 36, 0)
        # self.expandLayout.addWidget(self.personalGroup)

    def __showRestartTooltip(self):
        """ show restart tooltip """
        InfoBar.success(
            self.tr('Updated successfully'),
            self.tr('Configuration takes effect after restart'),
            duration=1500,
            parent=self
        )

    def __connectSignalToSlot(self):
        """ connect signal to slot """
        cfg.appRestartSig.connect(self.__showRestartTooltip)

        # personalization
        self.themeCard.optionChanged.connect(lambda ci: setTheme(cfg.get(ci)))
