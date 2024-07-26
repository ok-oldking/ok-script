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

# https://update.greasyfork.org/scripts/412245/Github%20%E5%A2%9E%E5%BC%BA%20-%20%E9%AB%98%E9%80%9F%E4%B8%8B%E8%BD%BD.user.js
download_url_us = [
    ['https://gh.h233.eu.org/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [@X.I.U/XIU2] 提供'],
    ['https://gh.ddlc.top/https://github.com', '美国',
     '[美国 Cloudflare CDN] - 该公益加速源由 [@mtr-static-official] 提供'],
    ['https://dl.ghpig.top/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [feizhuqwq.com] 提供'],
    ['https://slink.ltd/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [知了小站] 提供'],
    ['https://gh.con.sh/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [佚名] 提供'],
    ['https://cors.isteed.cc/github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [@Lufs\'s] 提供'],
    ['https://hub.gitmirror.com/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [GitMirror] 提供'],
    ['https://sciproxy.com/github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [sciproxy.com] 提供'],
    ['https://ghproxy.cc/https://github.com', '美国', '[美国 洛杉矶] - 该公益加速源由 [@yionchiii lau] 提供'],
    ['https://cf.ghproxy.cc/https://github.com', '美国',
     '[美国 Cloudflare CDN] - 该公益加速源由 [@yionchiii lau] 提供'],
    ['https://www.ghproxy.cc/https://github.com', '美国',
     '[美国 Cloudflare CDN] - 该公益加速源由 [@yionchiii lau] 提供'],
    ['https://ghproxy.cn/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [@yionchiii lau] 提供'],
    ['https://www.ghproxy.cn/https://github.com', '美国',
     '[美国 Cloudflare CDN] - 该公益加速源由 [@yionchiii lau] 提供'],
    ['https://gh.jiasu.in/https://github.com', '美国', '[美国 Cloudflare CDN] - 该公益加速源由 [@0-RTT] 提供'],
    ['https://dgithub.xyz', '美国', '[美国 西雅图] - 该公益加速源由 [dgithub.xyz] 提供'],
    ['https://download.ixnic.net', '美国', '[美国 洛杉矶] - 该公益加速源由 [@黃埔興國] 提供'],
    ['https://download.nuaa.cf', '美国', '[美国 洛杉矶] - 该公益加速源由 [FastGit 群组成员] 提供'],
    ['https://download.yzuu.cf', '美国', '[美国 纽约] - 该公益加速源由 [FastGit 群组成员] 提供']
]

download_url = [
    ['https://mirror.ghproxy.com/https://github.com', '韩国',
     '[日本、韩国、德国等]（CDN 不固定） - 该公益加速源由 [ghproxy] 提供&#10;&#10;提示：希望大家尽量多使用前面的美国节点（每次随机 负载均衡），&#10;避免流量都集中到亚洲公益节点，减少成本压力，公益才能更持久~'],
    ['https://ghproxy.net/https://github.com', '日本',
     '[日本 大阪] - 该公益加速源由 [ghproxy] 提供&#10;&#10;提示：希望大家尽量多使用前面的美国节点（每次随机 负载均衡），&#10;避免流量都集中到亚洲公益节点，减少成本压力，公益才能更持久~'],
    ['https://kkgithub.com', '香港',
     '[中国香港、日本、新加坡等] - 该公益加速源由 [help.kkgithub.com] 提供&#10;&#10;提示：希望大家尽量多使用前面的美国节点（每次随机 4 个来负载均衡），&#10;避免流量都集中到亚洲公益节点，减少成本压力，公益才能更持久~'],
]


def parse_url(urls):
    ret = []
    for sublist in urls:
        ret.append(sublist[0].replace('/https://github.com', ''))
    return ret


class GithubMultiDownloader:
    def __init__(self, app_config, exit_event):
        self.app_config = app_config
        self.exit_event = exit_event
        self.proxys = parse_url(download_url) + parse_url(download_url_us)
        logger.debug(f'proxys = {self.proxys}')
        self.fast_proxys = []
        random.shuffle(self.proxys)
        self.proxys = ["", "", "", "", ""] + self.proxys  # try to use no proxy first
        self.lock = threading.Lock()
        self.num_parts = 5
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
                    self.downloaded += part_size
                    return
                elif downloaded > part_size:
                    logger.warning(f'File size error {file} {downloaded} > {part_size}')
                    os.remove(file)
                else:
                    part_start += downloaded
                    if last_proxy is None:
                        self.downloaded += downloaded

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
            response = requests.get(url, headers=headers, stream=True, timeout=5, verify=False)  # 10 seconds timeout
            response_size = int(response.headers.get('Content-Length', 0))

            if response_size != target_size:
                response.close()
                raise Exception(f'response_size mismatch: {response_size} != {target_size}')
            part_downloaded = 0
            last_chunk_time = time.time()
            with open(file, 'ab') as f:
                for chunk in response.iter_content(chunk_size=1024):  # 1 KB chunks
                    with self.lock:
                        if time.time() - last_chunk_time > 1 and time.time() - start_time > 10:  # If more than 1 seconds have passed since the last chunk
                            response.close()
                            logger.error(f'{proxy} Server is not responding with the chunk every 0.5 seconds')
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
                if part_downloaded == target_size:
                    logger.debug("download_part finished")
                    return
                else:
                    logger.warning(f'download_part size failed {part_downloaded} {target_size}')
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
