import argparse
import importlib
import json
import locale
import math
import os
import re
import shutil
import subprocess
import sys
import time
from functools import cmp_to_key

import git
import psutil
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error, alert_info
from ok.logging.LogTailer import LogTailer
from ok.logging.Logger import get_logger
from ok.update.python_env import create_venv
from ok.util.Handler import Handler
from ok.util.path import get_relative_path, delete_if_exists

logger = get_logger(__name__)

repo_path = get_relative_path(os.path.join('update', "repo"))


class GitUpdater:

    def __init__(self, app_config, exit_event):
        self.exit_event = exit_event
        self.app_config = app_config
        self.config = app_config.get('git_update')
        self.debug = app_config.get('debug')
        self.lts_ver = ""
        self.handler = Handler(exit_event, self.__class__.__name__)
        self.launcher_configs = []
        self.launcher_config = Config('launcher', {'profile_name': '', 'source': self.get_default_source(),
                                                   'app_dependencies_installed': False,
                                                   'app_version': app_config.get('version'),
                                                   'launcher_version': app_config.get('version')})

        self.launch_profiles = []
        self.all_versions = []
        self.load_current_ver()
        self.version_to_hash = {}
        self.log_tailer = None
        self.yanked = False
        self.outdated = False
        self.starting_version = self.version

    @property
    def url(self):
        return self.get_current_source()['git_url']

    @property
    def version(self):
        return self.launcher_config.get('app_version')

    def update_launcher(self):
        if self.app_config.get('version') != self.launcher_config.get('launcher_version'):
            logger.info(
                f'need to update launcher version {self.launcher_config.get("launcher_version")} to {self.app_config.get("version")} ')
            self.handler.post(self.do_update_launcher, 5)

    def do_update_launcher(self):
        # Create the parser
        parser = argparse.ArgumentParser(description='Process some parameters.')

        # Add the arguments
        parser.add_argument('--parent_pid', type=int, help='Parent process ID')

        # Parse the arguments
        args = parser.parse_args()

        logger.info(f'parent_pid {args.parent_pid}')
        if args.parent_pid:
            wait_for_pid(args.parent_pid)
        python_folder = os.path.abspath(os.path.join('python', 'launcher_env'))
        kill_process_by_path(python_folder)
        if self.install_dependencies('launcher_env'):
            logger.debug('update launcher_env dependencies success')
            self.launcher_config['launcher_version'] = self.app_config.get('version')

        copy_exe_files(os.path.join('repo', self.launcher_config['launcher_version']), os.getcwd())
        clean_repo('repo', [self.app_config.get("version")])

    def load_current_ver(self):
        path = os.path.join('repo', self.version)
        self.launch_profiles = self.read_launcher_config(path)

    def log_handler(self, level, message):
        communicate.log.emit(level, message)

    def handle_log(self, level, message):
        if 'Window has fully displayed' in message:
            logger.info(f'start success, exit launcher')
            self.set_start_success()
            self.exit_event.set()
            QApplication.quit()

    def get_current_profile(self):
        return next((obj for obj in self.launch_profiles if obj['name'] == self.launcher_config.get('profile_name')),
                    None)

    def update_source(self, text):
        self.launcher_config['source'] = text
        self.list_all_versions()

    def start_app(self):
        try:
            if self.yanked or self.outdated:
                alert_error(
                    QCoreApplication.translate('app', 'The current version {} must be updated').format(self.version))
                communicate.update_running.emit(False)
                return

            new_ver = self.starting_version
            entry = self.get_current_profile()['entry']
            script_path = os.path.join('repo', new_ver, entry)

            python_path = os.path.join('python', 'app_env', 'Scripts', 'pythonw.exe')
            # Launch the script detached from the current process
            logger.info(f'launching {python_path} {script_path}')
            process = subprocess.Popen(
                [python_path, script_path, f'--parent_pid={os.getpid()}'],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

            # Get the process ID (PID)
            pid = process.pid
            logger.info(f"Process ID (PID): {pid}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    def version_selection_changed(self, new_version):
        self.handler.post(lambda: self.do_version_selection_changed(new_version), remove_existing=True,
                          skip_if_running=False)

    def do_version_selection_changed(self, new_version):
        date = None
        log = None
        try:
            if self.launcher_config.get('app_version') != new_version:
                start_hash = self.version_to_hash[self.launcher_config.get('app_version')]
                end_hash = self.version_to_hash[new_version]
                repo = self.check_out_version(new_version)
                log = QCoreApplication.translate('app', "Updates:") + "\n"

                started = False

                for commit in repo.iter_commits(rev=end_hash):
                    if commit.hexsha == start_hash:
                        break
                    if commit.hexsha == end_hash:
                        date = format_date(commit.committed_datetime)
                        started = True
                    if started:
                        log += commit.message.strip() + '\n'
            else:
                log = ""
        except Exception as e:
            logger.error(f"version_selection_changed error occurred:", e)
            alert_error("get version log error")
        communicate.update_logs.emit(get_version_text(new_version == self.lts_ver, new_version, date, log))

    def install_package(self, package_name, app_env_path):
        try:
            # Run pip install command
            app_env_python_exe = os.path.join(app_env_path, 'Scripts', 'python.exe')
            params = [app_env_python_exe, "-m", "pip", "install"] + package_name.split()
            if '-i' not in package_name.split():
                params += ['-i',
                           self.get_current_source()[
                               'pip_url']]
            params += ['--no-cache-dir']
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
        communicate.update_running.emit(True)
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

    def install_dependencies(self, env):
        env_path = create_venv(env)
        profile = self.get_current_profile()
        logger.info(f'installing dependencies for {profile}')
        if profile:
            for dependency in profile[f'install_dependencies']:
                if env == 'launcher_env':
                    split_strings = dependency.split()
                    dependency = next((s for s in split_strings if "ok-script" in s), None)
                    if not dependency:
                        continue
                    logger.info(f'found ok-script version in launcher.json {dependency}')
                if not self.install_package(dependency, env_path):
                    logger.error(f'failed to install {dependency}')
                    return False
            return True

    def run(self):
        if self.handler.post(self.do_run, skip_if_running=True, remove_existing=True):
            communicate.update_running.emit(True)

    def do_run(self):
        if not self.launcher_config['app_dependencies_installed']:
            if not self.install_dependencies('app_env'):
                alert_info(QCoreApplication.translate('app', f'Install dependencies Failed'))
                communicate.update_running.emit(False)
                return
        self.start_app()
        logger.info('start_app end')

    def set_start_success(self):
        self.launcher_config['app_version'] = self.starting_version
        self.launcher_config['app_dependencies_installed'] = True

    def check_out_version(self, version, depth=10):
        path = os.path.join('repo', version)
        logger.info(f'start cloning repo {path}')
        repo = check_repo(path, self.url)
        if repo is None:
            delete_if_exists(path)
            repo = git.Repo.clone_from(self.url, path, branch=version, depth=depth)
        else:
            repo.git.fetch('origin', f'refs/tags/{version}:refs/tags/{version}', '--depth=1')
            repo.git.checkout(version, force=True)

        logger.info(f'clone repo success {path}')
        return repo

    def do_update_to_version(self, version):
        try:
            if self.version == version:
                alert_info(QCoreApplication.translate('app', f'Already updated to version:') + version)
                communicate.clone_version.emit(None)
                communicate.update_running.emit(False)
                return
            python_folder = os.path.abspath(os.path.join('python', 'app_env'))
            kill_process_by_path(python_folder)
            repo = self.check_out_version(version)
            self.launch_profiles = self.read_launcher_config(repo.working_tree_dir)
            self.launcher_config['app_dependencies_installed'] = False
            self.starting_version = version
            self.yanked = False
            self.outdated = False
            communicate.clone_version.emit(None)
            self.do_run()
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
            if not self.log_tailer:
                communicate.log.connect(self.handle_log)
                self.log_tailer = LogTailer(os.path.join('logs', 'ok-script.log'), self.exit_event, self.log_handler)
                self.log_tailer.start()
                logger.info('start log tailer')

            logger.info(f'start fetching remote version {self.url}')
            remote_refs = git.cmd.Git().ls_remote(self.url, tags=True)

            lts_hash = ''
            # Parse the output to get tag names
            hash_to_ver = {}
            for line in remote_refs.splitlines():
                if line.endswith('^{}') and 'refs/tags/' in line:
                    hash, tag = line[:-3].split('refs/tags/')
                    hash = hash.strip()
                    if tag == 'lts':
                        lts_hash = hash
                    elif is_valid_version(tag):
                        self.version_to_hash[tag] = hash
                        hash_to_ver[hash] = tag
            self.lts_ver = hash_to_ver.get(lts_hash) or 'v0.0.0'
            logger.info(f'lts hash: {lts_hash} lts_ver: {self.lts_ver}')
            if self.version not in self.version_to_hash:
                logger.info('version yanked')
                self.yanked = True
            if is_newer_or_eq_version(self.version, self.lts_ver) < 0:
                logger.info(f'version outdated {self.version} {self.lts_ver}')
                self.outdated = True
            tags = sorted(list(filter(lambda x: is_newer_or_eq_version(x, self.lts_ver) >= 0 and x != self.version,
                                      hash_to_ver.values())),
                          key=cmp_to_key(is_newer_or_eq_version),
                          reverse=True)
            logger.info(f'done fetching remote version size {len(tags)}')
            self.all_versions = tags
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


def check_repo(path, new_url):
    try:
        if os.path.isdir(path):
            repo = git.Repo(path)
            if not repo.bare:
                origin = repo.remotes.origin
                current_url = origin.url
                if current_url != new_url:
                    logger.info(f"Updating remote URL from {current_url} to {new_url}")
                    origin.set_url(new_url)
                logger.info(f'check_repo {path} {repo.head.commit}')
                return repo
    except Exception as e:
        logger.error(f'invalid repo path {path}', e)


def move_file(src, dst_folder):
    # Get the file name from the source path
    file_name = os.path.basename(src)
    # Construct the full destination path
    dst = os.path.join(dst_folder, file_name)

    # Check if the destination file already exists
    if os.path.exists(dst):
        os.remove(dst)  # Remove the existing file
    shutil.move(src, dst)  # Move the file


def format_date(date):
    return date.strftime('%Y-%m-%d')


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


def get_version_text(lts, version, date, logs):
    if date and logs:
        text = "<h3>{title}: {version}</h3>"
        if lts:
            title = QCoreApplication.translate('app', 'Stable Version')
        else:
            title = QCoreApplication.translate('app', 'Beta Version')
        text = text.format(title=title, version=version)
        text += "<p>{date}</p>".format(date=date)
        text += "<p>{notes}</p>".format(notes=logs.replace('\n', "<br/>"))
        return text


def wait_for_pid(pid):
    while True:
        if not psutil.pid_exists(pid):
            logger.info(f'Process {pid} has exited.')
            break
        time.sleep(1)


def kill_process_by_path(exe_path):
    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'exe']):
        try:
            # Check if the process executable path starts with the given path
            if proc.info['exe'] and proc.info['exe'].startswith(exe_path):
                # Terminate the process
                proc.kill()
                logger.info(f"Terminated process {proc.info['pid']} {proc.info['exe']} with executable {exe_path}")
                # Wait for the process to terminate
                proc.wait(timeout=5)
                logger.info(f"Process {proc.info['pid']} terminated successfully")
        except Exception as e:
            logger.error(f"Failed to kill process {proc.info['pid']}: {e}")


def clean_repo(repo_path, whitelist):
    """
    Walk through the top-level subfolders in the 'repo' folder and delete those not in the whitelist.

    :param repo_path: Path to the 'repo' folder.
    :param whitelist: Set of subfolder names to keep.
    """
    for subfolder in os.listdir(repo_path):
        subfolder_path = os.path.join(repo_path, subfolder)
        if os.path.isdir(subfolder_path) and subfolder not in whitelist:
            # Delete the subfolder if it's not in the whitelist
            delete_if_exists(subfolder_path)
            logger.info(f'clean_repo Deleted subfolder: {subfolder_path}')

    logger.info('clean_repo complete.')


def copy_exe_files(folder1, folder2):
    """
    Copy all .exe files from folder1 to folder2, replacing existing files.

    :param folder1: Source folder containing .exe files.
    :param folder2: Destination folder where .exe files will be copied.
    """
    # Ensure the destination folder exists

    # Iterate through the files in the source folder
    try:
        for file_name in os.listdir(folder1):
            if file_name.endswith('.exe'):
                source_file = os.path.join(folder1, file_name)
                destination_file = os.path.join(folder2, file_name)
                shutil.copy2(source_file, destination_file)
                logger.info(f'Copied {source_file} to {destination_file}')
    except Exception as e:
        logger.error(f'copy_exe_files error', e)

    logger.info(f'Copy exe complete. {folder1} -> {folder2}')


if __name__ == '__main__':
    print(get_updater_exe_local())
