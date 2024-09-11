import shutil
import subprocess
import sys

from ok.logging.Logger import get_logger
from ok.util.path import delete_if_exists

logger = get_logger(__name__)

import os
import fnmatch


def delete_files(
        blacklist_patterns=['opencv_videoio_ffmpeg*.dll', 'opengl32sw.dll', 'Qt6Quick.dll', 'Qt6Pdf.dll', 'Qt6Qml.dll',
                            'Qt6OpenGL.dll',
                            'Qt6OpenGL.pyd', '*.chm', '*.pdf', 'QtOpenGL.pyd',
                            'Qt6Network.dll', 'Qt6QmlModels.dll', 'Qt6VirtualKeyboard.dll', 'QtNetwork.pyd',
                            'Qt6Designer.dll'
            , 'openvino_pytorch_frontend.dll', 'openvino_tensorflow_frontend.dll', 'NEWS.txt',
                            'py_tensorflow_frontend.cp311-win_amd64.pyd', 'py_pytorch_frontend.cp311-win_amd64.pyd',
                            '*.exe'], whitelist_patterns=['adb.exe', 'python*.exe', '*pip*'], root_dir='python'):
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


def modify_venv_cfg(env_dir):
    python_dir = os.path.dirname(env_dir)
    file_path = os.path.join(env_dir, 'pyvenv.cfg')
    with open(file_path, 'r') as file:
        lines = file.readlines()

    with open(file_path, 'w') as file:
        for line in lines:
            if line.startswith('home ='):
                file.write(f'home = {python_dir}\n')
            elif line.startswith('executable ='):
                file.write(f'executable = {os.path.join(python_dir, "python.exe")}\n')
            elif line.startswith('command ='):
                file.write(f'command = {os.path.join(python_dir, "python.exe")} -m venv {env_dir}')
            else:
                file.write(line)


def get_env_path(name, dir=None):
    if dir is None:
        dir = os.getcwd()
    return os.path.join(dir, 'python', name)


def create_venv(name, dir=None):
    if dir is None:
        dir = os.getcwd()
    mini_python_exe = os.path.join(dir, 'python', 'python.exe')
    lenv_path = get_env_path(name, dir)
    ok = False
    if os.path.exists(lenv_path):
        logger.info(f'venv already exists: {lenv_path}')
        try:
            result = subprocess.run([os.path.join(lenv_path, 'Scripts', 'python.exe'), '--version'],
                                    capture_output=True,
                                    text=True)

            # Get the output
            output = result.stdout.strip() or result.stderr.strip()

            # Check if the output starts with "Python" and ends with a version number
            if output.startswith("Python") and output.split()[1].replace('.', '').isdigit():
                logger.info(f'venv check ok : {output}')
                ok = True
            else:
                logger.info(f'venv check error : {output}')
                kill_exe(lenv_path)
                delete_if_exists(lenv_path)
        except Exception as e:
            logger.error(f'venv check error : {e}')
            kill_exe(lenv_path)
    if not ok:
        delete_if_exists(lenv_path)
        # Execute the command to create a virtual environment
        result = subprocess.run([mini_python_exe, '-m', 'venv', lenv_path], check=True, capture_output=True, text=True)
        logger.info(f"Virtual environment {lenv_path} created successfully.")
        logger.info(result.stdout)
    modify_venv_cfg(env_dir=lenv_path)
    logger.info('modify venv.cfg done')
    return lenv_path


def kill_exe(relative_path):
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            if proc.info['name'] == 'adb.exe' and os.path.normpath(proc.info['exe']).startswith(
                    os.path.abspath(relative_path)):
                logger.info(f'try kill the exe {proc.info}')
                proc.kill()
    except Exception as e:
        logger.error(f'kill process error', e)


if __name__ == '__main__':
    print(find_line_in_requirements('requirements.txt', 'ok-script'))
    delete_files(
        ['opencv_videoio_ffmpeg', 'opengl32sw.dll', 'Qt6Quick.dll', 'Qt6Pdf.dll', 'Qt6Qml.dll', 'Qt6OpenGL.dll',
         'Qt6OpenGL.pyd', '*.chm', '*.pdf', 'QtOpenGL.pyd',
         'Qt6Network.dll', 'Qt6QmlModels.dll', 'Qt6VirtualKeyboard.dll', 'QtNetwork.pyd',
         'Qt6Designer.dll'
            , 'openvino_pytorch_frontend.dll', 'openvino_tensorflow_frontend.dll', 'NEWS.txt',
         'py_tensorflow_frontend.cp311-win_amd64.pyd', 'py_pytorch_frontend.cp311-win_amd64.pyd',
         '*.exe'], ['adb.exe', 't64.exe'], 'python-launcher-lib')
