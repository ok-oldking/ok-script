import filecmp
import os
import re
import subprocess

from ok import Logger
from ok.update.python_env import delete_files, \
    create_venv

logger = Logger.get_logger(__name__)


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


def create_repo_venv(python_dir, code_dir='.', last_env_folder=None, index_url="https://pypi.org/simple/",
                     no_cache=True):
    logger.info(f'create_repo_venv: {python_dir} {code_dir} {last_env_folder} {index_url}')
    lenv_path = create_venv(python_dir, code_dir, last_env_folder)
    # return
    try:
        python_executable = os.path.join(lenv_path, 'Scripts', 'python')
        if not os.path.exists(os.path.join(lenv_path, 'Scripts', 'pip-sync.exe')):
            logger.info(f'pip-sync.exe not found, install using pip')
            params_install = [python_executable, '-m', 'pip', "install", "pip-tools", "-i", index_url]
            if no_cache:
                params_install.append('--no-cache')
            print(f"Running command: {' '.join(params_install)}")
            result_install = subprocess.run(params_install, check=True, capture_output=True,
                                            encoding='utf-8',
                                            text=True)

            logger.info("\n--- pip install pip-tools Output ---")
            logger.info("Standard Output:")
            logger.info(result_install.stdout)
            logger.info("Standard Error:")
            logger.info(result_install.stderr)

        # Run pip-sync
        requirements = os.path.join(code_dir, 'requirements.txt')
        if last_env_folder:
            old_code_path = os.path.dirname(last_env_folder)
            old_requirements = os.path.join(old_code_path, 'requirements.txt')
        else:
            old_requirements = None

        if not last_env_folder or not files_exist(requirements, old_requirements) or not files_content_equal(
                requirements, old_requirements):
            params_sync = [python_executable, '-m', 'piptools', 'sync', requirements, '--python-executable',
                           python_executable]
            if not check_string_in_file(requirements, '--index-url'):
                if not check_string_in_file(requirements, '--extra-index-url'):
                    params_sync += ["-i", index_url]
            if no_cache:
                params_sync += ['--pip-args', '"--no-cache"']
            logger.info(f"\nRunning command: {' '.join(params_sync)}")
            result_sync = subprocess.run(params_sync, check=True, capture_output=True, encoding='utf-8',
                                         text=True)

            logger.info("\n--- pip-sync Output ---")
            logger.info("Standard Output:")
            logger.info(result_sync.stdout)
            logger.info("Standard Error:")
            logger.info(result_sync.stderr)
            logger.info("sync requirements success")
            if not last_env_folder:
                delete_files(root_dir=python_dir)
                delete_files(root_dir=lenv_path)
            logger.info(
                f"requirements not equal use pip-sync '{requirements}' and '{old_requirements}'")
        else:
            logger.info(
                f"requirements equal skip pip-sync '{requirements}' and '{old_requirements}' exist and their contents are equal.")
        return True
    except Exception as e:
        logger.error("An error occurred while creating the virtual environment.", e)


def check_string_in_file(filename, search_string):
    with open(filename, 'r') as file:
        content = file.read()
        return search_string in content


def files_exist(file1, file2):
    return file1 and file2 and os.path.isfile(file1) and os.path.isfile(file2)


def files_content_equal(file1, file2):
    return filecmp.cmp(file1, file2, shallow=False)
