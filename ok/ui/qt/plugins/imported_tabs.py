"""Host-owned task/custom pages for imported plugins."""

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import FluentIcon, NavigationItemPosition
from shiboken6 import isValid

from ok import Logger, og
from ok.core.plugins import import_plugin_class
from ok.ui.qt.common.icons import resolve_icon
from ok.ui.qt.tasks.OneTimeTaskTab import OneTimeTaskTab
from ok.ui.qt.widget.Tab import Tab

logger = Logger.get_logger(__name__)


class ImportedTaskTab(OneTimeTaskTab):
    def __init__(self, namespace, name):
        self.namespace = namespace
        super().__init__(is_standalone=False, group_name=name)
        self.imported_file_name = namespace

    def refresh_ui(self):
        from ok.task.task import TriggerTask
        from ok.ui.qt.tasks.TaskCard import TaskCard

        for card in self.card_widgets:
            self.remove_task_card(card)
            card.dispose()
            card.deleteLater()
        self.card_widgets.clear()
        entry = og.task_manager.imported_scripts.get(self.namespace, {})
        self.tasks = [task for task in entry.get('tasks', ()) if getattr(task, 'visible', True)]
        for task in self.tasks:
            card = TaskCard(task, not isinstance(task, TriggerTask))
            self.card_widgets.append(card)
            self.add_task_card(card)


def _dispose_widget(widget):
    if not isValid(widget):
        return
    try:
        cleanup = getattr(widget, 'dispose', None) or getattr(widget, 'stop_worker', None)
        if callable(cleanup):
            cleanup()
    except Exception as error:
        logger.error('Failed to dispose plugin page', error)


class ImportedPluginPage(Tab):
    """Adapt an imported task's page factory without exposing MainWindow internals."""

    def __init__(self, task):
        super().__init__()
        self.page = None
        try:
            page = task.create_import_page(self.view)
            if not isinstance(page, QWidget) or page.isWindow():
                raise TypeError('create_import_page must return an embedded QWidget')
            self.page = page
            self.vBoxLayout.addWidget(page, 1)
            self.name = task.name
            self.icon = task.group_icon
        except Exception:
            self.deleteLater()
            raise

    def dispose(self):
        if self.page is not None:
            _dispose_widget(self.page)


class ImportedTabs(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.custom_tabs = {}
        self._entries = {}
        self._refreshing = False
        self._closed = False
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.dispose)

    def _remove(self, namespace):
        widgets = self.custom_tabs.pop(namespace, [])
        task_tab = self.window.imported_tabs.pop(namespace, None)
        if task_tab is not None:
            widgets.append(task_tab)
        for widget in widgets:
            if not isValid(widget):
                continue
            _dispose_widget(widget)
            self.window.navigationInterface.removeWidget(widget.objectName())
            self.window.stackedWidget.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self._entries.pop(namespace, None)

    def _add(self, widget, name, icon):
        if not widget.objectName():
            widget.setObjectName(f'plugin_{id(widget)}')
        self.window.addSubInterface(
            widget, resolve_icon(icon), self.window.app.tr(name),
            position=NavigationItemPosition.SCROLL,
        )

    def refresh(self):
        if self._closed:
            return
        if self._refreshing:
            QTimer.singleShot(0, self.refresh)
            return
        self._refreshing = True
        try:
            entries = og.task_manager.imported_scripts
            for namespace in tuple(self._entries):
                entry = entries.get(namespace)
                state = self._state(entry) if entry is not None else None
                if self._entries[namespace] != state:
                    self._remove(namespace)
            for namespace, entry in tuple(entries.items()):
                if namespace not in self._entries:
                    self._entries[namespace] = self._state(entry)
                    self._create(namespace, entry)
            self.window.update_navigation_width()
        finally:
            self._refreshing = False

    @staticmethod
    def _state(entry):
        return (id(entry), tuple(id(task) for task in entry.get('tasks', ())
                                 if getattr(task, 'visible', True)))

    def _create(self, namespace, entry):
        from ok.core.plugin_staging import finish_plugin_update
        tasks = [task for task in entry.get('tasks', ()) if getattr(task, 'visible', True)]
        pages = []
        errors = entry.setdefault('tab_errors', {})
        specifications = entry.get('custom_tabs', [])
        for module, name in specifications:
            widget = None
            try:
                cls = import_plugin_class(entry['folder'], (module, name))
                widget = cls()
                if not isinstance(widget, QWidget):
                    raise TypeError('Plugin custom_tabs must create QWidgets')
                widget.executor = self.window.executor
                self._add(widget, getattr(widget, 'name', entry['script_name']),
                          getattr(widget, 'icon', FluentIcon.APPLICATION))
                pages.append(widget)
            except Exception as error:
                if isinstance(widget, QWidget):
                    _dispose_widget(widget)
                    widget.deleteLater()
                errors[f'{module}.{name}'] = str(error)
                logger.error(f'Failed to load plugin tab {namespace}/{module}.{name}', error)

        # Existing packages such as Workshop already expose a task-owned page.
        # Keep its shared task runtime, and let the host own the Qt container.
        if not specifications:
            for task in tasks:
                if not callable(getattr(task, 'create_import_page', None)):
                    continue
                widget = None
                try:
                    widget = ImportedPluginPage(task)
                    self._add(widget, widget.name, widget.icon)
                    pages.append(widget)
                except Exception as error:
                    if widget is not None:
                        widget.deleteLater()
                    errors[type(task).__name__] = str(error)
                    logger.error(f'Failed to create plugin page {namespace}', error)

        if pages:
            self.custom_tabs[namespace] = pages
        # A task-owned page replaces its generic cards. Explicit tabs can
        # coexist with runnable tasks, while tab-only plugins need no task tab.
        if tasks and (specifications or not pages):
            group_tab = ImportedTaskTab(namespace, entry['script_name'])
            self.window.imported_tabs[namespace] = group_tab
            self._add(group_tab, entry['script_name'], getattr(tasks[0], 'group_icon', FluentIcon.APPLICATION))
        finish_plugin_update(namespace, error='\n'.join(errors.values()) or None)

    def dispose(self):
        if self._closed:
            return
        self._closed = True
        for namespace in tuple(self._entries):
            self._remove(namespace)
