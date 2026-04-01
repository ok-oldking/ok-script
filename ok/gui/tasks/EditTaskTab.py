import os
import sys
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QInputDialog, QMessageBox, QListWidgetItem, QTreeWidgetItem, QAbstractItemView
from qfluentwidgets import ListWidget, TextEdit, PushButton, FluentIcon, Dialog, PrimaryPushButton, SearchLineEdit, \
    BodyLabel, ComboBox, PrimaryDropDownToolButton, RoundMenu, Action, TreeWidget, TreeView, CommandBar, \
    TransparentDropDownToolButton
from PySide6.QtCore import QFileSystemWatcher

from ok import og
from ok.gui.tasks.TemplateFactory import TemplateFactory, get_templates, filter_templates
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.highlightingRules = []

        keywordFormat = QTextCharFormat()
        keywordFormat.setForeground(QColor("#569CD6")) # Visual Studio Code dark blue
        keywordFormat.setFontWeight(QFont.Bold)
        keywords = ["and", "as", "assert", "break", "class", "continue", "def",
                    "del", "elif", "else", "except", "False", "finally", "for",
                    "from", "global", "if", "import", "in", "is", "lambda", "None",
                    "nonlocal", "not", "or", "pass", "raise", "return", "True",
                    "try", "while", "with", "yield"]
        for word in keywords:
            pattern = f"\\b{word}\\b"
            self.highlightingRules.append((pattern, keywordFormat))

        classFormat = QTextCharFormat()
        classFormat.setForeground(QColor("#4EC9B0"))
        classFormat.setFontWeight(QFont.Bold)
        self.highlightingRules.append(("\\b[A-Za-z0-9_]+(?=\\()", classFormat))
        
        selfFormat = QTextCharFormat()
        selfFormat.setForeground(QColor("#A074C4")) # Dark purpleish color
        selfFormat.setFontItalic(True)
        self.highlightingRules.append(("\\bself\\b", selfFormat))
        
        stringFormat = QTextCharFormat()
        stringFormat.setForeground(QColor("#D69D85"))
        self.highlightingRules.append(("\"[^\"]*\"", stringFormat))
        self.highlightingRules.append(("'[^']*'", stringFormat))

        commentFormat = QTextCharFormat()
        commentFormat.setForeground(QColor("#57A64A"))
        self.highlightingRules.append(("#[^\n]*", commentFormat))

        import re
        self.compiledRules = [(re.compile(pattern), fmt) for pattern, fmt in self.highlightingRules]

    def highlightBlock(self, text):
        for pattern, format in self.compiledRules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class EditTaskTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("EditTaskTab")
        self.task = None
        self.python_file = None
        self.all_templates = get_templates()
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self.on_file_changed)
        self.init_ui()

    def _update_file_watcher(self):
        if self.file_watcher.files():
            self.file_watcher.removePaths(self.file_watcher.files())
        if self.python_file and os.path.exists(self.python_file):
            self.file_watcher.addPath(self.python_file)
            self._last_mtime = os.path.getmtime(self.python_file)

    def on_file_changed(self, path):
        if path == self.python_file and os.path.exists(path):
            try:
                current_mtime = os.path.getmtime(path)
                if hasattr(self, '_last_mtime') and current_mtime == self._last_mtime:
                    return
                self._last_mtime = current_mtime

                with open(path, 'r', encoding='utf-8') as f:
                    new_content = f.read()

                if new_content == self.editor.toPlainText():
                    return

                if getattr(self, 'editor', None) and self.editor.document().isModified():
                    reply = QMessageBox.question(self, self.tr('File Changed Externally'),
                                                 self.tr("The file was modified externally. Do you want to overwrite your unsaved changes?"),
                                                 QMessageBox.Yes | QMessageBox.No)
                    if reply == QMessageBox.No:
                        return

                if getattr(self, 'editor', None):
                    cursor = self.editor.textCursor()
                    pos = cursor.position()
                    v_scroll = self.editor.verticalScrollBar().value()
                    
                    self.editor.setPlainText(new_content)
                    self.editor.document().setModified(False)
                    
                    cursor.setPosition(min(pos, len(new_content)))
                    self.editor.setTextCursor(cursor)
                    self.editor.verticalScrollBar().setValue(v_scroll)
                
                # Re-add path in case the editor saved via rename
                self._update_file_watcher()
            except Exception as e:
                logger.error(f"Error handling file change: {e}")

    def load_task(self, task):
        self.task = task
        self.python_file = og.task_manager.task_map.get(task, [None])[0]
        self._load_file_content()

    def _load_file_content(self):
        if self.python_file and os.path.exists(self.python_file):
            self.save_action.setVisible(True)
            self.delete_action.setVisible(True)
            with open(self.python_file, 'r', encoding='utf-8') as f:
                self.editor.setPlainText(f.read())
            self.editor.document().setModified(False)
            self._update_file_watcher()
            # Select correct dropdown index
            for i in range(self.task_dropdown.count()):
                if self.task_dropdown.itemData(i) == self.python_file:
                    self.task_dropdown.blockSignals(True)
                    self.task_dropdown.setCurrentIndex(i)
                    self._current_dropdown_index = i
                    self.task_dropdown.blockSignals(False)
                    break
        else:
            self.save_action.setVisible(False)
            self.delete_action.setVisible(False)
            self.editor.clear()
            self.editor.document().setModified(False)
            self._update_file_watcher()
        self.editor.setFocus()

    def init_ui(self):
        self.layout = QHBoxLayout(self)

        # Left: Template Chooser with search filter
        self.template_panel = QVBoxLayout()
        
        self.search_filter = SearchLineEdit()
        self.search_filter.setPlaceholderText(self.tr("Search templates..."))
        self.search_filter.textChanged.connect(self.on_search_changed)
        self.template_panel.addWidget(self.search_filter)
        
        self.template_list = TreeWidget()
        self.template_list.setBorderVisible(True)
        self.template_list.setBorderRadius(8)
        self.template_list.setHeaderHidden(True)
        self.template_list.setMaximumWidth(250)
        self._populate_template_list("")
        self.template_list.itemClicked.connect(self.on_template_clicked)
        self.template_panel.addWidget(self.template_list)
        
        template_container = QWidget()
        template_container.setLayout(self.template_panel)
        template_container.setMaximumWidth(250)
        self.layout.addWidget(template_container)

        # Right: Editor Area
        self.editor_layout = QVBoxLayout()
        self.editor = TextEdit()
        self.editor.setFont(QFont("Courier", 10))
        self.highlighter = PythonHighlighter(self.editor.document())

        self.top_layout = QHBoxLayout()
        
        # Left side: Choose Task label + dropdown
        self.choose_task_label = BodyLabel(self.tr("Choose Task:"))
        self.task_dropdown = ComboBox()
        self.task_dropdown.currentIndexChanged.connect(self.on_task_selected)
        
        self.top_layout.addWidget(self.choose_task_label)
        self.top_layout.addWidget(self.task_dropdown)
        
        # Spacer to push buttons to the right
        self.top_layout.addStretch(1)
        
        # Right side: action buttons menu
        self.menu = RoundMenu(parent=self)
        
        self.save_action = Action(FluentIcon.SAVE, self.tr("Save"), shortcut='Ctrl+S')
        self.save_action.triggered.connect(self.save_code)
        self.menu.addAction(self.save_action)
        
        self.create_action = Action(FluentIcon.ADD, self.tr("Create Task"))
        self.create_action.triggered.connect(self.create_task)
        self.menu.addAction(self.create_action)
        
        self.delete_action = Action(FluentIcon.DELETE, self.tr("Delete Task"))
        self.delete_action.triggered.connect(self.delete_task)
        self.menu.addAction(self.delete_action)
        
        self.commandBar = CommandBar(self)
        self.commandBar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        self.run_action = Action(FluentIcon.PLAY, self.tr("Run"))
        self.run_action.triggered.connect(self.run_task)
        self.commandBar.addAction(self.run_action)
        self.commandBar.addSeparator()

        self.file_button = TransparentDropDownToolButton(FluentIcon.MENU, self)
        self.file_button.setText(self.tr("File"))
        self.file_button.setMenu(self.menu)
        self.file_button.clicked.connect(self.file_button.showMenu)
        
        self.commandBar.addWidget(self.file_button)
        self.top_layout.addWidget(self.commandBar)
        
        # Hide save and delete actions initially
        self.save_action.setVisible(False)
        self.delete_action.setVisible(False)

        self.editor_layout.addLayout(self.top_layout)
        self.editor_layout.addWidget(self.editor)
        
        self.error_label = BodyLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        self.editor_layout.addWidget(self.error_label)
        
        self.layout.addLayout(self.editor_layout)
        
        self.refresh_dropdown()

    def _update_error_display(self):
        if self.python_file and self.python_file in og.task_manager.task_errors:
            self.error_label.setText(og.task_manager.task_errors[self.python_file])
            self.error_label.setVisible(True)
        else:
            self.error_label.setVisible(False)

    def _populate_template_list(self, query):
        self.template_list.clear()
        
        filtered = filter_templates(self.all_templates, query)
        
        groups = {}
        for t in filtered:
            cname = t.get('category', 'Other')
            if cname not in groups:
                groups[cname] = []
            groups[cname].append(t)
            
        categories_order = [
            "Mouse", "Key", "Control", "OCR", "Template Matching",
            "Box", "Window", "ADB", "Logging", "Other"
        ]
        
        for cname in categories_order:
            if cname in groups:
                templates = groups[cname]
                parent_item = QTreeWidgetItem([cname])
                parent_item.setFlags(parent_item.flags() & ~Qt.ItemIsSelectable)
                self.template_list.addTopLevelItem(parent_item)
                
                for t in templates:
                    doc_preview = t.get('doc', '')
                    display_text = t['template_name']
                    if doc_preview:
                        display_text = f"{t['template_name']} - {doc_preview}"
                    item = QTreeWidgetItem([display_text])
                    item.setData(0, Qt.UserRole, t)
                    item.setToolTip(0, t.get('full_doc', t.get('doc', '')))
                    parent_item.addChild(item)
                    
        self.template_list.collapseAll()

    def on_search_changed(self, text):
        self._populate_template_list(text)

    def refresh_dropdown(self):
        self.task_dropdown.blockSignals(True)
        self.task_dropdown.clear()
        folder = og.task_manager.task_folder
        if folder and os.path.exists(folder):
            for file in os.listdir(folder):
                if file.endswith('.py'):
                    self.task_dropdown.addItem(os.path.splitext(file)[0], userData=os.path.join(folder, file))
        self.task_dropdown.blockSignals(False)
        if self.task_dropdown.count() > 0 and not self.python_file:
            self.task_dropdown.setCurrentIndex(0)
            self.on_task_selected(0)
        else:
            # Reselect current item correctly
            for i in range(self.task_dropdown.count()):
                if self.task_dropdown.itemData(i) == self.python_file:
                    self.task_dropdown.blockSignals(True)
                    self.task_dropdown.setCurrentIndex(i)
                    self._current_dropdown_index = i
                    self.task_dropdown.blockSignals(False)
                    break

    def on_task_selected(self, index):
        if hasattr(self, 'editor') and self.editor.document().isModified() and hasattr(self, 'python_file') and self.python_file:
            reply = QMessageBox.question(self, self.tr('Save Changes'),
                                         self.tr("The current task has unsaved changes. Do you want to save them?"),
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if reply == QMessageBox.Yes:
                if not self.save_code():
                    self._revert_dropdown_index()
                    return
            elif reply == QMessageBox.Cancel:
                self._revert_dropdown_index()
                return

        if index >= 0:
            self.python_file = self.task_dropdown.itemData(index)
            
            # Match task instance if exists
            self.task = None
            for t, data in og.task_manager.task_map.items():
                if data[0] == self.python_file:
                    self.task = t
                    break
            
            if self.python_file and os.path.exists(self.python_file):
                self.save_action.setVisible(True)
                self.delete_action.setVisible(True)
                with open(self.python_file, 'r', encoding='utf-8') as f:
                    self.editor.setPlainText(f.read())
                self.editor.document().setModified(False)
                self._update_file_watcher()
            else:
                self.save_action.setVisible(False)
                self.delete_action.setVisible(False)
                self.editor.clear()
                self.editor.document().setModified(False)
                self._update_file_watcher()
            self._update_error_display()
            self._current_dropdown_index = index

    def _revert_dropdown_index(self):
        if hasattr(self, '_current_dropdown_index'):
            self.task_dropdown.blockSignals(True)
            self.task_dropdown.setCurrentIndex(self._current_dropdown_index)
            self.task_dropdown.blockSignals(False)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.save_code()
            event.accept()
        else:
            super().keyPressEvent(event)

    def run_task(self):
        if self.save_code(silent=True):
            if self.python_file:
                for t, data in og.task_manager.task_map.items():
                    if data[0] == self.python_file:
                        t.start()
                        self._switch_to_task_tab()
                        return

    def _switch_to_task_tab(self):
        """Switch to the tab that contains the current task."""
        if not self.task:
            return
        try:
            main_window = og.main_window
            # Check if task is in onetime_tab
            if main_window.onetime_tab and main_window.onetime_tab.in_current_list(self.task):
                main_window.switchTo(main_window.onetime_tab)
                return
            # Check grouped tabs
            for group_tab in main_window.grouped_task_tabs:
                if group_tab.in_current_list(self.task):
                    main_window.switchTo(group_tab)
                    return
            # Check trigger_tab
            if main_window.trigger_tab and main_window.trigger_tab.in_current_list(self.task):
                main_window.switchTo(main_window.trigger_tab)
                return
            # Fallback: switch to onetime_tab if available
            if main_window.onetime_tab:
                main_window.switchTo(main_window.onetime_tab)
        except Exception as e:
            logger.error(f"Error switching tab: {e}")

    def save_code(self, silent=False):
        code = self.editor.toPlainText()
        if self.python_file:
            try:
                with open(self.python_file, 'w', encoding='utf-8') as f:
                    f.write(code)
                self._last_mtime = os.path.getmtime(self.python_file)
                if self.task:
                    og.task_manager.reload_task_code(self.task)
                else:
                    og.task_manager.load_single_user_task(self.python_file)
                self._update_error_display()
                
                # If there's an error, don't show success or switch tab
                if self.python_file in og.task_manager.task_errors:
                    return False

                self.editor.document().setModified(False)
                if not silent:
                    from ok.gui.util.app import show_info_bar
                    show_info_bar(self.window(), self.tr("Task rebuilt successfully."), title=self.tr("Success"))
                return True
            except Exception as e:
                from ok.gui.util.Alert import alert_error
                alert_error(f"{self.tr('Failed to save')}: {e}")
                return False
        return False

    def delete_task(self):
        if not self.python_file:
            return
            
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, self.tr('Confirm Delete'), 
                                     self.tr(f"Are you sure you want to delete {os.path.basename(self.python_file)}?"),
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                                     
        if reply == QMessageBox.Yes:
            try:
                if self.task:
                    og.task_manager.delete_task(self.task)
                else:
                    if os.path.exists(self.python_file):
                        os.remove(self.python_file)
                
                from ok.gui.util.app import show_info_bar
                show_info_bar(self.window(), self.tr("Task deleted successfully."), title=self.tr("Success"))
                self.python_file = None
                self.task = None
                self.editor.clear()
                self.refresh_dropdown()
            except Exception as e:
                from ok.gui.util.Alert import alert_error
                alert_error(f"Error deleting task: {e}")

    def on_template_clicked(self, item, column):
        template = item.data(0, Qt.UserRole)
        if not template:
            if item.isExpanded():
                item.setExpanded(False)
            else:
                item.setExpanded(True)
            return
        code_to_insert = TemplateFactory.handle_template(template, self)
        
        if code_to_insert:
            cursor = self.editor.textCursor()
            # Determine proper indentation
            block = cursor.block()
            line_text = block.text()
            indent_spaces = len(line_text) - len(line_text.lstrip(' '))
            
            # If the current line is completely empty, fallback to basic indent (e.g., 8 spaces) if inside a function
            if not line_text:
                indent_spaces = max(8, indent_spaces)
                
            indent_str = ' ' * indent_spaces
            
            # Format the insertion
            if line_text.strip():
                # If there is already code on this line, insert a new line with indentation
                final_text = f"\n{indent_str}{code_to_insert}\n"
            else:
                # If the line is empty, just insert the code with correct indentation
                if len(line_text) < indent_spaces:
                    # Pad the missing spaces if needed
                    final_text = (' ' * (indent_spaces - len(line_text))) + code_to_insert + "\n"
                else:
                    final_text = code_to_insert + "\n"
                    
            cursor.insertText(final_text)
            self.editor.setFocus()

    def create_task(self):
        from qfluentwidgets import MessageBoxBase, LineEdit, SubtitleLabel
        from ok.gui.util.Alert import alert_error
        import re

        class CreateTaskDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.titleLabel = SubtitleLabel(self.tr('Create Task'), self)
                
                self.class_name_input = LineEdit(self)
                self.class_name_input.setPlaceholderText(self.tr("Class Name (English only)"))
                
                self.task_name_input = LineEdit(self)
                self.task_name_input.setPlaceholderText(self.tr("Task Name"))
                
                self.task_desc_input = LineEdit(self)
                self.task_desc_input.setPlaceholderText(self.tr("Description (Optional)"))
                
                self.viewLayout.addWidget(self.titleLabel)
                self.viewLayout.addWidget(self.class_name_input)
                self.viewLayout.addWidget(self.task_name_input)
                self.viewLayout.addWidget(self.task_desc_input)
                self.yesButton.setText(self.tr('Confirm'))
                self.cancelButton.setText(self.tr('Cancel'))
                self.widget.setMinimumWidth(360)

        dialog = CreateTaskDialog(self.window())
        
        if dialog.exec():
            class_name = dialog.class_name_input.text().strip()
            task_name = dialog.task_name_input.text().strip()
            task_desc = dialog.task_desc_input.text().strip()
            
            if not class_name or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', class_name):
                alert_error(self.tr("Invalid Class Name. Must be English characters only."))
                return
            if not task_name:
                alert_error(self.tr("Task Name is required."))
                return

            base_class = "BaseTask"  # Defaulting to BaseTask for custom tasks
            
            task_code = f"""from ok import {base_class}

class {class_name}({base_class}):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "{task_name}"
        self.description = "{task_desc}"

    def run(self):
        pass
"""
            file_path = os.path.join(og.task_manager.task_folder, f"{class_name}.py")
            if os.path.exists(file_path):
                alert_error(self.tr("Task file already exists."))
                return
                
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(task_code)
                self.refresh_dropdown()
                
                # Auto select the newly created task
                for i in range(self.task_dropdown.count()):
                    if self.task_dropdown.itemData(i) == file_path:
                        self.task_dropdown.setCurrentIndex(i)
                        break
                        
                og.task_manager.load_single_user_task(file_path)
                from ok.gui.util.app import show_info_bar
                show_info_bar(self.window(), self.tr("Task created successfully."), title=self.tr("Success"))
            except Exception as e:
                alert_error(f"Error creating task: {e}")
