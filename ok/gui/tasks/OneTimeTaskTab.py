from ok import Logger, og

from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TaskTab import TaskTab

logger = Logger.get_logger(__name__)


class OneTimeTaskTab(TaskTab):
    def __init__(self, is_standalone=True, group_name=None):
        super().__init__()
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
            from PySide6.QtWidgets import QHBoxLayout, QSpacerItem, QSizePolicy
            from qfluentwidgets import PushButton, FluentIcon
            
            self.btn_layout = QHBoxLayout()
            self.btn_layout.setContentsMargins(0, 10, 0, 0)
            self.btn_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
            
            self.delete_btn = PushButton(self.tr('Delete Script'), self, FluentIcon.DELETE)
            self.delete_btn.clicked.connect(self.delete_script)
            self.btn_layout.addWidget(self.delete_btn)
            
            # Position it at the end of vBoxLayout
            self.vBoxLayout.addLayout(self.btn_layout)
            
        from ok.gui.Communicate import communicate
        communicate.task_list_updated.connect(self.refresh_ui)
        self.refresh_ui()

    def delete_script(self):
        from qfluentwidgets import MessageBox
        w = MessageBox(self.tr('Confirm Delete'), 
                       self.tr('Are you sure you want to delete the script "{}"?').format(self.group_name), 
                       self.window())
        if w.exec():
            og.task_manager.delete_imported_script(self.imported_file_name)

    def refresh_ui(self):
        # Remove old cards
        for w in self.card_widgets:
            self.removeWidget(w)
            w.deleteLater()
        self.card_widgets.clear()
        
        # If we have a delete button, it's at the end. We need to keep it there.
        if hasattr(self, 'btn_layout'):
            self.vBoxLayout.removeItem(self.btn_layout)
        
        self.tasks = []
        for task in og.executor.onetime_tasks:
            task_group = getattr(task, 'group_name', None)
            if self.is_standalone and not task_group:
                self.tasks.append(task)
            elif self.group_name and task_group == self.group_name:
                self.tasks.append(task)
                
        for task in self.tasks:
            task_card = TaskCard(task, True)
            self.card_widgets.append(task_card)
            self.vBoxLayout.addWidget(task_card) # Use vBoxLayout directly to avoid stretch issues
            
        if hasattr(self, 'btn_layout'):
            self.vBoxLayout.addLayout(self.btn_layout)

    def in_current_list(self, task):
        return getattr(self, 'tasks', None) and task in self.tasks
