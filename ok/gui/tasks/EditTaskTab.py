import os

from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor, QPainter
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QMessageBox, QTreeWidgetItem, QFileDialog
from qfluentwidgets import MessageBox, PlainTextEdit, PushButton, FluentIcon, PrimaryPushButton, SearchLineEdit, \
    BodyLabel, ComboBox, RoundMenu, Action, TreeWidget, TransparentDropDownPushButton, CheckBox

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

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

class CodeEditor(PlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.error_line_number = -1
        
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        
        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        space = 8 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, new_block_count):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(Qt.transparent))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        font_metrics = self.fontMetrics()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                
                if (block_number + 1) == self.error_line_number:
                    painter.setPen(Qt.red)
                else:
                    painter.setPen(Qt.gray)

                painter.drawText(0, int(top), self.line_number_area.width() - 4, int(font_metrics.height()),
                                 Qt.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def set_error_line(self, line_number):
        self.error_line_number = line_number
        self.line_number_area.update()


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
        self.template_list.itemExpanded.connect(self.on_item_expanded_collapsed)
        self.template_list.itemCollapsed.connect(self.on_item_expanded_collapsed)
        self._last_toggled_time = 0
        self.template_panel.addWidget(self.template_list)
        
        template_container = QWidget()
        template_container.setLayout(self.template_panel)
        template_container.setMaximumWidth(250)
        self.layout.addWidget(template_container)

        # Right: Editor Area
        self.editor_layout = QVBoxLayout()
        self.right_container = QWidget()
        self.right_container_layout = QVBoxLayout(self.right_container)
        self.right_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.editor = CodeEditor()
        self.editor.setFont(QFont("Courier", 10))
        self.highlighter = PythonHighlighter(self.editor.document())

        self.top_layout = QHBoxLayout()
        
        # Left side: Choose Task label + dropdown
        self.choose_task_label = BodyLabel(self.tr("Choose Task:"))
        self.task_dropdown = ComboBox()
        self.task_dropdown.currentIndexChanged.connect(self.on_task_selected)
        
        # Right side: action buttons menu
        self.menu = RoundMenu(parent=self)
        
        self.save_action = Action(FluentIcon.SAVE, self.tr("Save"), shortcut='Ctrl+S')
        self.save_action.triggered.connect(self.save_code)
        self.menu.addAction(self.save_action)
        
        self.create_action = Action(FluentIcon.ADD, self.tr("Create Task"))
        self.create_action.triggered.connect(self.create_task)
        self.menu.addAction(self.create_action)
        
        self.copy_action = Action(FluentIcon.COPY, self.tr("Copy Task"))
        self.copy_action.triggered.connect(self.copy_task)
        self.menu.addAction(self.copy_action)
        
        self.delete_action = Action(FluentIcon.DELETE, self.tr("Delete Task"))
        self.delete_action.triggered.connect(self.delete_task)
        self.menu.addAction(self.delete_action)

        self.menu.addSeparator()

        self.export_action = Action(FluentIcon.SHARE, self.tr("Export Script"))
        self.export_action.triggered.connect(self.show_export_dialog)
        self.menu.addAction(self.export_action)

        self.import_action = Action(FluentIcon.DOWNLOAD, self.tr("Import Script"))
        self.import_action.triggered.connect(self.show_import_dialog)
        self.menu.addAction(self.import_action)

        self.file_button = TransparentDropDownPushButton(FluentIcon.MENU, self.tr("File"), self)
        self.file_button.setMenu(self.menu)
        
        self.top_layout.addWidget(self.choose_task_label)
        self.top_layout.addWidget(self.task_dropdown)
        self.top_layout.addWidget(self.file_button)
        
        # Spacer to push buttons to the right
        self.top_layout.addStretch(1)
        
        self.tools_layout = QHBoxLayout()
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(8)
        
        self.run_button = PrimaryPushButton(self)
        self.run_button.setText(self.tr("Run"))
        self.run_button.setIcon(FluentIcon.PLAY)
        self.run_button.clicked.connect(self.run_task)
        self.tools_layout.addWidget(self.run_button)

        self.record_button = PushButton(self)
        self.record_button.setText(self.tr("Record"))
        self.record_button.setIcon(FluentIcon.CAMERA)
        self.record_button.clicked.connect(self.toggle_record)
        self.tools_layout.addWidget(self.record_button)
        
        self.top_layout.addLayout(self.tools_layout)
        
        # Hide save and delete actions initially
        self.save_action.setVisible(False)
        self.delete_action.setVisible(False)

        self.right_container_layout.addLayout(self.top_layout)
        self.right_container_layout.addWidget(self.editor)
        
        self.error_label = BodyLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        self.right_container_layout.addWidget(self.error_label)
        
        self.empty_widget = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_widget)
        self.empty_layout.setAlignment(Qt.AlignCenter)
        
        self.empty_buttons_layout = QHBoxLayout()
        self.empty_buttons_layout.setAlignment(Qt.AlignCenter)
        
        self.center_create_button = PrimaryPushButton(FluentIcon.ADD, self.tr("Create New Task"))
        self.center_create_button.clicked.connect(self.create_task)
        self.empty_buttons_layout.addWidget(self.center_create_button)
        
        self.center_copy_button = PushButton(FluentIcon.COPY, self.tr("Copy Task"))
        self.center_copy_button.clicked.connect(self.copy_task)
        self.empty_buttons_layout.addWidget(self.center_copy_button)
        
        self.empty_layout.addLayout(self.empty_buttons_layout)

        self.editor_layout.addWidget(self.right_container)
        self.editor_layout.addWidget(self.empty_widget)

        self.layout.addLayout(self.editor_layout)
        
        self.refresh_dropdown()

    def _update_error_display(self):
        if self.python_file and self.python_file in og.task_manager.task_errors:
            error_msg = og.task_manager.task_errors[self.python_file]
            self.error_label.setText(error_msg)
            self.error_label.setVisible(True)
            
            import re
            m = re.search(r'line (\d+)', error_msg.lower())
            if m:
                self.editor.set_error_line(int(m.group(1)))
            else:
                self.editor.set_error_line(-1)
        else:
            self.error_label.setVisible(False)
            if hasattr(self, 'editor') and hasattr(self.editor, 'set_error_line'):
                self.editor.set_error_line(-1)

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

        category_translations = {
            "Mouse": self.tr("Mouse"),
            "Key": self.tr("Key"),
            "Control": self.tr("Control"),
            "OCR": self.tr("OCR"),
            "Template Matching": self.tr("Template Matching"),
            "Box": self.tr("Box"),
            "Window": self.tr("Window"),
            "ADB": self.tr("ADB"),
            "Logging": self.tr("Logging"),
            "Other": self.tr("Other"),
        }
        
        for cname in categories_order:
            if cname in groups:
                templates = groups[cname]
                display_name = category_translations.get(cname, cname)
                parent_item = QTreeWidgetItem([display_name])
                parent_item.setFlags(parent_item.flags() & ~Qt.ItemIsSelectable)
                self.template_list.addTopLevelItem(parent_item)
                
                for t in templates:
                    doc_preview = t.get('doc', '')
                    display_text = t['template_name']
                    if doc_preview:
                        display_text = f"{t['template_name']}"
                    item = QTreeWidgetItem([self.tr(display_text)])
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
        
        has_tasks = self.task_dropdown.count() > 0
        if has_tasks:
            self.right_container.setVisible(True)
            self.empty_widget.setVisible(False)
            if not self.python_file:
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
        else:
            self.right_container.setVisible(False)
            self.empty_widget.setVisible(True)
            self.python_file = None
            self.task = None

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
                        self._switch_to_task_tab() # Switch first for immediate UI response
                        og.app.start_controller.start(t) # Launch asynchronously via start_controller
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

    def toggle_record(self):
        from .RecordScript import recorder
        from qfluentwidgets import MessageBox
        
        if not recorder.is_recording:
            w = MessageBox(self.tr('Warning'), 
                           self.tr("Record will override the current script logic. Continue?"), 
                           self.window())
            if w.exec():
                hwnd_name = og.device_manager.get_hwnd_name()
                from ok.gui.util.Alert import alert_info
                alert_info(f"Recording will start when window '{hwnd_name}' becomes active.")
                
                recorder.start(hwnd_name)
                
                self.run_button.setText(self.tr("Stop"))
                self.run_button.setIcon(FluentIcon.PAUSE)
                self.run_button.clicked.disconnect()
                self.run_button.clicked.connect(self.toggle_record)
                self.record_button.setVisible(False)
        else:
            init_code, run_code = recorder.stop()
            self.run_button.setText(self.tr("Run"))
            self.run_button.setIcon(FluentIcon.PLAY)
            self.run_button.clicked.disconnect()
            self.run_button.clicked.connect(self.run_task)
            self.record_button.setVisible(True)
            self._replace_run_block(init_code, run_code)

    def _replace_run_block(self, init_code, run_code):
        import re
        code = self.editor.toPlainText()
        
        lines = code.split('\n')
        
        # 1. Replace capture_config in __init__
        if init_code:
            init_start = -1
            init_indentation = ""
            for i, line in enumerate(lines):
                if re.match(r'^\s*def\s+__init__\s*\(.*?\)\s*:', line):
                    init_start = i
                    match = re.match(r'^(\s*)def', line)
                    base_indent = match.group(1) if match else ""
                    init_indentation = base_indent + "    "
                    break
                    
            if init_start != -1:
                capture_config_start = -1
                capture_config_end = -1
                
                for i in range(init_start + 1, len(lines)):
                    if re.match(r'^\s*def\s+', lines[i]) or (lines[i].strip() and not lines[i].startswith(init_indentation)):
                        break
                        
                    if re.match(r'^\s*self\.capture_config\s*=', lines[i]):
                        capture_config_start = i
                        brackets = 0
                        for j in range(i, len(lines)):
                            if j > i and (re.match(r'^\s*def\s+', lines[j]) or (lines[j].strip() and not lines[j].startswith(init_indentation))):
                                capture_config_end = j - 1
                                break
                            brackets += lines[j].count('{') - lines[j].count('}')
                            if brackets <= 0:
                                capture_config_end = j
                                break
                        if capture_config_end == -1:
                            capture_config_end = i
                        break
                        
                init_lines = init_code.strip('\n').split('\n')
                formatted_init_code = []
                for line in init_lines:
                    formatted_init_code.append(init_indentation + line.strip(' '))
                    
                if capture_config_start != -1 and capture_config_end != -1:
                    lines = lines[:capture_config_start] + formatted_init_code + lines[capture_config_end + 1:]
                else:
                    insert_idx = init_start + 1
                    for i in range(init_start + 1, len(lines)):
                        if re.match(r'^\s*def\s+', lines[i]) or (lines[i].strip() and not lines[i].startswith(init_indentation)):
                            break
                        insert_idx = i + 1
                    lines = lines[:insert_idx] + formatted_init_code + lines[insert_idx:]

        # 2. Replace run method body
        run_start = -1
        indentation = ""
        for i, line in enumerate(lines):
            if re.match(r'^\s*def\s+run\s*\(.*?\)\s*:', line):
                run_start = i
                match = re.match(r'^(\s*)def', line)
                base_indent = match.group(1) if match else ""
                indentation = base_indent + "    "
                break
                
        if run_start != -1:
            run_end = len(lines)
            for i in range(run_start + 1, len(lines)):
                if re.match(r'^\s*def\s+', lines[i]) or (lines[i].strip() and not lines[i].startswith(indentation)):
                    run_end = i
                    break
                    
            new_lines = lines[:run_start+1]
            generated_code_lines = run_code.strip('\n').split('\n')
            for line in generated_code_lines:
                new_lines.append(indentation + line.strip(' '))
            new_lines.extend(lines[run_end:])
            
            cursor = self.editor.textCursor()
            v_scroll = self.editor.verticalScrollBar().value()
            
            self.editor.setPlainText("\n".join(new_lines))
            self.editor.verticalScrollBar().setValue(v_scroll)

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
                    
                self.task = None
                for t, data in og.task_manager.task_map.items():
                    if data[0] == self.python_file:
                        self.task = t
                        break

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
            
        w = MessageBox(self.tr('Confirm Delete'), 
                       self.tr(f"Are you sure you want to delete {os.path.basename(self.python_file)}?"), 
                       self.window())
                                     
        if w.exec():
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

    def on_item_expanded_collapsed(self, item):
        import time
        self._last_toggled_time = time.time()

    def on_template_clicked(self, item, column):
        import time
        template = item.data(0, Qt.UserRole)
        if not template:
            # If the item was expanded/collapsed natively by the chevron just now, don't revert it
            if time.time() - getattr(self, '_last_toggled_time', 0) < 0.1:
                return
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
        self.instructions = \"\"\"<a href="https://github.com/ok-oldking/ok-py">ok-py</a>\"\"\"

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

    def copy_task(self):
        from qfluentwidgets import MessageBoxBase, ComboBox, SubtitleLabel
        from ok.gui.util.Alert import alert_error
        import inspect

        class CopyTaskDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.titleLabel = SubtitleLabel(self.tr('Copy Task'), self)
                self.task_dropdown = ComboBox(self)
                self.task_dropdown.setPlaceholderText(self.tr("Select task to copy..."))
                
                self.tasks = []
                for task in og.task_manager.task_executor.onetime_tasks + og.task_manager.task_executor.trigger_tasks:
                    if task not in self.tasks:
                        self.tasks.append(task)
                        
                for task in og.task_manager.task_map.keys():
                    if task not in self.tasks:
                        self.tasks.append(task)
                        
                for task in self.tasks:
                    name = getattr(task, 'name', task.__class__.__name__)
                    class_name = task.__class__.__name__
                    display_text = f"{name} ({class_name})" if name != class_name else name
                    self.task_dropdown.addItem(display_text, userData=task)
                
                self.viewLayout.addWidget(self.titleLabel)
                self.viewLayout.addWidget(self.task_dropdown)
                self.yesButton.setText(self.tr('Confirm'))
                self.cancelButton.setText(self.tr('Cancel'))
                self.widget.setMinimumWidth(360)

        dialog = CopyTaskDialog(self.window())
        
        if dialog.exec():
            selected_task = dialog.task_dropdown.currentData()
            if not selected_task:
                return
                
            python_file, _ = og.task_manager.task_map.get(selected_task, (None, None))
            if not python_file or not os.path.exists(python_file):
                try:
                    python_file = inspect.getsourcefile(selected_task.__class__)
                except TypeError:
                    python_file = None
                    
            if not python_file or not os.path.exists(python_file):
                alert_error(self.tr(f"Could not find source file for {selected_task.__class__.__name__}"))
                return
                
            try:
                with open(python_file, "r", encoding="utf-8") as f:
                    source_code = f.read()
            except Exception as e:
                alert_error(self.tr(f"Failed to read source file: {e}"))
                return
                
            import re
            new_source = re.sub(
                r'(self\.name\s*=\s*)(self\.tr\(\s*)?(["\'])(.*?)\3(\))?',
                lambda m: f'{m.group(1)}{m.group(2) or ""}{m.group(3)}{m.group(4)}_copy{m.group(3)}{m.group(5) or ""}',
                source_code
            )
            
            base_name = os.path.basename(python_file)
            name_root, ext = os.path.splitext(base_name)
            
            new_file_name = f"{name_root}{ext}"
            counter = 1
            while os.path.exists(os.path.join(og.task_manager.task_folder, new_file_name)):
                new_file_name = f"{name_root}_{counter}{ext}"
                counter += 1
                
            target_path = os.path.join(og.task_manager.task_folder, new_file_name)
            
            try:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(new_source)
                self.refresh_dropdown()
                
                for i in range(self.task_dropdown.count()):
                    if self.task_dropdown.itemData(i) == target_path:
                        self.task_dropdown.setCurrentIndex(i)
                        break
                        
                og.task_manager.load_single_user_task(target_path)
                from ok.gui.util.app import show_info_bar
                show_info_bar(self.window(), self.tr("Task copied successfully."), title=self.tr("Success"))
            except Exception as e:
                alert_error(f"Error copying task: {e}")

    def show_export_dialog(self):
        from qfluentwidgets import MessageBoxBase, LineEdit, SubtitleLabel
        from ok.gui.util.Alert import alert_error
        from ok.gui.tasks.ScriptPackager import get_task_files, load_manifest, export_script, validate_filename

        task_files = get_task_files()
        if not task_files:
            alert_error(self.tr("No tasks to export."))
            return

        manifest = load_manifest()
        parent = self

        class ExportScriptDialog(MessageBoxBase):
            def __init__(self, p=None):
                super().__init__(p)
                self.titleLabel = SubtitleLabel(parent.tr('Export Script'), self)
                self.viewLayout.addWidget(self.titleLabel)

                # Task checkboxes
                self.task_label = BodyLabel(parent.tr('Select tasks to export:'), self)
                self.viewLayout.addWidget(self.task_label)

                self.checkboxes = []
                for tf in task_files:
                    cb = CheckBox(os.path.splitext(tf)[0], self)
                    cb.setChecked(True)
                    cb.setProperty('filename', tf)
                    self.viewLayout.addWidget(cb)
                    self.checkboxes.append(cb)

                # File name
                self.file_name_label = BodyLabel(parent.tr('File Name:'), self)
                self.viewLayout.addWidget(self.file_name_label)
                self.file_name_input = LineEdit(self)
                self.file_name_input.setPlaceholderText(parent.tr('English, numbers and valid filename chars only'))
                self.file_name_input.setText(manifest.get('file_name', ''))
                self.viewLayout.addWidget(self.file_name_input)

                # Script name
                self.script_name_label = BodyLabel(parent.tr('Script Name:'), self)
                self.viewLayout.addWidget(self.script_name_label)
                self.script_name_input = LineEdit(self)
                self.script_name_input.setPlaceholderText(parent.tr('Display name for the script'))
                self.script_name_input.setText(manifest.get('script_name', ''))
                self.viewLayout.addWidget(self.script_name_input)

                # Version
                self.version_label = BodyLabel(parent.tr('Version:'), self)
                self.viewLayout.addWidget(self.version_label)
                self.version_input = LineEdit(self)
                self.version_input.setPlaceholderText('1.0.0')
                self.version_input.setText(manifest.get('version', '1.0.0'))
                self.viewLayout.addWidget(self.version_input)

                self.yesButton.setText(parent.tr('Export'))
                self.cancelButton.setText(parent.tr('Cancel'))
                self.widget.setMinimumWidth(400)

        dialog = ExportScriptDialog(self.window())

        if dialog.exec():
            file_name = dialog.file_name_input.text().strip()
            script_name = dialog.script_name_input.text().strip()
            version = dialog.version_input.text().strip()

            if not validate_filename(file_name):
                alert_error(self.tr('Invalid file name. Use English letters, numbers, underscores, hyphens only.'))
                return

            if not script_name:
                alert_error(self.tr('Script name is required.'))
                return

            selected = [cb.property('filename') for cb in dialog.checkboxes if cb.isChecked()]
            if not selected:
                alert_error(self.tr('Please select at least one task to export.'))
                return

            success, message, output_path = export_script(selected, file_name, script_name, version)
            if success:
                from ok.gui.util.app import show_info_bar
                show_info_bar(self.window(), self.tr('Script exported successfully to Downloads folder.'), title=self.tr('Success'))
                # Open Explorer and select the file
                import subprocess
                subprocess.Popen(f'explorer /select,"{os.path.normpath(output_path)}"')
            else:
                alert_error(f"{self.tr('Export failed')}: {message}")

    def show_import_dialog(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self, self.tr('Select Script File'), '',
            self.tr('OKScript Files (*.okscript);;All Files (*)')
        )

        if not file_path:
            return

        self._show_import_warning(file_path)

    def _show_import_warning(self, file_path):
        from qfluentwidgets import MessageBoxBase, SubtitleLabel, BodyLabel, CheckBox
        from PySide6.QtCore import QTimer
        
        class ImportWarningDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.titleLabel = SubtitleLabel(self.tr('Warning'), self)
                self.viewLayout.addWidget(self.titleLabel)

                warning_text = self.tr('Make sure that you trust the script publisher, unverified script can and not limited to steal your account/ data money, destroy your data, harm/ controlling your computer.')
                self.warning_label = BodyLabel(warning_text, self)
                self.warning_label.setWordWrap(True)
                self.warning_label.setStyleSheet("color: red; font-weight: bold;")
                self.viewLayout.addWidget(self.warning_label)
                
                self.check_box = CheckBox(self.tr('I understand the risks and want to import this script.'), self)
                self.viewLayout.addWidget(self.check_box)

                self.countdown = 15
                self.yesButton.setText(self.tr('Confirm') + f' ({self.countdown})')
                self.yesButton.setEnabled(False)
                
                self.cancelButton.setText(self.tr('Cancel'))
                self.widget.setMinimumWidth(400)
                
                self.timer = QTimer(self)
                self.timer.timeout.connect(self.update_countdown)
                self.timer.start(1000)
                
                self.check_box.stateChanged.connect(self.check_state_changed)
                
            def update_countdown(self):
                self.countdown -= 1
                if self.countdown > 0:
                    self.yesButton.setText(self.tr('Confirm') + f' ({self.countdown})')
                else:
                    self.timer.stop()
                    self.yesButton.setText(self.tr('Confirm'))
                    self.check_state_changed()

            def check_state_changed(self):
                if self.countdown <= 0 and self.check_box.isChecked():
                    self.yesButton.setEnabled(True)
                else:
                    self.yesButton.setEnabled(False)
                    
        dialog = ImportWarningDialog(self.window())
        if dialog.exec():
            self._do_import(file_path)

    def _do_import(self, file_path):
        from ok.gui.util.Alert import alert_error
        from ok.gui.tasks.ScriptPackager import import_script

        success, message, import_folder = import_script(file_path)
        if success:
            from ok.gui.util.app import show_info_bar
            show_info_bar(self.window(), message, title=self.tr('Success'))
            # Load the imported tasks
            og.task_manager.load_import_folder(import_folder)
        else:
            alert_error(f"{self.tr('Import failed')}: {message}")
