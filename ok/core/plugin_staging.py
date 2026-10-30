"""Persist plugin changes and apply them before importing plugin code."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from ok.core.events import communicate
from ok.core.plugins import write_plugin_source
from ok.core.script_packager import (
    get_ok_import_folder, import_script, inspect_script_archive, load_manifest,
    validate_plugin_manifest,
)
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)
STAGING_FOLDER = '.plugin-staging'
_PHASES = {'pending', 'applying', 'validating', 'rollback', 'failed', 'committed', 'recovery'}


def _paths(namespace, import_base=None):
    validate_plugin_manifest({'file_name': namespace})
    base = Path(import_base or get_ok_import_folder()).resolve()
    staging = base / STAGING_FOLDER
    operation = staging / namespace
    target = base / namespace
    for path in (staging, operation, target, operation / 'incoming', operation / 'previous'):
        if path.resolve() != path:
            raise ValueError('Plugin paths must be directly inside ok_import without links')
    return base, operation, target


def _write_operation(folder, operation):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder,
                                         prefix='.journal-', delete=False) as output:
            temporary = Path(output.name)
            json.dump(operation, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, folder / 'operation.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def pending_plugin_changes(import_base=None):
    base = Path(import_base or get_ok_import_folder()).resolve()
    staging = base / STAGING_FOLDER
    if not staging.exists():
        return {}
    if staging.resolve() != staging:
        raise ValueError('Plugin staging folder must not be a link')
    changes = {}
    for folder in staging.iterdir():
        if folder.name.startswith('.') or not folder.is_dir():
            continue
        if not any(folder.iterdir()):
            continue  # Cleanup may have been interrupted after removing the journal.
        try:
            _paths(folder.name, base)
            operation = json.loads((folder / 'operation.json').read_text(encoding='utf-8'))
            if (operation['namespace'] != folder.name or operation['action'] not in {'update', 'delete'}
                    or operation['phase'] not in _PHASES):
                raise ValueError('Invalid plugin operation')
            changes[folder.name] = operation
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Never load a potentially half-replaced plugin with a broken journal.
            changes[folder.name] = {'namespace': folder.name, 'action': 'update',
                                    'phase': 'recovery', 'invalid_journal': True, 'error': str(error)}
    return changes


def _prepare_operation(namespace, action, import_base=None):
    base, folder, target = _paths(namespace, import_base)
    if folder.exists() and not any(folder.iterdir()):
        folder.rmdir()
    if folder.exists():
        raise ValueError('This plugin already has a pending change; cancel it first')
    if not target.is_dir():
        raise ValueError('Plugin is not installed')
    folder.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.prepare-', dir=folder.parent))
    manifest = load_manifest(target)
    operation = {'namespace': namespace, 'action': action, 'phase': 'pending',
                 'script_name': manifest.get('script_name', namespace)}
    return base, folder, temporary, operation


def stage_plugin_update(archive_path, source=None, import_base=None):
    manifest = inspect_script_archive(archive_path)
    namespace = manifest['file_name']
    base, folder, temporary, operation = _prepare_operation(namespace, 'update', import_base)
    try:
        success, message, incoming = import_script(
            archive_path, import_base=temporary / 'extract',
            prepare_staging=lambda path: write_plugin_source(path, source),
        )
        if not success:
            raise ValueError(message)
        if validate_plugin_manifest(load_manifest(incoming))['file_name'] != namespace:
            raise ValueError('Staged archive belongs to a different plugin')
        os.replace(incoming, temporary / 'incoming')
        operation['version'] = manifest.get('version') or (source or {}).get('tag', '')
        _write_operation(temporary, operation)
        os.rename(temporary, folder)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    communicate.plugin_changes_updated.emit()
    return operation


def stage_plugin_delete(namespace, import_base=None):
    _base, folder, temporary, operation = _prepare_operation(namespace, 'delete', import_base)
    try:
        _write_operation(temporary, operation)
        os.rename(temporary, folder)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    communicate.plugin_changes_updated.emit()
    return operation


def cancel_pending_plugin_change(namespace, import_base=None):
    _base, folder, _target = _paths(namespace, import_base)
    operation = pending_plugin_changes(import_base).get(namespace)
    if operation is None:
        return
    if operation['phase'] not in {'pending', 'failed'}:
        raise ValueError('This plugin change must finish recovery on the next launch')
    shutil.rmtree(folder)
    communicate.plugin_changes_updated.emit()


def install_or_stage_plugin(archive_path, source=None, import_base=None):
    manifest = inspect_script_archive(archive_path)
    namespace = manifest['file_name']
    base, operation_folder, target = _paths(namespace, import_base)
    if operation_folder.exists() and any(operation_folder.iterdir()):
        raise ValueError('This plugin already has a pending change; cancel it first')
    if target.exists():
        stage_plugin_update(archive_path, source, base)
        return {'namespace': namespace, 'folder': str(target), 'restart_required': True,
                'message': 'Plugin update staged. Restart the application to apply it.'}
    success, message, folder = import_script(
        archive_path, import_base=base,
        prepare_staging=lambda path: write_plugin_source(path, source),
    )
    if not success:
        raise ValueError(message)
    return {'namespace': namespace, 'folder': folder, 'restart_required': False, 'message': message}


def _cleanup(folder, operation):
    # The durable committed marker precedes cleanup; an interrupted cleanup
    # cannot make the next launch roll back a known-good update or undo deletion.
    operation['phase'] = 'committed'
    _write_operation(folder, operation)
    try:
        for name in ('previous', 'incoming', 'extract'):
            path = folder / name
            if path.exists():
                shutil.rmtree(path)
        for path in folder.iterdir():
            if path.name != 'operation.json':
                path.unlink()
        (folder / 'operation.json').unlink()
        folder.rmdir()
    except OSError as error:
        logger.error('Plugin backup cleanup will be retried on the next launch', error)


def _rollback(folder, target, operation, error):
    previous, incoming = folder / 'previous', folder / 'incoming'
    try:
        if previous.exists():
            if target.exists():
                if incoming.exists():
                    raise ValueError('Cannot restore plugin over an unexpected installation')
                os.replace(target, incoming)
            os.replace(previous, target)
        elif (operation.get('had_previous') is False and not incoming.exists()
              and target.exists() and operation['action'] == 'update'):
            os.replace(target, incoming)
        operation.update(phase='failed', error=str(error))
    except Exception as failure:
        operation.update(phase='recovery', error=f'{error}; rollback failed: {failure}')
    _write_operation(folder, operation)


def apply_pending_plugin_changes(import_base=None):
    """Call once at startup, after the app mutex and before any plugin imports.

    An unconfirmed update from an earlier run is restored before loading code.
    Failed changes remain visible/cancellable, rather than repeatedly loading a
    broken update or partially deleting an installed plugin.
    """
    changes = pending_plugin_changes(import_base)
    root = Path(import_base or get_ok_import_folder()).resolve() / STAGING_FOLDER
    if root.exists():
        for preparation in root.glob('.prepare-*'):
            if preparation.is_dir() and preparation.resolve() == preparation:
                try:
                    shutil.rmtree(preparation)
                except OSError as error:
                    logger.error('Failed to clean interrupted plugin preparation', error)
    results = {}
    for namespace, operation in changes.items():
        folder = target = None
        try:
            _base, folder, target = _paths(namespace, import_base)
            phase = operation['phase']
            if phase == 'committed':
                _cleanup(folder, operation)
            elif phase in {'validating', 'rollback', 'applying', 'recovery'}:
                if operation.get('invalid_journal') and not (folder / 'previous').exists():
                    results[namespace] = dict(operation)
                    continue
                if operation['action'] == 'delete' and (folder / 'previous').exists() and not target.exists():
                    _cleanup(folder, operation)
                else:
                    _rollback(folder, target, operation,
                              operation.get('error', 'Previous launch did not confirm plugin initialization'))
            elif phase == 'pending':
                operation['had_previous'] = target.exists()
                operation['phase'] = 'applying'
                _write_operation(folder, operation)
                if operation['action'] == 'update':
                    incoming = folder / 'incoming'
                    manifest = validate_plugin_manifest(load_manifest(incoming))
                    if manifest['file_name'] != namespace:
                        raise ValueError('Staged archive belongs to a different plugin')
                    if target.exists():
                        os.replace(target, folder / 'previous')
                    os.replace(incoming, target)
                    operation['phase'] = 'validating'
                    _write_operation(folder, operation)
                else:
                    if target.exists():
                        os.replace(target, folder / 'previous')
                    _cleanup(folder, operation)
            results[namespace] = dict(operation)
        except Exception as error:
            logger.error(f'Failed to apply plugin change: {namespace}', error)
            if folder is not None and folder.exists():
                try:
                    _rollback(folder, target, operation, error)
                except Exception as failure:
                    logger.error(f'Plugin recovery could not be recorded: {namespace}', failure)
            results[namespace] = {**operation, 'error': str(error)}
    return results


def finish_plugin_update(namespace, error=None, import_base=None):
    """Confirm task/page initialization, or arrange restoration on next launch."""
    operation = pending_plugin_changes(import_base).get(namespace)
    if operation is None or operation['phase'] != 'validating':
        return
    _base, folder, _target = _paths(namespace, import_base)
    if error:
        operation.update(phase='rollback', error=str(error))
        _write_operation(folder, operation)
    else:
        _cleanup(folder, operation)
    communicate.plugin_changes_updated.emit()
