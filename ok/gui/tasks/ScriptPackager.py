import json
import os
import re
import shutil
import zipfile

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

MANIFEST_FILE = 'manifest.json'
OK_TASKS_FOLDER = 'ok_tasks'
OK_IMPORT_FOLDER = 'ok_import'


def get_ok_tasks_folder():
    return os.path.join(os.getcwd(), OK_TASKS_FOLDER)


def get_ok_import_folder():
    return os.path.join(os.getcwd(), OK_IMPORT_FOLDER)


def get_downloads_folder():
    """Get the user's Downloads folder."""
    try:
        import winreg
        sub_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            downloads_path = winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')[0]
            downloads_path = os.path.expandvars(downloads_path)
            if os.path.exists(downloads_path):
                return downloads_path
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Downloads')


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


def export_script(selected_files, file_name, script_name, version):
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
    task_folder = get_ok_tasks_folder()
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
    downloads = get_downloads_folder()
    output_path = os.path.join(downloads, f"{file_name}.okscript")

    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add selected .py files
            for py_file in selected_files:
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


def import_script(okscript_path):
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
            # Read manifest first
            if MANIFEST_FILE not in zf.namelist():
                return False, "Invalid .okscript file: missing manifest.json", ""

            manifest_data = json.loads(zf.read(MANIFEST_FILE).decode('utf-8'))
            file_name = manifest_data.get('file_name', '')
            if not file_name:
                return False, "Invalid manifest: missing file_name", ""

            # Extract to ok_import/<file_name>/
            import_base = get_ok_import_folder()
            import_folder = os.path.join(import_base, file_name)

            # Clean existing import folder
            if os.path.exists(import_folder):
                shutil.rmtree(import_folder)

            os.makedirs(import_folder, exist_ok=True)
            zf.extractall(import_folder)

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
