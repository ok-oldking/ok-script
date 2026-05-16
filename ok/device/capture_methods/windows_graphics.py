import ctypes
import threading
import time

import numpy as np
import win32gui

from ok.util.logger import Logger
from ok.util.window import WINDOWS_BUILD_NUMBER, WGC_NO_BORDER_MIN_BUILD

from ok.device.capture_methods import bitblt
from ok.device.capture_methods.base import BaseWindowsCaptureMethod
from ok.device.capture_methods.bitblt_utils import PBYTE, composite_hwnds, get_crop_point

logger = Logger.get_logger(__name__)

class WindowsGraphicsCaptureMethod(BaseWindowsCaptureMethod):
    name = "Windows Graphics Capture"
    description = "fast, most compatible, capped at 60fps"

    def __init__(self, hwnd_window):
        super().__init__(hwnd_window)
        self.lock = threading.RLock()
        self.frame_event = threading.Event()
        self.last_frame_time = time.time()
        self.exit_event = hwnd_window.app_exit_event
        self.cputex = None
        self.contexts = {}
        self.capture_hwnd = 0
        self.frame_pool = None
        self.session = None
        self.item = None
        self.rtdevice = None
        self.dxdevice = None
        self.immediatedc = None
        self.last_frame = None
        self.last_size = None
        self.last_start_failure_key = None
        self.last_start_failure_time = 0
        self.start_or_stop()

    def frame_arrived_callback(self, *args):
        next_frame = None
        with self.lock:
            if self.exit_event.is_set():
                logger.warning('frame_arrived_callback exit_event.is_set() return')
                return
            try:
                self.last_frame_time = time.time()
                if self.frame_pool is not None:
                    next_frame = self.frame_pool.TryGetNextFrame()
            except Exception as e:
                logger.error(f"TryGetNextFrame error {e}")
                return

        # Always accept and process the new frame to guarantee lowest latency
        if next_frame is not None:
            frame = self.convert_dx_frame(next_frame)
            if hasattr(next_frame, 'Close'):
                next_frame.Close()

            if frame is not None:
                with self.lock:
                    self.last_frame = frame
                    self.frame_event.set()

    def convert_dx_frame(self, frame):
        if not frame or self.dxdevice is None or self.immediatedc is None:
            return None

        need_reset_framepool = False
        need_reset_device = False

        if frame.ContentSize.Width != self.last_size.Width or frame.ContentSize.Height != self.last_size.Height:
            need_reset_framepool = True
            self.last_size = frame.ContentSize

        if need_reset_framepool:
            logger.info('need_reset_framepool')
            self.reset_framepool(frame.ContentSize)
            return None

        tex = None
        try:
            tex = frame.Surface.astype(self.IDirect3DDxgiInterfaceAccess).GetInterface(
                self.d3d11.ID3D11Texture2D.GUID).astype(self.d3d11.ID3D11Texture2D)

            if self.cputex is None:
                desc = tex.GetDesc()
                desc.Usage = self.d3d11.D3D11_USAGE_STAGING
                desc.CPUAccessFlags = self.d3d11.D3D11_CPU_ACCESS_READ
                desc.BindFlags = 0
                desc.MiscFlags = 0
                self.cputex = self.dxdevice.CreateTexture2D(ctypes.byref(desc), None)

            self.immediatedc.CopyResource(self.cputex, tex)
            mapinfo = self.immediatedc.Map(self.cputex, 0, self.d3d11.D3D11_MAP_READ, 0)
            img = np.ctypeslib.as_array(ctypes.cast(mapinfo.pData, PBYTE),
                                        (self.last_size.Height, mapinfo.RowPitch // 4, 4))[
                :, :self.last_size.Width].copy()
            self.immediatedc.Unmap(self.cputex, 0)
            return img
        except OSError as e:
            if e.winerror == self.d3d11.DXGI_ERROR_DEVICE_REMOVED or e.winerror == self.d3d11.DXGI_ERROR_DEVICE_RESET:
                need_reset_framepool = True
                need_reset_device = True
                logger.error('convert_dx_frame win error', e)
            else:
                raise e
        finally:
            if tex is not None:
                tex.Release()

        if need_reset_framepool:
            self.reset_framepool(frame.ContentSize, need_reset_device)
        return None


    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window
        self.start_or_stop()

    def connected(self):
        return self.hwnd_window is not None and self.hwnd_window.exists and self.frame_pool is not None

    def get_capture_hwnd(self):
        hwnd = getattr(self.hwnd_window, 'hwnd', 0)
        try:
            if hwnd and win32gui.IsWindow(hwnd):
                return hwnd
        except Exception:
            pass
        return 0

    def start_or_stop(self, capture_cursor=False):
        with self.lock:
            if self.exit_event.is_set():
                logger.warning('start_or_stop exit_event.is_set() return')
                self.close()
                return False
            elif not self.hwnd_window.exists:
                logger.warning('start_or_stop not self.hwnd_window.exists')
                self.close()
                return False

            capture_hwnd = self.get_capture_hwnd()
            if not capture_hwnd:
                logger.warning(f'start_or_stop no valid hwnd: {self.hwnd_window}')
                self.close()
                return False

            if self.frame_pool is not None and self.capture_hwnd != capture_hwnd:
                logger.info(f'start_or_stop hwnd changed from {self.capture_hwnd} to {capture_hwnd}')
                self.close()

            failure_key = capture_hwnd
            if self.frame_pool is None and self.last_start_failure_key == failure_key and time.time() - self.last_start_failure_time < 5:
                return False

            if self.hwnd_window.exists and self.frame_pool is None:
                logger.info('start_or_stop start WGC capture')
                try:
                    from ok.capture.windows import d3d11
                    from ok.rotypes import IInspectable
                    from ok.rotypes.Windows.Foundation import TypedEventHandler
                    from ok.rotypes.Windows.Graphics.Capture import Direct3D11CaptureFramePool, \
                        IGraphicsCaptureItemInterop, \
                        IGraphicsCaptureItem, GraphicsCaptureItem
                    from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
                    from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDevice, \
                        IDirect3DDxgiInterfaceAccess
                    from ok.rotypes.roapi import GetActivationFactory

                    self.d3d11 = d3d11
                    self.IDirect3DDxgiInterfaceAccess = IDirect3DDxgiInterfaceAccess

                    interop = GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                        IGraphicsCaptureItemInterop)
                    self.rtdevice = IDirect3DDevice()
                    self.dxdevice = self.d3d11.ID3D11Device()
                    self.immediatedc = self.d3d11.ID3D11DeviceContext()
                    self.create_device()
                    self.capture_hwnd = capture_hwnd
                    item = interop.CreateForWindow(capture_hwnd, IGraphicsCaptureItem.GUID)
                    self.item = item
                    self.last_size = item.Size
                    delegate = TypedEventHandler(GraphicsCaptureItem, IInspectable).delegate(
                        self.close)
                    self.evtoken = item.add_Closed(delegate)

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
                    self.last_start_failure_key = None
                    return True
                except Exception as e:
                    self.last_start_failure_key = failure_key
                    self.last_start_failure_time = time.time()
                    self.close()
                    logger.error(f'start_or_stop failed: {self.hwnd_window}', exception=e)
                    return False
            return self.hwnd_window.exists

    def create_device(self):
        from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import CreateDirect3D11DeviceFromDXGIDevice
        self.d3d11.D3D11CreateDevice(
            None,
            self.d3d11.D3D_DRIVER_TYPE_HARDWARE,
            None,
            self.d3d11.D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            None,
            0,
            self.d3d11.D3D11_SDK_VERSION,
            ctypes.byref(self.dxdevice),
            None,
            ctypes.byref(self.immediatedc)
        )
        self.rtdevice = CreateDirect3D11DeviceFromDXGIDevice(self.dxdevice)
        self.evtoken = None

    def close(self):
        with self.lock:
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
                self.rtdevice = None
            if self.dxdevice:
                self.dxdevice.Release()
                self.dxdevice = None
            if self.immediatedc:
                self.immediatedc.Release()
                self.immediatedc = None
            if self.cputex:
                self.cputex.Release()
                self.cputex = None
            self.capture_hwnd = 0

    def do_get_frame(self):

        if self.start_or_stop():
            now = time.time()
            if now - self.last_frame_time > 10:
                logger.warning('no frame for 10 sec, try to restart')
                self.close()
                self.last_frame_time = time.time()
                return self.do_get_frame()

            with self.lock:
                frame = self.last_frame
                self.last_frame = None  # Pop the frame instantly so we don't get stuck on it next time
                self.frame_event.clear()

            start_wait = time.time()
            while frame is None:
                timeout_duration = 1.0 - (time.time() - start_wait)
                if timeout_duration <= 0:
                    break

                self.frame_event.wait(timeout_duration)

                with self.lock:
                    if self.frame_pool is None:
                        return None
                    frame = self.last_frame
                    self.last_frame = None  # Pop the frame
                    self.frame_event.clear()

            if frame is None:
                return None

            latency = time.time() - self.last_frame_time
            if latency > 2:
                logger.warning(f"latency too large return None frame: {latency}")
                return None

            frame = self.crop_image(frame)

            frame = composite_hwnds(frame, self.hwnd_window, self.contexts, bitblt.render_full)

            if frame is not None:
                new_height = frame.shape[0]
                new_width = frame.shape[1]
                if new_width <= 0 or new_height <= 0:
                    logger.warning(f"get_frame size <=0 {new_width}x{new_height}")
                    return None

            return frame

    def reset_framepool(self, size, reset_device=False):
        logger.info(f'reset_framepool')
        from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
        if self.cputex:
            self.cputex.Release()
            self.cputex = None
        if reset_device:
            self.create_device()
        self.frame_pool.Recreate(self.rtdevice,
                                 DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, size)

    def crop_image(self, frame):
        if frame is not None:
            border, title_height = get_crop_point(frame.shape[1], frame.shape[0], self.hwnd_window.width,
                                                  self.hwnd_window.height)
            if border > 0 or title_height > 0:
                height = frame.shape[0]
                width = frame.shape[1]
                x2 = width - border
                y2 = height - border
                return frame[title_height:y2, border:x2]
        return frame
