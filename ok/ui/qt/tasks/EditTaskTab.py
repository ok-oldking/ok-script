import os
import re
import time

from PySide6.QtCore import QFileSystemWatcher, QUrl, Signal, QCoreApplication
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QPainter, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPlainTextEdit, QScrollArea, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.dialogs import Dialog, confirm
from ok.ui.qt.kit.feedback import show_toast
from ok.ui.qt.kit.icons import icon
from ok.ui.qt.kit.inputs import ComboBox, NumberBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme
from ok.ui.qt.tasks.PythonHighlighter import PythonHighlighter
from ok.ui.qt.tasks.TemplateFactory import TemplateFactory, get_templates, filter_templates
from ok.util.explorer import reveal_in_explorer
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

PAGE_MARGINS = (28, 18, 28, 20)
PAGE_SPACING = 16
LIBRARY_WIDTH = 280


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """A Python editor with a line number gutter and 4-space (de)indentation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("codeEditor")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.line_number_area = LineNumberArea(self)
        self.error_line_number = -1

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        theme.changed.connect(self.line_number_area.update)

        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 20 + self.fontMetrics().horizontalAdvance('9') * max(digits, 3)

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
        painter.setFont(self.font())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        current = self.textCursor().blockNumber()
        font_metrics = self.fontMetrics()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if (block_number + 1) == self.error_line_number:
                    painter.setPen(theme.color("danger"))
                elif block_number == current:
                    painter.setPen(theme.color("text_secondary"))
                else:
                    painter.setPen(theme.color("text_disabled"))
                painter.drawText(0, int(top), self.line_number_area.width() - 12, int(font_metrics.height()),
                                 Qt.AlignRight, str(block_number + 1))

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def set_error_line(self, line_number):
        self.error_line_number = line_number
        self.line_number_area.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                start_block = self.document().findBlock(cursor.selectionStart()).blockNumber()
                end_block = self.document().findBlock(cursor.selectionEnd()).blockNumber()

                cursor.beginEditBlock()
                for i in range(start_block, end_block + 1):
                    block = self.document().findBlockByNumber(i)
                    block_cursor = self.textCursor()
                    block_cursor.setPosition(block.position())
                    block_cursor.insertText("    ")
                cursor.endEditBlock()
                return
            else:
                cursor.insertText("    ")
                return
        elif event.key() == Qt.Key_Backtab:
            cursor = self.textCursor()
            start_block = self.document().findBlock(cursor.selectionStart()).blockNumber()
            end_block = self.document().findBlock(cursor.selectionEnd()).blockNumber()

            cursor.beginEditBlock()
            for i in range(start_block, end_block + 1):
                block = self.document().findBlockByNumber(i)
                block_cursor = self.textCursor()
                block_cursor.setPosition(block.position())

                line_text = block.text()
                spaces = 0
                for c in line_text:
                    if c == ' ' and spaces < 4:
                        spaces += 1
                    else:
                        break
                if spaces > 0:
                    block_cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, spaces)
                    block_cursor.removeSelectedText()
            cursor.endEditBlock()
            return

        super().keyPressEvent(event)
        # Repaint the gutter so the current line number follows the cursor.
        self.line_number_area.update()


def _form_row(dialog, label, widget):
    dialog.body.addWidget(Label(label, "strong", dialog.panel))
    dialog.body.addWidget(widget)


class EditTaskTab(QWidget):
    reload_done = Signal(object, str, bool, object)

    @property
    def all_templates(self):
        if self._all_templates is None:
            self._all_templates = get_templates()
        return self._all_templates

    def __init__(self):
        super().__init__()
        self.setObjectName("EditTaskTab")
        self.task = None
        self.python_file = None
        self._all_templates = None  # parsed on first use; it costs ~50ms at startup
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self.on_file_changed)
        self.reload_done.connect(self._on_reload_done)
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

                if self.editor.document().isModified() and not confirm(
                        self, self.tr('File Changed Externally'),
                        self.tr("The file was modified externally. Do you want to overwrite your unsaved changes?")):
                    return

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
            self._set_file_actions(True)
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
            self._set_file_actions(False)
            self.editor.clear()
            self.editor.document().setModified(False)
            self._update_file_watcher()
        self._update_file_label()
        self.editor.setFocus()

    def _set_file_actions(self, has_file):
        self.save_action.setVisible(has_file)
        self.delete_action.setVisible(has_file)

    # --- layout -------------------------------------------------------------------

    def init_ui(self):
        self.page_layout = QHBoxLayout(self)
        self.page_layout.setContentsMargins(*PAGE_MARGINS)
        self.page_layout.setSpacing(PAGE_SPACING)

        # Left: the template library, a searchable tree of insertable calls.
        library = Card(self)
        library.setFixedWidth(LIBRARY_WIDTH)
        self.template_panel = QVBoxLayout(library)
        self.template_panel.setContentsMargins(12, 14, 12, 12)
        self.template_panel.setSpacing(10)
        library_title = QHBoxLayout()
        library_title.addWidget(Label(self.tr("Templates"), "subtitle", library))
        library_title.addStretch(1)
        self.template_panel.addLayout(library_title)
        self.template_panel.addWidget(Label(self.tr("Click a call to insert it at the cursor."), "caption", library,
                                            word_wrap=True))

        self.search_filter = QLineEdit(library)
        self.search_filter.setPlaceholderText(self.tr("Search templates..."))
        self.search_filter.setClearButtonEnabled(True)
        self.search_filter.addAction(icon("search"), QLineEdit.LeadingPosition)
        self.search_filter.textChanged.connect(self.on_search_changed)
        self.template_panel.addWidget(self.search_filter)

        self.template_list = QTreeWidget(library)
        self.template_list.setObjectName("templateTree")
        self.template_list.setHeaderHidden(True)
        self.template_list.setIndentation(14)
        self.template_list.setRootIsDecorated(True)
        self.template_list.setFrameShape(QFrame.NoFrame)
        # Items act as buttons: a click inserts, nothing stays selected.
        self.template_list.setSelectionMode(QTreeWidget.NoSelection)
        self.template_list.setFocusPolicy(Qt.NoFocus)
        self._populate_template_list("")
        self.template_list.itemClicked.connect(self.on_template_clicked)
        self.template_list.itemExpanded.connect(self.on_item_expanded_collapsed)
        self.template_list.itemCollapsed.connect(self.on_item_expanded_collapsed)
        self._last_toggled_time = 0
        self.template_panel.addWidget(self.template_list, 1)
        self.page_layout.addWidget(library)

        # Right: header, editor and error banner.
        self.editor_layout = QVBoxLayout()
        self.editor_layout.setSpacing(0)
        self.right_container = QWidget()
        self.right_container_layout = QVBoxLayout(self.right_container)
        self.right_container_layout.setContentsMargins(0, 0, 0, 0)
        self.right_container_layout.setSpacing(12)

        self.editor = CodeEditor()
        self.editor.cursorPositionChanged.connect(self.editor.line_number_area.update)
        self.highlighter = PythonHighlighter(self.editor.document())

        self.top_layout = QHBoxLayout()
        self.top_layout.setSpacing(8)
        self.choose_task_label = Label(QCoreApplication.translate("MainWindow", "Script"), "display", self)
        self.task_dropdown = ComboBox()
        self.task_dropdown.setMinimumWidth(240)
        self.task_dropdown.currentIndexChanged.connect(self.on_task_selected)

        # File menu: save, create, copy, delete, export and import.
        self.menu = QMenu(self)
        self.save_action = self._menu_action("Save", "check", self.save_code, QKeySequence.Save)
        self.create_action = self._menu_action("Create Task", "plus", self.create_task)
        self.copy_action = self._menu_action("Copy Task", "layers", self.copy_task)
        self.delete_action = self._menu_action("Delete Task", "trash", self.delete_task)
        self.menu.addSeparator()
        self.export_action = self._menu_action("Export Script", "share", self.show_export_dialog)
        self.import_action = self._menu_action("Import Script", "download", self.show_import_dialog)
        # Ctrl+S works anywhere on the page, also while the menu is closed.
        self.addAction(self.save_action)

        self.file_button = Button(self.tr("File"), "file", "subtle")
        self.file_button.clicked.connect(lambda: self.menu.exec(
            self.file_button.mapToGlobal(self.file_button.rect().bottomLeft())))

        self.top_layout.addWidget(self.choose_task_label)
        self.top_layout.addSpacing(8)
        self.top_layout.addWidget(self.task_dropdown)
        self.top_layout.addWidget(self.file_button)
        self.top_layout.addStretch(1)

        self.tools_layout = QHBoxLayout()
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(8)

        self.guide_button = Button(self.tr("Guide"), "help", "subtle")
        self.guide_button.clicked.connect(self.open_guide)
        self.tools_layout.addWidget(self.guide_button)

        self.record_button = Button(self.tr("Record"), "camera")
        self.record_button.clicked.connect(self.toggle_record)
        self.tools_layout.addWidget(self.record_button)

        self.run_button = Button(self.tr("Run"), "play", "primary")
        self.run_button.clicked.connect(self.run_task)
        self.tools_layout.addWidget(self.run_button)

        self.top_layout.addLayout(self.tools_layout)

        self._set_file_actions(False)

        editor_card = Card(self)
        editor_card_layout = QVBoxLayout(editor_card)
        editor_card_layout.setContentsMargins(0, 0, 0, 0)
        editor_card_layout.setSpacing(0)
        self.file_label = Label("", "caption", editor_card)
        self.file_label.setObjectName("editorFileBar")
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        editor_card_layout.addWidget(self.file_label)
        editor_card_layout.addWidget(self.editor, 1)
        self.editor.modificationChanged.connect(self._update_file_label)

        self.error_label = Label("", "mono", self, word_wrap=True)
        self.error_label.setObjectName("errorBanner")
        self.error_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error_label.setVisible(False)

        self.right_container_layout.addLayout(self.top_layout)
        self.right_container_layout.addWidget(editor_card, 1)
        self.right_container_layout.addWidget(self.error_label)

        # Empty state: no scripts in the task folder yet.
        self.empty_widget = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_widget)
        self.empty_layout.setAlignment(Qt.AlignCenter)
        self.empty_layout.setSpacing(8)
        empty_icon = QLabel(self.empty_widget)
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_icon.setPixmap(icon("code").pixmap(QSize(40, 40), self.devicePixelRatioF()))
        self.empty_layout.addWidget(empty_icon)
        empty_title = Label(self.tr("No scripts yet"), "subtitle", self.empty_widget)
        empty_title.setAlignment(Qt.AlignCenter)
        self.empty_layout.addWidget(empty_title)
        empty_hint = Label(self.tr("Create a task from scratch or copy an existing one to start."), "secondary",
                           self.empty_widget)
        empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_layout.addWidget(empty_hint)
        self.empty_layout.addSpacing(8)

        self.empty_buttons_layout = QHBoxLayout()
        self.empty_buttons_layout.setAlignment(Qt.AlignCenter)
        self.empty_buttons_layout.setSpacing(8)
        self.center_copy_button = Button(self.tr("Copy Task"), "layers")
        self.center_copy_button.clicked.connect(self.copy_task)
        self.empty_buttons_layout.addWidget(self.center_copy_button)
        self.center_create_button = Button(self.tr("Create New Task"), "plus", "primary")
        self.center_create_button.clicked.connect(self.create_task)
        self.empty_buttons_layout.addWidget(self.center_create_button)
        self.empty_layout.addLayout(self.empty_buttons_layout)

        self.editor_layout.addWidget(self.right_container)
        self.editor_layout.addWidget(self.empty_widget)

        self.page_layout.addLayout(self.editor_layout, 1)
        theme.install(self)

        self.refresh_dropdown()

    def _menu_action(self, text, icon_name, slot, shortcut=None):
        action = QAction(icon(icon_name), self.tr(text), self)
        if shortcut is not None:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda _checked=False: slot())
        self.menu.addAction(action)
        return action

    def _update_file_label(self, *_args):
        if not self.python_file:
            self.file_label.setText("")
            return
        modified = "  ●" if self.editor.document().isModified() else ""
        self.file_label.setText(f"{self.python_file}{modified}")

    def _update_error_display(self):
        if self.python_file and self.python_file in og.task_manager.task_errors:
            error_msg = og.task_manager.task_errors[self.python_file]
            self.error_label.setText(error_msg)
            self.error_label.setVisible(True)

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
            groups.setdefault(t.get('category', 'Other'), []).append(t)

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
                display_name = f"{category_translations.get(cname, cname)}  ({len(templates)})"
                parent_item = QTreeWidgetItem([display_name])
                parent_item.setFlags(parent_item.flags() & ~Qt.ItemIsSelectable)
                font = parent_item.font(0)
                font.setWeight(font.Weight.DemiBold)
                parent_item.setFont(0, font)
                self.template_list.addTopLevelItem(parent_item)

                for t in templates:
                    item = QTreeWidgetItem([self.tr(t['template_name'])])
                    item.setData(0, Qt.UserRole, t)
                    item.setToolTip(0, t.get('full_doc', t.get('doc', '')))
                    parent_item.addChild(item)

        # Searching shows every match; browsing starts collapsed.
        if query:
            self.template_list.expandAll()
        else:
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
        self._update_file_label()

    def _ask_save_changes(self):
        """``"save"``, ``"discard"`` or ``"cancel"`` for unsaved edits."""
        dialog = Dialog(self, self.tr('Save Changes'),
                        self.tr("The current task has unsaved changes. Do you want to save them?"),
                        ok_text=self.tr('Save'))
        try:
            dialog.add_button("discard", self.tr("Don't Save"))
            dialog.exec()
            return {"ok": "save", "discard": "discard"}.get(dialog.choice, "cancel")
        finally:
            dialog.deleteLater()

    def on_task_selected(self, index):
        if hasattr(self, 'editor') and self.editor.document().isModified() and self.python_file:
            reply = self._ask_save_changes()
            if reply == "save":
                if not self.save_code():
                    self._revert_dropdown_index()
                    return
            elif reply == "cancel":
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
                self._set_file_actions(True)
                with open(self.python_file, 'r', encoding='utf-8') as f:
                    self.editor.setPlainText(f.read())
                self.editor.document().setModified(False)
                self._update_file_watcher()
            else:
                self._set_file_actions(False)
                self.editor.clear()
                self.editor.document().setModified(False)
                self._update_file_watcher()
            self._update_error_display()
            self._update_file_label()
            self._current_dropdown_index = index

    def _revert_dropdown_index(self):
        if hasattr(self, '_current_dropdown_index'):
            self.task_dropdown.blockSignals(True)
            self.task_dropdown.setCurrentIndex(self._current_dropdown_index)
            self.task_dropdown.blockSignals(False)

    def run_task(self):
        self.save_code(silent=True, on_reloaded=self._run_reloaded_task)

    def _run_reloaded_task(self):
        if self.task is not None:
            self._switch_to_task_tab()
            og.app.start_controller.start(self.task)

    def _switch_to_task_tab(self):
        """Switch to the tab that contains the current task."""
        if not self.task:
            return
        try:
            main_window = og.main_window
            if not main_window.show_task(self.task) and main_window.tasks_page is not None:
                main_window.switch_to(main_window.tasks_page)
        except Exception as e:
            logger.error(f"Error switching tab: {e}")

    def open_guide(self):
        QDesktopServices.openUrl(QUrl("https://github.com/ok-oldking/ok-py"))

    def _set_recording(self, recording):
        self.run_button.setText(self.tr("Stop") if recording else self.tr("Run"))
        self.run_button.set_icon("pause" if recording else "play")
        self.run_button.clicked.disconnect()
        self.run_button.clicked.connect(self.toggle_record if recording else self.run_task)
        self.record_button.setVisible(not recording)

    def toggle_record(self):
        from .RecordScript import recorder

        if not recorder.is_recording:
            dialog = Dialog(self, self.tr('Warning'), self.tr("Record will override the current script logic. Continue?"),
                            ok_text=self.tr('OK'), cancel_text=self.tr('Cancel'))
            loop_combo = ComboBox([self.tr("No loop"), self.tr("Loop x times"), self.tr("Loop infinitely")],
                                  dialog.panel)
            loop_count_input = NumberBox(10, 1, 999999, parent=dialog.panel)
            loop_count_input.setVisible(False)

            def on_combo_changed(index):
                loop_count_input.setVisible(index == 1)
                dialog._fit()

            loop_combo.currentIndexChanged.connect(on_combo_changed)
            dialog.body.addWidget(loop_combo)
            dialog.body.addWidget(loop_count_input)
            try:
                accepted = dialog.exec()
                loop_type, loop_count = loop_combo.currentIndex(), loop_count_input.value()
            finally:
                dialog.deleteLater()
            if accepted:
                self._record_loop_type = loop_type
                if loop_type == 1:
                    self._record_loop_count = loop_count

                hwnd_name = og.device_manager.get_hwnd_name()
                from ok.ui.qt.util.Alert import alert_info
                alert_msg = self.tr("Recording will start when window '{hwnd_name}' becomes active.")
                alert_info(alert_msg.replace("{hwnd_name}", hwnd_name))

                recorder.start(hwnd_name)
                self._set_recording(True)
        else:
            init_code, run_code = recorder.stop()

            loop_type = getattr(self, '_record_loop_type', 0)
            if loop_type in (1, 2):
                header = f"for _ in range({getattr(self, '_record_loop_count', 1)}):" if loop_type == 1 \
                    else "while True:"
                run_code_lines = [line for line in run_code.strip('\n').split('\n') if line.strip()]
                body = ["    " + line for line in run_code_lines] or ["    pass"]
                run_code = "\n".join([header, *body])

            self._set_recording(False)
            self._replace_run_block(init_code, run_code)

    def _replace_run_block(self, init_code, run_code):
        from ok.core.script_editing import merge_recorded_code
        v_scroll = self.editor.verticalScrollBar().value()
        self.editor.setPlainText(merge_recorded_code(
            self.editor.toPlainText(), init_code, run_code))
        self.editor.verticalScrollBar().setValue(v_scroll)

    def _success(self, message):
        show_toast(self, message, tone="success")

    def save_code(self, silent=False, on_reloaded=None):
        code = self.editor.toPlainText()
        if self.python_file:
            try:
                with open(self.python_file, 'w', encoding='utf-8') as f:
                    f.write(code)
                self._last_mtime = os.path.getmtime(self.python_file)
                if self.task:
                    path = self.python_file
                    job = og.task_manager.reload_task_code(self.task)
                    self.editor.document().setModified(False)
                    job.future.add_done_callback(
                        lambda _: self.reload_done.emit(job, path, silent, on_reloaded))
                    return True
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
                    self._success(self.tr("Task rebuilt successfully."))
                if on_reloaded is not None:
                    on_reloaded()
                return True
            except Exception as e:
                from ok.ui.qt.util.Alert import alert_error
                alert_error(f"{self.tr('Failed to save')}: {e}")
                return False
        return False

    def _on_reload_done(self, job, path, silent, on_reloaded):
        try:
            job.future.result()
        except Exception as error:
            if path == self.python_file:
                self._update_error_display()
            from ok.ui.qt.util.Alert import alert_error
            alert_error(str(error))
            return
        if path != self.python_file:
            return
        self.task = next((task for task, data in og.task_manager.task_map.items()
                          if data[0] == path), None)
        self._update_error_display()
        if not silent:
            self._success(self.tr('Task rebuilt successfully.'))
        if on_reloaded is not None:
            on_reloaded()

    def delete_task(self):
        if not self.python_file:
            return

        if confirm(self, self.tr('Confirm Delete'),
                   self.tr("Are you sure you want to delete {}?").format(os.path.basename(self.python_file)),
                   ok_text=self.tr("Delete Task"), danger=True):
            try:
                if self.task:
                    og.task_manager.delete_task(self.task)
                else:
                    if os.path.exists(self.python_file):
                        os.remove(self.python_file)

                self._success(self.tr("Task deleted successfully."))
                self.python_file = None
                self.task = None
                self.editor.clear()
                self.editor.document().setModified(False)
                self.refresh_dropdown()
            except Exception as e:
                from ok.ui.qt.util.Alert import alert_error
                alert_error(self.tr("Error deleting task: {error}").format(error=e))

    def on_item_expanded_collapsed(self, item):
        self._last_toggled_time = time.time()

    def on_template_clicked(self, item, column):
        template = item.data(0, Qt.UserRole)
        if not template:
            # If the item was expanded/collapsed natively by the chevron just now, don't revert it
            if time.time() - getattr(self, '_last_toggled_time', 0) < 0.1:
                return
            item.setExpanded(not item.isExpanded())
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

            if line_text.strip():
                # If there is already code on this line, insert a new line with indentation
                final_text = f"\n{indent_str}{code_to_insert}\n"
            else:
                # If the line is empty, just insert the code with correct indentation
                if len(line_text) < indent_spaces:
                    final_text = (' ' * (indent_spaces - len(line_text))) + code_to_insert + "\n"
                else:
                    final_text = code_to_insert + "\n"

            cursor.insertText(final_text)
            self.editor.setFocus()

    def create_task(self):
        from ok.ui.qt.util.Alert import alert_error

        dialog = Dialog(self, self.tr('Create Task'), ok_text=self.tr('Confirm'), cancel_text=self.tr('Cancel'))
        class_name_input = QLineEdit(dialog.panel)
        class_name_input.setPlaceholderText("MyTask")
        task_name_input = QLineEdit(dialog.panel)
        task_desc_input = QLineEdit(dialog.panel)
        _form_row(dialog, self.tr("Class Name (English only)"), class_name_input)
        _form_row(dialog, self.tr("Task Name"), task_name_input)
        _form_row(dialog, self.tr("Description (Optional)"), task_desc_input)
        try:
            accepted = dialog.exec()
            class_name = class_name_input.text().strip()
            task_name = task_name_input.text().strip()
            task_desc = task_desc_input.text().strip()
        finally:
            dialog.deleteLater()
        if not accepted:
            return

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
            self._success(self.tr("Task created successfully."))
        except Exception as e:
            alert_error(self.tr("Error creating task: {error}").format(error=e))

    def copy_task(self):
        from ok.ui.qt.util.Alert import alert_error
        import inspect

        tasks = []
        for task in og.task_manager.task_executor.onetime_tasks + og.task_manager.task_executor.trigger_tasks:
            if task not in tasks:
                tasks.append(task)
        for task in og.task_manager.task_map.keys():
            if task not in tasks:
                tasks.append(task)

        dialog = Dialog(self, self.tr('Copy Task'), ok_text=self.tr('Confirm'), cancel_text=self.tr('Cancel'))
        task_dropdown = ComboBox(parent=dialog.panel)
        task_dropdown.setPlaceholderText(self.tr("Select task to copy..."))
        for task in tasks:
            name = getattr(task, 'name', task.__class__.__name__)
            class_name = task.__class__.__name__
            display_text = f"{name} ({class_name})" if name != class_name else name
            task_dropdown.addItem(display_text, userData=task)
        dialog.body.addWidget(task_dropdown)
        try:
            accepted = dialog.exec()
            selected_task = task_dropdown.currentData()
        finally:
            dialog.deleteLater()
        if not accepted or not selected_task:
            return

        python_file, _ = og.task_manager.task_map.get(selected_task, (None, None))
        if not python_file or not os.path.exists(python_file):
            try:
                python_file = inspect.getsourcefile(selected_task.__class__)
            except TypeError:
                python_file = None

        if not python_file or not os.path.exists(python_file):
            alert_error(self.tr("Could not find source file for {}").format(selected_task.__class__.__name__))
            return

        try:
            with open(python_file, "r", encoding="utf-8") as f:
                source_code = f.read()
        except Exception as e:
            alert_error(self.tr("Failed to read source file: {}").format(e))
            return

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
            self._success(self.tr("Task copied successfully."))
        except Exception as e:
            alert_error(self.tr("Error copying task: {error}").format(error=e))

    def show_export_dialog(self):
        from ok.ui.qt.util.Alert import alert_error
        from ok.ui.qt.tasks.ScriptPackager import get_task_files, load_manifest, export_script, validate_filename

        task_files = get_task_files()
        if not task_files:
            alert_error(self.tr("No tasks to export."))
            return

        manifest = load_manifest()
        dialog = Dialog(self, self.tr('Export Script'), ok_text=self.tr('Export'), cancel_text=self.tr('Cancel'),
                        width=480)
        panel = dialog.panel

        # Task checkboxes, scrolling when there are many.
        dialog.body.addWidget(Label(self.tr('Select tasks to export:'), "strong", panel))
        checks = QWidget()
        checks.setObjectName("scrollContents")
        checks_layout = QVBoxLayout(checks)
        checks_layout.setContentsMargins(0, 0, 0, 0)
        checks_layout.setSpacing(6)
        checkboxes = []
        for tf in task_files:
            cb = QCheckBox(os.path.splitext(tf)[0], checks)
            cb.setChecked(True)
            cb.setProperty('filename', tf)
            checks_layout.addWidget(cb)
            checkboxes.append(cb)
        scroll = QScrollArea(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(checks)
        scroll.setFixedHeight(min(200, 28 * len(task_files) + 4))
        dialog.body.addWidget(scroll)

        file_name_input = QLineEdit(manifest.get('file_name', ''), panel)
        file_name_input.setPlaceholderText(self.tr('English, numbers and valid filename chars only'))
        script_name_input = QLineEdit(manifest.get('script_name', ''), panel)
        script_name_input.setPlaceholderText(self.tr('Display name for the script'))
        version_input = QLineEdit(manifest.get('version', '1.0.0'), panel)
        version_input.setPlaceholderText('1.0.0')
        _form_row(dialog, self.tr('File Name:'), file_name_input)
        _form_row(dialog, self.tr('Script Name:'), script_name_input)
        _form_row(dialog, self.tr('Version:'), version_input)

        try:
            accepted = dialog.exec()
            file_name = file_name_input.text().strip()
            script_name = script_name_input.text().strip()
            version = version_input.text().strip()
            selected = [cb.property('filename') for cb in checkboxes if cb.isChecked()]
        finally:
            dialog.deleteLater()
        if not accepted:
            return

        if not validate_filename(file_name):
            alert_error(self.tr('Invalid file name. Use English letters, numbers, underscores, hyphens only.'))
            return

        if not script_name:
            alert_error(self.tr('Script name is required.'))
            return

        if not selected:
            alert_error(self.tr('Please select at least one task to export.'))
            return

        success, message, output_path = export_script(selected, file_name, script_name, version)
        if success:
            self._success(self.tr('Script exported successfully to Downloads folder.'))
            reveal_in_explorer(output_path)
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
        from ok.ui.qt.widget.ImportWarningDialog import ImportWarningDialog
        dialog = ImportWarningDialog(self.window())
        try:
            if dialog.exec():
                self._do_import(file_path)
        finally:
            dialog.deleteLater()

    def _do_import(self, file_path):
        from ok.ui.qt.util.Alert import alert_error
        from ok.core.plugin_staging import install_or_stage_plugin
        try:
            result = install_or_stage_plugin(file_path)
            message = result['message']
            if result['restart_required']:
                message = QCoreApplication.translate('PluginTab', 'Restart the application to apply plugin changes.')
            self._success(message)
            if not result['restart_required']:
                og.task_manager.load_import_folder(result['folder'])
        except Exception as error:
            alert_error(f"{self.tr('Import failed')}: {error}")
