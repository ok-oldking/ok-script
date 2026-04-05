from PySide6.QtWidgets import QHBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import FluentIcon, PushButton, SwitchButton, MessageBox

from ok import Logger, BaseTask, og
from ok.gui.Communicate import communicate
from ok.gui.common.OKIcon import OKIcon
from ok.gui.tasks.ConfigCard import ConfigCard

logger = Logger.get_logger(__name__)


class TaskCard(ConfigCard):
    def __init__(self, task: BaseTask, onetime):
        super().__init__(task, task.name, task.config, task.description, task.default_config, task.config_description,
                         task.config_type, config_icon=task.icon or FluentIcon.INFO)
        self.task = task
        self.onetime = onetime

        # Create a container widget for buttons with consistent 6px spacing
        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.setSpacing(6)
        self.button_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.addWidget(self.button_container)

        self.instructions_button = PushButton(FluentIcon.INFO, self.tr("Instructions"), self)
        self.instructions_button.clicked.connect(self.show_instructions)

        if getattr(self.task, 'is_custom', False):
            self.edit_button = PushButton(FluentIcon.EDIT, self.tr("Edit"))
            self.edit_button.clicked.connect(self.edit_clicked)
        else:
            self.edit_button = None

        if onetime:
            self.pause_button = PushButton(FluentIcon.PAUSE, self.tr("Pause"), self)
            self.pause_button.clicked.connect(self.pause_clicked)

            self.stop_button = PushButton(OKIcon.STOP, self.tr("Stop"), self)
            self.stop_button.clicked.connect(self.stop_clicked)

            self.start_button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
            self.start_button.clicked.connect(self.start_clicked)
            self.enable_button = None
        else:
            self.pause_button = None
            self.stop_button = None
            self.start_button = None
            self.enable_button = SwitchButton()
            self.enable_button.setOnText(self.tr('Enabled'))
            self.enable_button.setOffText(self.tr('Disabled'))
            self.enable_button.checkedChanged.connect(self.check_changed)

        # Collect all buttons in display order
        self.all_buttons = [b for b in [
            self.instructions_button,
            self.edit_button,
            self.pause_button,
            self.stop_button,
            self.start_button,
            self.enable_button,
        ] if b is not None]

        self.update_buttons(self.task)
        communicate.task.connect(self.update_buttons)

    def start_clicked(self):
        self.setExpand(False)
        if self.task.first_run_alert:
            if not self.task.config.get('_first_run_alert'):
                title = og.app.tr('Alert')
                content = og.app.tr(self.task.first_run_alert)
                from qfluentwidgets import Dialog
                w = Dialog(title, content, self.window())
                # w.cancelButton.setVisible(False)
                w.yesButton.setText(og.app.tr('Confirm'))
                w.cancelButton.setText(og.app.tr('Cancel'))
                w.setContentCopyable(True)
                if w.exec():
                    self.task.config['_first_run_alert'] = self.task.first_run_alert
                else:
                    return
        og.app.start_controller.start(self.task)

    def stop_clicked(self):
        self.task.disable()
        self.task.unpause()

    def pause_clicked(self):
        self.task.pause()

    def edit_clicked(self):
        from ok import og
        og.main_window.edit_task_tab.load_task(self.task)
        og.main_window.switchTo(og.main_window.edit_task_tab)

    def show_instructions(self):
        if instructions := getattr(self.task, 'instructions', None):
            import re
            from PySide6.QtCore import Qt
            from qfluentwidgets import Dialog
            # Auto-link plain URLs while preserving existing <a> tags
            parts = re.split(r'(<a\s[^>]*>.*?</a>)', instructions, flags=re.DOTALL)
            for i, part in enumerate(parts):
                if not part.startswith('<a '):
                    parts[i] = re.sub(r'(https?://[^\s<>"]+)', r'<a href="\1">\1</a>', part)
            html = ''.join(parts).replace('\n', '<br>')
            w = Dialog(self.task.name, "", self.window())
            w.setContentCopyable(True)
            w.cancelButton.hide()
            w.contentLabel.setTextFormat(Qt.RichText)
            w.contentLabel.setOpenExternalLinks(True)
            w.contentLabel.setTextInteractionFlags(Qt.TextBrowserInteraction)
            w.contentLabel.setText(html)
            w.exec()

    def delete_task(self):
        w = MessageBox(self.tr('Delete Task'), self.tr('Are you sure you want to delete {}').format(self.task.name),
                       self.window())
        if w.exec():
            logger.info('Yes button is pressed')
            og.task_manager.delete_task(self.task)
        else:
            logger.info('No button is pressed')

    def _rebuild_button_layout(self):
        """Remove all buttons from layout, then re-add only visible ones for consistent spacing."""
        # Remove all items from the layout without deleting them
        while self.button_layout.count():
            self.button_layout.takeAt(0)
        # Add back only the visible buttons
        for btn in self.all_buttons:
            if not btn.isHidden():
                self.button_layout.addWidget(btn)

    def update_buttons(self, task):
        if task == self.task:
            # Determine visibility for instructions button
            has_instructions = bool(getattr(self.task, 'instructions', None))
            self.instructions_button.setVisible(has_instructions)

            if self.onetime:
                if self.task.enabled:
                    if self.task.paused:
                        self.start_button.setText(self.tr("Resume"))
                        self.start_button.setVisible(True)
                        self.pause_button.setVisible(False)
                        self.stop_button.setVisible(True)
                    elif self.task.running:
                        self.start_button.setVisible(False)
                        self.stop_button.setVisible(True)
                        self.pause_button.setVisible(True)
                    else:
                        self.start_button.setVisible(False)
                        self.stop_button.setVisible(True)
                        self.pause_button.setVisible(False)
                else:
                    self.start_button.setText(self.tr("Start"))
                    self.start_button.setVisible(True)
                    self.pause_button.setVisible(False)
                    self.stop_button.setVisible(False)
            else:
                if self.enable_button:
                    self.enable_button.setChecked(task.enabled)

            self._rebuild_button_layout()

    def check_changed(self, checked):
        if checked:
            import threading
            threading.Thread(target=self.task.enable, name="TaskEnable").start()
        else:
            self.task.disable()
