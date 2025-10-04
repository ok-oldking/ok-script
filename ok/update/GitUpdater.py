import argparse
import importlib
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
import threading  # Added for real-time stream reading
from functools import cmp_to_key

from ok import Logger, get_path_relative_to_exe

logger = Logger.get_logger(__name__)
bundled_git = os.path.join(os.getcwd(), 'python', 'git', 'bin', 'git.exe')


def add_to_path(folder_path):
    current_path = os.environ.get('PATH', '')
    if folder_path not in current_path:
        os.environ['PATH'] = folder_path + os.pathsep + current_path
        logger.info(f"Added {folder_path} to PATH for the current script.")
    else:
        logger.info(f"{folder_path} is already in the PATH for the current script.")


if os.path.isfile(bundled_git):
    logger.info(f'use bundled_git {bundled_git}')
    os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = bundled_git
    add_to_path(os.path.join(os.getcwd(), 'python', 'git', 'bin'))
os.environ['GIT_CEILING_DIRECTORIES'] = os.getcwd()

try:
    import git
except Exception as e:
    logger.error("Failed to import git", e)
import psutil
import win32api
import win32security
from PySide6.QtCore import QCoreApplication

from ok import Config
from ok import Handler
from ok import delete_if_exists
from ok import og, kill_exe
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error, alert_info
from ok.update.init_launcher_env import create_repo_venv


# Helper function to read a stream in a separate thread
def stream_reader(stream, log_function, line_buffer=None):
    try:
        for line in iter(stream.readline, ''):  # process.stdout and process.stderr are text streams
            if line:
                stripped_line = line.strip()
                log_function(stripped_line)
                if line_buffer is not None:
                    line_buffer.append(stripped_line)
    except Exception as e:
        logger.error(f"Error reading stream: {e}")
    finally:
        stream.close()


class GitUpdater:

    def __init__(self, app_config, exit_event):
        self.exit_event = exit_event
        self.app_config = app_config
        self.config = app_config.get('git_update')
        self.debug = app_config.get('debug')
        self.lts_ver = ""
        self.cleaned = False

        self.cuda_version = None
        self.launch_profiles = []
        self.versions = []
        self.launcher_config = Config('launcher', {'profile_index': 0, 'source_index': self.get_default_source(),
                                                   'profile_name': "",
                                                   'app_dependencies_installed': False,
                                                   'app_version': app_config.get('version'),
                                                   'launcher_version': app_config.get('version')})

        self.starting_version = self.launcher_config.get('app_version')
        self.version_to_hash = {}
        self.log_tailer = None
        self.yanked = False
        self.latest_ver = None
        self.outdated = False
        self.download_monitor = None
        self.handler = Handler(exit_event, self.__class__.__name__)
        self.launcher_configs = []
        self.app_env_path = None
        communicate.start_success.connect(self.update_success)
        self.update_logs = ""

    @property
    def url(self):
        return self.get_current_source()['git_url']

    def update_success(self):
        self.handler.post(self.do_update_success, 1)

    def do_update_success(self):
        logger.info(f'do_update_launcher start {sys.executable}')
        if self.set_start_success():
            self.kill_launcher()
            current_version = self.app_config.get('version')
            if os.path.isdir('repo'):
                for item in os.listdir('repo'):
                    item_path = os.path.join('repo', item)
                    if os.path.isdir(item_path) and item != current_version:
                        logger.info(f"Deleting: {item_path}")
                        kill_exe(item_path)
                        delete_folder_native(item_path)
            repo_path = os.path.join('repo', current_version)
            copy_exe_files(repo_path, os.getcwd())

        self.list_all_versions()

    def kill_launcher(self):
        try:
            # Create the parser
            parser = argparse.ArgumentParser(description='Process some parameters.')
            # Add the arguments
            parser.add_argument('--parent_pid', type=int, help='Parent process ID', default=0)
            # Parse the arguments
            args, _ = parser.parse_known_args()
            logger.info(f'parent_pid {args.parent_pid}')
            if args.parent_pid:
                logger.info(f'kill launcher {args.parent_pid}')
                wait_kill_pid(args.parent_pid)

        except Exception as e:
            logger.error('parse parent_pid error', e)

    def log_handler(self, level, message):
        if "Skipping " not in message:
            communicate.log.emit(level, message)

    def get_current_profile(self):
        return self.launch_profiles[self.launcher_config['profile_index']]

    def update_source(self, index):
        if self.launcher_config['source_index'] != index:
            self.launcher_config['source_index'] = index
            self.list_all_versions()

    def auto_update(self):
        if (self.yanked or self.outdated) and not os.path.exists('main.py'):
            logger.info(f'auto_update start')
            og.executor.pause()
            alert_info(
                QCoreApplication.translate('app', 'The current version {} must be updated').format(
                    self.launcher_config.get('app_version')), tray=True)
            # communicate.update_running.emit(False, False)
            logger.info(f'yanked {self.yanked} or outdated {self.outdated}, start auto update')
            self.do_update_to_version(self.lts_ver, auto_start=False)
            return True

    def start_app(self):
        communicate.update_running.emit(True, True)
        logger.info(f'start_app enter')
        try:
            new_ver = self.starting_version
            entry = 'main.py'

            script_path = os.path.join('repo', new_ver, entry)

            if not os.path.exists(script_path):
                script_path = os.path.join(os.getcwd(), entry)
                if os.path.isfile(script_path):
                    logger.info('dev env use local entry ')
                else:
                    logger.error(f'could not find {script_path}')
                    alert_error(f'could not find {script_path}')
                    return False
            python_folder_path = os.path.join('repo', new_ver, '.venv')

            python_path = os.path.join(python_folder_path, 'Scripts', 'python.exe')

            # Launch the script detached from the current process
            logger.info(f'launching my_pid={os.getpid()} {python_path} {script_path}')
            process = subprocess.Popen(
                [python_path, script_path, f'--parent_pid={os.getpid()}'],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',  # Explicitly set encoding to UTF-8
                errors='replace'
            )

            collected_stderr_lines = []
            stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, logger.info))
            stderr_thread = threading.Thread(target=stream_reader,
                                             args=(process.stderr, logger.error, collected_stderr_lines))

            stdout_thread.start()
            stderr_thread.start()

            process.wait()
            stdout_thread.join()
            stderr_thread.join()

            if process.returncode != 0 or collected_stderr_lines:
                err_output = "\n".join(collected_stderr_lines)
                logger.error(f"App exited with code {process.returncode}. Stderr:\n{err_output}")
                alert_error(QCoreApplication.translate('app',
                                                       "App startup error. Please add the installation folder to the Windows Defender whitelist and reinstall:") + "\n" + err_output)
                communicate.update_running.emit(False, False)
                return False

            return True
        except Exception as e:
            alert_error(f'Start App Error {str(e)}')
            logger.error(f"An error occurred:", e)
            communicate.update_running.emit(False, False)
            return False

    def version_selection_changed(self, new_version):
        is_newer = is_newer_or_eq_version(new_version, self.starting_version)
        logger.info(f'version_selection_changed {new_version} {self.starting_version} {is_newer}')
        if is_newer > 0:
            self.handler.post(lambda: self.do_version_selection_changed(new_version), remove_existing=True,
                              skip_if_running=False)

    def do_version_selection_changed(self, new_version):
        date = None
        log = None
        try:
            if self.launcher_config.get('app_version') != new_version:
                last_log = ""
                start_hash = self.version_to_hash.get(self.launcher_config.get('app_version'))
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
                        if last_log != commit.message.strip():
                            log += commit.message.strip() + '\n'
                            last_log = commit.message.strip()
            else:
                log = ""
        except Exception as e:
            logger.error(f"version_selection_changed error occurred:", e)
            alert_error("get version log error")
        self.update_logs = get_version_text(new_version == self.lts_ver, new_version, date, log)
        communicate.update_logs.emit()

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
            params += ['--trusted-host', 'pypi.python.org', '--trusted-host', 'files.pythonhosted.org',
                       '--trusted-host', 'pypi.org', '--trusted-host', 'files.pythonhosted.org', '--trusted-host',
                       'files.pythonhosted.org', '--trusted-host', 'www.paddlepaddle.org.cn', '--trusted-host',
                       'mirrors.cloud.tencent.com', '--trusted-host', 'paddle-whl.bj.bcebos.com']
            logger.info(f'executing pip install with: {params}')
            process = subprocess.Popen(
                params,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',  # Explicitly set encoding to UTF-8
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, logger.info))
            stderr_thread = threading.Thread(target=stream_reader, args=(process.stderr, logger.error))

            stdout_thread.start()
            stderr_thread.start()

            process.wait()
            stdout_thread.join()
            stderr_thread.join()

            if process.returncode == 0:
                logger.info(f"Package '{package_name}' installed successfully.")
                return True
            else:
                logger.error(f"Failed to install package '{package_name}'. Exit code: {process.returncode}")
                alert_error(f'Failed to install package. {package_name}')
                return False
        except Exception as e:
            logger.error(f"An error occurred during install_package: {e}")
            return False

    def update_to_version(self, version):
        communicate.update_running.emit(True, True)
        self.handler.post(lambda: self.do_update_to_version(version))

    def run(self):
        if self.handler.post(self.do_run, skip_if_running=True, remove_existing=True):
            communicate.update_running.emit(True, True)

    def do_run(self):
        try:
            self.start_app()
            logger.info('start_app end')
        except Exception as e:
            logger.error('do_run exception', e)
            alert_error(QCoreApplication.translate('app', 'Start App Exception:') + str(e))
            communicate.update_running.emit(False, False)

    def set_start_success(self):
        if self.launcher_config['app_version'] != self.app_config.get('version'):
            self.launcher_config['app_version'] = self.app_config.get('version')
            self.launcher_config['app_dependencies_installed'] = True
            logger.info('set_start_success success')
            return True

    def check_out_version(self, version, depth=10):
        path = os.path.join('repo', version)
        logger.info(f'start cloning repo {path}')
        repo = check_repo(path, self.url)
        if repo is not None:
            try:
                repo.git.fetch('origin', f'refs/tags/{version}:refs/tags/{version}', '--depth=1', '--force', '--prune',
                               '--tags')
                repo.git.checkout(version, force=True)
            except Exception as e:
                logger.error(f'check_out_version error: {e}')
                repo = None
        if repo is None:
            delete_folder_native(path)
            try:
                source_folder = get_path_relative_to_exe()
                copy_folder_with_exclusions(source_folder, path, exclude_folders=['.venv', 'repo'])
                repo = check_repo(path, self.url)
                repo.git.fetch('origin', f'refs/tags/{version}:refs/tags/{version}', '--depth=1', '--force', '--prune',
                               '--tags')
                repo.git.checkout(version, force=True)
                logger.info(f'check_out_version copy and check repo success {source_folder} {path}')
            except Exception as e:
                logger.error(f'check_out_version copied version error: {e}')
                repo = None
                delete_folder_native(path)
            if repo is None:
                repo = git.Repo.clone_from(self.url, path, branch=version, depth=depth)

        remove_ok_requirements(path, version)

        logger.info(f'clone repo success {path}')
        return repo

    def do_update_to_version(self, version, auto_start=True):
        try:
            if self.launcher_config.get('app_version') == version:
                alert_info(QCoreApplication.translate('app', f'Already updated to version:') + version)
                communicate.update_running.emit(False, False)
                return
            venv_path = os.path.abspath(os.path.join('repo', self.launcher_config.get('app_version'), '.venv'))
            if not os.path.exists(venv_path):
                venv_path = os.path.abspath(os.path.join('python', 'app_env'))
            if not os.path.exists(venv_path):
                venv_path = os.path.abspath('.venv')
            if not os.path.exists(venv_path):
                logger.error(f'venv path {venv_path} does not exist')
                alert_info(QCoreApplication.translate('app', "Can't find python venv"))
                communicate.update_running.emit(False, False)
                return
            repo = self.check_out_version(version)
            repo_dir = os.path.join('repo', version)
            if not create_repo_venv(os.path.join(os.getcwd(), 'python'), repo_dir, venv_path, self.get_current_source()[
                'pip_url']):
                logger.error(f'failed to create venv {venv_path}')
                alert_info(QCoreApplication.translate('app', "Create venv failed."))
                communicate.update_running.emit(False, False)
                return False
            copy_exe_files(repo_dir, os.getcwd())
            self.starting_version = version
            self.yanked = False
            self.outdated = False
            if auto_start:
                self.do_run()
            else:
                communicate.must_update.emit()
        except Exception as e:
            logger.error('do_update_to_version error', e)
            communicate.update_running.emit(False, False)

    def list_all_versions(self):
        if self.handler.post(self.do_list_all_versions, skip_if_running=True):
            communicate.update_running.emit(True, False)

    def do_list_all_versions(self):
        try:
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
            if self.launcher_config.get('app_version') not in self.version_to_hash and not os.path.exists(
                    'requirements.txt'):
                logger.info('version yanked')
                self.yanked = True
            else:
                self.yanked = False
            if is_newer_or_eq_version(self.launcher_config.get('app_version'), self.lts_ver) < 0:
                logger.info(f'version outdated {self.launcher_config.get("app_version")} {self.lts_ver}')
                self.outdated = True
            else:
                self.outdated = False
            tags = sorted(list(filter(
                lambda x: is_newer_or_eq_version(x, self.lts_ver) >= 0,
                hash_to_ver.values())),
                key=cmp_to_key(is_newer_or_eq_version),
                reverse=True)
            logger.info(f'done fetching remote version size {len(tags)}')
            self.versions = tags
            if not self.latest_ver and self.versions and is_newer_or_eq_version(self.versions[0],
                                                                                self.launcher_config.get(
                                                                                    'app_version')) > 0:
                self.latest_ver = self.versions[0]
                logger.info(f'latest version is {self.latest_ver}')
                alert_info(QCoreApplication.translate('app', 'New Version {} Available').format(self.latest_ver),
                           tray=True, show_tab='about')
            self.auto_update()
            communicate.update_running.emit(False, False)
            communicate.versions.emit()
        except Exception as e:
            logger.error('Fetch remote version list error', e)
            alert_error('Fetch remote version list error!')
            communicate.update_running.emit(False, False)
            communicate.versions.emit()

    def change_profile(self, index):
        if self.launcher_config['profile_index'] != index:
            self.launcher_config['profile_index'] = index
            self.launcher_config['app_dependencies_installed'] = False
            logger.info(f'profile changed {index}')

    def get_sources(self):
        return self.config['sources']

    def get_default_source(self):
        if 'cn' in locale.getdefaultlocale()[0].lower():
            for i in range(len(self.config['sources'])):
                if self.config['sources'][i]['name'] == 'China':
                    return i
        return 0

    def get_current_source(self):
        index = self.launcher_config.get("source_index")
        sources = self.get_sources()
        logger.info(f'get_current_source {sources} {index}')
        if 0 <= index < len(sources):
            return sources[index]
        else:
            default_source = self.get_default_source()
            logger.info(f'get_current_source failed return default {default_source}')
            self.launcher_config["source_index"] = default_source
            return sources[default_source]


def delete_folder_native(folder):
    if not os.path.exists(folder):
        logger.info(f'delete_folder_native {folder} does not exist, skipping.')
        return
    if platform.system() == "Windows":
        try:
            cmd = ["cmd", "/c", "rd", folder, "/S", "/Q", ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    check=False,
                                    shell=False)
            if result.stdout and result.stdout.strip():
                logger.info(f"Deletion command stdout for '{folder}':\n{result.stdout.strip()}")
            if result.stderr and result.stderr.strip():
                logger.error(f"Deletion command stderr for '{folder}':\n{result.stderr.strip()}")

            if result.returncode == 0:
                logger.info(f"Successfully deleted: {folder}")
            else:
                logger.error(f"Failed to delete '{folder}'. Exit code: {result.returncode}")
            return
        except Exception as e:
            logger.error(f"Error deleting '{folder}'", e)
    delete_if_exists(folder)


def load_gitignore(source_folder):
    gitignore_path = os.path.join(source_folder, ".gitignore")
    excluded_paths = set()

    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as file:  # Added encoding for reading .gitignore
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    excluded_paths.add(line.replace('/', ''))
    return excluded_paths


def should_exclude(path, excluded_patterns):
    for pattern in excluded_patterns:
        if path.startswith(pattern) or pattern in path:
            return True
    return False


def copy_folder_with_exclusions(source_folder, destination_folder, exclude_folders=[".venv"]):
    excluded_patterns = load_gitignore(source_folder)  # Uses the version with encoding
    excluded_patterns.update(exclude_folders)

    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    for root, dirs, files in os.walk(source_folder):
        relative_path = os.path.relpath(root, source_folder)
        if should_exclude(relative_path, excluded_patterns):
            dirs[:] = []  # Don't recurse into excluded directories
            continue

        target_folder = os.path.join(destination_folder, relative_path)

        if not os.path.exists(target_folder):
            os.makedirs(target_folder)

        for file_name in files:  # Changed 'file' to 'file_name' to avoid conflict
            source_file = os.path.join(root, file_name)
            relative_file = os.path.relpath(source_file, source_folder)
            if not should_exclude(relative_file, excluded_patterns):
                destination_file = os.path.join(target_folder, file_name)
                shutil.copy2(source_file, destination_file)


def get_file_in_path_or_cwd(path, file):
    if os.path.exists(os.path.join(path, file)):
        return os.path.join(path, file)
    elif os.path.exists(file):
        return file
    elif os.path.exists(os.path.join('src', file)):
        return os.path.join('src', file)
    raise FileNotFoundError(f'{path} {file} not found')


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
                logger.info(f'check_repo {path}')
                return repo
    except Exception as e:
        logger.error(f'invalid repo path {path}', e)


def format_date(date):
    return date.strftime('%Y-%m-%d')


def is_newer_or_eq_version(v1, v2):
    try:
        v1_stripped = v1.lstrip('v')
        v2_stripped = v2.lstrip('v')

        v1_parts = [int(part) for part in v1_stripped.split('.')]
        v2_parts = [int(part) for part in v2_stripped.split('.')]

        for p1, p2 in zip(v1_parts, v2_parts):
            if p1 > p2:
                return 1
            elif p1 < p2:
                return -1

        if len(v1_parts) > len(v2_parts):
            return 1
        elif len(v1_parts) < len(v2_parts):
            return -1
        else:
            return 0
    except Exception as e:
        logger.error(f'is_newer_or_eq_version error {v1} {v2}', e)
        return 0


def get_updater_exe_local():
    if sys.version_info < (3, 9):
        context = importlib.resources.path("ok.binaries", "__init__.py")
    else:
        ref = importlib.resources.files("ok.binaries") / "__init__.py"
        context = importlib.resources.as_file(ref)
    with context as path:
        pass
    return str(path.parent) + '.exe'


def decode_and_clean(byte_string):
    decoded_string = byte_string.decode('utf-8')
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


def wait_kill_pid(pid):
    process = psutil.Process(pid)
    process.terminate()
    process.wait(timeout=30)
    logger.info(f'kill process {pid} exists {psutil.pid_exists(pid)}')


def remove_readonly(func, path, excinfo):
    os.chmod(path, os.stat.S_IWRITE)
    func(path)


def take_ownership(folder_path):
    logger.info(f"Starting ownership change on {folder_path}")
    if not os.path.isdir(folder_path):
        logger.error(f"Error: '{folder_path}' is not a valid directory.")
        return

    try:
        username = win32api.GetUserName()
        user_sid, _, _ = win32security.LookupAccountName("", username)

        security_descriptor = win32security.GetFileSecurity(folder_path, win32security.OWNER_SECURITY_INFORMATION)
        security_descriptor.SetSecurityDescriptorOwner(user_sid, False)
        win32security.SetFileSecurity(folder_path, win32security.OWNER_SECURITY_INFORMATION, security_descriptor)
        logger.info(f"Ownership change done on {folder_path}")

        for root, dirs, files in os.walk(folder_path):
            for name in dirs:
                full_dir_path = os.path.join(root, name)
                logger.info(f"Starting ownership change on {full_dir_path}")
                security_descriptor = win32security.GetFileSecurity(full_dir_path,
                                                                    win32security.OWNER_SECURITY_INFORMATION)
                security_descriptor.SetSecurityDescriptorOwner(user_sid, False)
                win32security.SetFileSecurity(full_dir_path, win32security.OWNER_SECURITY_INFORMATION,
                                              security_descriptor)
                logger.info(f"Ownership change done on {full_dir_path}")

            for name in files:
                full_file_path = os.path.join(root, name)
                logger.info(f"Starting ownership change on {full_file_path}")
                security_descriptor = win32security.GetFileSecurity(full_file_path,
                                                                    win32security.OWNER_SECURITY_INFORMATION)
                security_descriptor.SetSecurityDescriptorOwner(user_sid, False)
                win32security.SetFileSecurity(full_file_path, win32security.OWNER_SECURITY_INFORMATION,
                                              security_descriptor)
                logger.info(f"Ownership change done on {full_file_path}")
        logger.info(f"Finished ownership change on all subfolders and files under {folder_path}")
    except Exception as e:
        logger.error(f"Error taking ownership of '{folder_path}': {e}")


def kill_process_by_path(exe_path):
    for proc in psutil.process_iter(['pid', 'exe']):
        try:
            if proc.info['exe'] and proc.info['exe'].startswith(exe_path):
                proc.kill()
                logger.info(f"Terminated process {proc.info['pid']} {proc.info['exe']} with executable {exe_path}")
                proc.wait(timeout=5)
                logger.info(f"Process {proc.info['pid']} terminated successfully")
        except Exception as e:
            logger.error(f"Failed to kill process {proc.info['pid']}: {e}")


def clean_repo(repo_path, whitelist):
    for subfolder in os.listdir(repo_path):
        subfolder_path = os.path.join(repo_path, subfolder)
        if os.path.isdir(subfolder_path) and subfolder not in whitelist:
            delete_folder_native(subfolder_path)
            logger.info(f'clean_repo Deleted subfolder: {subfolder_path} {whitelist}')
    logger.info('clean_repo complete.')


def copy_exe_files(folder1, folder2):
    try:
        if os.path.isdir(folder1):
            for file_name in os.listdir(folder1):
                if file_name.endswith('.exe'):
                    source_file = os.path.join(folder1, file_name)
                    destination_file = os.path.join(folder2, file_name)
                    shutil.copy2(source_file, destination_file)
                    logger.info(f'Copied {source_file} to {destination_file}')
    except Exception as e:
        logger.error(f'copy_exe_files error', e)
    logger.info(f'Copy exe complete. {folder1} -> {folder2}')


def remove_ok_requirements(repo_dir, tag):
    config_file = get_file_in_path_or_cwd(repo_dir, 'config.py')
    with open(config_file, 'r', encoding='utf-8') as file:
        content = file.read()
    new_content = re.sub(r'version = ".+"', f'version = "{tag}"', content)
    with open(config_file, 'w', encoding='utf-8') as file:
        file.write(new_content)

    if os.path.exists(os.path.join(repo_dir, 'ok')):
        logger.info('ok-script is bundled with source code, skip downloading')
    file_path = os.path.join(repo_dir, 'requirements.txt')
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    filtered_lines = [line for line in lines if 'ok-script' not in line]
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(filtered_lines)
