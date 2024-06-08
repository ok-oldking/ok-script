import math
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class GithubMultiDownloader:
    def __init__(self, app_config, exit_event):
        self.app_config = app_config
        self.exit_event = exit_event
        self.proxys = ["", "https://gh.h233.eu.org", "https://gh.ddlc.top",
                       "https://dl.ghpig.top", "https://slink.ltd",
                       "https://gh.con.sh", "https://cors.isteed.cc/github.com",
                       "https://hub.gitmirror.com", "https://sciproxy.com/github.com",
                       "https://ghproxy.cc", "https://cf.ghproxy.cc",
                       "https://www.ghproxy.cc", "https://ghproxy.cn",
                       "https://www.ghproxy.cn", "https://gh.jiasu.in",
                       "https://dgithub.xyz", "https://download.ixnic.net", "https://download.nuaa.cf",
                       "https://download.scholar.rr.nu", "https://download.yzuu.cf",
                       "https://mirror.ghproxy.com", "https://ghproxy.net",
                       "https://kkgithub.com"]
        self.fast_proxys = []
        random.shuffle(self.proxys)
        self.lock = threading.Lock()
        self.num_parts = 6
        self.downloaded = 0
        self.start_time = 0
        self.size = 0

    def next_url(self, url):
        with self.lock:
            proxy = None
            if len(self.fast_proxys) > 0:
                proxy = self.fast_proxys.pop(0)
            elif len(self.proxys) > 0:
                proxy = self.proxys.pop(0)  # Remove the first item
                self.proxys.append(proxy)  # Add the removed item to the end
            prefix = '' if proxy == "" else '/'
            url = (proxy + prefix + url) if proxy is not None else None
            return url, proxy

    def download_part(self, part_size, start, end, file, giturl, last_proxy=None):
        part_start = start
        with self.lock:
            if os.path.exists(file):
                downloaded = os.path.getsize(file)
                if downloaded == part_size:
                    logger.info(f'File {file} already downloaded')
                    return
                elif downloaded > part_size:
                    logger.warning(f'File size error {file} {downloaded} > {part_size}')
                    os.remove(file)
                else:
                    part_start += downloaded
                self.downloaded += part_size

        target_size = end - part_start + 1

        if target_size <= 0:
            logger.debug(f'end multi part downloading {part_size} {target_size} {file} {last_proxy}')
            with self.lock:
                if last_proxy is not None:
                    self.fast_proxys.insert(0, last_proxy)
            return

        headers = {'Range': f'bytes={part_start}-{end}'}
        url, proxy = self.next_url(giturl)
        if proxy is None:
            logger.error(f'all proxies failed to download {file}')
            return
        logger.debug(f'start multi part downloading {part_size} {target_size} {target_size <= part_size} {file} {url}')
        start_time = time.time()

        try:
            response = requests.get(url, headers=headers, stream=True, timeout=5)  # 10 seconds timeout
            response_size = int(response.headers.get('Content-Length', 0))

            if response_size != target_size:
                response.close()
                raise Exception(f'response_size mismatch: {response_size} != {target_size}')
            part_downloaded = 0
            last_chunk_time = time.time()
            with open(file, 'ab') as f:
                for chunk in response.iter_content(chunk_size=1024):  # 1 KB chunks
                    with self.lock:
                        if time.time() - last_chunk_time > 5:  # If more than 5 seconds have passed since the last chunk
                            response.close()
                            logger.error(f'{proxy} Server is not responding with the chunk every 5 seconds')
                            break
                        if self.exit_event.is_set():
                            return
                        if chunk:
                            f.write(chunk)
                            self.downloaded += len(chunk)
                            part_downloaded += len(chunk)
                            percent = self.downloaded / self.size * 100
                            # Every 1%
                            communicate.download_update.emit(percent,
                                                             convert_size(self.downloaded) + '/' + convert_size(
                                                                 self.size),
                                                             False,
                                                             None
                                                             )
                            if part_downloaded > target_size:
                                logger.error(f'part_downloaded > target_size')
                        last_chunk_time = time.time()  # Update the time when the last chunk was received
                        if len(self.fast_proxys) > 0:
                            response.close()
                            logger.debug('switch to fast proxy')
                            break
        except Exception as e:
            with self.lock:
                if proxy in self.proxys:
                    self.proxys.remove(proxy)
            logger.error(f'multipart download error {file} {url}', e)
        self.download_part(part_size, start, end, file, giturl, proxy)

    def download(self, dir, release):
        # Calculate the size of each part
        self.size = release.get('size')
        part_size = self.size // self.num_parts
        self.downloaded = 0

        # Create a ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.num_parts) as executor:
            futures = []
            for i in range(self.num_parts):
                file = self.get_part_name(dir, i, release)
                start = i * part_size
                # The end byte is one less than the start byte of the next part
                end = start + part_size - 1 if i < self.num_parts - 1 else self.size - 1
                futures.append(
                    executor.submit(self.download_part, end - start + 1, start, end, file, release.get('url'), None))

        # Wait for all parts to finish downloading
        for future in futures:
            future.result()

        # Combine all parts into one file
        whole = os.path.join(dir, release.get('version') + '.' + release.get('type'))
        with open(whole, 'wb') as fp:  # replace with your file path
            for i in range(self.num_parts):
                file = self.get_part_name(dir, i, release)
                if not os.path.exists(file):
                    logger.error(f'file part does not exist: {file}')
                    return False
                with open(file, 'rb') as part_file:
                    fp.write(part_file.read())
                os.remove(file)  # Delete the part file after combining
            combined_size = os.path.getsize(whole)
        if combined_size != self.size:
            logger.error(f'combined_size mismatch: {combined_size} != {self.size}')
            os.remove(whole)
            return False
        return True

    def get_part_name(self, update_dir, i, release):
        return os.path.join(update_dir, release.get('version') + '.' + release.get('type')) + '.part' + str(i)


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"
