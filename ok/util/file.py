import hashlib
import json
import math
import os
import re
import shutil
import sys
import time


def read_json_file(file_path) -> dict | None:
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        return None


def write_json_file(file_path, data):
    ensure_dir_for_file(file_path)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return True


def delete_if_exists(file_path):
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            shutil.rmtree(file_path, onerror=handle_remove_error)
        else:
            os.remove(file_path)


def get_path_relative_to_exe(*files):
    for file in files:
        if file is None:
            return
    frozen = getattr(sys, 'frozen', False)
    if frozen:
        # The application is running as a bundled executable
        application_path = os.path.abspath(sys.executable)
    else:
        # The application is running as a Python script
        application_path = os.path.abspath(sys.argv[0])
    # logger.debug(f'get_path_relative_to_exe application_path {application_path} frozen {frozen}')
    the_dir = os.path.dirname(application_path)

    # Join the directory with the file paths
    path = os.path.join(the_dir, *files)

    # Normalize the path
    normalized_path = os.path.normpath(path)

    if not os.path.exists(normalized_path):
        path = path = os.path.join(os.getcwd(), *files)
        normalized_path = os.path.normpath(path)

    return normalized_path


def get_relative_path(*files):
    for file in files:
        if file is None:
            return

    # Join the directory with the file paths
    path = os.path.join(os.getcwd(), *files)

    # Normalize the path
    normalized_path = os.path.normpath(path)

    return normalized_path


def install_path_isascii():
    path = get_path_relative_to_exe('')

    isascii = path.isascii()

    return isascii, path


def get_downloads_folder():
    """Return the user's Downloads folder, honoring custom Windows locations."""
    downloads_folder_id = '{374DE290-123F-4565-9164-39C4925E467B}'
    if sys.platform == 'win32':
        path = _get_windows_known_folder_path(downloads_folder_id) or _get_windows_user_shell_folder(downloads_folder_id)
        if path:
            return os.path.abspath(os.path.expandvars(path))
    return os.path.abspath(os.path.join(os.path.expanduser('~'), 'Downloads'))


def _get_windows_known_folder_path(folder_id):
    path_ptr = None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ('Data1', wintypes.DWORD),
                ('Data2', wintypes.WORD),
                ('Data3', wintypes.WORD),
                ('Data4', ctypes.c_ubyte * 8),
            ]

        folder_guid = GUID.from_buffer_copy(uuid.UUID(folder_id).bytes_le)
        path_ptr = wintypes.LPWSTR()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(folder_guid),
            0,
            None,
            ctypes.byref(path_ptr),
        )
        if hr == 0 and path_ptr.value:
            return path_ptr.value
    except Exception:
        return None
    finally:
        if path_ptr:
            try:
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            except Exception:
                pass
    return None


def _get_windows_user_shell_folder(folder_id):
    try:
        import winreg

        sub_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            path, _ = winreg.QueryValueEx(key, folder_id)
            return path
    except Exception:
        return None


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    # Get the absolute path of the current script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if 'site-packages' in base_dir:  # if ok is installed by pip
        return relative_path
    # Move up one directory level
    base_dir = os.path.dirname(base_dir)
    # Move up another directory level
    base_dir = os.path.dirname(base_dir)
    # Check if the '_MEIPASS' attribute exists in the 'sys' module (used by PyInstaller)
    # If it exists, set 'base_path' to its value; otherwise, use 'base_dir'
    base_path = getattr(sys, '_MEIPASS', base_dir)
    # Combine 'base_path' with 'relative_path' to form the absolute path to the resource
    return os.path.join(base_path, relative_path)


def ensure_dir_for_file(file_path):
    # Extract the directory from the file path
    directory = os.path.dirname(file_path)

    return ensure_dir(directory)


def ensure_dir(directory, clear=False):
    # Check if the directory is a file
    if os.path.isfile(directory):
        # If it is a file, delete it
        os.remove(directory)

    # Check if the directory exists
    if directory and not os.path.exists(directory):
        # If the directory does not exist, create it (including any intermediate directories)
        os.makedirs(directory)
    elif clear:
        clear_folder(directory)

    return directory


def delete_folders_starts_with(path, starts_with):
    if os.path.isdir(path):
        for folder_name in os.listdir(path):
            folder_path = os.path.join(path, folder_name)
            if os.path.isdir(folder_path) and folder_name.startswith(starts_with):
                shutil.rmtree(folder_path, onerror=handle_remove_error)


def handle_remove_error(func, path, exc_info):
    print(f"Error removing {path}: {exc_info}")
    os.chmod(path, 0o777)
    time.sleep(0.01)
    func(path)


def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '_', filename)


def clear_folder(folder_path):
    # Check if the folder exists
    if folder_path is None:
        return

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        # logger.info(f'makedirs {folder_path}')
        return

    # Check if the path is a folder
    if not os.path.isdir(folder_path):
        # logger.error(f"The path {folder_path} is not a folder.")
        return

    # Delete all files in the folder
    try:
        shutil.rmtree(folder_path)
    except OSError as e:
        # Retry mechanism: Windows sometimes locks the folder briefly
        # logger.error(f"Error removing tree: {e}. Retrying in 1s...")
        time.sleep(1)
        try:
            shutil.rmtree(folder_path)
        except Exception as e2:
            # logger.error(f"Failed to delete folder: {e2}")
            # If we can't delete the folder, fall back to the old method
            # (clearing contents manually) only as a last resort.
            return

    # 4. Recreate the empty folder
    try:
        os.makedirs(folder_path)
        # logger.info(f"Successfully cleared (recreated) {folder_path}")
    except Exception as e:
        pass
        # logger.error(f"Deleted folder but failed to recreate it: {e}")


def find_first_existing_file(filenames, directory):
    for filename in filenames:
        full_path = os.path.join(directory, filename)
        if os.path.isfile(full_path):
            return full_path
    return None


def get_path_in_package(base, file):
    the_dir = os.path.dirname(os.path.realpath(base))

    # Get the path of the file relative to the script
    return os.path.join(the_dir, file)


def dir_checksum(directory, excludes=None):
    if excludes is None:
        excludes = []
    md5_hash = hashlib.md5()

    # Iterate over all files in the directory
    for path, dirs, files in os.walk(directory):
        for name in files:
            # Skip files in the excludes list
            if name in excludes:
                continue

            filepath = os.path.join(path, name)

            # Open the file in binary mode and calculate its MD5 checksum
            with open(filepath, 'rb') as f:
                while True:
                    data = f.read(8192)
                    if not data:
                        break
                    md5_hash.update(data)

    # Return the hexadecimal representation of the checksum
    return md5_hash.hexdigest()


def find_folder_with_file(root_folder, target_file):
    # Check the root folder itself
    if target_file in os.listdir(root_folder):
        return root_folder

    # Iterate over all subfolders in the root folder
    for folder, subfolders, files in os.walk(root_folder):
        if target_file in files:
            return folder

    return None


def get_folder_size(folder_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
    return total_size  # Convert bytes to MB


def bytes_to_readable_size(size_bytes):
    """Converts bytes to a human-readable size.

    Args:
        size_bytes (int): The size in bytes.

    Returns:
        str: The human-readable size.
    """

    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s}{size_name[i]}"
