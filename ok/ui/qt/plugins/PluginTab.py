import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

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
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.dialogs import Dialog, confirm
from ok.ui.qt.kit.feedback import Pill
from ok.ui.qt.kit.icons import icon
from ok.ui.qt.kit.inputs import ComboBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import set_style_property, theme
from ok.ui.qt.tasks.tasks_page import monogram
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


class PluginCard(Card):
    """One installed (or staged) plugin: tile, name, version, notes and actions."""

    def __init__(self, name, version='', parent=None):
        super().__init__(parent)
        tile = QLabel(monogram(name), self)
        tile.setObjectName("taskTile")
        tile.setFixedSize(40, 40)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(Label(name, "strong", self))
        if version:
            title_row.addWidget(Pill(version, "neutral", self))
        title_row.addStretch(1)
        self.notes = QVBoxLayout()
        self.notes.setSpacing(2)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addLayout(title_row)
        text.addLayout(self.notes)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        layout.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        layout.addLayout(self.actions)

    def add_note(self, text, tone=None):
        label = Label(text, "secondary", self, word_wrap=True)
        if tone:
            set_style_property(label, "tone", tone)
        self.notes.addWidget(label)
        return label

    def add_action(self, button):
        button.setParent(self)
        self.actions.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        return button


class PluginTab(QWidget):
    """Manage installed plugins; downloads and archive work run off the GUI thread."""

    def __init__(self):
        super().__init__()
        self.setObjectName("PluginTab")
        self._jobs = {}
        self._busy = False
        self._delete_buttons = []
        self._update_buttons = []
        self._update_timers = {}
        self._plugin_tokens = {}
        self._updates = {}
        self._check_errors = {}
        self._pending = {}

        self.local_button = Button(self.tr('Add from ZIP'), "plus", "primary")
        self.github_button = Button(self.tr('Add from GitHub'), "github")
        self.local_button.clicked.connect(self.add_local)
        self.github_button.clicked.connect(self.add_github)
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QVBoxLayout()
        title.setSpacing(4)
        title.addWidget(Label(self.tr('Plugins'), "display", self))
        self.status_label = Label('', "secondary", self, word_wrap=True)
        title.addWidget(self.status_label)
        header.addLayout(title, 1)
        header.addWidget(self.github_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.local_button, 0, Qt.AlignmentFlag.AlignTop)

        # Shown while staged changes wait for a restart.
        self.restart_label = QFrame(self)
        self.restart_label.setObjectName("noticeBanner")
        banner_icon = QLabel(self.restart_label)
        banner_icon.setPixmap(icon("alert").pixmap(QSize(18, 18), self.devicePixelRatioF()))
        banner_text = Label(self.tr('Restart the application to apply plugin changes.'), "body", self.restart_label,
                            word_wrap=True)
        banner = QHBoxLayout(self.restart_label)
        banner.setContentsMargins(14, 10, 14, 10)
        banner.setSpacing(10)
        banner.addWidget(banner_icon)
        banner.addWidget(banner_text, 1)
        self.restart_label.hide()

        self.plugins = QWidget()
        self.plugins.setObjectName("scrollContents")
        self.plugins_layout = QVBoxLayout(self.plugins)
        self.plugins_layout.setContentsMargins(0, 0, 0, 0)
        self.plugins_layout.setSpacing(10)
        self.plugins_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.plugins)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(self.restart_label)
        layout.addWidget(scroll, 1)
        theme.install(self)

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

    def _empty_state(self):
        card = Card(self.plugins, look="inset")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        glyph = QLabel(card)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setPixmap(icon("grid").pixmap(QSize(32, 32), self.devicePixelRatioF()))
        title = Label(self.tr('No plugins installed.'), "strong", card)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = Label(self.tr('Add a plugin from a ZIP file or a GitHub release.'), "secondary", card)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 36, 24, 36)
        layout.setSpacing(8)
        layout.addWidget(glyph)
        layout.addWidget(title)
        layout.addWidget(hint)
        return card

    def _change_message(self, change):
        if change['phase'] in ('failed', 'recovery'):
            return self.tr('Plugin change failed: {}').format(change.get('error', '')), "danger"
        if change['phase'] == 'rollback':
            return self.tr('Update failed. Restart to restore the previous version.'), "danger"
        if change['phase'] == 'committed':
            return self.tr('Backup cleanup pending. Restart to retry.'), "warning"
        if change['action'] == 'delete':
            return self.tr('Deletion staged. Restart to apply.'), "warning"
        return self.tr('Update staged: {}. Restart to apply.').format(change.get('version', '')), "warning"

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
            self.plugins_layout.addWidget(self._empty_state())
        manager = og.task_manager
        for entry in entries:
            namespace = entry['file_name']
            card = PluginCard(entry['script_name'], entry['version'], self.plugins)
            loaded = manager.imported_scripts.get(namespace, {})
            errors = loaded.get('errors', []) + list(loaded.get('tab_errors', {}).values())
            if errors:
                card.add_note('\n'.join(errors), "danger")
            change = self._pending.get(namespace)
            if change is not None:
                card.add_note(*self._change_message(change))
            if namespace in self._check_errors:
                card.add_note(self.tr('Update check failed: {}').format(self._check_errors[namespace]), "warning")
            if change is None and read_plugin_source(entry['folder']) is not None:
                card.add_note(self.tr('From GitHub: {}').format(read_plugin_source(entry['folder'])['repository']))
                if namespace in self._updates:
                    version = self._updates[namespace][0]['tag']
                    update = card.add_action(Button(self.tr('Update to {}').format(version), "download", "primary"))
                    update.setEnabled(not self._busy)
                    update.clicked.connect(lambda _checked=False, entry=entry: self.update_plugin(entry))
                    self._update_buttons.append(update)
                check = card.add_action(Button(self.tr('Check for updates'), "refresh", "subtle"))
                check.setEnabled(not self._busy)
                check.clicked.connect(lambda _checked=False, entry=entry: self.check_updates(entry))
                self._update_buttons.append(check)
            if change is not None:
                button = card.add_action(Button(self.tr('Cancel pending change'), "x"))
                button.setProperty('pendingChangeLocked', change['phase'] not in {'pending', 'failed'})
                button.setEnabled(not self._busy and change['phase'] in {'pending', 'failed'})
                button.clicked.connect(lambda _checked=False, namespace=namespace: self.cancel_change(namespace))
            else:
                button = card.add_action(Button(self.tr('Delete plugin'), "trash", "subtle"))
                button.setEnabled(not self._busy)
                button.clicked.connect(lambda _checked=False, entry=entry: self.delete_plugin(entry))
            self._delete_buttons.append(button)
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
        dialog = Dialog(self, self.tr('GitHub repository'), ok_text=self.tr('Add from GitHub'), width=480)
        try:
            repository = QLineEdit(dialog.panel)
            repository.setPlaceholderText('https://github.com/owner/repository')
            dialog.body.addWidget(repository)
            dialog.ok_button.setEnabled(False)
            repository.textChanged.connect(lambda text: dialog.ok_button.setEnabled(bool(text.strip())))
            QTimer.singleShot(0, repository.setFocus)
            if dialog.exec():
                value = repository.text()
                self._start_job(lambda: github_release_assets(value), self._select_release)
        finally:
            dialog.deleteLater()

    def _confirm_import(self):
        dialog = ImportWarningDialog(self)
        try:
            return bool(dialog.exec())
        finally:
            dialog.deleteLater()

    def _select_release(self, assets, namespace=None):
        if len(assets) == 1:
            selected = assets[0]
        else:
            dialog = Dialog(self, self.tr('Release asset'), ok_text=self.tr('Install plugin'))
            try:
                choices = ComboBox([asset['name'] for asset in assets], dialog.panel)
                dialog.body.addWidget(choices)
                if not dialog.exec():
                    self.status_label.clear()
                    return
                selected = assets[choices.currentIndex()]
            finally:
                dialog.deleteLater()
        self._start_job(lambda: download_plugin(selected),
                        lambda prepared: self._install_release(prepared, selected, namespace))

    def _install_release(self, prepared, asset, namespace=None):
        try:
            prepared.source = github_asset_source(asset)
            if namespace is not None:
                if prepared.manifest['file_name'] != namespace:
                    raise ValueError(self.tr('The release archive belongs to a different plugin'))
                installed = next(entry for entry in scan_import_folders() if entry['file_name'] == namespace)
                source = read_plugin_source(installed['folder'])
                current = installed['version'] or (source or {}).get('tag', '')
                candidate = prepared.manifest.get('version') or prepared.source['tag']
                if not newer_plugin_version(candidate, current):
                    raise ValueError(self.tr('The release archive is not a newer plugin version'))
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
        if not confirm(self, self.tr('Delete plugin'), self.tr('Delete plugin "{}"?').format(entry['script_name']),
                       ok_text=self.tr('Delete plugin'), danger=True):
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
