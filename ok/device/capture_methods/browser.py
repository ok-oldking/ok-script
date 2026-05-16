import asyncio
import os
import re
import threading

import win32gui

from ok.gui.Communicate import communicate
from ok.task.exceptions import CaptureException
from ok.util.logger import Logger
from ok.util.window import resize_window, windows_graphics_available, find_hwnd

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.capture_methods.bitblt_utils import get_crop_point
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod

logger = Logger.get_logger(__name__)

class BrowserCaptureMethod(BaseCaptureMethod):
    name = "Browser Capture"
    description = "Capture from Browser using Playwright and Windows Graphics Capture"

    def __init__(self, config, exit_event):
        super().__init__()
        self.config = config
        self.exit_event = exit_event
        res = config.get('resolution', (1280, 720))
        self._size = (res[0], res[1])
        logger.info(f'BrowserCaptureMethod init {self._size}')
        self.playwright = None
        self.browser = None
        self.page = None
        self.latest_frame = None
        self.wgc_capture = None
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._start_loop, daemon=True, name="PlaywrightLoop")
        self.loop_thread.start()

        self.hwnd = 0
        self.x_offset = 0
        self.y_offset = 0
        self.last_width = 0
        self.last_height = 0
        self.last_hwnd = 0
        self.exe_full_path = None

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_in_loop(self, coro):
        if self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            try:
                return future.result()
            except Exception as e:
                logger.error(f"Playwright execution error: {e}")
        return None

    async def _start_browser_async(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()

        width, height = self._size


        disable_features = ["CalculateNativeWinOcclusion"]

        args = [
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
            "--high-dpi-support=1",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]


        args.append(f"--disable-features={','.join(disable_features)}")

        user_data_dir = os.path.join('cache', 'playwright')

        channels = ['msedge', 'chrome', 'chromium']
        for channel in channels:
            try:
                logger.info(f'Attempting to launch persistent context with channel: {channel}')
                self.browser = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel=channel,
                    headless=False,
                    args=args,
                    viewport={'width': width, 'height': height},
                    device_scale_factor=1
                )
                logger.info(f'Successfully launched {channel}')
                break
            except Exception as e:
                logger.warning(f"Failed to launch {channel}: {e}")

        if self.browser is None:
            raise Exception("Failed to launch system browser.")

        await asyncio.sleep(0.1)

        self.page = None
        url = self.config.get('url')

        if len(self.browser.pages) > 1:
            for p in self.browser.pages:
                if p.url == "about:blank":
                    try:
                        await p.close()
                    except:
                        pass

        if url:
            for p in self.browser.pages:
                logger.debug(f'BrowserCaptureMethod checking page: {p.url}')
                if p.url.rstrip('/') == url.rstrip('/'):
                    self.page = p
                    logger.info(f'Reusing existing page with URL: {p.url}')
                    break

        if self.page is None:
            if self.browser.pages:
                self.page = self.browser.pages[0]
            else:
                self.page = await self.browser.new_page()

            if url:
                await self.page.goto(url)

        await self.page.bring_to_front()
        await self.page.set_viewport_size({'width': width, 'height': height})

        for p in self.browser.pages:
            if p != self.page:
                try:
                    await p.close()
                except:
                    pass

        logger.info(f'BrowserCaptureMethod start browser {width, height} {url}')

        for _ in range(20):
            target_title = await self.page.title()
            if target_title:
                title_pattern = re.compile(re.escape(target_title))
                res = find_hwnd(title_pattern, ['chrome.exe', 'msedge.exe', 'chromium.exe'], width, height)
                if res[1] > 0:
                    self.hwnd = res[1]
                    self.exe_full_path = res[2]
                    self.x_offset = res[3]
                    self.y_offset = res[4]

                    real_w = res[5]
                    real_h = res[6]
                    if real_w > 0 and real_h > 0:
                        if real_w != width or real_h != height:
                            rect = win32gui.GetWindowRect(self.hwnd)
                            w_width = rect[2] - rect[0]
                            w_height = rect[3] - rect[1]
                            resize_window(self.hwnd, w_width + (width - real_w), w_height + (height - real_h))
                            await asyncio.sleep(0.5)
                            res = find_hwnd(title_pattern, ['chrome.exe', 'msedge.exe', 'chromium.exe'], width, height)
                            if res[1] > 0:
                                self.hwnd = res[1]
                                self.exe_full_path = res[2]
                                self.x_offset = res[3]
                                self.y_offset = res[4]
                                real_w = res[5]
                                real_h = res[6]
                        self._size = (real_w, real_h)

                    logger.info(
                        f"Browser window '{target_title}' found: {self.hwnd} offsets: {self.x_offset},{self.y_offset} size: {self._size}")
                    self.wgc_capture = BrowserWGC(self)
                    break
            await asyncio.sleep(0.5)

    async def _close_async(self):
        logger.info(f'BrowserCaptureMethod _close_async')
        if self.page:
            try:
                await self.page.close()
            except:
                pass
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass

    def start_browser(self):
        if not windows_graphics_available():
            raise CaptureException("Windows Graphics Capture is not supported on this system.")
        if self.page is not None and not self.page.is_closed():
            return
        self.run_in_loop(self._start_browser_async())

    def close(self):
        logger.info(f'BrowserCaptureMethod close browser')
        if self.wgc_capture:
            self.wgc_capture.close()
            self.wgc_capture = None

        if self.loop.is_running():
            self.run_in_loop(self._close_async())
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            try:
                if not self.loop.is_closed():
                    self.loop.run_until_complete(self._close_async())
            except Exception as e:
                logger.warning(f"Failed to run _close_async in stopped loop: {e}")
            logger.info(f'BrowserCaptureMethod close not loop.is_running')

        self.browser = None
        self.playwright = None
        self.page = None
        self.latest_frame = None
        if self.loop_thread.is_alive():
            self.loop_thread.join(timeout=1)

        self.hwnd = 0
        self.last_hwnd = 0

    def do_get_frame(self):
        if self.exit_event.is_set():
            logger.info(f'BrowserCaptureMethod self.exit_event.is_set()')
            self.close()
            return None

        if self.page is None or self.page.is_closed():
            if self.loop.is_running() and self.page is None:
                pass
            elif self.page is not None:
                logger.warning('BrowserCaptureMethod page closed')
                self.page = None
                self.browser = None
                communicate.notification.emit('Paused because browser exited', None, True, True, "start", None)
            return None

        if self.wgc_capture:
            return self.wgc_capture.do_get_frame()

        return None

    def connected(self):
        connected = self.page is not None and not self.page.is_closed()
        return connected



class BrowserWindowAdapter:
    def __init__(self, capture):
        self.capture = capture

    @property
    def hwnd(self):
        return self.capture.hwnd

    @property
    def exists(self):
        return self.capture.connected() and self.capture.hwnd > 0

    @property
    def app_exit_event(self):
        return self.capture.exit_event

    @property
    def width(self):
        return self.capture.width

    @property
    def height(self):
        return self.capture.height

    @property
    def exe_full_path(self):
        return self.capture.exe_full_path

    def get_abs_cords(self, x, y):
        try:
            rect = win32gui.GetWindowRect(self.capture.hwnd)
            return rect[0] + self.capture.x_offset + x, rect[1] + self.capture.y_offset + y
        except:
            return x, y



class BrowserWGC(WindowsGraphicsCaptureMethod):

    def __init__(self, browser_method):
        self.browser_method = browser_method
        super().__init__(BrowserWindowAdapter(browser_method))

    def crop_image(self, frame):
        if frame is None:
            return None

        fh, fw = frame.shape[:2]
        target_w = int(getattr(self.hwnd_window, "width", 0) or 0)
        target_h = int(getattr(self.hwnd_window, "height", 0) or 0)
        if target_w <= 0 or target_h <= 0:
            return frame

        x = int(getattr(self.browser_method, "x_offset", 0) or 0)
        y = int(getattr(self.browser_method, "y_offset", 0) or 0)

        if 0 <= x and 0 <= y and x + target_w <= fw and y + target_h <= fh:
            left_extra = x
            right_extra = fw - (x + target_w)
            top_extra = y
            bottom_extra = fh - (y + target_h)
            if abs(left_extra - right_extra) <= 2 and abs(bottom_extra - left_extra) <= 2:
                return frame[y:y + target_h, x:x + target_w]

        border, title_height = get_crop_point(fw, fh, target_w, target_h)
        border = max(0, int(border))
        title_height = max(0, int(title_height))
        if border == 0 and title_height == 0:
            return frame

        x1 = border
        y1 = title_height
        x2 = fw - border
        y2 = fh - border
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]
