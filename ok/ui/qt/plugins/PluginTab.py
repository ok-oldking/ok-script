import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, LineEdit, MessageBox, MessageBoxBase,
    PrimaryPushButton, PushButton, SimpleCardWidget, SubtitleLabel,
)

from ok import og
from ok.core.events import communicate
from ok.core.plugins import (
    download_plugin, github_asset_source, github_release_assets, newer_plugin_version,
    plugin_update_assets, prepare_local_plugin, read_plugin_source,
)
from ok.core.plugin_staging import (
    cancel_pending_plugin_change, install_or_stage_plugin, pending_plugin_changes,
)
from ok.core.script_packager import get_ok_import_folder, scan_import_folders
from ok.ui.qt.widget.Tab import Tab
from ok.ui.qt.widget.ImportWarningDialog import ImportWarningDialog


class _JobSignals(QObject):
    finished = Signal(object, object, object)


class _Job(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _JobSignals()

    def run(self):
        try:
            result = self.operation()
        except Exception as error:
            self.signals.finished.emit(self, None, str(error))
        else:
            self.signals.finished.emit(self, result, None)


class PluginTab(Tab):
    """Manage installed plugins; downloads and archive work run off the GUI thread."""

    def __init__(self):
        super().__init__()
        self._jobs = {}
        self._busy = False
        self._delete_buttons = []
        self._update_buttons = []
        self._update_timers = {}
        self._plugin_tokens = {}
        self._updates = {}
        self._check_errors = {}
        self.vBoxLayout.addWidget(SubtitleLabel(self.tr('Plugins'), self))
        toolbar = QHBoxLayout()
        self.local_button = PrimaryPushButton(FluentIcon.ADD, self.tr('Add from ZIP'), self)
        self.github_button = PushButton(FluentIcon.GITHUB, self.tr('Add from GitHub'), self)
        self.local_button.clicked.connect(self.add_local)
        self.github_button.clicked.connect(self.add_github)
        toolbar.addWidget(self.local_button)
        toolbar.addWidget(self.github_button)
        toolbar.addStretch()
        self.vBoxLayout.addLayout(toolbar)
        self.status_label = BodyLabel('', self)
        self.status_label.setWordWrap(True)
        self.vBoxLayout.addWidget(self.status_label)
        self.restart_label = BodyLabel(self.tr('Restart the application to apply plugin changes.'), self)
        self.restart_label.setWordWrap(True)
        self.restart_label.hide()
        self.vBoxLayout.addWidget(self.restart_label)
        self.plugins = QWidget(self)
        self.plugins_layout = QVBoxLayout(self.plugins)
        self.plugins_layout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.addWidget(self.plugins)
        communicate.task_list_updated.connect(self.refresh)
        communicate.plugin_changes_updated.connect(self.refresh)
        callback = self.refresh
        self.destroyed.connect(lambda *_: (
            communicate.task_list_updated.disconnect(callback),
            communicate.plugin_changes_updated.disconnect(callback),
        ))
        self.refresh()

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    @Slot()
    def refresh(self):
        while self.plugins_layout.count():
            item = self.plugins_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self._delete_buttons = []
        self._update_buttons = []
        entries = scan_import_folders()
        self._pending = pending_plugin_changes()
        installed = {entry['file_name'] for entry in entries}
        for namespace, change in self._pending.items():
            if namespace not in installed:
                entries.append({'file_name': namespace, 'script_name': change.get('script_name', namespace),
                                'folder': str(Path(get_ok_import_folder()) / namespace), 'version': ''})
        self.restart_label.setVisible(any(
            change['phase'] != 'failed' for change in self._pending.values()))
        self._schedule_update_checks(entries)
        if not entries:
            self.plugins_layout.addWidget(BodyLabel(self.tr('No plugins installed.'), self.plugins))
        manager = og.task_manager
        for entry in entries:
            card = SimpleCardWidget(self.plugins)
            layout = QHBoxLayout(card)
            text = QVBoxLayout()
            text.addWidget(BodyLabel(entry['script_name'], card))
            if entry['version']:
                text.addWidget(BodyLabel(self.tr('Version: {}').format(entry['version']), card))
            loaded = manager.imported_scripts.get(entry['file_name'], {})
            errors = loaded.get('errors', []) + list(loaded.get('tab_errors', {}).values())
            if errors:
                label = BodyLabel('\n'.join(errors), card)
                label.setWordWrap(True)
                text.addWidget(label)
            namespace = entry['file_name']
            change = self._pending.get(namespace)
            if change is not None:
                if change['phase'] == 'failed':
                    message = self.tr('Plugin change failed: {}').format(change.get('error', ''))
                elif change['phase'] == 'rollback':
                    message = self.tr('Update failed. Restart to restore the previous version.')
                elif change['phase'] == 'committed':
                    message = self.tr('Backup cleanup pending. Restart to retry.')
                elif change['phase'] == 'recovery':
                    message = self.tr('Plugin change failed: {}').format(change.get('error', ''))
                elif change['action'] == 'delete':
                    message = self.tr('Deletion staged. Restart to apply.')
                else:
                    message = self.tr('Update staged: {}. Restart to apply.').format(change.get('version', ''))
                label = BodyLabel(message, card)
                label.setWordWrap(True)
                text.addWidget(label)
            if namespace in self._check_errors:
                label = BodyLabel(self.tr('Update check failed: {}').format(self._check_errors[namespace]), card)
                label.setWordWrap(True)
                text.addWidget(label)
            layout.addLayout(text, 1)
            if change is None and read_plugin_source(entry['folder']) is not None:
                check = PushButton(FluentIcon.SYNC, self.tr('Check for updates'), card)
                check.setEnabled(not self._busy)
                check.clicked.connect(lambda _checked=False, entry=entry: self.check_updates(entry))
                self._update_buttons.append(check)
                layout.addWidget(check)
                if namespace in self._updates:
                    version = self._updates[namespace][0]['tag']
                    update = PrimaryPushButton(self.tr('Update to {}').format(version), card)
                    update.setEnabled(not self._busy)
                    update.clicked.connect(lambda _checked=False, entry=entry: self.update_plugin(entry))
                    self._update_buttons.append(update)
                    layout.addWidget(update)
            if change is not None:
                button = PushButton(self.tr('Cancel pending change'), card)
                button.setProperty('pendingChangeLocked', change['phase'] not in {'pending', 'failed'})
                button.setEnabled(not self._busy and change['phase'] in {'pending', 'failed'})
                button.clicked.connect(lambda _checked=False, namespace=namespace: self.cancel_change(namespace))
            else:
                button = PushButton(FluentIcon.DELETE, self.tr('Delete plugin'), card)
                button.setEnabled(not self._busy)
                button.clicked.connect(lambda _checked=False, entry=entry: self.delete_plugin(entry))
            self._delete_buttons.append(button)
            layout.addWidget(button)
            self.plugins_layout.addWidget(card)

    def _set_busy(self, busy, quiet=False):
        self._busy = busy
        for button in (self.local_button, self.github_button, *self._delete_buttons, *self._update_buttons):
            button.setEnabled(not busy and not button.property('pendingChangeLocked'))
        if busy and not quiet:
            self.status_label.setText(self.tr('Working…'))

    def _start_job(self, operation, callback, on_error=None, quiet=False):
        self._set_busy(True, quiet=quiet)
        worker = _Job(operation)
        self._jobs[worker] = (callback, on_error)
        worker.signals.finished.connect(self._job_finished)
        QThreadPool.globalInstance().start(worker)

    @Slot(object, object, object)
    def _job_finished(self, worker, result, error):
        callback, on_error = self._jobs.pop(worker)
        self._set_busy(bool(self._jobs), quiet=True)
        try:
            if error:
                if on_error is not None:
                    on_error(error)
                    return
                raise ValueError(error)
            callback(result)
        except Exception as failure:
            self.status_label.setText(self.tr('Plugin operation failed: {}').format(failure))

    def add_local(self):
        if self._busy or not self._confirm_import():
            return
        path, _filter = QFileDialog.getOpenFileName(
            self.window(), self.tr('Install plugin'), '', self.tr('Plugins') + ' (*.zip *.okscript)')
        if path:
            self._start_job(lambda: prepare_local_plugin(path), self._install_prepared)

    def add_github(self):
        if self._busy or not self._confirm_import():
            return
        dialog = MessageBoxBase(self.window())
        dialog.viewLayout.addWidget(SubtitleLabel(self.tr('GitHub repository'), dialog))
        repository = LineEdit(dialog)
        repository.setPlaceholderText('https://github.com/owner/repository')
        repository.setMinimumWidth(360)
        dialog.viewLayout.addWidget(repository)
        dialog.yesButton.setText(self.tr('Add from GitHub'))
        dialog.yesButton.setEnabled(False)
        repository.textChanged.connect(lambda text: dialog.yesButton.setEnabled(bool(text.strip())))
        if dialog.exec():
            value = repository.text()
            self._start_job(lambda: github_release_assets(value), self._select_release)

    def _confirm_import(self):
        dialog = ImportWarningDialog(self.window())
        try:
            return bool(dialog.exec())
        finally:
            dialog.deleteLater()

    def _select_release(self, assets, namespace=None):
        if len(assets) == 1:
            selected = assets[0]
        else:
            dialog = MessageBoxBase(self.window())
            dialog.viewLayout.addWidget(SubtitleLabel(self.tr('Release asset'), dialog))
            choices = ComboBox(dialog)
            for asset in assets:
                choices.addItem(asset['name'])
            dialog.viewLayout.addWidget(choices)
            dialog.yesButton.setText(self.tr('Install plugin'))
            if not dialog.exec():
                self.status_label.clear()
                return
            selected = assets[choices.currentIndex()]
        self._start_job(lambda: download_plugin(selected),
                        lambda prepared: self._install_release(prepared, selected, namespace))

    def _install_release(self, prepared, asset, namespace=None):
        try:
            prepared.source = github_asset_source(asset)
            if namespace is not None:
                if prepared.manifest['file_name'] != namespace:
                    raise ValueError('The release archive belongs to a different plugin')
                installed = next(entry for entry in scan_import_folders() if entry['file_name'] == namespace)
                source = read_plugin_source(installed['folder'])
                current = installed['version'] or (source or {}).get('tag', '')
                candidate = prepared.manifest.get('version') or prepared.source['tag']
                if not newer_plugin_version(candidate, current):
                    raise ValueError('The release archive is not a newer plugin version')
        except Exception:
            prepared.close()
            raise
        self._install_prepared(prepared)

    def _install_prepared(self, prepared):
        manager = og.task_manager

        def install():
            try:
                return install_or_stage_plugin(prepared.path, source=prepared.source)
            finally:
                prepared.close()

        def complete(result):
            if result['restart_required']:
                self.status_label.clear()
            else:
                manager.load_import_folder(result['folder'])
                self.status_label.setText(self.tr('Plugin installed.'))
            self.refresh()

        self._start_job(install, complete)

    def _schedule_update_checks(self, entries):
        now = time.monotonic()
        tokens = {}
        for entry in entries:
            namespace = entry['file_name']
            loaded = og.task_manager.imported_scripts.get(namespace)
            source = read_plugin_source(entry['folder'])
            if loaded is None or source is None or namespace in self._pending:
                continue
            token = (id(loaded), entry['version'], source['repository'], source.get('tag', ''))
            tokens[namespace] = token
            if self._plugin_tokens.get(namespace) == token:
                continue
            old_timer = self._update_timers.pop(namespace, None)
            if old_timer is not None:
                old_timer.stop()
                old_timer.deleteLater()
            self._updates.pop(namespace, None)
            self._check_errors.pop(namespace, None)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda namespace=namespace, token=token: self._automatic_check(namespace, token))
            self._update_timers[namespace] = timer
            elapsed = max(0, now - loaded.get('loaded_at', now))
            timer.start(max(0, 10_000 - int(elapsed * 1000)))
        for namespace in self._plugin_tokens.keys() - tokens.keys():
            timer = self._update_timers.pop(namespace, None)
            if timer is not None:
                timer.stop()
                timer.deleteLater()
            self._updates.pop(namespace, None)
            self._check_errors.pop(namespace, None)
        self._plugin_tokens = tokens

    def _automatic_check(self, namespace, token):
        if self._plugin_tokens.get(namespace) != token:
            return
        if self._busy:
            self._update_timers[namespace].start(1000)
            return
        entry = next((entry for entry in scan_import_folders() if entry['file_name'] == namespace), None)
        if entry is not None:
            self.check_updates(entry, automatic=True)

    def check_updates(self, entry, automatic=False):
        if self._busy or entry['file_name'] in self._pending:
            return
        namespace = entry['file_name']
        token = self._plugin_tokens.get(namespace)
        timer = self._update_timers.get(namespace)
        if timer is not None:
            timer.stop()

        def complete(assets):
            if self._plugin_tokens.get(namespace) != token:
                return
            self._check_errors.pop(namespace, None)
            if assets:
                self._updates[namespace] = assets
                self.status_label.setText(self.tr('Update available for {}: {}').format(
                    entry['script_name'], assets[0]['tag']))
            else:
                self._updates.pop(namespace, None)
                if not automatic:
                    self.status_label.setText(self.tr('Plugin is up to date.'))
            self.refresh()

        def failed(error):
            if self._plugin_tokens.get(namespace) != token:
                return
            self._check_errors[namespace] = error
            if not automatic:
                self.status_label.setText(self.tr('Update check failed: {}').format(error))
            self.refresh()

        self._start_job(lambda: plugin_update_assets(entry), complete, on_error=failed, quiet=automatic)
        if not automatic:
            self.status_label.setText(self.tr('Checking for updates…'))

    def update_plugin(self, entry):
        if self._busy or not self._confirm_import():
            return
        assets = self._updates.get(entry['file_name'])
        if assets:
            self._select_release(assets, namespace=entry['file_name'])

    def delete_plugin(self, entry):
        if self._busy:
            return
        dialog = MessageBox(self.tr('Delete plugin'),
                            self.tr('Delete plugin "{}"?').format(entry['script_name']), self.window())
        if not dialog.exec():
            return
        try:
            og.task_manager.delete_imported_script(entry['file_name'])
            self.refresh()
            self.status_label.clear()
        except Exception as error:
            self.status_label.setText(self.tr('Plugin operation failed: {}').format(error))

    def cancel_change(self, namespace):
        if self._busy:
            return
        try:
            cancel_pending_plugin_change(namespace)
            self.status_label.clear()
            self.refresh()
        except Exception as error:
            self.status_label.setText(self.tr('Plugin operation failed: {}').format(error))
