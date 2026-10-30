from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import PushButton, TextEdit, ComboBox, FluentIcon

from ok import Config, og
from ok.core.code_runner import CodeSession
from ok.core.events import communicate
from ok.ui.qt.debug.JobControls import JobControls
from ok.ui.qt.util.Alert import alert_info
from ok.ui.qt.widget.Tab import Tab


class RunCodeTab(Tab):
    """Runs Python code on the task executor's thread, keeping variables between runs."""

    def __init__(self, app_config, exit_event):
        super().__init__()
        self.config = Config('run_code', {'code': "", 'target_task': ""})
        self.session = CodeSession(og.executor)

        container = QWidget()
        layout = QVBoxLayout(container)

        self.code_input = TextEdit()
        self.code_input.setPlaceholderText(self.tr(
            "Enter Python code here...\n"
            "og, executor and task (the selected task) are predefined, "
            "variables are kept between runs, and the value of the last line is shown."))
        if self.config.get('code'):
            self.code_input.setText(self.config.get('code'))
        layout.addWidget(self.code_input, stretch=2)

        toolbar = QHBoxLayout()
        self.tasks_combo_box = ComboBox()
        self.tasks_combo_box.addItem(self.tr('No Task'), userData=None)
        for task in og.executor.get_all_tasks():
            self.tasks_combo_box.addItem(task.__class__.__name__, userData=task)
        target_task = self.config.get('target_task')
        for index in range(self.tasks_combo_box.count()):
            task = self.tasks_combo_box.itemData(index)
            if task is not None and task.__class__.__name__ == target_task:
                self.tasks_combo_box.setCurrentIndex(index)
                break
        toolbar.addWidget(self.tasks_combo_box)

        self.controls = JobControls(self.tr("Run Code"))
        self.controls.run_clicked.connect(self.run_code)
        self.controls.output.connect(self.append_output)
        self.controls.finished.connect(self.show_result)
        toolbar.addWidget(self.controls, stretch=1)

        reset_button = PushButton(FluentIcon.SYNC, self.tr("Reset Variables"))
        reset_button.clicked.connect(self.reset_session)
        toolbar.addWidget(reset_button)

        clear_button = PushButton(FluentIcon.DELETE, self.tr("Clear Output"))
        toolbar.addWidget(clear_button)
        layout.addLayout(toolbar)

        self.output_area = TextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText(self.tr("Output will be shown here..."))
        clear_button.clicked.connect(self.output_area.clear)
        layout.addWidget(self.output_area, stretch=1)

        self.add_card(self.tr("Run Python Code"), container)
        communicate.task_list_updated.connect(self.refresh_tasks)
        callback = self.refresh_tasks
        self.destroyed.connect(lambda *_: communicate.task_list_updated.disconnect(callback))

    def refresh_tasks(self):
        selected = self.selected_task()
        key = (type(selected).__module__, type(selected).__qualname__) if selected is not None else None
        self.tasks_combo_box.blockSignals(True)
        self.tasks_combo_box.clear()
        self.tasks_combo_box.addItem(self.tr('No Task'), userData=None)
        for task in og.executor.get_all_tasks():
            self.tasks_combo_box.addItem(type(task).__name__, userData=task)
            if (type(task).__module__, type(task).__qualname__) == key:
                self.tasks_combo_box.setCurrentIndex(self.tasks_combo_box.count() - 1)
        self.tasks_combo_box.blockSignals(False)
        # A code session's globals can otherwise keep invoking an unloaded task.
        self.session.namespace.pop('task', None)

    def selected_task(self):
        return self.tasks_combo_box.currentData()

    def run_code(self):
        code = self.code_input.toPlainText()
        self.config['code'] = code
        task = self.selected_task()
        self.config['target_task'] = task.__class__.__name__ if task is not None else ""
        if task is None:
            self.session.namespace.pop('task', None)
        self.output_area.clear()
        self.controls.start(lambda on_output: self.session.submit(code, task=task, on_output=on_output))

    def reset_session(self):
        self.session.reset()
        alert_info(self.tr("Variables reset"))

    def append_output(self, text):
        self.output_area.moveCursor(QTextCursor.End)
        self.output_area.insertPlainText(text)

    def show_result(self, result):
        if result.value is not None:
            self.append_output(result.value + '\n')
        if result.error:
            self.append_output(result.error)
        elif result.cancelled:
            self.append_output(self.tr("Cancelled") + '\n')
