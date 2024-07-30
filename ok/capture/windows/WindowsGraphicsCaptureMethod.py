# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import ctypes
import ctypes.wintypes
import platform
import sys
import time

import numpy as np
from typing_extensions import override

from ok.capture.HwndWindow import HwndWindow
from ok.capture.windows import d3d11
from ok.capture.windows.BaseWindowsCaptureMethod import BaseWindowsCaptureMethod
from ok.capture.windows.utils import WINDOWS_BUILD_NUMBER
from ok.logging.Logger import get_logger

PBYTE = ctypes.POINTER(ctypes.c_ubyte)
WGC_NO_BORDER_MIN_BUILD = 20348
WGC_MIN_BUILD = 19041

logger = get_logger(__name__)


class WindowsGraphicsCaptureMethod(BaseWindowsCaptureMethod):
    name = "Windows Graphics Capture"
    description = "fast, most compatible, capped at 60fps"

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        self.last_frame = None
        self.last_frame_time = 0
        self.frame_pool = None
        self.item = None
        self.session = None
        self.cputex = None
        self.rtdevice = None
        self.dxdevice = None
        self.start_or_stop()

    def frame_arrived_callback(self, x, y):
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

    def convert_dx_frame(self, frame):
        if not frame:
            # logger.warning('convert_dx_frame self.last_dx_frame is none')
            return None
        need_reset_framepool = False
        if frame.ContentSize.Width != self.last_size.Width or frame.ContentSize.Height != self.last_size.Height:
            need_reset_framepool = True
            self.last_size = frame.ContentSize

        if need_reset_framepool:
            logger.info('need_reset_framepool')
            self.reset_framepool(frame.ContentSize)
            return
        need_reset_device = False

        tex = None

        cputex = None
        try:
            from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDxgiInterfaceAccess
            from ok.rotypes.roapi import GetActivationFactory
            tex = frame.Surface.astype(IDirect3DDxgiInterfaceAccess).GetInterface(
                d3d11.ID3D11Texture2D.GUID).astype(d3d11.ID3D11Texture2D)
            desc = tex.GetDesc()
            desc2 = d3d11.D3D11_TEXTURE2D_DESC()
            desc2.Width = desc.Width
            desc2.Height = desc.Height
            desc2.MipLevels = desc.MipLevels
            desc2.ArraySize = desc.ArraySize
            desc2.Format = desc.Format
            desc2.SampleDesc = desc.SampleDesc
            desc2.Usage = d3d11.D3D11_USAGE_STAGING
            desc2.CPUAccessFlags = d3d11.D3D11_CPU_ACCESS_READ
            desc2.BindFlags = 0
            desc2.MiscFlags = 0
            cputex = self.dxdevice.CreateTexture2D(ctypes.byref(desc2), None)
            self.immediatedc.CopyResource(cputex, tex)
            mapinfo = self.immediatedc.Map(cputex, 0, d3d11.D3D11_MAP_READ, 0)
            img = np.ctypeslib.as_array(ctypes.cast(mapinfo.pData, PBYTE),
                                        (desc.Height, mapinfo.RowPitch // 4, 4))[
                  :, :desc.Width].copy()
            self.immediatedc.Unmap(cputex, 0)
            # logger.debug(f'frame latency {(time.time() - start):.3f} {(time.time() - dx_time):.3f}')
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
        if self.hwnd_window.hwnd and self.hwnd_window.exists and self.frame_pool is None:
            try:
                from ok.rotypes import IInspectable
                from ok.rotypes.Windows.Foundation import TypedEventHandler
                from ok.rotypes.Windows.Graphics.Capture import Direct3D11CaptureFramePool, IGraphicsCaptureItemInterop, \
                    IGraphicsCaptureItem, GraphicsCaptureItem
                from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
                from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDevice, \
                    CreateDirect3D11DeviceFromDXGIDevice, \
                    IDirect3DDxgiInterfaceAccess
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
        elif not self.hwnd_window.exists and self.frame_pool is not None:
            self.close()
            return False
        return self.hwnd_window.exists

    def create_device(self):
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

    @override
    def close(self):
        logger.info('destroy windows capture')
        if self.frame_pool is not None:
            self.frame_pool.Close()
            self.frame_pool = None
        if self.session is not None:
            self.session.Close()  # E_UNEXPECTED ???
            self.session = None
        self.item = None
        if self.rtdevice:
            self.rtdevice.Release()
        if self.dxdevice:
            self.dxdevice.Release()
        if self.cputex:
            self.cputex.Release()

    @override
    def do_get_frame(self):
        if self.start_or_stop():
            frame = self.last_frame
            self.last_frame = None
            if frame is None:
                if time.time() - self.last_frame_time > 10:
                    logger.warning(f'no frame for 10 sec, try to restart')
                    self.close()
                    self.last_frame_time = time.time()
                    return self.do_get_frame()
                else:
                    return None
            latency = time.time() - self.last_frame_time

            frame = self.crop_image(frame)

            if frame is not None:
                new_height, new_width = frame.shape[:2]
                if new_width <= 0 or new_width <= 0:
                    logger.warning(f"get_frame size <=0 {new_width}x{new_height}")
                    frame = None
            if latency > 2:
                logger.warning(f"latency too large return None frame: {latency}")
                return None
            else:
                # logger.debug(f'frame latency: {latency}')
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
            x, y = self.get_crop_point(frame.shape[1], frame.shape[0], self.hwnd_window.width, self.hwnd_window.height)
            if x > 0 or y > 0:
                frame = crop_image(frame, x, y)
        return frame


def crop_image(image, border, title_height):
    # Load the image
    # Image dimensions
    height, width = image.shape[:2]

    # Calculate the coordinates for the bottom-right corner
    x2 = width - border
    y2 = height - border

    # Crop the image
    cropped_image = image[title_height:y2, border:x2]

    # print(f"cropped image: {title_height}-{y2}, {border}-{x2} {cropped_image.shape}")
    #
    # cv2.imshow('Image Window', cropped_image)
    #
    # # Wait for any key to be pressed before closing the window
    # cv2.waitKey(0)

    return cropped_image


WINDOWS_BUILD_NUMBER = int(platform.version().split(".")[-1]) if sys.platform == "win32" else -1


def windows_graphics_available():
    logger.debug(
        f"check available WINDOWS_BUILD_NUMBER:{WINDOWS_BUILD_NUMBER} >= {WGC_MIN_BUILD} {WINDOWS_BUILD_NUMBER >= WGC_MIN_BUILD}")
    if WINDOWS_BUILD_NUMBER >= WGC_MIN_BUILD:
        try:
            from ok.rotypes.roapi import GetActivationFactory
            from ok.rotypes.Windows.Graphics.Capture import IGraphicsCaptureItemInterop
            GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                IGraphicsCaptureItemInterop)
            return True
        except Exception as e:
            logger.error(f'check available failed: {e}', exception=e)
            return False
