# coding:utf-8
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import InfoBar
from qfluentwidgets import (SettingCardGroup, OptionsSettingCard, ComboBoxSettingCard, setTheme)

import ok.gui
from ok.gui.common.config import cfg
from ok.gui.settings.GlobalConfigCard import GlobalConfigCard
from ok.gui.widget.Tab import Tab


class SettingTab(Tab):
    """ Setting interface """

    def __init__(self):
        super().__init__()
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

        self.app_group = None
        self.__initWidget()

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
        self.add_global_config()
        self.__connectSignalToSlot()

    def __initLayout(self):
        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.languageCard)

    def add_global_config(self):
        global_configs = ok.gui.executor.global_config.get_all_visible_configs()
        if global_configs:
            self.app_group = SettingCardGroup(
                self.tr('App Settings'))
            for name, config, option in global_configs:
                card = GlobalConfigCard(config, option)
                self.app_group.addSettingCard(card)
            self.vBoxLayout.addWidget(self.app_group)

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
