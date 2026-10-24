import json
import os
import threading
import time
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget
from qfluentwidgets import FluentIcon
from shiboken6 import delete, isValid

from ok import og
from ok.core.events import communicate
from ok.core import events
from ok.core.plugin_staging import apply_pending_plugin_changes, pending_plugin_changes, stage_plugin_update
from ok.core.plugins import PLUGIN_SOURCE_FILE, prepare_local_plugin, read_plugin_source, write_plugin_source
from ok.core.task_manager import TaskManager
from ok.ui.qt.events import QtEventDispatcher
from ok.ui.qt.MainWindow import MainWindow
from ok.ui.qt.plugins.PluginTab import PluginTab
from ok.ui.qt.plugins.imported_tabs import ImportedTabs
from ok.ui.qt.widget.ImportWarningDialog import ImportWarningDialog


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


class Window(QWidget):
    def __init__(self, executor):
        super().__init__()
        self.executor = executor
        self.app = SimpleNamespace(tr=lambda text: text)
        self.navigationInterface = Mock()
        self.stackedWidget = QStackedWidget(self)
        self.imported_tabs = {}
        self.added = []
        self.update_navigation_width = Mock()

    def addSubInterface(self, widget, icon, name, **kwargs):
        self.stackedWidget.addWidget(widget)
        self.added.append((widget, name))


@pytest.fixture
def environment(qt_app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    executor = SimpleNamespace(onetime_tasks=[], trigger_tasks=[], current_task=None, feature_set=None)
    manager = TaskManager.__new__(TaskManager)
    manager.task_executor = executor
    manager.app = SimpleNamespace(debug=False)
    manager.scene = None
    manager.file_watcher_factory = Mock()
    manager.imported_scripts, manager.task_map, manager.task_errors = {}, {}, {}
    manager._update_debug_watched_files = Mock()
    monkeypatch.setattr(og, 'task_manager', manager)
    monkeypatch.setattr(og, 'executor', executor)
    monkeypatch.setattr(og, 'app', SimpleNamespace(tr=lambda text: text))
    dispatcher = QtEventDispatcher()
    monkeypatch.setattr(events, '_dispatcher', dispatcher.dispatch)
    window = Window(executor)
    controller = ImportedTabs(window)
    communicate.task_list_updated.connect(controller.refresh)
    yield SimpleNamespace(manager=manager, window=window, controller=controller, root=tmp_path)
    communicate.task_list_updated.disconnect(controller.refresh)
    controller.dispose()
    for namespace in tuple(manager.imported_scripts):
        manager.unload_imported_script(namespace)
    delete(window)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


PAGE_SOURCE = '''from ok.ui.qt.widget.CustomTab import CustomTab
from qfluentwidgets import FluentIcon
class Page(CustomTab):
    icon = FluentIcon.APPLICATION
    @property
    def name(self): return 'Plugin page'
    def dispose(self): self.disposed = True
'''


def install_files(environment, manifest, files):
    folder = environment.root / 'ok_import' / manifest['file_name']
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    for name, content in files.items():
        (folder / name).write_text(content)
    environment.manager.load_import_folder(str(folder))
    return folder


@pytest.mark.parametrize('configured', [None, False, True])
def test_plugin_manager_tab_is_opt_in(environment, configured):
    window = environment.window
    window.config = {} if configured is None else {'plugin': configured}
    MainWindow._add_plugin_tab(window)
    assert hasattr(window, 'plugin_tab') is bool(configured)
    if configured:
        assert window.added[-1][1] == 'Plugins'


def test_tab_only_plugin_stays_live_until_staged_deletion_is_applied(environment):
    install_files(environment, {'file_name': 'demo', 'tasks': [], 'custom_tabs': [['page', 'Page']]},
                  {'page.py': PAGE_SOURCE})
    page, = environment.controller.custom_tabs['demo']
    assert page.executor is environment.window.executor
    assert environment.window.imported_tabs == {}
    assert environment.window.stackedWidget.count() == 1
    environment.manager.delete_imported_script('demo')
    assert not getattr(page, 'disposed', False)
    assert 'demo' in environment.controller.custom_tabs
    assert pending_plugin_changes()['demo']['action'] == 'delete'
    environment.manager.unload_imported_script('demo')  # Normal shutdown owns cleanup.
    assert page.disposed
    assert environment.controller.custom_tabs == {}
    assert environment.window.stackedWidget.count() == 0


def test_explicit_custom_tabs_can_coexist_with_one_time_and_trigger_tasks(environment, monkeypatch):
    from ok.task.task import TriggerTask

    class FakeCard(QWidget):
        def __init__(self, task, onetime):
            super().__init__()
            self.task, self.onetime = task, onetime
            self.dispose = Mock()

    monkeypatch.setattr('ok.ui.qt.tasks.TaskCard.TaskCard', FakeCard)
    folder = install_files(environment, {'file_name': 'demo', 'tasks': [],
                                        'custom_tabs': [['page', 'Page']]}, {'page.py': PAGE_SOURCE})
    ordinary = SimpleNamespace(visible=True, group_icon=FluentIcon.APPLICATION)
    trigger = object.__new__(TriggerTask)
    trigger.visible, trigger.group_icon = True, FluentIcon.APPLICATION
    environment.manager.imported_scripts['demo']['tasks'] = [ordinary, trigger]
    environment.controller.refresh()
    task_tab = environment.window.imported_tabs['demo']
    assert [card.onetime for card in task_tab.card_widgets] == [True, False]
    assert len(environment.controller.custom_tabs['demo']) == 1
    assert environment.window.stackedWidget.count() == 2
    environment.manager.imported_scripts['demo']['tasks'] = []


FACTORY_TASK_SOURCE = '''from ok import BaseTask
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon
class FactoryTask(BaseTask):
    def __init__(self, executor=None, app=None):
        self.name = 'Workshop'
        self.group_icon = FluentIcon.APPLICATION
        self.destroyed = False
        self.stopped = False
    def after_init(self, **kwargs): pass
    def disable(self): pass
    def on_destroy(self):
        assert self.stopped
        self.destroyed = True
    def create_import_page(self, parent):
        self.page = QWidget(parent)
        def stop():
            assert not self.destroyed
            self.stopped = True
        self.page.stop_worker = stop
        return self.page
'''


def test_workshop_page_factory_reloads_before_closing_old_runtime(environment):
    install_files(environment, {'file_name': 'demo'}, {'entry.py': FACTORY_TASK_SOURCE})
    old, = environment.manager.imported_scripts['demo']['tasks']
    old_page, = environment.controller.custom_tabs['demo']
    assert old_page.page is old.page
    assert environment.window.imported_tabs == {}
    environment.manager.reload_task_code(old)
    new, = environment.manager.imported_scripts['demo']['tasks']
    assert old.destroyed and old.stopped
    assert new is not old
    assert environment.controller.custom_tabs['demo'][0].page is new.page
    environment.manager.delete_imported_script('demo')
    assert not new.destroyed
    environment.manager.unload_imported_script('demo')
    assert new.destroyed


def test_broken_custom_tab_does_not_block_other_tabs(environment):
    source = PAGE_SOURCE + '\nclass Broken:\n    def __init__(self): raise RuntimeError("bad page")\n'
    install_files(environment, {'file_name': 'demo', 'tasks': [],
                               'custom_tabs': [['page', 'Broken'], ['page', 'Page']]}, {'page.py': source})
    assert len(environment.controller.custom_tabs['demo']) == 1
    assert environment.manager.imported_scripts['demo']['tab_errors'] == {'page.Broken': 'bad page'}


def test_archive_install_worker_returns_to_gui_thread(environment, qt_app):
    archive = environment.root / 'demo.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('demo/manifest.json', json.dumps({
            'file_name': 'demo', 'tasks': [], 'custom_tabs': [['page', 'Page']],
        }))
        output.writestr('demo/page.py', PAGE_SOURCE)
    tab = PluginTab()
    try:
        tab._install_prepared(prepare_local_plugin(archive))
        deadline = time.monotonic() + 5
        while tab._jobs and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.01)
        assert not tab._jobs
        assert tab.status_label.text() == 'Plugin installed.'
        assert 'demo' in environment.controller.custom_tabs
        assert not tab._busy
        assert len(tab._delete_buttons) == 1
    finally:
        delete(tab)


def test_github_asset_download_flows_into_archive_install(environment, qt_app, monkeypatch):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    archive = environment.root / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps({
            'file_name': 'demo', 'tasks': [], 'custom_tabs': [['page', 'Page']],
        }))
        output.writestr('page.py', PAGE_SOURCE)
    download = Mock(side_effect=lambda _asset: prepare_local_plugin(archive))
    monkeypatch.setattr(module, 'download_plugin', download)
    asset = {'name': 'demo.zip', 'url': 'https://github.com/owner/repo/releases/download/v1/demo.zip'}
    tab = PluginTab()
    try:
        tab._select_release([asset])
        deadline = time.monotonic() + 5
        while tab._jobs and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.01)
        download.assert_called_once_with(asset)
        assert tab.status_label.text() == 'Plugin installed.'
        assert 'demo' in environment.controller.custom_tabs
    finally:
        delete(tab)


def test_failed_staging_leaves_previous_plugin_running(environment, qt_app, monkeypatch):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    install_files(environment, {'file_name': 'demo', 'tasks': [], 'custom_tabs': [['page', 'Page']]},
                  {'page.py': PAGE_SOURCE})
    old, = environment.controller.custom_tabs['demo']
    archive = environment.root / 'replacement.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps({'file_name': 'demo', 'tasks': []}))
    monkeypatch.setattr(module, 'install_or_stage_plugin', Mock(side_effect=ValueError('synthetic extraction failure')))
    tab = PluginTab()
    try:
        tab._install_prepared(prepare_local_plugin(archive))
        deadline = time.monotonic() + 5
        while tab._jobs and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.01)
        assert not getattr(old, 'disposed', False)
        replacement, = environment.controller.custom_tabs['demo']
        assert replacement is old
        assert 'synthetic extraction failure' in tab.status_label.text()
        assert not tab._busy
    finally:
        delete(tab)


def test_worker_operation_is_background_and_completion_is_gui_thread(environment, qt_app):
    tab = PluginTab()
    worker_threads, gui_threads = [], []
    main_thread = threading.get_ident()
    try:
        def operation():
            worker_threads.append(threading.get_ident())
            return 1
        tab._start_job(operation, lambda _result: gui_threads.append(QThread.currentThread()))
        deadline = time.monotonic() + 5
        while tab._jobs and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.01)
        assert worker_threads and worker_threads[0] != main_thread
        assert gui_threads == [qt_app.thread()]
    finally:
        delete(tab)


def wait_for_jobs(tab, qt_app):
    deadline = time.monotonic() + 5
    qt_app.processEvents()
    while tab._jobs and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert not tab._jobs


def test_import_warning_requires_countdown_and_checkbox(environment):
    dialog = ImportWarningDialog(environment.window)
    try:
        assert not dialog.yesButton.isEnabled()
        dialog.check_box.setChecked(True)
        assert not dialog.yesButton.isEnabled()
        for _ in range(15):
            dialog.update_countdown()
        assert dialog.yesButton.isEnabled()
        dialog.check_box.setChecked(False)
        assert not dialog.yesButton.isEnabled()
        dialog.reject()
        assert not dialog.timer.isActive()
    finally:
        delete(dialog)


@pytest.mark.parametrize('button', ['local_button', 'github_button'])
def test_cancelled_plugin_warning_prevents_install_flow(environment, monkeypatch, button):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    warning = Mock(return_value=False)
    chooser = Mock()
    repository_dialog = Mock()
    monkeypatch.setattr(module.QFileDialog, 'getOpenFileName', chooser)
    monkeypatch.setattr(module, 'MessageBoxBase', repository_dialog)
    tab = PluginTab()
    try:
        monkeypatch.setattr(tab, '_confirm_import', warning)
        getattr(tab, button).click()
        warning.assert_called_once_with()
        chooser.assert_not_called()
        repository_dialog.assert_not_called()
        assert not tab._jobs
    finally:
        delete(tab)


def test_script_importer_uses_shared_warning(environment, monkeypatch):
    from ok.ui.qt.tasks.EditTaskTab import EditTaskTab
    monkeypatch.setattr(ImportWarningDialog, 'exec', lambda self: True)
    harness = SimpleNamespace(window=lambda: environment.window, _do_import=Mock())
    EditTaskTab._show_import_warning(harness, 'plugin.okscript')
    harness._do_import.assert_called_once_with('plugin.okscript')


def github_plugin(environment):
    folder = install_files(environment, {'file_name': 'demo', 'version': '1.0', 'tasks': [],
                                        'custom_tabs': [['page', 'Page']]}, {'page.py': PAGE_SOURCE})
    write_plugin_source(folder, {'repository': 'owner/repo', 'tag': 'v1.0', 'asset_name': 'demo-v1.zip'})
    return folder


def test_github_plugins_auto_check_once_ten_seconds_after_load(environment, qt_app, monkeypatch):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    folder = github_plugin(environment)
    environment.manager.imported_scripts['demo']['loaded_at'] = 100
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: 100))
    update = {'name': 'demo-v2.zip', 'tag': 'v2.0', 'repository': 'owner/repo',
              'url': 'https://github.com/owner/repo/releases/download/v2.0/demo-v2.zip'}
    check = Mock(return_value=[update])
    monkeypatch.setattr(module, 'plugin_update_assets', check)
    tab = PluginTab()
    try:
        timer = tab._update_timers['demo']
        assert timer.interval() == 10_000 and timer.isActive()
        tab.refresh()
        assert tab._update_timers['demo'] is timer
        check.assert_not_called()
        timer.start(0)
        wait_for_jobs(tab, qt_app)
        check.assert_called_once()
        assert tab._updates['demo'] == [update]
        assert any(button.text() == 'Update to v2.0' for button in tab._update_buttons)
        assert 'v2.0' in tab.status_label.text()
        tab.refresh()
        assert not timer.isActive()
        assert check.call_count == 1
        environment.manager.load_import_folder(str(folder))
        assert tab._update_timers['demo'] is not timer
        assert tab._update_timers['demo'].isActive()
        environment.manager.delete_imported_script('demo')
        assert 'demo' not in tab._update_timers
    finally:
        delete(tab)


def test_automatic_update_check_defers_during_installs_and_handles_errors_quietly(environment, qt_app, monkeypatch):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    github_plugin(environment)
    check = Mock(side_effect=RuntimeError('network unavailable'))
    monkeypatch.setattr(module, 'plugin_update_assets', check)
    tab = PluginTab()
    try:
        tab._set_busy(True, quiet=True)
        tab._automatic_check('demo', tab._plugin_tokens['demo'])
        check.assert_not_called()
        assert tab._update_timers['demo'].interval() == 1000
        tab._set_busy(False)
        tab._update_timers['demo'].start(0)
        wait_for_jobs(tab, qt_app)
        assert tab._check_errors == {'demo': 'network unavailable'}
        assert tab.status_label.text() == ''
        assert not tab._busy
    finally:
        delete(tab)


def test_manual_update_is_staged_without_replacing_running_plugin(environment, qt_app, monkeypatch):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    folder = github_plugin(environment)
    old_page, = environment.controller.custom_tabs['demo']
    archive = environment.root / 'demo-v2.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps({
            'file_name': 'demo', 'version': '2.0', 'tasks': [], 'custom_tabs': [['page', 'Page']],
        }))
        output.writestr('page.py', PAGE_SOURCE)
    asset = {'name': 'demo-v2.zip', 'tag': 'v2.0', 'repository': 'owner/repo',
             'url': 'https://github.com/owner/repo/releases/download/v2.0/demo-v2.zip'}
    monkeypatch.setattr(module, 'plugin_update_assets', lambda entry: [asset])
    monkeypatch.setattr(module, 'download_plugin', lambda asset: prepare_local_plugin(archive))
    tab = PluginTab()
    try:
        monkeypatch.setattr(tab, '_confirm_import', lambda: True)
        check, = tab._update_buttons
        check.click()
        wait_for_jobs(tab, qt_app)
        update = next(button for button in tab._update_buttons if button.text() == 'Update to v2.0')
        update.click()
        wait_for_jobs(tab, qt_app)
        assert not getattr(old_page, 'disposed', False)
        assert environment.manager.imported_scripts['demo']['version'] == '1.0'
        assert read_plugin_source(folder) == {'repository': 'owner/repo', 'tag': 'v1.0', 'asset_name': 'demo-v1.zip'}
        assert pending_plugin_changes()['demo']['version'] == '2.0'
        assert 'demo' not in tab._updates
        assert 'demo' not in tab._update_timers
        assert not tab.restart_label.isHidden()
        cancel, = tab._delete_buttons
        assert cancel.text() == 'Cancel pending change'
        cancel.click()
        assert pending_plugin_changes() == {}
        assert environment.manager.imported_scripts['demo']['version'] == '1.0'
        assert tab._update_timers['demo'].isActive()
    finally:
        delete(tab)


@pytest.mark.parametrize('package_id,version', [('other', '2.0'), ('demo', '1.0')])
def test_update_archive_must_match_plugin_and_contain_newer_version(environment, monkeypatch, package_id, version):
    github_plugin(environment)
    prepared = SimpleNamespace(manifest={'file_name': package_id, 'version': version}, close=Mock())
    asset = {'name': 'demo-v2.zip', 'tag': 'v2.0', 'repository': 'owner/repo'}
    tab = PluginTab()
    try:
        with pytest.raises(ValueError):
            tab._install_release(prepared, asset, 'demo')
        prepared.close.assert_called_once()
        assert environment.manager.imported_scripts['demo']['version'] == '1.0'
        assert not tab._jobs
    finally:
        delete(tab)


def test_local_install_discards_packaged_github_metadata(environment, qt_app):
    archive = environment.root / 'local.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps({'file_name': 'demo', 'tasks': []}))
        output.writestr(PLUGIN_SOURCE_FILE, json.dumps({'repository': 'owner/repo', 'tag': 'v1'}))
    tab = PluginTab()
    try:
        tab._install_prepared(prepare_local_plugin(archive))
        wait_for_jobs(tab, qt_app)
        assert read_plugin_source(environment.root / 'ok_import/demo') is None
        assert not tab._update_timers
        assert not tab._update_buttons
    finally:
        delete(tab)


def test_delete_button_stages_and_cancel_keeps_runtime_running(environment, monkeypatch):
    import importlib
    module = importlib.import_module('ok.ui.qt.plugins.PluginTab')
    folder = github_plugin(environment)
    page, = environment.controller.custom_tabs['demo']
    monkeypatch.setattr(module, 'MessageBox', lambda *args: SimpleNamespace(exec=lambda: True))
    tab = PluginTab()
    try:
        tab._delete_buttons[0].click()
        assert pending_plugin_changes()['demo']['action'] == 'delete'
        assert folder.exists() and not getattr(page, 'disposed', False)
        assert environment.controller.custom_tabs['demo'][0] is page
        assert not tab._update_timers and not tab._update_buttons
        assert not tab.restart_label.isHidden()
        tab._delete_buttons[0].click()  # Now the cancel-pending-change button.
        assert pending_plugin_changes() == {}
        assert tab.restart_label.isHidden()
        assert environment.controller.custom_tabs['demo'][0] is page
        assert tab._update_timers['demo'].isActive()
    finally:
        delete(tab)


def test_successful_startup_validation_resumes_checks_without_opening_manager(environment):
    folder = github_plugin(environment)
    archive = environment.root / 'new.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps({
            'file_name': 'demo', 'version': '2.0', 'tasks': [], 'custom_tabs': [['page', 'Page']],
        }))
        output.writestr('page.py', PAGE_SOURCE)
    stage_plugin_update(archive, {'repository': 'owner/repo', 'tag': 'v2.0', 'asset_name': 'new.zip'})
    environment.manager.unload_imported_script('demo')  # Simulate old-process shutdown.
    apply_pending_plugin_changes()
    assert pending_plugin_changes()['demo']['phase'] == 'validating'
    tab = PluginTab()
    try:
        assert not tab._update_timers
        assert not tab.restart_label.isHidden()
        environment.manager.load_import_folder(str(folder))
        assert pending_plugin_changes() == {}
        assert tab.restart_label.isHidden()
        assert tab._update_timers['demo'].isActive()
    finally:
        delete(tab)
