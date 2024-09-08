import os
import re
import subprocess
import sys

from ok.logging.Logger import config_logger, get_logger
from ok.update.python_env import delete_files, \
    create_venv, find_line_in_requirements

logger = get_logger(__name__)


def replace_string_in_file(file_path, old_pattern, new_string):
    """
    Replace occurrences of old_pattern with new_string in the specified file using regex.

    :param file_path: Path to the file
    :param old_pattern: Regex pattern to be replaced
    :param new_string: Replacement string
    """

    # Read the file content
    with open(file_path, 'r') as file:
        content = file.read()

    # Replace the old pattern with the new string using regex
    new_content = re.sub(old_pattern, new_string, content)

    # Write the new content back to the file
    with open(file_path, 'w') as file:
        file.write(new_content)

    logger.info(f"Replaced pattern '{old_pattern}' with '{new_string}' in {file_path}")


def create_launcher_env(code_dir='.', build_dir='.'):
    full_version = find_line_in_requirements(os.path.join(code_dir, 'requirements.txt'), 'ok-script')
    if not full_version:
        logger.error('Could not find ok-script version in requirements.txt')
        sys.exit(1)
    logger.info(f'ok-script full_version: {full_version}')
    lenv_path = create_venv('launcher_env', os.path.join(build_dir))
    replace_string_in_file(os.path.join(code_dir, 'launcher.json'), r'ok-script(?:==[\d.]+)?', full_version)
    try:
        lenv_python_exe = os.path.join(lenv_path, 'Scripts', 'python.exe')
        params = [lenv_python_exe, "-m", "pip", "install", "PySide6-Fluent-Widgets==1.5.5", '--no-deps',
                  '--no-cache-dir']
        result = subprocess.run(params, check=True, capture_output=True, text=True)
        logger.info("install PySide6-Fluent-Widgets success")
        logger.info(result.stdout)

        params = [lenv_python_exe, "-m", "pip", "install",
                  full_version,
                  '--no-cache-dir']
        result = subprocess.run(params, check=True, capture_output=True, text=True)
        logger.info("install ok-script success")
        logger.info(result.stdout)
        delete_files(root_dir=lenv_path)
    except Exception as e:
        logger.error("An error occurred while creating the virtual environment.", e)
        sys.exit(1)


# python -m ok.gui.launcher.init_lenv
if __name__ == '__main__':
    config_logger(name='launcher')
    full_version = find_line_in_requirements('requirements.txt', 'ok-script')
    if not full_version:
        logger.error('Could not find ok-script version in requirements.txt')
        sys.exit(1)
    lenv_path = create_venv('launcher_env')
    replace_string_in_file('launcher.json', r'ok-script(?:==[\d.]+)?', full_version)
    try:
        lenv_python_exe = os.path.join(lenv_path, 'Scripts', 'python.exe')
        params = [lenv_python_exe, "-m", "pip", "install", "PySide6-Fluent-Widgets==1.5.5", '--no-deps',
                  '--no-cache-dir']
        result = subprocess.run(params, check=True, capture_output=True, text=True)
        logger.info("install PySide6-Fluent-Widgets success")
        logger.info(result.stdout)

        params = [lenv_python_exe, "-m", "pip", "install",
                  full_version,
                  '--no-cache-dir']
        result = subprocess.run(params, check=True, capture_output=True, text=True)
        logger.info("install ok-script success")
        logger.info(result.stdout)
        delete_files()
    except subprocess.CalledProcessError as e:
        logger.error("An error occurred while creating the virtual environment.")
        logger.error(e.stderr)
