import os
import re
import sys


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


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(base_dir)
    base_dir = os.path.dirname(base_dir)
    base_path = getattr(sys, '_MEIPASS', base_dir)
    return os.path.join(base_path, relative_path)


def ensure_dir_for_file(file_path):
    # Extract the directory from the file path
    directory = os.path.dirname(file_path)

    return ensure_dir(directory)


def ensure_dir(directory):
    # Check if the directory exists
    if directory and not os.path.exists(directory):
        # If the directory does not exist, create it (including any intermediate directories)
        os.makedirs(directory)
    return directory


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
        # Check if the path is a file
        if os.path.isfile(file_path):
            os.remove(file_path)


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
