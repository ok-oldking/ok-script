import math
import os
import queue
import subprocess
import threading
import zipfile
from datetime import datetime

import py7zr
import requests

from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.update.GithubMultiDownloader import GithubMultiDownloader
from ok.util.path import get_path_relative_to_exe, ensure_dir, dir_checksum, find_folder_with_file

logger = get_logger(__name__)

updater_bat = r'''@echo off
set "source_dir=%~1"
set "target_dir=%~2"

if not defined source_dir (
    echo Source directory is not defined.
    exit /b
)

if not defined target_dir (
    echo Target directory is not defined.
    exit /b
)

echo "%source_dir%"
echo "%target_dir%"

for %%F in ("%source_dir%\*") do (
    if exist "%target_dir%\%%~nxF" (
        echo Deleting "%target_dir%\%%~nxF"
        del /Q /F "%target_dir%\%%~nxF"
    )
    echo Copying "%%F"
    copy /Y "%%F" "%target_dir%"
)

for /D %%D in ("%source_dir%\*") do (
    if exist "%target_dir%\%%~nxD" (
        echo Deleting "%target_dir%\%%~nxD"
        rmdir /S /Q "%target_dir%\%%~nxD"
    )
    echo Copying "%%D"
    xcopy /E /I "%%D" "%target_dir%\%%~nxD"
)
'''


class Updater:
    def __init__(self, app_config, exit_event):
        self.config = app_config.get('update')
        self.version = app_config.get('version')
        self.debug = app_config.get('debug')
        self.latest_release = None
        self.stable_release = None
        self.error = None
        self.to_update = None
        self.downloading = False
        if self.config is None:
            return
        self.update_url = self.config.get('releases_url')
        self.proxy_url = self.config.get('proxy_url')
        self.use_proxy = self.config.get('use_proxy')
        self.update_dir = get_path_relative_to_exe('updates')
        self.exit_event = exit_event
        self.task_queue = queue.Queue()
        self.exit_event.bind_queue(self.task_queue)
        self.downloader = GithubMultiDownloader(app_config, exit_event)
        t = threading.Thread(target=self._run_tasks, name='run_tasks')
        t.start()

    def _run_tasks(self):
        while True and not self.exit_event.is_set():
            task = self.task_queue.get()
            if task is None:
                logger.debug("Task queue get is None quit")
                break
            task()
            self.task_queue.task_done()

    def get_url(self, url):
        if self.use_proxy:
            url = self.proxy_url + url
        logger.info(f'get_url: {url}')
        return url

    def check_for_updates(self):
        try:
            # Send GET request to the API endpoint
            response = requests.get(self.get_url(self.update_url))

            # Raise an exception if the request was unsuccessful
            response.raise_for_status()

            # Parse the JSON response to a dictionary
            releases = response.json()

            # Extract useful information from each release
            self.latest_release = None
            self.stable_release = None
            self.error = None
            for release in releases:
                release = self.parse_data(release)

                if not release.get('draft') and is_newer_version(self.version, release.get('version')):
                    if self.latest_release is None:
                        self.latest_release = release
                    if not release.get('prerelease') and self.stable_release is None:
                        self.stable_release = release

                    if self.latest_release and self.stable_release:
                        break

            if self.latest_release == self.stable_release:
                self.latest_release = None

        except Exception as e:
            print(f"HTTP error occurred: {e}")
        communicate.check_update.emit()

    def async_run(self, task):
        self.task_queue.put(task)

    def download(self, release):
        try:
            ensure_dir(self.update_dir)
            file = os.path.join(self.update_dir, release.get('version') + '.' + release.get('type'))
            size = release.get('size')
            if os.path.exists(file):
                downloaded = os.path.getsize(file)
                if downloaded == size:
                    logger.info(f'File {file} already downloaded')
                    self.extract(file, release.get('version'))
                    return
                else:
                    logger.warning(f'File size error {file} {downloaded} != {size}')
                    os.remove(file)
            self.downloading = True
            success = self.downloader.download(self.update_dir, release)
            self.downloading = False
            if success:
                logger.info(f'download success: {file}')
                self.extract(file, release.get('version'))
            return

        except Exception as e:
            logger.error('download error occurred', e)
            self.downloading = False
            communicate.download_update.emit(0, "", True, e.args[0])

    def extract(self, file, version):
        communicate.download_update.emit(100, "Extracting", False, None)
        folder, extension = file.rsplit('.', 1)
        ensure_dir(folder)
        try:
            if extension == '7z':
                with py7zr.SevenZipFile(file, mode='r') as z:
                    z.extractall(folder)
            elif extension == 'zip':
                with zipfile.ZipFile(file, 'r') as z:
                    z.extractall(folder)
        except Exception as e:
            logger.error('extract error occurred', e)
            self.check_package_error()
            return
        update_package_folder = find_folder_with_file(folder, 'md5.txt')

        if update_package_folder is None:
            logger.error('check_package_error no md5.txt found')
            self.check_package_error()
            return
        correct_md5_file = os.path.join(update_package_folder, 'md5.txt')
        try:
            with open(correct_md5_file, 'r') as file:
                # Read the content of the file
                correct_md5 = file.read()
        except Exception as e:
            logger.error(f'check_package_error md5.txt not found {correct_md5_file}', e)
            self.check_package_error()
            return

        md5 = dir_checksum(update_package_folder, ['md5.txt'])
        if md5 != correct_md5:
            logger.error(f'check_package_error md5.txt mismatch {correct_md5_file} != {md5}')
            self.check_package_error()
            return
        logger.info(f'extract md5: {md5}')

        # Open the file in write mode ('w')
        try:
            bat_path = get_path_relative_to_exe('update.bat')
            with open(bat_path, 'w') as file:
                # Write a string to the file
                file.write(updater_bat)
                logger.info(f'write {bat_path} update .bat')
        except Exception as e:
            logger.error(f'write updater_bat error', e)
            self.check_package_error()
            return

        # Now, 'Hello, World!' is written to 'filename.txt'
        self.to_update = {'version': version, 'update_package_folder': update_package_folder,
                          'updater_bat': bat_path}
        communicate.download_update.emit(100, "", True, None)

    def update(self):
        exe_folder = get_path_relative_to_exe()
        batch_command = f'{self.to_update.get("updater_bat")} {self.to_update.get("update_package_folder")} {exe_folder}'
        logger.info(f'execute update {batch_command}')
        # ok.gui.app.quit()
        os._exit(0)
        subprocess.run(batch_command, shell=True)

    def check_package_error(self):
        # clear_folder(self.update_dir)
        communicate.download_update.emit(100, "", True, "Update Package CheckSum Error!")

    def enabled(self):
        return self.config is not None

    def parse_data(self, release):
        version = release.get('tag_name')
        time = datetime.strptime(release.get('published_at'), "%Y-%m-%dT%H:%M:%SZ").strftime('%Y-%m-%d %H:%M:%S')
        target_asset = None
        for asset in release.get('assets'):
            asset = {
                'name': asset.get('name'),
                'url': asset.get('browser_download_url'),
                'size': asset.get('size'),
                'readable_size': convert_size(asset.get('size'))
            }
            asset['type'] = asset['url'].rsplit('.', 1)[1]
            url = asset.get('url')
            if version in url:
                if 'debug' in url and self.debug:
                    target_asset = asset
                elif 'release' in url and not self.debug:
                    target_asset = asset
        if not target_asset:
            raise ValueError(f'No asset found for version: {version}')
        release = {
            'version': version,
            'notes': release.get('body'),
            'time': time,
            'draft': release.get('draft'),
            'prerelease': release.get('prerelease'),
        }
        release.update(target_asset)
        return release


def is_newer_version(base_version, target_version):
    base_version = list(map(int, base_version[1:].split('.')))
    target_version = list(map(int, target_version[1:].split('.')))

    # Compare the versions
    return base_version < target_version


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"