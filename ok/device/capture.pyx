# capture.pyx
import asyncio
import ctypes
import json
import os
import re
import sys
import threading
import time
from enum import IntEnum

import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32process
import win32ui

from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_info
from ok.task.exceptions import CaptureException
from ok.util.GlobalConfig import basic_options
from ok.util.collection import deep_get
from ok.util.color import is_close_to_pure_color
from ok.util.logger import Logger
from ok.util.process import read_global_gpu_pref, read_game_gpu_pref
from ok.util.window import WINDOWS_BUILD_NUMBER, WGC_NO_BORDER_MIN_BUILD, show_title_bar, get_window_bounds, \
    resize_window, get_exe_by_hwnd, windows_graphics_available, find_display, is_foreground_window

logger = Logger.get_logger(__name__)

PW_CLIENT_ONLY = 1 << 0
cdef int PW_RENDERFULLCONTENT = 0x00000002
PBYTE = ctypes.POINTER(ctypes.c_ubyte)
cdef int BGRA_CHANNEL_COUNT = 4

cdef try_delete_dc(dc):
    if dc is not None:
        try:
            dc.DeleteDC()
            return True
        except win32ui.error:
            pass

cdef object capture_by_bitblt(object context, int hwnd, int width, int height, int x, int y, bint render_full_content):
    if hwnd <= 0 or width <= 0 or height <= 0:
        logger.error(f'capture_by_bitblt invalid params: hwnd={hwnd}, w={width}, h={height}')
        return None

    cdef object image = None

    try:
        if context.last_hwnd != hwnd or context.last_height != height or context.last_width != width:
            if context.last_hwnd > 0:
                try_delete_dc(context.dc_object)
                try_delete_dc(context.compatible_dc)
                if context.window_dc:
                    win32gui.ReleaseDC(context.last_hwnd, context.window_dc)
                if context.bitmap:
                    win32gui.DeleteObject(context.bitmap.GetHandle())
                context.window_dc = None
                context.dc_object = None
                context.compatible_dc = None
                context.bitmap = None

            context.window_dc = win32gui.GetWindowDC(hwnd)
            context.dc_object = win32ui.CreateDCFromHandle(context.window_dc)
            context.compatible_dc = context.dc_object.CreateCompatibleDC()
            context.bitmap = win32ui.CreateBitmap()
            context.bitmap.CreateCompatibleBitmap(context.dc_object, width, height)
            context.last_hwnd = hwnd
            context.last_width = width
            context.last_height = height

        if render_full_content:
            ctypes.windll.user32.PrintWindow(hwnd, context.dc_object.GetSafeHdc(), PW_RENDERFULLCONTENT)

        context.compatible_dc.SelectObject(context.bitmap)
        context.compatible_dc.BitBlt(
            (0, 0),
            (width, height),
            context.dc_object,
            (x, y),
            win32con.SRCCOPY,
        )
        image = np.frombuffer(context.bitmap.GetBitmapBits(True), dtype=np.uint8)
    except Exception as e:
        logger.error(f'capture_by_bitblt exception: {e}')
        context.last_hwnd = 0
        return None

    image.shape = (height, width, BGRA_CHANNEL_COUNT)
    return image

cdef class BaseCaptureMethod:
    name = "None"
    description = ""
    cdef public tuple _size
    cdef public object exit_event

    def __init__(self):
        self._size = (0, 0)
        self.exit_event = None

    def close(self):
        pass

    @property
    def width(self):
        self.measure_if_0()
        return self._size[0]

    @property
    def height(self):
        return self._size[1]

    def get_name(self):
        return self.name

    def measure_if_0(self):
        if self._size[0] == 0:
            self.get_frame()

    cpdef object get_frame(self):
        cdef object frame
        if self.exit_event.is_set():
            return
        try:
            frame = self.do_get_frame()
            if frame is not None:
                self._size = (frame.shape[1], frame.shape[0])
                if frame.shape[2] == 4:
                    frame = frame[:, :, :3]
            return frame
        except Exception as e:
            raise CaptureException(str(e)) from e

    def __str__(self):
        return f'{self.get_name()}_{self.width}x{self.height}'

    def do_get_frame(self):
        pass

    def draw_rectangle(self):
        pass

    def clickable(self):
        pass

    def connected(self):
        pass

cdef class BaseWindowsCaptureMethod(BaseCaptureMethod):
    cdef public object _hwnd_window

    def __init__(self, object hwnd_window):
        super().__init__()
        self._hwnd_window = hwnd_window

    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window

    def connected(self):
        return self._hwnd_window is not None and self._hwnd_window.exists and self._hwnd_window.hwnd > 0

    def get_abs_cords(self, x, y):
        return self._hwnd_window.get_abs_cords(x, y)

    def clickable(self):
        return self._hwnd_window is not None and self._hwnd_window.visible

cdef get_crop_point(int frame_width, int frame_height, int target_width, int target_height):
    cdef int x = round((frame_width - target_width) / 2)
    cdef int y = (frame_height - target_height) - x
    return x, y

cdef parse_reg_flag(value, flag_name):
    if not value or not isinstance(value, str): return None
    parts = value.split(';')
    for part in parts:
        kv = part.split('=')
        if len(kv) == 2 and kv[0].strip() == flag_name:
            try:
                v = int(kv[1])
                return v % 2 != 0
            except:
                pass
    return None

cdef class WindowsGraphicsCaptureMethod(BaseWindowsCaptureMethod):
    name = "Windows Graphics Capture"
    description = "fast, most compatible, capped at 60fps"

    cdef object last_frame
    cdef double last_frame_time
    cdef object frame_pool
    cdef object item
    cdef object session
    cdef object cputex
    cdef object rtdevice
    cdef object dxdevice
    cdef object immediatedc
    cdef object evtoken
    cdef object last_size

    def __init__(self, object hwnd_window):
        super().__init__(hwnd_window)
        self.last_frame_time = time.time()
        self.exit_event = hwnd_window.app_exit_event
        self.start_or_stop()

    cdef frame_arrived_callback(self, x, y):
        if self.exit_event.is_set():
            logger.warning('frame_arrived_callback exit_event.is_set() return')
            self.close()
            return
        cdef object next_frame
        try:
            self.last_frame_time = time.time()
            next_frame = self.frame_pool.TryGetNextFrame()
            if next_frame is not None:
                self.last_frame = self.convert_dx_frame(next_frame)
            else:
                logger.warning('frame_arrived_callback TryGetNextFrame returned None')
        except Exception as e:
            logger.error(f"TryGetNextFrame error {e}")
            self.close()
            return

    cdef object convert_dx_frame(self, frame):
        if not frame:
            return None
        cdef bint need_reset_framepool = False
        if frame.ContentSize.Width != self.last_size.Width or frame.ContentSize.Height != self.last_size.Height:
            need_reset_framepool = True
            self.last_size = frame.ContentSize

        if need_reset_framepool:
            logger.info('need_reset_framepool')
            self.reset_framepool(frame.ContentSize)
            return
        cdef bint need_reset_device = False

        cdef object tex = None

        cdef object cputex = None
        cdef object desc = None
        cdef object mapinfo = None
        cdef object img = None
        try:
            from ok.capture.windows import d3d11
            from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDxgiInterfaceAccess
            tex = frame.Surface.astype(IDirect3DDxgiInterfaceAccess).GetInterface(
                d3d11.ID3D11Texture2D.GUID).astype(d3d11.ID3D11Texture2D)

            desc = tex.GetDesc()
            desc.Usage = d3d11.D3D11_USAGE_STAGING
            desc.CPUAccessFlags = d3d11.D3D11_CPU_ACCESS_READ
            desc.BindFlags = 0
            desc.MiscFlags = 0

            cputex = self.dxdevice.CreateTexture2D(ctypes.byref(desc), None)
            self.immediatedc.CopyResource(cputex, tex)
            mapinfo = self.immediatedc.Map(cputex, 0, d3d11.D3D11_MAP_READ, 0)
            img = np.ctypeslib.as_array(ctypes.cast(mapinfo.pData, PBYTE),
                                        (desc.Height, mapinfo.RowPitch // 4, 4))[
                  :, :desc.Width].copy()
            self.immediatedc.Unmap(cputex, 0)
            return img
        except OSError as e:
            if e.winerror == d3d11.DXGI_ERROR_DEVICE_REMOVED or e.winerror == d3d11.DXGI_ERROR_DEVICE_RESET:
                need_reset_framepool = True
                need_reset_device = True
                logger.error('convert_dx_frame win error', e)
            else:
                raise e
        finally:
            if tex is not None:
                tex.Release()
            if cputex is not None:
                cputex.Release()
        if need_reset_framepool:
            self.reset_framepool(frame.ContentSize, need_reset_device)
            return self.get_frame()

    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window
        self.start_or_stop()

    def connected(self):
        return self.hwnd_window is not None and self.hwnd_window.exists and self.frame_pool is not None

    def start_or_stop(self, capture_cursor=False):
        if self.exit_event.is_set():
            logger.warning('start_or_stop exit_event.is_set() return')
            self.close()
            return False
        elif not self.hwnd_window.exists and self.frame_pool is not None:
            logger.warning('start_or_stop not self.hwnd_window.exists')
            self.close()
            return False
        elif self.hwnd_window.hwnd and self.hwnd_window.exists and self.frame_pool is None:
            try:
                from ok.capture.windows import d3d11
                from ok.rotypes import IInspectable
                from ok.rotypes.Windows.Foundation import TypedEventHandler
                from ok.rotypes.Windows.Graphics.Capture import Direct3D11CaptureFramePool, IGraphicsCaptureItemInterop, \
                    IGraphicsCaptureItem, GraphicsCaptureItem
                from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
                from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDevice
                from ok.rotypes.roapi import GetActivationFactory
                logger.info('init windows capture')
                interop = GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                    IGraphicsCaptureItemInterop)
                self.rtdevice = IDirect3DDevice()
                self.dxdevice = d3d11.ID3D11Device()
                self.immediatedc = d3d11.ID3D11DeviceContext()
                self.create_device()
                item = interop.CreateForWindow(self.hwnd_window.hwnd, IGraphicsCaptureItem.GUID)
                self.item = item
                self.last_size = item.Size
                delegate = TypedEventHandler(GraphicsCaptureItem, IInspectable).delegate(
                    self.close)
                self.evtoken = item.add_Closed(delegate)

                hdr, _ = read_game_gpu_pref(self.hwnd_window.exe_full_path)
                if hdr:
                    logger.info(f'Auto HDR enabled for {self.hwnd_window.exe_full_path}, capture mapped to SDR')

                self.frame_pool = Direct3D11CaptureFramePool.CreateFreeThreaded(self.rtdevice,
                                                                                DirectXPixelFormat.B8G8R8A8UIntNormalized,
                                                                                1, item.Size)
                self.session = self.frame_pool.CreateCaptureSession(item)
                pool = self.frame_pool
                pool.add_FrameArrived(
                    TypedEventHandler(Direct3D11CaptureFramePool, IInspectable).delegate(
                        self.frame_arrived_callback))
                self.session.IsCursorCaptureEnabled = capture_cursor
                if WINDOWS_BUILD_NUMBER >= WGC_NO_BORDER_MIN_BUILD:
                    self.session.IsBorderRequired = False
                self.session.StartCapture()
                return True
            except Exception as e:
                logger.error(f'start_or_stop failed: {self.hwnd_window}', exception=e)
                return False
        return self.hwnd_window.exists

    def create_device(self):
        from ok.capture.windows import d3d11
        from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import CreateDirect3D11DeviceFromDXGIDevice
        d3d11.D3D11CreateDevice(
            None,
            d3d11.D3D_DRIVER_TYPE_HARDWARE,
            None,
            d3d11.D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            None,
            0,
            d3d11.D3D11_SDK_VERSION,
            ctypes.byref(self.dxdevice),
            None,
            ctypes.byref(self.immediatedc)
        )
        self.rtdevice = CreateDirect3D11DeviceFromDXGIDevice(self.dxdevice)
        self.evtoken = None

    def close(self):
        logger.info('destroy windows capture')
        if self.frame_pool is not None:
            self.frame_pool.Close()
            self.frame_pool = None
        if self.session is not None:
            self.session.Close()
            self.session = None
        self.item = None
        if self.rtdevice:
            self.rtdevice.Release()
        if self.dxdevice:
            self.dxdevice.Release()
        if self.cputex:
            self.cputex.Release()

    cpdef object do_get_frame(self):
        cdef object frame
        cdef double latency, now, start_wait
        if self.start_or_stop():
            frame = self.last_frame
            if frame is None:
                now = time.time()
                if now - self.last_frame_time > 10:
                    logger.warning('no frame for 10 sec, try to restart')
                    self.close()
                    self.last_frame_time = time.time()
                    return self.do_get_frame()
                start_wait = now
                while self.last_frame is None and (time.time() - start_wait) < 1.0:
                    if self.frame_pool is None:
                        return None
                    time.sleep(0.003)
                frame = self.last_frame
            if frame is None:
                return None
            self.last_frame = None
            latency = time.time() - self.last_frame_time
            if latency > 2:
                logger.warning(f"latency too large return None frame: {latency}")
                return None
            frame = self.crop_image(frame)
            if frame is not None:
                new_height, new_width = frame.shape[:2]
                if new_width <= 0 or new_height <= 0:
                    logger.warning(f"get_frame size <=0 {new_width}x{new_height}")
                    return None

            return frame

    def reset_framepool(self, size, reset_device=False):
        logger.info(f'reset_framepool')
        from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
        if reset_device:
            self.create_device()
        self.frame_pool.Recreate(self.rtdevice,
                                 DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, size)

    def crop_image(self, frame):
        if frame is not None:
            border, title_height = get_crop_point(frame.shape[1], frame.shape[0], self.hwnd_window.width,
                                                  self.hwnd_window.height)
            if border > 0 or title_height > 0:
                height, width = frame.shape[:2]
                x2 = width - border
                y2 = height - border
                return frame[title_height:y2, border:x2]
        return frame

cdef bint render_full
render_full = False

cdef class BitBltCaptureMethod(BaseWindowsCaptureMethod):
    name = "BitBlt"
    short_description = "fastest, least compatible"
    description = (
            "\nThe best option when compatible. But it cannot properly record "
            + "\nOpenGL, Hardware Accelerated or Exclusive Fullscreen windows. "
            + "\nThe smaller the selected region, the more efficient it is. "
    )

    cdef public object dc_object, bitmap, window_dc, compatible_dc
    cdef public int last_hwnd, last_width, last_height

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        self.dc_object = None
        self.bitmap = None
        self.window_dc = None
        self.compatible_dc = None
        self.last_hwnd = 0
        self.last_width = 0
        self.last_height = 0

    cpdef object do_get_frame(self):
        cdef int x, y
        if self.hwnd_window.real_x_offset != 0 or self.hwnd_window.real_y_offset != 0:
            x = self.hwnd_window.real_x_offset
            y = self.hwnd_window.real_y_offset
        else:
            x, y = get_crop_point(self.hwnd_window.window_width, self.hwnd_window.window_height,
                                  self.hwnd_window.width, self.hwnd_window.height)

        cdef int width = self.hwnd_window.real_width or self.hwnd_window.width
        cdef int height = self.hwnd_window.real_height or self.hwnd_window.height

        return capture_by_bitblt(self, self.hwnd_window.hwnd, width, height, x, y, render_full)

    def get_name(self):
        return f'BitBlt_{render_full}'

    def test_exclusive_full_screen(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error(f'Failed to test_exclusive_full_screen {self.hwnd_window}')
            return False
        return True

    def test_is_not_pure_color(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error(f'Failed to test_is_not_pure_color frame is None {self.hwnd_window}')
            return False
        else:
            if is_close_to_pure_color(frame):
                logger.error(f'Failed to test_is_not_pure_color failed {self.hwnd_window}')
                return False
            else:
                return True

cdef class HwndWindow:
    cdef public object app_exit_event, stop_event, mute_option, thread, device_manager, global_config
    cdef public str title, exe_full_path, hwnd_class, _hwnd_title
    cdef public int hwnd, player_id, window_width, window_height, x, y, width, height, frame_width, frame_height, real_width, real_height, real_x_offset, real_y_offset
    cdef public bint visible, exists, pos_valid, to_handle_mute
    cdef public double scaling, frame_aspect_ratio, last_mute_check
    cdef public list monitors_bounds, exe_names
    cdef public list visible_monitors

    def __init__(self, exit_event, title, exe_name=None, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None,
                 global_config=None, device_manager=None):
        super().__init__()
        logger.info(f'HwndWindow init title:{title} player_id:{player_id} exe_name:{exe_name} hwnd_class:{hwnd_class}')
        self.app_exit_event = exit_event
        self.exe_names = None
        self.visible_monitors = []
        self.device_manager = device_manager
        self.to_handle_mute = True
        self.title = title
        self.stop_event = threading.Event()
        self.visible = False
        self.player_id = player_id
        self.window_width = 0
        self.window_height = 0
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.hwnd = 0
        self.frame_width = 0
        self.frame_height = 0
        self.exists = False
        self.title = None
        self.exe_full_path = None
        self.real_width = 0
        self.real_height = 0
        self.real_x_offset = 0
        self.real_y_offset = 0
        self.scaling = 1.0
        self.frame_aspect_ratio = 0
        self.last_mute_check = 0

        self.hwnd_class = hwnd_class
        self.pos_valid = False
        self._hwnd_title = ""
        self.monitors_bounds = get_monitors_bounds()
        self.mute_option = global_config.get_config(basic_options)
        self.global_config = global_config
        self.mute_option.validator = self.validate_mute_config
        self.update_window(title, exe_name, frame_width, frame_height, player_id, hwnd_class)
        self.thread = threading.Thread(target=self.update_window_size, name="update_window_size")
        self.thread.start()

    def validate_mute_config(self, key, value):
        if key == 'Mute Game while in Background' and self.hwnd:
            logger.info(f'validate_mute_config {value}')
            if value:
                self.handle_mute(value)
            else:
                logger.info(f'config changed unmute set_mute_state {value}')
                set_mute_state(self.hwnd, 0)
        return True, None

    def stop(self):
        self.stop_event.set()

    def bring_to_front(self):
        if self.hwnd:
            win32gui.SetForegroundWindow(self.hwnd)

    def try_resize_to(self, resize_to):
        if not self.global_config.get_config('Basic Options').get('Auto Resize Game Window'):
            return False
        if self.hwnd and self.window_width > 0:
            show_title_bar(self.hwnd)
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            x, y, window_width, window_height, width, height, scaling = get_window_bounds(self.hwnd)
            title_height = window_height - height
            logger.info(f'try_resize_to {x, y, window_width, window_height, width, height, scaling} ')
            border = window_width - width
            resize_width = 0
            resize_height = 0
            for resolution in resize_to:
                if screen_width >= border + resolution[0] and screen_height >= title_height + resolution[
                    1]:
                    resize_width = resolution[0] + border
                    resize_height = resolution[1] + title_height
                    break
            if resize_width > 0:
                resize_window(self.hwnd, resize_width, resize_height)
                self.do_update_window_size()
                if self.window_height == resize_height and self.window_width == resize_width:
                    logger.info(f'resize hwnd success to {self.width}x{self.height}')
                    return True
                else:
                    logger.error(f'resize hwnd failed: {self.width}x{self.height}')

    def update_window(self, title, exe_name, frame_width, frame_height, player_id=-1, hwnd_class=None):
        self.player_id = player_id
        self.title = title
        if isinstance(exe_name, str):
            self.exe_names = [exe_name]
        else:
            self.exe_names = exe_name
        self.update_frame_size(frame_width, frame_height)
        self.hwnd_class = hwnd_class

    def update_frame_size(self, width, height):
        logger.debug(f"update_frame_size:{self.frame_width}x{self.frame_height} to {width}x{height}")
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            if width > 0 and height > 0:
                self.frame_aspect_ratio = width / height
                logger.debug(f"HwndWindow: frame ratio: width: {width}, height: {height}")
        self.hwnd = 0
        self.do_update_window_size()

    def update_window_size(self):
        while not self.app_exit_event.is_set() and not self.stop_event.is_set():
            self.do_update_window_size()
            time.sleep(0.2)
        if self.hwnd and self.mute_option.get('Mute Game while in Background'):
            logger.info(f'exit reset mute state to 0')
            set_mute_state(self.hwnd, 0)

    def get_abs_cords(self, x, y):
        return self.x + x, self.y + y

    def do_update_window_size(self):
        try:
            changed = False
            exists = False
            visible, x, y, window_width, window_height, width, height, scaling = self.visible, self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling
            if self.hwnd == 0:
                name, self.hwnd, self.exe_full_path, self.real_x_offset, self.real_y_offset, self.real_width, self.real_height = find_hwnd(
                    self.title,
                    self.exe_names or self.device_manager.config.get('selected_exe'),
                    self.frame_width, self.frame_height, player_id=self.player_id, class_name=self.hwnd_class,
                    selected_hwnd=self.device_manager.config.get('selected_hwnd'))
                if self.hwnd > 0:
                    logger.info(
                        f'do_update_window_size find_hwnd {self.hwnd} {self.exe_full_path} {win32gui.GetClassName(self.hwnd)} real:{self.real_x_offset},{self.real_y_offset},{self.real_width},{self.real_height}')
                    changed = True
                exists = self.hwnd > 0
            if self.hwnd > 0:
                exists = win32gui.IsWindow(self.hwnd)
                if exists:
                    visible = self.is_foreground()
                    x, y, window_width, window_height, width, height, scaling = get_window_bounds(
                        self.hwnd)
                    if self.frame_aspect_ratio != 0 and height != 0:
                        window_ratio = width / height
                        if window_ratio < self.frame_aspect_ratio:
                            cropped_window_height = int(width / self.frame_aspect_ratio)
                            height = cropped_window_height
                    pos_valid = check_pos(x, y, width, height, self.monitors_bounds)
                    if isinstance(self.device_manager.capture_method,
                                  BaseWindowsCaptureMethod) and not pos_valid and pos_valid != self.pos_valid and self.device_manager.executor is not None:
                        if self.device_manager.executor.pause():
                            logger.error(f'og.executor.pause pos_invalid: {x, y, width, height}')
                            communicate.notification.emit('Paused because game window is minimized or out of screen!',
                                                          None,
                                                          True, True, "start")
                    if pos_valid != self.pos_valid:
                        self.pos_valid = pos_valid
                else:
                    if self.global_config.get_config('Basic Options').get(
                            'Exit App when Game Exits') and self.device_manager.executor is not None and self.device_manager.executor.pause():
                        alert_info('Auto exit because game exited', True)
                        communicate.quit.emit()
                    else:
                        communicate.notification.emit('Game Exited', None, True, True, None)
                    self.hwnd = 0
                if visible != self.visible:
                    self.visible = visible
                    for visible_monitor in self.visible_monitors:
                        visible_monitor.on_visible(visible)
                    changed = True

                if changed or (time.time() - self.last_mute_check > 2):
                    self.handle_mute()
                    self.last_mute_check = time.time()

                if (window_width != self.window_width or window_height != self.window_height or
                    x != self.x or y != self.y or width != self.width or height != self.height or scaling != self.scaling) and (
                        (x >= -1 and y >= -1) or self.visible):
                    self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling = x, y, window_width, window_height, width, height, scaling
                    changed = True
                if self.exists != exists:
                    self.exists = exists
                    changed = True
                if changed:
                    device = self.device_manager.get_preferred_device()
                    if device and device['connected'] != self.exists:
                        logger.info(f"hwnd changed,connected:{self.exists}")
                        device['connected'] = self.exists
                        communicate.adb_devices.emit(True)
                    logger.info(
                        f"do_update_window_size changed,visible:{self.visible},exists:{self.exists} x:{self.x} y:{self.y} window:{self.width}x{self.height} self.window:{self.window_width}x{self.window_height} real:{self.real_width}x{self.real_height}")
                    communicate.window.emit(self.visible, self.x + self.real_x_offset, self.y + self.real_y_offset,
                                            self.window_width, self.window_height,
                                            self.width,
                                            self.height, self.scaling)
        except Exception as e:
            logger.error(f"do_update_window_size exception", e)

    def is_foreground(self):
        return is_foreground_window(self.hwnd)

    def handle_mute(self, mute=None):
        if mute is None:
            mute = self.mute_option.get('Mute Game while in Background')
        if self.hwnd and self.to_handle_mute and mute:
            set_mute_state(self.hwnd, 0 if self.visible else 1)

    def frame_ratio(self, size):
        if self.frame_width > 0 and self.width > 0:
            return int(size / self.frame_width * self.width)
        else:
            return size

    @property
    def hwnd_title(self):
        if not self._hwnd_title:
            if self.hwnd:
                self._hwnd_title = win32gui.GetWindowText(self.hwnd)
        return self._hwnd_title

    def __str__(self) -> str:
        return str(
            f"title_{self.title}_{self.exe_names}_{self.width}x{self.height}_{self.hwnd}_{self.exists}_{self.visible}")

def check_pos(x, y, width, height, monitors_bounds):
    return width >= 0 and height >= 0 and is_window_in_screen_bounds(x, y, width, height, monitors_bounds)

def get_monitors_bounds():
    monitors_bounds = []
    monitors = win32api.EnumDisplayMonitors()
    for monitor in monitors:
        monitor_info = win32api.GetMonitorInfo(monitor[0])
        monitor_rect = monitor_info['Monitor']
        monitors_bounds.append(monitor_rect)
    return monitors_bounds

def is_window_in_screen_bounds(window_left, window_top, window_width, window_height, monitors_bounds):
    window_right, window_bottom = window_left + window_width, window_top + window_height

    for monitor_rect in monitors_bounds:
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_rect

        if (window_left >= monitor_left and window_top >= monitor_top and
                window_right <= monitor_right and window_bottom <= monitor_bottom):
            return True

    return False

def find_hwnd(title, exe_names, frame_width, frame_height, player_id=-1, class_name=None,
              selected_hwnd=0):
    if exe_names is None and title is None:
        return None, 0, None, 0, 0, 0, 0
    frame_aspect_ratio = frame_width / frame_height if frame_height != 0 else 0

    def callback(hwnd, results):
        if selected_hwnd > 0:
            if selected_hwnd != selected_hwnd:
                return True
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd) and win32gui.IsWindowVisible(hwnd):
            text = None
            if title:
                text = win32gui.GetWindowText(hwnd)
                if isinstance(title, str):
                    if title != text:
                        return True
                elif not re.search(title, text):
                    return True
            name, full_path, cmdline = get_exe_by_hwnd(hwnd)
            if not name:
                return True
            if exe_names:
                match = False
                for exe_name in exe_names:
                    if compare_path_safe(name, exe_name) or compare_path_safe(exe_name, full_path):
                        match = True
                if not match:
                    return True
            if player_id != -1:
                if player_id != get_player_id_from_cmdline(cmdline):
                    logger.warning(
                        f'player id check failed,cmdline {cmdline} {get_player_id_from_cmdline(cmdline)} != {player_id}')
                    return True
                else:
                    logger.info(f'player id check success')
            if class_name is not None:
                if win32gui.GetClassName(hwnd) != class_name:
                    return True
            if text is None:
                text = win32gui.GetWindowText(hwnd)
            x, y, _, _, width, height, scaling = get_window_bounds(
                hwnd)
            ret = (hwnd, full_path, width, height, x, y, text)
            results.append(ret)
        return True

    results = []
    win32gui.EnumWindows(callback, results)

    if len(results) > 0:
        logger.info(f'find_hwnd results {len(results)} {results}')
        biggest = None
        for result in results:
            if biggest is None or (result[2] * result[3]) > biggest[2] * biggest[3]:
                biggest = result
        x_offset = 0
        y_offset = 0
        real_width = 0
        real_height = 0
        if frame_aspect_ratio != 0:
            real_width, real_height = biggest[2], biggest[3]
            matching_child = enum_child_windows(biggest, frame_aspect_ratio, frame_width, frame_height)
            if matching_child is not None:
                x_offset, y_offset, real_width, real_height = matching_child
            logger.info(
                f'find_hwnd {frame_width, frame_height} {biggest} {x_offset, y_offset, real_width, real_height}')
        return biggest[6], biggest[0], biggest[1], x_offset, y_offset, real_width, real_height

    return None, 0, None, 0, 0, 0, 0

def get_mute_state(hwnd):
    from pycaw.api.audioclient import ISimpleAudioVolume
    from pycaw.utils import AudioUtilities
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.pid == pid:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            return volume.GetMute()
    return 0

def set_mute_state(hwnd, mute):
    from pycaw.api.audioclient import ISimpleAudioVolume
    from pycaw.utils import AudioUtilities
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.pid == pid:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            volume.SetMute(mute, None)
            break

def get_player_id_from_cmdline(cmdline):
    for i in range(len(cmdline)):
        if i != 0:
            if cmdline[i].isdigit():
                return int(cmdline[i])
    for i in range(len(cmdline)):
        if i != 0:
            value = re.search(r'index=(\d+)', cmdline[i])
            if value is not None:
                return int(value.group(1))
    return 0

def enum_child_windows(biggest, frame_aspect_ratio, frame_width, frame_height):
    ratio_match = []

    def child_callback(hwnd, _):
        visible = win32gui.IsWindowVisible(hwnd)
        parent = win32gui.GetParent(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        parent_rect = win32gui.GetWindowRect(parent)
        real_width = rect[2] - rect[0]
        real_height = rect[3] - rect[1]
        if visible:
            ratio = real_width / real_height
            difference = abs(ratio - frame_aspect_ratio)
            support = difference <= 0.01 * frame_aspect_ratio
            percent = (real_width * real_height) / (biggest[2] * biggest[3])
            x_offset = rect[0] - biggest[4]
            y_offset = rect[1] - biggest[5]
            child_class = win32gui.GetClassName(hwnd)
            if support and percent >= 0.7 or (frame_width == real_width and real_width >= frame_width) or (
                    frame_height == real_height and real_height >= frame_height):
                ratio_match.append((difference, (x_offset, y_offset, real_width, real_height)))
            logger.info(
                f'find_hwnd child_callback {child_class} {visible} {parent_rect} {rect} {real_width} {real_height} support:{support}')
        return True

    win32gui.EnumChildWindows(biggest[0], child_callback, None)

    if len(ratio_match) > 0:
        ratio_match.sort(key=lambda x: x[0])
        logger.debug(f'ratio_match sorted {ratio_match}')
        return ratio_match[0][1]

    return None

cdef class DesktopDuplicationCaptureMethod(BaseWindowsCaptureMethod):
    name = "Direct3D Desktop Duplication"
    short_description = "slower, bound to display"
    description = (
            "\nDuplicates the desktop using Direct3D. "
            + "\nIt can record OpenGL and Hardware Accelerated windows. "
            + "\nAbout 10-15x slower than BitBlt. Not affected by window size. "
            + "\nOverlapping windows will show up and can't record across displays. "
            + "\nThis option may not be available for hybrid GPU laptops, "
            + "\nsee D3DDD-Note-Laptops.md for a solution. "
    )
    cdef object desktop_duplication

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        import d3dshot
        self.desktop_duplication = d3dshot.create(capture_output="numpy")

    cpdef object do_get_frame(self):

        hwnd = self.hwnd_window.hwnd
        if hwnd == 0:
            return None

        hmonitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        if not hmonitor:
            return None

        self.desktop_duplication.display = find_display(hmonitor, self.desktop_duplication.displays)

        cdef int left, top, right, bottom
        cdef object screenshot
        left = self.hwnd_window.x
        top = self.hwnd_window.y
        right = left + self.hwnd_window.width
        bottom = top + self.hwnd_window.height
        screenshot = self.desktop_duplication.screenshot((left, top, right, bottom))
        if screenshot is None:
            return None
        return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

    def close(self):
        if self.desktop_duplication is not None:
            self.desktop_duplication.stop()

def update_capture_method(config, capture_method, hwnd, exit_event=None):
    try:
        method_preferences = config.get('capture_method', [])

        for method_name in method_preferences:
            if method_name == 'WGC':
                if win_graphic := get_win_graphics_capture(capture_method, hwnd, exit_event):
                    logger.info(f'use WGC capture')
                    return win_graphic
            elif method_name == 'BitBlt_RenderFull':
                global render_full
                render_full = True
                if bitblt_capture := get_capture(capture_method, BitBltCaptureMethod, hwnd, exit_event):
                    logger.info(f'use BitBlt_RenderFull capture')
                    return bitblt_capture
            elif method_name == 'BitBlt':
                global render_full
                hdr_enabled, swap_enabled = read_game_gpu_pref(hwnd.exe_full_path)
                render_full = swap_enabled is True or \
                              (swap_enabled is None and read_global_gpu_pref()[1] is True)
                logger.info(f'use BitBlt capture swap_enabled: {swap_enabled}, render_full: {render_full}')

                if bitblt_capture := get_capture(capture_method, BitBltCaptureMethod, hwnd, exit_event):
                    return bitblt_capture
            elif method_name == 'DXGI':
                if dxgi_capture := get_capture(capture_method, DesktopDuplicationCaptureMethod, hwnd, exit_event):
                    return dxgi_capture

        return None
    except Exception as e:
        logger.error(f'update_capture_method exception, return None: {e}')
        return None

def get_win_graphics_capture(capture_method, hwnd, exit_event):
    if windows_graphics_available():
        target_method = WindowsGraphicsCaptureMethod
        capture_method = get_capture(capture_method, target_method, hwnd, exit_event)
        if capture_method.start_or_stop():
            return capture_method

def get_capture(capture_method, target_method, hwnd, exit_event):
    if not isinstance(capture_method, target_method):
        if capture_method is not None:
            capture_method.close()
        capture_method = target_method(hwnd)
    capture_method.hwnd_window = hwnd
    capture_method.exit_event = exit_event
    return capture_method


class ImageShape(IntEnum):
    Y = 0
    X = 1
    Channels = 2


class ColorChannel(IntEnum):
    Blue = 0
    Green = 1
    Red = 2
    Alpha = 3


def decimal(value: float):
    return f"{int(value * 100) / 100}".ljust(4, "0")

def is_digit(value: str | int | None):
    if value is None:
        return False
    try:
        return 0 <= int(value) <= 9
    except (ValueError, TypeError):
        return False

def is_valid_hwnd(hwnd: int):
    if not hwnd:
        return False
    if sys.platform == "win32":
        return bool(win32gui.IsWindow(hwnd) and win32gui.GetWindowText(hwnd))
    return True

cdef class BrowserCaptureMethod(BaseCaptureMethod):
    name = "Browser Capture"
    description = "Capture from Browser using Playwright and Windows Graphics Capture"
    cdef public object playwright, browser, page, config, loop, loop_thread, latest_frame
    cdef public object wgc_capture
    cdef public int hwnd, x_offset, y_offset, last_width, last_height, last_hwnd
    cdef public str exe_full_path

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
        args = [
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
            "--high-dpi-support=1",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=CalculateNativeWinOcclusion",
            "--force-color-profile=srgb"
        ]

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

        target_title = await self.page.title()

        if target_title:
            target_title = re.compile(target_title)

        for _ in range(10):
            res = find_hwnd(target_title, ['chrome.exe', 'msedge.exe', 'chromium.exe'], width, height)
            if res[1] > 0:
                self.hwnd = res[1]
                self.exe_full_path = res[2]
                self.x_offset = res[3]
                self.y_offset = res[4]
                logger.info(f"Browser window {target_title} found:  {res[1]} offsets: {self.x_offset},{self.y_offset}")
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

    cpdef object do_get_frame(self):
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
                communicate.notification.emit('Paused because browser exited', None, True, True, "start")
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


cdef class BrowserWGC(WindowsGraphicsCaptureMethod):
    cdef BrowserCaptureMethod browser_method

    def __init__(self, BrowserCaptureMethod browser_method):
        self.browser_method = browser_method
        super().__init__(BrowserWindowAdapter(browser_method))

    def crop_image(self, frame):
        if frame is None:
            return None
        cdef int x = self.browser_method.x_offset
        cdef int y = self.browser_method.y_offset
        cdef int w = self.browser_method.width
        cdef int h = self.browser_method.height

        fh, fw = frame.shape[:2]
        if x < 0 or y < 0 or x + w > fw or y + h > fh:
            x = max(0, x)
            y = max(0, y)
            w = min(w, fw - x)
            h = min(h, fh - y)

        return frame[y:y + h, x:x + w]

cdef class ADBCaptureMethod(BaseCaptureMethod):
    name = "ADB command line Capture"
    description = "use the adb screencap command, slow but works when in background/minimized, takes 300ms per frame"
    cdef bint _connected
    cdef object device_manager

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.device_manager = device_manager

    cpdef object do_get_frame(self):
        return self.screencap()

    cdef object screencap(self):
        if self.exit_event.is_set():
            return None
        cdef object frame
        frame = self.device_manager.do_screencap(self.device_manager.device)
        if frame is not None:
            self._connected = True
        else:
            self._connected = False
        return frame

    def connected(self):
        if not self._connected and self.device_manager.device is not None:
            self.screencap()
        return self._connected and self.device_manager.device is not None

cdef class ImageCaptureMethod(BaseCaptureMethod):
    name = "Image capture method "
    description = "for debugging"
    cdef list images
    cdef int index

    def __init__(self, exit_event, images):
        super().__init__()
        self.exit_event = exit_event
        self.set_images(images)
        self.index = 0

    def set_images(self, images):
        self.images = list(reversed(images))
        self.index = 0
        self.get_frame()

    def get_abs_cords(self, x, y):
        return x, y

    cpdef object do_get_frame(self):
        cdef str image_path
        if len(self.images) > 0:
            image_path = self.images[self.index]
            if image_path:
                frame = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if self.index < len(self.images) - 1:
                    self.index += 1
                return frame

    def connected(self):
        return True

cdef class NemuIpcCaptureMethod(BaseCaptureMethod):
    name = "Nemu Ipc Capture"
    description = "mumu player 12 only"
    cdef bint _connected
    cdef public object device_manager, nemu_impl, emulator

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.device_manager = device_manager
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.nemu_impl = None
        self.emulator = None

    def update_emulator(self, emulator):
        self.emulator = emulator
        logger.info(f'update_path_and_id {emulator}')
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def init_nemu(self):
        self.check_mumu_app_keep_alive_400()
        if not self.nemu_impl:
            from ok.capture.adb.nemu_ipc import NemuIpc
            self.nemu_impl = NemuIpc(
                nemu_folder=self.base_folder(),
                instance_id=self.emulator.player_id,
                display_id=0
            )

    def base_folder(self):
        return os.path.dirname(os.path.dirname(self.emulator.path))

    def check_mumu_app_keep_alive_400(self):
        file = os.path.abspath(os.path.join(
            self.base_folder(),
            f'vms/MuMuPlayer-12.0-{self.emulator.player_id}/configs/customer_config.json'))

        try:
            with open(file, mode='r', encoding='utf-8') as f:
                s = f.read()
                data = json.loads(s)
        except FileNotFoundError:
            logger.warning(f'Failed to check check_mumu_app_keep_alive, file {file} not exists')
            return False
        value = deep_get(data, keys='customer.app_keptlive', default=None)
        if str(value).lower() == 'true':
            logger.error('Please turn off enable background keep alive in MuMuPlayer settings')
            raise Exception('Please turn off enable background keep alive in MuMuPlayer settings')
        return True

    def close(self):
        super().close()
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    cpdef object do_get_frame(self):
        self.init_nemu()
        return self.screencap()

    cdef object screencap(self):
        if self.exit_event.is_set():
            return None
        if self.nemu_impl:
            return self.nemu_impl.screenshot(timeout=0.5)

    def connected(self):
        return True

cdef bint compare_path_safe(str str1, str str2):
    if str1 is None and str2 is None:
        return True
    if str1 is None or str2 is None:
        return False
    return str1.replace('\\', '/').lower() == str2.replace('\\', '/').lower()