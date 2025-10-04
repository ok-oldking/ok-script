import os.path
import shutil
import subprocess
import sys

import git

from ok import Config
from ok import config_logger, Logger
from ok import dir_checksum, delete_if_exists
from ok.update.GitUpdater import copy_exe_files, remove_ok_requirements
from ok.update.init_launcher_env import create_repo_venv

logger = Logger.get_logger(__name__)


def write_checksum_to_file(folder_path):
    # Call the dir_checksum function
    checksum = dir_checksum(folder_path)

    # Write the checksum to a file named 'md5.txt' in the same folder
    file = os.path.join(folder_path, 'md5.txt')
    with open(file, 'w') as file:
        file.write(checksum)
    logger.info(f'write checksum {checksum} to {file}')


def get_git_exe_location():
    # Run the 'where' command to find git.exe location
    result = subprocess.run(['where', 'git'], capture_output=True, text=True, check=True)
    return result.stdout.strip()


if __name__ == "__main__":
    config_logger(name='build')
    try:
        # Get the folder path from the command line arguments
        tag = sys.argv[1]
        files_filename = sys.argv[2]

        logger.info(f'Tag: {tag}')
        build_dir = os.path.join(os.getcwd(), 'dist')
        delete_if_exists(build_dir)
        logger.info(f'Build directory: {build_dir}')

        mini_python = os.path.join(os.getcwd(), 'mini_python')
        if os.path.isdir(mini_python):
            python_repo = git.Repo(mini_python)
            origin = python_repo.remotes.origin
            origin.pull()
        else:
            build_repo = git.Repo.clone_from('https://github.com/ok-oldking/mini_python', mini_python,
                                             depth=1)
        python_dir = os.path.join(build_dir, 'python')
        python_src = os.path.join(mini_python, 'Python_3.12.6_win_64')

        shutil.copytree(python_src, python_dir)

        logger.info(f'copied {python_src} to {python_dir}')

        git_dir = os.path.join(mini_python, 'git_2.46.0_win_64')
        target_git_dir = os.path.join(python_dir, 'git')
        shutil.copytree(git_dir, target_git_dir)

        logger.info(f'copied {git_dir} to {target_git_dir}')

        repo_dir = os.path.join(build_dir, 'repo', tag)

        os.makedirs(repo_dir, exist_ok=True)

        # Read the list of files from the file
        try:
            with open(files_filename, 'r') as file:
                files_to_copy = [line.strip() for line in file.readlines()]
        except FileNotFoundError:
            print(f"Error: File '{files_filename}' not found.")
            sys.exit(1)

        logger.info(f'start to copy files {files_to_copy} to: {repo_dir}')

        for item in files_to_copy:
            if os.path.isfile(item):
                shutil.copy(item, repo_dir)  # Copy file
            elif os.path.isdir(item):
                shutil.copytree(item, os.path.join(repo_dir, os.path.basename(item)))  # Copy directory

        remove_ok_requirements(repo_dir, tag)

        delete_if_exists(os.path.join(repo_dir, '.git'))
        logger.info(f'Deleted .git directory in: {repo_dir}')

        copy_exe_files(repo_dir, build_dir)

        if not create_repo_venv(python_dir, repo_dir, no_cache=False):
            sys.exit(1)

        config = Config('launcher', {
            'profile_index': 0,
            'app_dependencies_installed': False,
            'app_version': tag,
            'launcher_version': tag
        }, folder=os.path.join(build_dir, 'configs'))
        logger.info('Configuration created successfully.')

    except Exception as e:
        logger.error(f'Error:', e)
        sys.exit(1)
