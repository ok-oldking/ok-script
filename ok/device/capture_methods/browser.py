import asyncio
import ctypes
import os
import re
import threading
import time
from urllib.parse import urlsplit
from ctypes import wintypes

import cv2
import numpy as np
import win32con
import win32gui

from ok.core.events import communicate
from ok.task.exceptions import CaptureBusyException, CaptureException
from ok.util.logger import Logger
from ok.util.window import DWMWA_EXTENDED_FRAME_BOUNDS, windows_graphics_available, find_hwnd

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.capture_methods.browser_webrtc import (
    PEER_CONNECTION_REGISTRY_JS,
    STATUS_ENDED,
    TAP_JS,
    WebRtcFrameReceiver,
    parse_message,
    place_in_viewport,
)
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod

logger = Logger.get_logger(__name__)

# WebRTC capture mode: how often to look for (or re-check) the page's video, and how long a
# Playwright screenshot may take when there is no video.
TAP_CHECK_INTERVAL = 1.0
SCREENSHOT_TIMEOUT_MS = 3000
FRAME_SOURCE_TIMEOUT = 10
TAP_RETRY_AFTER_FAILURE = 30

# Pages ask for pointer lock on mouse down (e.g. cloud game SDKs). The automated browser window is
# usually not the OS foreground window, so Chromium rejects the lock (pointerlockerror) and such pages
# fall back to cursor mode, drop the click or send Esc. Fake a granted lock; pages still release it
# through exitPointerLock exactly as with a real lock. Disable with browser config 'fake_pointer_lock': False.
FAKE_POINTER_LOCK_JS = '''() => {
  if (window.__okFakePointerLock === undefined) {
    window.__okFakePointerLock = null;
    Object.defineProperty(Document.prototype, 'pointerLockElement', {configurable: true,
      get() { return window.__okFakePointerLock; }});
    window.__okRequestPointerLock = function () {
      if (window.__okFakePointerLock !== this) {
        window.__okFakePointerLock = this;
        document.dispatchEvent(new Event('pointerlockchange'));
      }
      return Promise.resolve();
    };
    Element.prototype.requestPointerLock = window.__okRequestPointerLock;
    Document.prototype.exitPointerLock = function () {
      if (window.__okFakePointerLock) {
        window.__okFakePointerLock = null;
        document.dispatchEvent(new Event('pointerlockchange'));
      }
    };
  }
  // Already loaded pages may have cached the native function on the element itself.
  for (const el of document.querySelectorAll('video, canvas')) {
    if (Object.prototype.hasOwnProperty.call(el, 'requestPointerLock')) {
      el.requestPointerLock = window.__okRequestPointerLock;
    }
  }
  return true;
}'''


class BrowserCaptureMethod(BaseCaptureMethod):
    """Run the target page in a Playwright-controlled system browser and capture it.

    Browser config keys (app config 'browser'):
        url: page to open.
        resolution: page viewport (width, height); default (1280, 720).
        channels: browsers to try in order; default ['msedge', 'chrome', 'chromium'].
        args: extra browser command-line arguments.
        navigation_timeout: seconds to wait for the page to load; default 60, 0 waits without limit.
        fake_pointer_lock: grant pointer lock requests without OS focus; default True.
        capture: 'wgc' (default) captures the browser window with Windows Graphics Capture.
            'webrtc' reads the decoded frames of the page's largest WebRTC <video> directly (or,
            when the page draws the stream on a canvas, the video track its peer connection
            receives), which keeps working while the window is minimized but captures only the
            video (page elements over or around it are black) and uses more CPU. While the page
            shows no such video, frames come from Playwright screenshots, which are slower.
    """
    name = "Browser Capture"
    description = "Capture from Browser using Playwright and Windows Graphics Capture"
    capture_mode = 'wgc'

    def __init__(self, config, exit_event, global_config=None):
        super().__init__()
        self.config = config
        self.exit_event = exit_event
        self.global_config = global_config
        self._audio_mute = None
        res = config.get('resolution', (1280, 720))
        self._size = (res[0], res[1])
        logger.info(f'BrowserCaptureMethod init {self._size}')
        self.playwright = None
        self.browser = None
        self.page = None
        self.latest_frame = None
        self.wgc_capture = None
        self.capture_mode = config.get('capture', 'wgc')
        self._webrtc = None
        self._tap_offset = (0.0, 0.0)
        self._next_tap_check = 0.0
        self._frame_source = None
        self._frame_lock = threading.Lock()
        self._loopback_origins = set()
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
        # A start that fails part way (navigation timeout, window not found) must not leave a page
        # behind: connected() and start_browser() treat a live page as a started browser.
        try:
            await self._launch_browser_async()
        except Exception:
            await self._close_async()
            if self.wgc_capture:
                self.wgc_capture.close()
                self.wgc_capture = None
            self.browser = None
            self.playwright = None
            self.page = None
            self.hwnd = 0
            raise

    async def _launch_browser_async(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self._loopback_origins = set()

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
        args.extend(self.config.get('args', []))

        user_data_dir = os.path.join('cache', 'playwright')

        channels = self.config.get('channels', ['msedge', 'chrome', 'chromium'])
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

        fake_pointer_lock = self.config.get('fake_pointer_lock', True)
        if fake_pointer_lock:
            await self.browser.add_init_script(script=f'({FAKE_POINTER_LOCK_JS})()')
        if self.capture_mode == 'webrtc':
            await self.browser.add_init_script(script=f'({PEER_CONNECTION_REGISTRY_JS})()')

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
                # Seconds; 0 waits without limit.
                timeout = self.config.get('navigation_timeout', 60)
                await self.page.goto(url, timeout=timeout * 1000)

        if fake_pointer_lock:
            # A reused page loaded before the init script was registered.
            await self.page.evaluate(FAKE_POINTER_LOCK_JS)
        if self.capture_mode == 'webrtc':
            # Connections a reused page already created stay unregistered until it reloads.
            await self.page.evaluate(PEER_CONNECTION_REGISTRY_JS)

        await self.page.bring_to_front()
        await self.page.set_viewport_size({'width': width, 'height': height})

        for p in self.browser.pages:
            if p != self.page:
                try:
                    await p.close()
                except:
                    pass

        logger.info(f'BrowserCaptureMethod start browser {width, height} {url}')

        found = False
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

                    if not self.update_window_geometry():
                        await asyncio.sleep(0.1)
                        continue

                    logger.info(
                        f"Browser window '{target_title}' found: {self.hwnd} offsets: {self.x_offset},{self.y_offset} size: {self._size}")
                    if self.capture_mode != 'webrtc':
                        self.wgc_capture = BrowserWGC(self)
                    if getattr(self, 'global_config', None) is not None:
                        from ok.device.browser_audio import BrowserAudioMute
                        self._audio_mute = BrowserAudioMute(
                            self.page,
                            lambda: win32gui.GetForegroundWindow() == self.hwnd,
                            lambda: self.global_config.get_config('Basic Options').get(
                                'Mute Game while in Background'), self.exit_event)
                        self._audio_mute.start()
                    found = True
                    break
            await asyncio.sleep(0.5)

        if not found:
            raise CaptureException(f'Browser window not found for page {self.page.url}')

    def get_viewport_rect(self):
        """Return the visible page renderer's bounds in screen coordinates."""
        rects = []

        def collect(hwnd, _):
            if (win32gui.IsWindowVisible(hwnd)
                    and win32gui.GetClassName(hwnd) == 'Chrome_RenderWidgetHostHWND'):
                left, top, right, bottom = win32gui.GetClientRect(hwnd)
                if right > left and bottom > top:
                    x, y = win32gui.ClientToScreen(hwnd, (left, top))
                    rects.append((x, y, x + right - left, y + bottom - top))
            return True

        win32gui.EnumChildWindows(self.hwnd, collect, None)
        return max(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), default=None)

    def update_window_geometry(self):
        viewport = self.get_viewport_rect()
        if viewport is None:
            return False
        client_x, client_y = win32gui.ClientToScreen(self.hwnd, (0, 0))
        _, _, client_w, client_h = win32gui.GetClientRect(self.hwnd)
        self.x_offset = viewport[0] - client_x
        self.y_offset = viewport[1] - client_y
        width, height = self._size
        # Playwright's fixed viewport can extend below the native window when
        # Chromium displays an infobar. Grow the window instead of losing pixels.
        missing_w = max(0, self.x_offset + width - client_w)
        missing_h = max(0, self.y_offset + height - client_h)
        if missing_w or missing_h:
            left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
            win32gui.SetWindowPos(self.hwnd, 0, 0, 0,
                                 right - left + missing_w, bottom - top + missing_h,
                                 win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            return False
        return True

    async def _close_async(self):
        logger.info(f'BrowserCaptureMethod _close_async')
        if getattr(self, '_audio_mute', None) is not None:
            await self._audio_mute.close()
            self._audio_mute = None
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
        if self._webrtc is not None:
            self._webrtc.close()
            self._webrtc = None
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
        return self.do_get_frame_wait(0)

    def do_get_frame_wait(self, timeout):
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
                communicate.notification.emit('Paused because browser exited', None, True, True, "start", None, None)
            return None

        if self.capture_mode == 'webrtc':
            acquired = self._frame_lock.acquire(timeout=timeout) if timeout > 0 else self._frame_lock.acquire(False)
            if not acquired:
                raise CaptureBusyException('Browser capture is busy')
            try:
                return self._webrtc_or_screenshot_frame()
            finally:
                self._frame_lock.release()

        if self.wgc_capture:
            if not self.update_window_geometry():
                return None
            return self.wgc_capture.do_get_frame_wait(timeout)

        return None

    def _webrtc_or_screenshot_frame(self):
        frame, source = self._webrtc_frame(), 'WebRTC video'
        if frame is None:
            frame, source = self._screenshot_frame(), 'Playwright screenshot'
        if frame is not None and source != self._frame_source:
            logger.info(f'BrowserCaptureMethod capturing from {source}')
            self._frame_source = source
        return frame

    def _webrtc_frame(self):
        if self._webrtc is None:
            self._webrtc = WebRtcFrameReceiver()
        if time.monotonic() >= self._next_tap_check:
            # Also re-checks a running tap: the page may have replaced or moved its video.
            self._next_tap_check = time.monotonic() + TAP_CHECK_INTERVAL
            result, offset = self._run_quietly(self._install_tap_async()) or ('error', None)
            if result != 'ok':
                if result == 'ws-failed':
                    logger.warning('BrowserCaptureMethod page cannot connect to the WebRTC frame receiver; '
                                   f'retrying in {TAP_RETRY_AFTER_FAILURE}s')
                    self._next_tap_check = time.monotonic() + TAP_RETRY_AFTER_FAILURE
                self._webrtc.disconnect()
                return None
            self._tap_offset = offset
        message = self._webrtc.request()
        if message is None:
            return None
        status, frame, content_rect, element_rect = parse_message(message)
        if status == STATUS_ENDED:
            self._webrtc.disconnect()
            self._next_tap_check = 0.0
        if frame is None:
            return None
        return place_in_viewport(frame, content_rect, element_rect, self._size, self._tap_offset)

    async def _install_tap_async(self):
        """Stream from the largest live WebRTC video in any frame of the page.

        Returns ('ok', offset of that frame in the page), ('no-video', None) or ('ws-failed', None).
        """
        page = self.page
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        result = 'no-video'
        for frame in frames:
            try:
                await self._allow_loopback_async(frame.url)
                status = await frame.evaluate(TAP_JS, {'wsUrl': self._webrtc.url})
                if status == 'ws-failed':
                    result = status
                if status != 'ok':
                    continue
                if frame == page.main_frame:
                    return 'ok', (0.0, 0.0)
                box = await (await frame.frame_element()).bounding_box()
                if box is not None:
                    return 'ok', (box['x'], box['y'])
            except Exception as e:
                logger.debug(f'WebRTC tap not installed in {frame.url}: {e}')
        return result, None

    async def _allow_loopback_async(self, url):
        """Let a public page reach the loopback frame receiver without Chrome's Local Network Access prompt."""
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https'):
            return
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin in self._loopback_origins:
            return
        self._loopback_origins.add(origin)
        try:
            await self.browser.grant_permissions(['local-network-access'], origin=origin)
        except Exception as e:
            logger.info(f'BrowserCaptureMethod cannot grant local network access to {origin}: {e}')

    def _screenshot_frame(self):
        data = self._run_quietly(self.page.screenshot(type='png', timeout=SCREENSHOT_TIMEOUT_MS))
        if not data:
            return None
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    def _run_quietly(self, coro):
        """run_in_loop without error logs: frame polling failures are expected (navigation, minimized)."""
        if not self.loop.is_running():
            coro.close()
            return None
        try:
            return asyncio.run_coroutine_threadsafe(coro, self.loop).result(FRAME_SOURCE_TIMEOUT)
        except Exception as e:
            logger.debug(f'BrowserCaptureMethod frame source failed: {e}')
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

    @property
    def capture_target_signature(self):
        return (
            self.hwnd,
            self.width,
            self.height,
            self.capture.x_offset,
            self.capture.y_offset,
            self.capture.exe_full_path,
        )

    def get_abs_cords(self, x, y):
        try:
            return win32gui.ClientToScreen(
                self.capture.hwnd, (self.capture.x_offset + x, self.capture.y_offset + y))
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

        # WGC excludes the invisible resize borders, whereas renderer offsets
        # are relative to the native client area. Convert both to screen space.
        bounds = wintypes.RECT()
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            self.browser_method.hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(bounds), ctypes.sizeof(bounds))
        if result != 0:
            return None
        screen_x, screen_y = self.hwnd_window.get_abs_cords(0, 0)
        x = screen_x - bounds.left
        y = screen_y - bounds.top
        if x < 0 or y < 0 or x + target_w > fw or y + target_h > fh:
            return None
        return frame[y:y + target_h, x:x + target_w]
