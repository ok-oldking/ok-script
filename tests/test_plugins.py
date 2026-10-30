import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from ok.core import plugins
from ok.core.script_packager import (
    export_script, import_script, inspect_script_archive, scan_import_folders,
)
from ok.core.task_manager import TaskManager


def archive_bytes(manifest, files=None, prefix=''):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr(prefix + 'manifest.json', json.dumps(manifest))
        for name, body in (files or {}).items():
            archive.writestr(prefix + name, body)
    return output.getvalue()


@pytest.mark.parametrize('prefix', ['', 'echo-workshop/'])
@pytest.mark.parametrize('bom', [False, True])
def test_installs_root_and_workshop_style_packages(tmp_path, monkeypatch, prefix, bom):
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / 'plugin.zip'
    manifest = {'file_name': 'demo', 'script_name': 'Demo', 'version': '1.0',
                'tasks': [], 'custom_tabs': [['pages.main', 'Page']]}
    with zipfile.ZipFile(archive, 'w') as output:
        text = json.dumps(manifest)
        output.writestr(prefix + 'manifest.json', ('\ufeff' if bom else '') + text)
        output.writestr(prefix + 'pages/main.py', 'class Page: pass')

    success, _message, folder = import_script(archive)

    assert success
    assert Path(folder) == tmp_path / 'ok_import/demo'
    assert (Path(folder) / 'pages/main.py').is_file()
    assert not (Path(folder) / 'echo-workshop').exists()
    entry, = scan_import_folders()
    assert entry['tasks'] == []
    assert entry['custom_tabs'] == [['pages.main', 'Page']]


@pytest.mark.parametrize('bad_file', ['../escaped.py', 'demo/.. /escaped.py', 'demo/a:b.py'])
def test_rejects_unsafe_archive_without_replacing_plugin(tmp_path, bad_file):
    existing = tmp_path / 'imports/demo'
    existing.mkdir(parents=True)
    (existing / 'old.txt').write_text('keep')
    archive = tmp_path / 'bad.zip'
    archive.write_bytes(archive_bytes({'file_name': 'demo'}, {bad_file: 'bad'}))
    success, _message, _folder = import_script(archive, import_base=existing.parent)
    assert not success
    assert (existing / 'old.txt').read_text() == 'keep'


def test_rejects_ambiguous_and_invalid_manifests(tmp_path):
    archive = tmp_path / 'ambiguous.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        for name in ['one', 'two']:
            output.writestr(f'{name}/manifest.json', json.dumps({'file_name': name}))
    with pytest.raises(ValueError, match='one manifest'):
        inspect_script_archive(archive)
    archive.write_bytes(archive_bytes({'file_name': 'demo', 'custom_tabs': [['../page', 'Page']]}))
    with pytest.raises(ValueError, match='custom_tabs'):
        inspect_script_archive(archive)


def test_export_preserves_plugin_entries_and_nested_python(tmp_path):
    source = tmp_path / 'source'
    (source / 'pages').mkdir(parents=True)
    (source / 'manifest.json').write_text(json.dumps({
        'file_name': 'demo', 'tasks': [], 'custom_tabs': [['pages.main', 'Page']],
    }))
    (source / 'pages/main.py').write_text('class Page: pass')
    (source / 'pages/manifest.json').write_text('{"native": true}')
    success, _message, path = export_script([], 'demo', 'Demo', '1', source, tmp_path / 'out')
    assert success
    assert inspect_script_archive(path)['custom_tabs'] == [['pages.main', 'Page']]
    with zipfile.ZipFile(path) as archive:
        assert archive.read('pages/main.py') == b'class Page: pass'
        assert archive.read('pages/manifest.json') == b'{"native": true}'


def test_export_includes_declared_root_tab_without_task_selection(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'manifest.json').write_text(json.dumps({
        'file_name': 'demo', 'tasks': [], 'custom_tabs': [['page', 'Page']],
    }))
    (source / 'page.py').write_text('class Page: pass')
    success, _message, path = export_script([], 'demo', 'Demo', '1', source, tmp_path / 'out')
    assert success
    with zipfile.ZipFile(path) as archive:
        assert 'page.py' in archive.namelist()


def test_failed_replacement_restores_previous_install(tmp_path, monkeypatch):
    from ok.core import script_packager
    existing = tmp_path / 'imports/demo'
    existing.mkdir(parents=True)
    (existing / 'old.txt').write_text('keep')
    archive = tmp_path / 'demo.zip'
    archive.write_bytes(archive_bytes({'file_name': 'demo'}, {'new.txt': 'new'}))
    original = script_packager.shutil.move
    def fail_replacement(source, target):
        if Path(source).name == 'demo' and Path(source).parent.name.startswith('.okscript-'):
            raise OSError('synthetic move failure')
        return original(source, target)
    monkeypatch.setattr(script_packager.shutil, 'move', fail_replacement)
    success, message, _folder = import_script(archive, import_base=existing.parent)
    assert not success and 'synthetic move failure' in message
    assert (existing / 'old.txt').read_text() == 'keep'
    assert not list(existing.parent.glob('.okscript-*'))


def test_provenance_write_failure_preserves_previous_install(tmp_path):
    existing = tmp_path / 'imports/demo'
    existing.mkdir(parents=True)
    (existing / 'old.txt').write_text('keep')
    archive = tmp_path / 'demo.zip'
    archive.write_bytes(archive_bytes({'file_name': 'demo'}, {'new.txt': 'new'}))
    def fail_metadata(_folder):
        raise OSError('metadata write failed')
    success, message, _folder = import_script(archive, import_base=existing.parent, prepare_staging=fail_metadata)
    assert not success and 'metadata write failed' in message
    assert (existing / 'old.txt').read_text() == 'keep'


@pytest.mark.parametrize('url', ['owner/repo', 'https://github.com/owner/repo',
                               'https://github.com/owner/repo.git/'])
def test_github_repository_formats(url):
    assert plugins.github_repository(url) == ('owner', 'repo')


@pytest.mark.parametrize('url', ['https://example.com/owner/repo',
                               'https://github.com/owner/repo/tree/main',
                               'https://github.com/owner/repo?token=secret'])
def test_rejects_non_repository_urls(url):
    with pytest.raises(ValueError):
        plugins.github_repository(url)


def asset(name):
    return {'name': name, 'size': 100,
            'browser_download_url': f'https://github.com/owner/repo/releases/download/v1/{name}'}


def test_finds_uploaded_release_assets_and_prefers_stable_release():
    session = Mock()
    session.get.return_value.json.return_value = [
        {'tag_name': 'v2rc1', 'prerelease': True, 'assets': [asset('demo.zip')]},
        {'tag_name': 'v1', 'assets': [asset('notes.txt'), asset('demo.zip'), asset('demo.okscript')]},
    ]
    assets = plugins.github_release_assets('owner/repo', session)
    assert [item['name'] for item in assets] == ['demo.okscript', 'demo.zip']
    assert all(item['tag'] == 'v1' for item in assets)
    session.get.return_value.json.return_value = [{'tag_name': 'v1', 'assets': []}]
    with pytest.raises(ValueError, match='No .zip or .okscript'):
        plugins.github_release_assets('owner/repo', session)


def test_download_validates_package_and_cleans_temporary_files():
    body = archive_bytes({'file_name': 'demo'}, {'entry.py': '# task'})
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.headers = {}
    response.iter_content.return_value = [body[:10], body[10:]]
    prepared = plugins.download_plugin({'name': 'demo.zip', 'url': asset('demo.zip')['browser_download_url']}, session)
    folder = Path(prepared.path).parent
    assert prepared.manifest['file_name'] == 'demo'
    assert prepared.source == {'repository': 'owner/repo', 'tag': '', 'asset_name': 'demo.zip'}
    assert folder.is_dir()
    prepared.close()
    assert not folder.exists()


def test_github_source_survives_restart_and_local_install_removes_it(tmp_path):
    source = {'repository': 'https://github.com/owner/repo', 'tag': 'v1.2', 'asset_name': 'demo.zip'}
    plugins.write_plugin_source(tmp_path, source)
    assert plugins.read_plugin_source(tmp_path) == {**source, 'repository': 'owner/repo'}
    plugins.write_plugin_source(tmp_path, None)
    assert plugins.read_plugin_source(tmp_path) is None
    (tmp_path / plugins.PLUGIN_SOURCE_FILE).write_text('{bad json')
    assert plugins.read_plugin_source(tmp_path) is None


@pytest.mark.parametrize('candidate,installed,expected', [
    ('v1.10.0', '1.9.0', True), ('v1.2', '1.2.0', False),
    ('v1.1', '1.2', False), ('2.0', '2.0rc1', True), ('2.0rc1', '2.0', False),
])
def test_plugin_updates_require_a_strictly_greater_version(candidate, installed, expected):
    assert plugins.newer_plugin_version(candidate, installed) is expected


def test_update_check_uses_saved_repository_and_installed_tag_fallback(tmp_path):
    plugins.write_plugin_source(tmp_path, {'repository': 'owner/repo', 'tag': 'v1.9', 'asset_name': 'demo.zip'})
    session = Mock()
    session.get.return_value.json.return_value = [{'tag_name': 'v1.10', 'assets': [asset('demo.zip')]}]
    entry = {'folder': tmp_path, 'version': ''}
    assert plugins.plugin_update_assets(entry, session)[0]['tag'] == 'v1.10'
    entry['version'] = '1.10'
    assert plugins.plugin_update_assets(entry, session) == []
    entry['version'] = '2.0'
    assert plugins.plugin_update_assets(entry, session) == []
    entry['version'] = 'development'
    with pytest.raises(ValueError, match='Cannot compare'):
        plugins.plugin_update_assets(entry, session)


def test_local_plugins_do_not_make_github_update_requests(tmp_path):
    session = Mock()
    assert plugins.plugin_update_assets({'folder': tmp_path, 'version': '1'}, session) == []
    session.get.assert_not_called()


def test_download_enforces_size_limit(monkeypatch):
    monkeypatch.setattr(plugins, 'MAX_ARCHIVE_SIZE', 5)
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.headers = {}
    response.iter_content.return_value = [b'123', b'456']
    with pytest.raises(ValueError, match='too large'):
        plugins.download_plugin({'name': 'demo.zip', 'url': asset('demo.zip')['browser_download_url']}, session)


TASK_SOURCE = '''from ok import BaseTask
class DemoTask(BaseTask):
    def __init__(self, executor=None, app=None):
        self.name = 'Demo'
        self.destroyed = False
    def after_init(self, **kwargs): pass
    def disable(self): pass
    def on_destroy(self): self.destroyed = True
'''


def make_manager():
    manager = TaskManager.__new__(TaskManager)
    manager.imported_scripts, manager.task_map, manager.task_errors = {}, {}, {}
    manager.task_executor = SimpleNamespace(onetime_tasks=[], trigger_tasks=[], feature_set=None,
                                            current_task=None)
    manager.app = SimpleNamespace(debug=False)
    manager.scene = None
    return manager


def test_declared_tasks_reload_and_delete_clean_up_instances_and_modules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'ok_import/demo'
    folder.mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps({
        'file_name': 'demo', 'tasks': [['entry', 'DemoTask']],
        'custom_tabs': [['page', 'Page']],
    }))
    (folder / 'entry.py').write_text(TASK_SOURCE)
    manager = make_manager()
    manager.load_imported_tasks()
    old, = manager.imported_scripts['demo']['tasks']
    assert old.import_namespace == 'demo'
    assert manager.imported_scripts['demo']['custom_tabs'] == [['page', 'Page']]
    manager._reload_tasks([old])
    replacement, = manager.imported_scripts['demo']['tasks']
    assert replacement is not old
    assert old.destroyed
    assert replacement in manager.task_map
    assert replacement.import_namespace == 'demo'
    manager.delete_imported_script('demo')
    assert not replacement.destroyed
    assert folder.exists() and replacement in manager.task_map
    manager.unload_imported_script('demo')  # Simulate normal application shutdown.
    from ok.core.plugin_staging import apply_pending_plugin_changes
    apply_pending_plugin_changes()
    assert replacement.destroyed
    assert not manager.task_map and not manager.imported_scripts
    assert not folder.exists()
    assert not any(str(folder) in str(getattr(module, '__file__', '')) for module in sys.modules.values())


def test_tab_only_plugin_does_not_scan_helper_classes_as_tasks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'ok_import/demo'
    folder.mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps({
        'file_name': 'demo', 'tasks': [], 'custom_tabs': [['entry', 'DemoTask']],
    }))
    (folder / 'entry.py').write_text(TASK_SOURCE)
    manager = make_manager()
    manager.load_imported_tasks()
    assert manager.imported_scripts['demo']['tasks'] == []
    assert manager.task_map == {}


def test_declared_tab_module_is_not_auto_imported_by_headless_task_loader(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'ok_import/demo'
    folder.mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps({
        'file_name': 'demo', 'custom_tabs': [['page', 'Page']],
    }))
    (folder / 'page.py').write_text('raise RuntimeError("Qt tab must not be imported by core")\nclass Page: pass')
    manager = make_manager()
    manager.load_imported_tasks()
    assert manager.imported_scripts['demo']['tasks'] == []
    assert manager.task_errors == {}


def test_declared_entry_modules_are_isolated_between_plugins(tmp_path):
    folders = [tmp_path / 'first', tmp_path / 'second']
    try:
        classes = []
        for number, folder in enumerate(folders):
            folder.mkdir()
            (folder / 'page.py').write_text(f'class Page:\n    identity = {number}\n')
            classes.append(plugins.import_plugin_class(folder, ('page', 'Page')))
        assert [cls.identity for cls in classes] == [0, 1]
        assert classes[0].__module__ != classes[1].__module__
    finally:
        for folder in folders:
            plugins.forget_plugin_modules(folder)


def test_delete_cannot_escape_plugin_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    manager = make_manager()
    manager.imported_scripts['demo'] = {'folder': str(outside), 'tasks': []}
    with pytest.raises(ValueError, match='directly inside'):
        manager.delete_imported_script('demo')
    assert outside.exists()
