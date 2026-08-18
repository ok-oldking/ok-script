import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from ok.util.file import get_downloads_folder
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

MANIFEST_FILE = 'manifest.json'
OK_TASKS_FOLDER = 'ok_tasks'
OK_IMPORT_FOLDER = 'ok_import'
MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000


def get_ok_tasks_folder():
    return os.path.join(os.getcwd(), OK_TASKS_FOLDER)


def get_ok_import_folder():
    return os.path.join(os.getcwd(), OK_IMPORT_FOLDER)


def load_manifest(folder=None):
    """Load manifest.json from the given folder (default: ok_tasks)."""
    if folder is None:
        folder = get_ok_tasks_folder()
    manifest_path = os.path.join(folder, MANIFEST_FILE)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
    return {}


def save_manifest(manifest, folder=None):
    """Save manifest.json to the given folder (default: ok_tasks)."""
    if folder is None:
        folder = get_ok_tasks_folder()
    os.makedirs(folder, exist_ok=True)
    manifest_path = os.path.join(folder, MANIFEST_FILE)
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save manifest: {e}")


def get_task_files(folder=None):
    """Get list of .py files in ok_tasks folder."""
    if folder is None:
        folder = get_ok_tasks_folder()
    if not os.path.exists(folder):
        return []
    return [f for f in os.listdir(folder) if f.endswith('.py')]


def validate_filename(name):
    """Validate filename: English letters, numbers, underscores, hyphens, dots only."""
    return bool(re.match(r'^[A-Za-z0-9_\-\.]+$', name)) and len(name) > 0


def _validate_package_id(name):
    """Validate the manifest identifier used as an import directory name."""
    return validate_filename(name) and name not in {'.', '..'} and Path(name).name == name


def validate_archive(zf, max_size=MAX_ARCHIVE_SIZE):
    """Reject unsafe or unreasonably large archive members before extraction."""
    members = zf.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("Script package contains too many files")

    total_size = 0
    for member in members:
        raw_name = member.filename.replace('\\', '/')
        path = PurePosixPath(raw_name)
        if (not raw_name or '\x00' in raw_name or raw_name.startswith('/') or path.is_absolute()
                or (path.parts and ':' in path.parts[0])
                or any(part in {'', '.', '..'} for part in path.parts)):
            raise ValueError("Unsafe script package path")
        # Unix symlinks can otherwise escape the destination during later use.
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("Script package cannot contain symbolic links")
        total_size += max(0, member.file_size)
        if total_size > max_size:
            raise ValueError("Script package is too large")
    return members


def export_script(selected_files, file_name, script_name, version, task_folder=None, output_folder=None):
    """
    Export selected tasks and ok_tasks contents as a .okscript file.

    Args:
        selected_files: list of .py filenames to include
        file_name: the export file name (without extension)
        script_name: the script name for display
        version: version string

    Returns:
        (success: bool, message: str, output_path: str)
    """
    task_folder = os.path.abspath(task_folder or get_ok_tasks_folder())
    if not os.path.exists(task_folder):
        return False, "ok_tasks folder does not exist", ""

    # Save manifest
    manifest = {
        'file_name': file_name,
        'script_name': script_name,
        'version': version
    }
    save_manifest(manifest, task_folder)

    # Build zip
    downloads = os.path.abspath(output_folder or get_downloads_folder())
    os.makedirs(downloads, exist_ok=True)
    output_path = os.path.join(downloads, f"{file_name}.okscript")

    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add selected .py files
            for py_file in selected_files:
                if Path(py_file).name != py_file or not py_file.endswith('.py'):
                    raise ValueError(f"Invalid task filename: {py_file}")
                full_path = os.path.join(task_folder, py_file)
                if os.path.exists(full_path):
                    zf.write(full_path, py_file)

            # Add manifest.json
            manifest_path = os.path.join(task_folder, MANIFEST_FILE)
            if os.path.exists(manifest_path):
                zf.write(manifest_path, MANIFEST_FILE)

            # Add all other files and folders (assets, etc.), excluding .py files already handled
            for root, dirs, files in os.walk(task_folder):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for fname in files:
                    if fname == MANIFEST_FILE:
                        continue  # Already added
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, task_folder)
                    # Skip .py files (already handled via selected_files)
                    if rel_path.endswith('.py'):
                        continue
                    zf.write(full_path, rel_path)

        logger.info(f"Exported script to {output_path}")
        return True, output_path, output_path
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return False, str(e), ""


def import_script(okscript_path, import_base=None, max_size=MAX_ARCHIVE_SIZE):
    """
    Import a .okscript file.

    Args:
        okscript_path: path to the .okscript file

    Returns:
        (success: bool, message: str, import_folder: str)
    """
    if not os.path.exists(okscript_path):
        return False, "File does not exist", ""

    try:
        with zipfile.ZipFile(okscript_path, 'r') as zf:
            members = validate_archive(zf, max_size=max_size)
            # Read manifest first
            if MANIFEST_FILE not in zf.namelist():
                return False, "Invalid .okscript file: missing manifest.json", ""

            manifest_data = json.loads(zf.read(MANIFEST_FILE).decode('utf-8'))
            file_name = str(manifest_data.get('file_name', '')).strip()
            if not _validate_package_id(file_name):
                return False, "Invalid manifest: invalid file_name", ""

            # Extract to ok_import/<file_name>/
            import_base = os.path.abspath(import_base or get_ok_import_folder())
            os.makedirs(import_base, exist_ok=True)
            import_folder = os.path.join(import_base, file_name)
            staging_root = tempfile.mkdtemp(prefix='.okscript-', dir=import_base)
            staging_folder = os.path.join(staging_root, file_name)
            backup_folder = os.path.join(staging_root, '.previous')
            os.makedirs(staging_folder)
            try:
                zf.extractall(staging_folder, members=members)
                if not os.path.isfile(os.path.join(staging_folder, MANIFEST_FILE)):
                    raise ValueError("Invalid .okscript file: missing manifest.json")
                if os.path.exists(import_folder):
                    shutil.move(import_folder, backup_folder)
                try:
                    shutil.move(staging_folder, import_folder)
                except Exception:
                    if os.path.exists(backup_folder) and not os.path.exists(import_folder):
                        shutil.move(backup_folder, import_folder)
                    raise
                if os.path.exists(backup_folder):
                    shutil.rmtree(backup_folder)
            finally:
                shutil.rmtree(staging_root, ignore_errors=True)

        logger.info(f"Imported script to {import_folder}")
        return True, f"Imported '{manifest_data.get('script_name', file_name)}'", import_folder
    except Exception as e:
        logger.error(f"Import failed: {e}")
        return False, str(e), ""


def scan_import_folders():
    """
    Scan ok_import/ for all valid imported scripts.

    Returns:
        list of dict: [{
            'folder': str,
            'file_name': str,
            'script_name': str,
            'version': str,
            'has_features': bool
        }]
    """
    import_base = get_ok_import_folder()
    results = []

    if not os.path.exists(import_base):
        return results

    for entry in os.listdir(import_base):
        folder = os.path.join(import_base, entry)
        if not os.path.isdir(folder):
            continue

        manifest_path = os.path.join(folder, MANIFEST_FILE)
        if not os.path.exists(manifest_path):
            logger.warning(f"Skipping import folder {entry}: no manifest.json")
            continue

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            coco_path = os.path.join(folder, 'assets', 'coco_annotations.json')
            has_features = os.path.exists(coco_path)

            results.append({
                'folder': folder,
                'file_name': manifest.get('file_name', entry),
                'script_name': manifest.get('script_name', entry),
                'version': manifest.get('version', ''),
                'has_features': has_features
            })
        except Exception as e:
            logger.error(f"Failed to read manifest in {folder}: {e}")

    return results
