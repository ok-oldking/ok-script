from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpacerItem, QSizePolicy, QVBoxLayout
from qfluentwidgets import PushButton, ComboBox, FluentIcon, PrimaryPushButton, BodyLabel, StateToolTip

from ok.gui.Communicate import communicate
from ok.gui.launcher.DownloadBar import DownloadBar



class UpdateBar(QWidget):

    def __init__(self, config, updater):
        super().__init__()
        self.updater = updater
        self.state_tooltip = None
        self.layout = QVBoxLayout()

        # self.log_scroll_area = SmoothScrollArea()
        # self.scroll_widget = QWidget(self.log_scroll_area)
        self.version_log_label = BodyLabel(self.tr("Checking for Updates..."))
        self.version_log_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.version_log_label.setWordWrap(True)

        self.download_bar = DownloadBar()
        self.layout.addWidget(self.download_bar)

        self.hbox_layout = QHBoxLayout()
        self.layout.addLayout(self.hbox_layout)
        self.hbox_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.hbox_layout.setSpacing(20)

        # self.version_log_hbox_layout.addWidget(self.log_scroll_area)

        self.update_hbox_layout = QHBoxLayout()
        self.layout.addLayout(self.update_hbox_layout)
        self.update_hbox_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.update_hbox_layout.setSpacing(20)

        communicate.update_logs.connect(self.update_logs)

        communicate.versions.connect(self.update_versions)
        communicate.update_running.connect(self.update_running)
        self.update_source_box = QHBoxLayout()

        self.update_source_box.setSpacing(6)

        self.hbox_layout.addLayout(self.update_source_box, stretch=0)
        self.source_label = BodyLabel(self.tr("Update Source:"))
        self.update_source_box.addWidget(self.source_label, stretch=0)

        self.update_sources = ComboBox()
        self.update_source_box.addWidget(self.update_sources, stretch=0)
        self.update_source_box.addSpacing(10)
        sources = config.get('git_update').get('sources')
        source_names = [QCoreApplication.translate('app', source['name']) for source in sources]
        self.update_sources.addItems(source_names)
        self.update_sources.setCurrentIndex(self.updater.launcher_config.get('source_index'))

        self.update_sources.currentTextChanged.connect(self.update_source)

        self.check_update_button = PushButton(self.tr("Check for Update"), icon=FluentIcon.SYNC)
        self.hbox_layout.addWidget(self.check_update_button)
        self.check_update_button.clicked.connect(self.updater.list_all_versions)

        self.version_label = BodyLabel()
        self.version_label_target = BodyLabel()
        self.update_hbox_layout.addWidget(self.version_label)

        self.current_version = ComboBox()
        self.update_hbox_layout.addWidget(self.current_version)
        self.update_hbox_layout.addWidget(self.version_label_target)
        self.current_version.addItems([self.updater.app_config.get(
            'version')])
        self.version_label.setText(self.tr('Current Version:'))
        self.version_label_target.setText(self.tr('TargetVersion:'))

        self.version_list = ComboBox()
        self.update_hbox_layout.addWidget(self.version_list)
        self.version_list.currentTextChanged.connect(self.version_selection_changed)

        self.update_button = PrimaryPushButton(self.tr("Update"), icon=FluentIcon.UP)
        self.update_button.clicked.connect(self.update_clicked)
        self.update_hbox_layout.addWidget(self.update_button)

        self.set_op_btn_enabled(False)

        # self.version_log_hbox_layout = QHBoxLayout()
        self.layout.addWidget(self.version_log_label)

        self.setLayout(self.layout)
        self.version_log_label.setText(self.updater.update_logs or self.tr("Checking for Updates..."))
        self.update_logs()

        self.update_versions()

    def update_source(self):
        if self.update_sources.currentText():
            self.updater.update_source(self.update_sources.currentIndex())

    def version_selection_changed(self, text):
        self.version_log_label.setText("")
        self.update_update_btns(text)
        self.updater.version_selection_changed(text)

    def update_update_btns(self, text):
        if text:
            from ok.update.GitUpdater import is_newer_or_eq_version
            cmp = is_newer_or_eq_version(text, self.updater.launcher_config.get('app_version'))
            if cmp >= 0:
                self.update_button.setText(self.tr("Update"))
                self.update_button.setIcon(icon=FluentIcon.UP)
            else:
                self.update_button.setText(self.tr("Downgrade"))
                self.update_button.setIcon(icon=FluentIcon.DOWN)
            self.update_button.setDisabled(cmp == 0)

    def update_logs(self):
        if self.updater.update_logs:
            self.version_log_label.setText(self.updater.update_logs)
        else:
            self.version_log_label.setText(self.tr("This is the newest version"))
        self.version_log_label.setVisible(self.updater.update_logs is not None and self.updater.update_logs != "")

    def update_clicked(self):
        self.updater.update_to_version(self.version_list.currentText())
        self.update_button.setDisabled(True)
        self.check_update_button.setDisabled(True)

    def update_running(self, running, updating=False):
        self.update_button.setDisabled(running)
        self.check_update_button.setDisabled(running)
        self.update_sources.setDisabled(running)
        self.version_list.setDisabled(running)
        self.set_op_btn_enabled(not running)

        if self.state_tooltip is None:
            self.state_tooltip = StateToolTip(
                self.tr('Checking for Update...'), "", self.window())
            self.state_tooltip.move(self.state_tooltip.getSuitablePos())
            self.state_tooltip.contentLabel.hide()
        if running:
            self.state_tooltip.setTitle(
                self.tr('Updating' if updating else 'Checking for Update...'))
            self.state_tooltip.setState(False)
            self.state_tooltip.show()
        else:
            self.state_tooltip.hide()
            self.state_tooltip.setState(True)
            self.state_tooltip = None

    def update_versions(self):
        if not self.updater.versions:  # fetch version error
            self.version_list.clear()
            self.version_label.setText(self.tr("This is the newest version"))
        else:
            current_items = [self.version_list.itemText(i) for i in range(self.version_list.count())]
            if current_items != self.updater.versions:
                self.version_list.clear()
                self.version_list.addItems(self.updater.versions)
                self.set_op_btn_enabled(len(self.updater.versions) != 0)

    def set_op_btn_enabled(self, enabled):
        for i in reversed(range(self.update_hbox_layout.count())):
            widget = self.update_hbox_layout.itemAt(i).widget()
            if widget is not None:
                widget.setEnabled(enabled)
