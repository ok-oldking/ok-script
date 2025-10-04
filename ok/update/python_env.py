import os
import shutil
import subprocess
import sys

from ok import Logger

logger = Logger.get_logger(__name__)

import fnmatch


def delete_files(
        blacklist_patterns=['opencv_videoio_ffmpeg*.dll', 'opengl32sw.dll', 'Qt6Quick.dll', 'Qt6Pdf.dll', 'Qt6Qml.dll',
                            'Qt6OpenGL.dll',
                            'Qt6OpenGL.pyd', '*.chm', '*.pdf', 'QtOpenGL.pyd',
                            'Qt6Network.dll', 'Qt6QmlModels.dll', 'Qt6VirtualKeyboard.dll', 'QtNetwork.pyd',
                            'Qt6Designer.dll'
            , 'openvino_pytorch_frontend.dll', 'openvino_tensorflow_frontend.dll', 'NEWS.txt',
                            'py_tensorflow_frontend.cp311-win_amd64.pyd', 'py_pytorch_frontend.cp311-win_amd64.pyd',
                            '__pycache__',
                            '*.exe'],
        whitelist_patterns=['adb.exe', 'git.exe', 'git*exe', 't64.exe', 'w64.exe', 'cli-64.exe', 'cli.exe',
                            'python*.exe',
                            '*pip*'],
        root_dir='python'):
    """
    Delete files matching the given patterns in all directories starting from root_dir,
    except those matching the whitelist patterns.

    :param blacklist_patterns: List of file names or patterns to match.
    :param whitelist_patterns: List of file names or patterns to exclude from deletion.
    :param root_dir: Root directory to start the search from.
    """
    if whitelist_patterns is None:
        whitelist_patterns = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        if blacklist_patterns is None:
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if any(fnmatch.fnmatch(filename, wp) for wp in whitelist_patterns):
                    print(f"Skipped (whitelisted): {file_path}")
                    continue
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted: {file_path}")
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting {file_path}", e)
                    print(f"Error deleting {file_path}", e)
        else:
            for pattern in blacklist_patterns:
                for filename in fnmatch.filter(filenames, pattern):
                    file_path = os.path.join(dirpath, filename)
                    if any(fnmatch.fnmatch(filename, wp) for wp in whitelist_patterns):
                        print(f"Skipped (whitelisted): {file_path}")
                        continue
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted: {file_path}")
                        print(f"Deleted: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}", e)
                        print(f"Error deleting {file_path}", e)


def find_line_in_requirements(file_path, search_term, encodings=['utf-8', 'utf-16', 'ISO-8859-1', 'cp1252']):
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                for line in file:
                    if search_term in line:
                        return line.strip()
            return None
        except Exception as e:
            print(f"Error with encoding {encoding}: {e}")
    return None


def get_base_python_exe():
    # Check if running inside a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # Get the path to the virtual environment's pyvenv.cfg file
        venv_cfg_path = os.path.join(sys.prefix, 'pyvenv.cfg')

        if os.path.exists(venv_cfg_path):
            with open(venv_cfg_path, 'r') as file:
                for line in file:
                    if line.startswith('home = '):
                        parent_python_path = line.split('=')[1].strip()
                        parent_python_exe = os.path.join(parent_python_path, 'python.exe')
                        return parent_python_exe
        else:
            print("pyvenv.cfg not found.")
    else:
        # Return the current Python executable location
        return sys.executable


def copy_python_files(python_dir, destination_dir):
    # Check if destination directory exists
    if os.path.exists(destination_dir):
        logger.info(f"Destination directory {destination_dir} already exists. Exiting without copying.")
        return

    # Create the destination directory
    os.makedirs(destination_dir, exist_ok=True)

    # Define the patterns to copy
    patterns_to_copy = ['*.exe', '*.dll', 'DLLs', 'Lib']

    # Check top-level files
    # Check top-level files
    for file_name in os.listdir(python_dir):
        file_path = os.path.join(python_dir, file_name)
        if os.path.isfile(file_path) and any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns_to_copy):
            shutil.copy(file_path, destination_dir)
            logger.info(f"Copied file {file_name} to {destination_dir}")

    # Check top-level subfolders
    for item in os.listdir(python_dir):
        item_path = os.path.join(python_dir, item)
        if os.path.isdir(item_path):
            if any(fnmatch.fnmatch(item, pattern) for pattern in patterns_to_copy):
                destination_path = os.path.join(destination_dir, item)
                shutil.copytree(item_path, destination_path)
                logger.info(f"Copied folder {item} to {destination_dir}")


def modify_venv_cfg(env_dir, python_dir):
    """
    Modifies the pyvenv.cfg file in a virtual environment.
    Adds missing lines if they don't exist.
    """

    if not os.path.isabs(env_dir):
        env_dir = os.path.abspath(env_dir)
    if not os.path.isabs(python_dir):
        python_dir = os.path.abspath(python_dir)
    os.environ['VIRTUAL_ENV'] = env_dir
    logger.info(f'modify_venv_cfg {env_dir} {python_dir}')

    file_path = os.path.join(env_dir, 'pyvenv.cfg')
    if not os.path.exists(file_path):
        logger.info(f"No pyvenv.cfg found in {env_dir}")
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(f"home = {python_dir}\n")
            file.write(f"executable = {os.path.join(python_dir, 'python.exe')}\n")
            return

    required_lines = {
        'home': f'home = {python_dir}\n',
        'executable': f'executable = {os.path.join(python_dir, "python.exe")}\n',
        'command': f'command = {os.path.join(python_dir, "python.exe")} -m venv {env_dir}\n',
        'base-executable': f'base-executable = {os.path.join(python_dir, "python.exe")}\n',
        'base-exec-prefix': f'base-exec-prefix = {python_dir}\n',
        'base-prefix': f'base-prefix = {python_dir}\n',
    }

    existing_lines = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            for key in required_lines:
                if line.startswith(key + ' ='):
                    existing_lines[key] = line.strip()  # Store the line without trailing newline
                    break  # prevent double check same line

    with open(file_path, 'w', encoding='utf-8') as file:
        for key, required_line in required_lines.items():
            if key in existing_lines:
                file.write(existing_lines[key] + '\n')
            else:
                logger.info(f"Adding missing line: {required_line.strip()} to pyvenv.cfg")
                file.write(required_line)


def get_env_path(name, dir=None):
    if dir is None:
        dir = os.getcwd()
    return os.path.join(dir, 'python', name)


def create_venv(python_dir, code_dir, last_env_folder):
    mini_python_exe = os.path.join(python_dir, 'python.exe')
    if not os.path.exists(mini_python_exe):
        mini_python_exe = sys.executable
        logger.info(f"No mini_python_exe change to current python {mini_python_exe}")
    new_venv_dir = os.path.join(code_dir, '.venv')
    if os.path.exists(new_venv_dir):
        shutil.rmtree(new_venv_dir)
    result = subprocess.run([mini_python_exe, '-m', 'venv', '--copies', new_venv_dir],
                            capture_output=True, encoding='utf-8',
                            text=True)
    logger.info(f'create venv {new_venv_dir} {result.stdout}')
    if last_env_folder:
        if os.path.exists(last_env_folder):
            copytree_no_overwrite(last_env_folder, new_venv_dir)
            logger.info(f"copied new venv folder {new_venv_dir}")
    logger.info('modify venv.cfg done')
    return new_venv_dir


def copytree_no_overwrite(src, dst):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        # Exclude folders named '__pycache__' and those starting with '~'
        if os.path.isdir(s) and (item == '__pycache__' or item.startswith('~')):
            continue

        if os.path.isdir(s):
            if not os.path.exists(d):
                logger.debug(f'copy tree {s} -> {d}')
                shutil.copytree(s, d, copy_function=shutil.copy2, dirs_exist_ok=True)
            else:
                copytree_no_overwrite(s, d)
        else:
            if not os.path.exists(d):
                shutil.copy2(s, d)
                logger.debug(f'copying {s} -> {d}')
            else:
                logger.debug(f'skip copy {s} -> {d}')
