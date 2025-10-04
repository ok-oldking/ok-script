from PySide6.QtWidgets import QHBoxLayout, QWidget
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

        if onetime:
            self.task_buttons = TaskButtons(self.task)
            self.task_buttons.start_button.clicked.connect(self.start_clicked)
            self.addWidget(self.task_buttons)
        else:
            self.enable_button = SwitchButton()
            self.enable_button.setOnText(self.tr('Enabled'))
            self.enable_button.setOffText(self.tr('Disabled'))
            self.enable_button.checkedChanged.connect(self.check_changed)
            self.addWidget(self.enable_button)

        if self.task.is_custom():
            self.delete_button = PushButton(FluentIcon.DELETE, self.tr("Delete"), self)
            self.delete_button.clicked.connect(self.delete_task)
            self.addWidget(self.delete_button)

        self.update_buttons(self.task)

        communicate.task.connect(self.update_buttons)

    def start_clicked(self):
        self.setExpand(False)

    def delete_task(self):
        w = MessageBox(self.tr('Delete Task'), self.tr('Are you sure you want to delete {}').format(self.task.name),
                       self.window())
        if w.exec():
            logger.info('Yes button is pressed')
            og.task_manager.delete_task(self.task)
        else:
            logger.info('No button is pressed')

    def update_buttons(self, task):
        if task == self.task:
            if self.onetime:
                self.task_buttons.update_buttons()
            else:
                self.enable_button.setChecked(task.enabled)

    def check_changed(self, checked):
        if checked:
            self.task.enable()
        else:
            self.task.disable()


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

    def add_button(self, button):
        self.layout.addWidget(button)

    def start_clicked(self):
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
