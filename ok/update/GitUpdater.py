import importlib
import json
import locale
import math
import os
import re
import shutil
import subprocess
import sys
from functools import cmp_to_key

import git
from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.gui.launcher.python_env import create_venv, delete_files
from ok.gui.util.Alert import alert_error
from ok.logging.LogTailer import LogTailer
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler
from ok.util.path import delete_if_exists, get_relative_path

logger = get_logger(__name__)

repo_path = get_relative_path(os.path.join('update', "repo"))


class GitUpdater:

    def __init__(self, app_config, exit_event):
        self.exit_event = exit_event
        self.config = app_config.get('git_update')
        self.version = app_config.get('version')
        self.debug = app_config.get('debug')
        self.repo = None
        self.handler = Handler(exit_event, self.__class__.__name__)
        self.launcher_configs = []
        self.launcher_config = Config('launcher', {'profile_name': '', 'source': self.get_default_source(),
                                                   'dependencies_installed': False, 'version': self.version})
        self.url = self.get_current_source()['git_url']
        self.launch_profiles = []
        self.load_current_ver()

    def load_current_ver(self):
        path = os.path.join('repo', self.version)
        self.launch_profiles = self.read_launcher_config(path)

    def get_current_profile(self):
        return next((obj for obj in self.launch_profiles if obj['name'] == self.launcher_config.get('profile_name')),
                    None)

    def update_source(self, text):
        self.launcher_config['source'] = text

    def start_app(self):
        try:
            # Run pip install command

            new_ver = self.launcher_config['version']
            entry = self.get_current_profile()['entry']
            script_path = os.path.join('repo', new_ver, entry)

            # startupinfo = subprocess.STARTUPINFO()
            # startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # cwd = os.getcwd()
            python_path = os.path.join('python', 'app_env', 'Scripts', 'pythonw.exe')
            # Launch the script detached from the current process
            logger.info(f'launching {python_path} {script_path}')
            process = subprocess.Popen(
                [python_path, script_path],
                # stderr=subprocess.PIPE,
                # stdout=subprocess.PIPE,
                # startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

            # subprocess.Popen(game_path, cwd=os.path.dirname(game_path), close_fds=True,
            #                  creationflags=subprocess.CREATE_NEW_CONSOLE)

            # Get the process ID (PID)
            pid = process.pid
            logger.info(f"Process ID (PID): {pid}")

            log_tailer = LogTailer(os.path.join('logs', 'ok-script.log'), self.exit_event)
            log_tailer.start()
            # Print the stdout and stderr in real-time
            # while True:
            #     output = process.stdout.readline() or process.stderr.readline()
            #     if output == '' and process.poll() is not None:
            #         break
            #     if output:
            #         logger.info(decode_and_clean(output.strip()))
            #
            # # Print any remaining stderr
            # stderr = process.communicate()[1]
            # if stderr:
            #     logger.error(decode_and_clean(stderr.strip()))
            #
            # # Check if the process was successfully launched
            # if process.poll() is None:
            #     logger.info("Process successfully started.")
            # else:
            #     logger.error("Failed to launch the process.")
            #
            #     # Read the output and error streams
            # stdout, stderr = process.communicate()
            #
            # # Print the output and error streams
            # if stdout:
            #     logger.info("Output:\n", stdout)
            # if stderr:
            #     logger.error("Errors:\n", stderr)
            #
            # # Check if the process was successfully launched
            # if process.returncode == 0:
            #     logger.info("Process returncode success.")
            # else:
            #     logger.error(f"Process returncode error. {process.returncode}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    def install_package(self, package_name, app_env_path):
        try:
            # Run pip install command
            app_env_python_exe = os.path.join(app_env_path, 'Scripts', 'python.exe')
            params = [app_env_python_exe, "-m", "pip", "install"] + package_name.split() + ['-i',
                                                                                            self.get_current_source()[
                                                                                                'pip_url'],
                                                                                            '--no-cache-dir']
            logger.info(f'executing pip install with: {params}')
            process = subprocess.Popen(
                params,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Print the stdout and stderr in real-time
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    logger.info(output.strip())

            # Print any remaining stderr
            stderr = process.communicate()[1]
            if stderr:
                logger.error(stderr.strip())

            # Check if the installation was successful
            if process.returncode == 0:
                logger.info(f"Package '{package_name}' installed successfully.")
                return True
            else:
                logger.error(f"Failed to install package '{package_name}'.")
                alert_error(f'Failed to install package. {package_name}')
                return
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    def update_to_version(self, version):
        self.handler.post(lambda: self.do_update_to_version(version))

    def read_launcher_config(self, path):
        launch_profiles = []
        if os.path.exists(path):
            with open(os.path.join(path, 'launcher.json'), 'r') as file:
                launch_profiles = json.load(file)
                logger.info(f'read launcher config success, {launch_profiles}')
        name = self.launcher_config.get('profile_name')
        if any(obj.get('name') == name for obj in launch_profiles):
            self.launcher_config['profile_name'] = name
        elif launch_profiles:
            self.launcher_config['profile_name'] = launch_profiles[0]['name']
        else:
            self.launcher_config['profile_name'] = ''
        self.launch_profiles = launch_profiles
        communicate.launcher_profiles.emit(launch_profiles)
        return launch_profiles

    def install_dependencies(self):
        app_env_path = create_venv('app_env')
        profile = self.get_current_profile()
        logger.info(f'installing dependencies for {profile}')
        if profile:
            for dependency in profile['install_dependencies']:
                if not self.install_package(dependency, app_env_path):
                    logger.error(f'failed to install {dependency}')
                    return False
            delete_files()
            return True

    def run(self):
        if self.handler.post(self.do_run, skip_if_running=True, remove_existing=True):
            communicate.update_running.emit(True)

    def do_run(self):
        if not self.launcher_config.get('dependencies_installed'):
            if not self.install_dependencies():
                communicate.update_running.emit(False)
                return False

        self.start_app()
        logger.info('start_app end')

    def do_update_to_version(self, version):
        try:
            self.config['dependencies_installed'] = False
            path = os.path.join('repo', version)
            logger.info(f'start cloning repo {path}')
            delete_if_exists(path)
            repo = git.Repo.clone_from(self.url, path, branch=version, depth=1)
            logger.info(f'clone repo success {path}')
            self.launch_profiles = self.read_launcher_config(path)
            self.launcher_config['version'] = version
            self.launcher_config['dependencies_installed'] = False
            communicate.clone_version.emit(None)
            communicate.update_running.emit(False)
        except Exception as e:
            logger.error('do_update_to_version error', e)
            communicate.clone_version.emit(str(e))
            communicate.update_running.emit(False)

    def list_all_versions(self):
        if self.handler.post(self.do_list_all_versions, skip_if_running=True):
            communicate.update_running.emit(True)
            communicate.versions.emit(None)

    def do_list_all_versions(self):
        try:
            logger.info(f'start fetching remote version {self.url}')
            remote_refs = git.cmd.Git().ls_remote(self.url, tags=True)

            # Parse the output to get tag names
            tags = []
            for line in remote_refs.splitlines():
                if 'refs/tags/' in line:
                    tag = line.split('refs/tags/')[1]
                    if '^{}' not in tag and is_valid_version(tag):
                        tags.append(tag)
            tags = sorted(tags, key=cmp_to_key(is_newer_or_eq_version), reverse=True)
            logger.info(f'done fetching remote version size {len(tags)}')
            communicate.update_running.emit(False)
            communicate.versions.emit(tags)
        except Exception as e:
            logger.error('fetch remote version list error', e)
            alert_error('Fetch remote version list error!')
            communicate.update_running.emit(False)
            communicate.versions.emit(None)

    def get_sources(self):
        return self.config['sources']

    def get_default_source(self):
        if 'cn' in locale.getdefaultlocale()[0].lower():
            for source in self.config['sources']:
                if source['name'] == 'China':
                    return source
        return self.config['sources'][0]['name']

    def get_current_source(self):
        for source in self.config['sources']:
            if source['name'] == self.launcher_config['source']:
                return source


def is_valid_version(tag):
    pattern = r'^v\d+\.\d+\.\d+$'
    return bool(re.match(pattern, tag))


def is_valid_repo(path):
    try:
        _ = git.Repo(path).git_dir
        return True
    except git.exc.InvalidGitRepositoryError:
        return False


def move_file(src, dst_folder):
    # Get the file name from the source path
    file_name = os.path.basename(src)
    # Construct the full destination path
    dst = os.path.join(dst_folder, file_name)

    # Check if the destination file already exists
    if os.path.exists(dst):
        os.remove(dst)  # Remove the existing file
    shutil.move(src, dst)  # Move the file


def is_newer_or_eq_version(v1, v2):
    try:
        v1_parts = list(map(int, v1.lstrip('v').split('.')))
        v2_parts = list(map(int, v2.lstrip('v').split('.')))
        return (v1_parts > v2_parts) - (v1_parts < v2_parts)
    except Exception as e:
        logger.error(f'is_newer_or_eq_version error {v1} {v2}', e)
        return False


def get_updater_exe_local():
    if sys.version_info < (3, 9):
        context = importlib.resources.path("ok.binaries", "__init__.py")
    else:
        ref = importlib.resources.files("ok.binaries") / "__init__.py"
        context = importlib.resources.as_file(ref)
    with context as path:
        pass
    # Return the dir. We assume that the data files are on a normal dir on the fs.
    return str(path.parent) + '.exe'


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def decode_and_clean(byte_string):
    # Decode the byte string to a normal string
    decoded_string = byte_string.decode('utf-8')

    # Remove ANSI escape sequences using a regular expression
    ansi_escape = re.compile(r'\x1b\[([0-9;]*[mG])')
    clean_string = ansi_escape.sub('', decoded_string)

    return clean_string


if __name__ == '__main__':
    print(get_updater_exe_local())
