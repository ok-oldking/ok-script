import hashlib
import os
import re
import shutil
import sys
import time


def get_path_relative_to_exe(*files):
    for file in files:
        if file is None:
            return
    if getattr(sys, 'frozen', False):
        # The application is running as a bundled executable
        application_path = os.path.abspath(sys.executable)
    else:
        # The application is running as a Python script
        application_path = os.path.abspath(sys.argv[0])
    the_dir = os.path.dirname(application_path)

    # Join the directory with the file paths
    path = os.path.join(the_dir, *files)

    # Normalize the path
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


def delete_if_exists(file_path):
    if os.path.exists(file_path):
        shutil.rmtree(file_path, onerror=handle_remove_error)


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
        return

    # Check if the path is a folder
    if not os.path.isdir(folder_path):
        print(f"The path {folder_path} is not a folder.")
        return

    # Delete all files in the folder
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)  # remove the file
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)  # remove dir and all contains
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


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
