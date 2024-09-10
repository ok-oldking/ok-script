import os.path
import shutil
import subprocess
import sys

import git

from ok.config.Config import Config
from ok.logging.Logger import config_logger, get_logger
from ok.update.GitUpdater import copy_exe_files, fix_version_in_repo
from ok.update.init_launcher_env import create_launcher_env
from ok.util.path import dir_checksum, delete_if_exists

logger = get_logger(__name__)


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
        profile = sys.argv[2]

        logger.info(f'Tag: {tag}')
        logger.info(f'Profile: {profile}')
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
        python_src = os.path.join(mini_python, 'Python_3.11.9')
        
        shutil.copytree(python_src, python_dir)

        logger.info(f'copied {python_src} to {python_dir}')

        git_dir = os.path.join(mini_python, 'git_2.46.0_win_64')
        target_git_dir = os.path.join(python_dir, 'git')
        shutil.copytree(git_dir, target_git_dir)

        logger.info(f'copied {git_dir} to {target_git_dir}')

        current_repo = git.Repo(os.getcwd())
        url = current_repo.remote('origin').url
        logger.info(f'Repository URL: {url}')

        repo_dir = os.path.join(build_dir, 'repo', tag)
        build_repo = git.Repo.clone_from(url, repo_dir, branch=tag, depth=1)
        logger.info(f'Cloned repository to: {repo_dir}')

        fix_version_in_repo(repo_dir, tag)

        delete_if_exists(os.path.join(repo_dir, '.git'))
        logger.info(f'Deleted .git directory in: {repo_dir}')

        copy_exe_files(repo_dir, build_dir)

        create_launcher_env(repo_dir, build_dir)

        config = Config('launcher', {
            'profile_name': profile,
            'app_dependencies_installed': False,
            'app_version': tag,
            'launcher_version': tag
        }, folder=os.path.join(build_dir, 'configs'))
        logger.info('Configuration created successfully.')

    except Exception as e:
        logger.info(f'Error: {e}')
        sys.exit(1)
