from ok import Logger, og

from ok.ui.qt.tasks.TaskCard import TaskCard
from ok.ui.qt.tasks.TaskTab import TaskTab

logger = Logger.get_logger(__name__)


class OneTimeTaskTab(TaskTab):
    def __init__(self, is_standalone=True, group_name=None):
        super().__init__()
        self.timer.setParent(self)
        self.is_standalone = is_standalone
        self.group_name = group_name
        self.card_widgets = []
        self.keep_info_when_done = True
        
        # Check if this is an imported script to show delete button
        self.imported_file_name = None
        for fn, imp in og.task_manager.imported_scripts.items():
            if imp['script_name'] == self.group_name:
                self.imported_file_name = fn
                break
                
        if self.imported_file_name:
            from PySide6.QtWidgets import QHBoxLayout, QSpacerItem, QSizePolicy, QWidget
            from qfluentwidgets import PushButton, FluentIcon
            
            self.button_container = QWidget()
            self.btn_layout = QHBoxLayout(self.button_container)
            self.btn_layout.setContentsMargins(0, 10, 0, 0)
            self.btn_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
            
            self.delete_btn = PushButton(self.tr('Delete Script'), self, FluentIcon.DELETE)
            self.delete_btn.clicked.connect(self.delete_script)
            self.btn_layout.addWidget(self.delete_btn)
            
            # Keep this ordinary footer outside the expandable-card layout.
            self.vBoxLayout.addWidget(self.button_container)
            
        from ok.ui.qt.Communicate import communicate
        communicate.task_list_updated.connect(self.refresh_ui)
        callback = self.refresh_ui
        self.destroyed.connect(lambda *_: communicate.task_list_updated.disconnect(callback))
        self.refresh_ui()

    def dispose(self):
        from ok.core.events import communicate
        communicate.task_list_updated.disconnect(self.refresh_ui)
        for card in self.card_widgets:
            card.dispose()

    def delete_script(self):
        from qfluentwidgets import MessageBox
        w = MessageBox(self.tr('Confirm Delete'), 
                       self.tr('Are you sure you want to delete the script "{}"?').format(self.group_name), 
                       self.window())
        if w.exec():
            from PySide6.QtCore import QCoreApplication
            from ok.ui.qt.util.app import show_info_bar
            try:
                og.task_manager.delete_imported_script(self.imported_file_name)
                show_info_bar(self.window(), QCoreApplication.translate(
                    'PluginTab', 'Restart the application to apply plugin changes.'))
            except Exception as error:
                from ok.ui.qt.util.Alert import alert_error
                alert_error(str(error))

    def refresh_ui(self):
        # Remove old cards
        for w in self.card_widgets:
            self.remove_task_card(w)
            w.dispose()
            w.deleteLater()
        self.card_widgets.clear()
        
        self.tasks = []
        for task in og.executor.onetime_tasks:
            if not getattr(task, 'visible', True):
                continue
            task_group = getattr(task, 'group_name', None)
            if self.is_standalone and not task_group:
                self.tasks.append(task)
            elif self.group_name and task_group == self.group_name:
                self.tasks.append(task)
                
        for task in self.tasks:
            task_card = TaskCard(task, True)
            self.card_widgets.append(task_card)
            self.add_task_card(task_card)

    def in_current_list(self, task):
        return getattr(self, 'tasks', None) and task in self.tasks
