# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import ctypes
import ctypes.wintypes
import time

import numpy as np
from typing_extensions import override

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.capture.HwndWindow import HwndWindow
from ok.capture.windows import d3d11
from ok.capture.windows.utils import WINDOWS_BUILD_NUMBER
from ok.logging.Logger import get_logger
from ok.rotypes import IInspectable
from ok.rotypes.Windows.Foundation import TypedEventHandler
from ok.rotypes.Windows.Graphics.Capture import Direct3D11CaptureFramePool, IGraphicsCaptureItemInterop, \
    IGraphicsCaptureItem, GraphicsCaptureItem
from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDevice, \
    CreateDirect3D11DeviceFromDXGIDevice, \
    IDirect3DDxgiInterfaceAccess
from ok.rotypes.roapi import GetActivationFactory

PBYTE = ctypes.POINTER(ctypes.c_ubyte)
WGC_NO_BORDER_MIN_BUILD = 20348

logger = get_logger(__name__)


class WindowsGraphicsCaptureMethod(BaseCaptureMethod):
    name = "Windows Graphics Capture"
    description = "fast, most compatible, capped at 60fps"
    last_frame = None
    last_frame_time = 0
    _hwnd_window: HwndWindow = None
    frame_pool = None
    item = None
    session = None
    cputex = None
    rtdevice = None
    dxdevice = None

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__()
        self._hwnd_window = hwnd_window
        self.start_or_stop()

    def frame_arrived_callback(self, x, y):
        try:
            frame = self.frame_pool.TryGetNextFrame()
        except Exception as e:
            logger.error(f"TryGetNextFrame error {e}")
            self.close()
            return
        if not frame:
            return
        self.last_frame_time = time.time()
        img = None
        with frame:
            need_reset_framepool = False
            need_reset_device = False
            if frame.ContentSize.Width != self.last_size.Width or frame.ContentSize.Height != self.last_size.Height:
                # print('size changed')
                need_reset_framepool = True
                self.last_size = frame.ContentSize

            if need_reset_framepool:
                self.reset_framepool(frame.ContentSize)
                return
            tex = None

            cputex = None
            try:
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
            except OSError as e:
                if e.winerror == d3d11.DXGI_ERROR_DEVICE_REMOVED or e.winerror == d3d11.DXGI_ERROR_DEVICE_RESET:
                    need_reset_framepool = True
                    need_reset_device = True
                else:
                    raise
            finally:
                if tex is not None:
                    tex.Release()
                if cputex is not None:
                    cputex.Release()
            if need_reset_framepool:
                self.reset_framepool(frame.ContentSize, need_reset_device)
                return self.get_frame()
        self.last_frame = img

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
        try:
            if self.hwnd_window.exists and self.frame_pool is None:
                logger.info('init windows capture')
                self.rtdevice = IDirect3DDevice()
                self.dxdevice = d3d11.ID3D11Device()
                self.immediatedc = d3d11.ID3D11DeviceContext()
                self.create_device()
                interop = GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                    IGraphicsCaptureItemInterop)
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
            elif not self.hwnd_window.exists and self.frame_pool is not None:
                self.close()
        except Exception as e:
            logger.error('start_or_stop failed:', exception=e)
        return self.hwnd_window.exists

    def create_device(self):
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

    def do_get_frame(self):
        if self.start_or_stop():
            frame = self.last_frame
            self.last_frame = None
            latency = time.time() - self.last_frame_time
            self.last_frame_time = time.time()

            if frame is not None:
                x, y = self.hwnd_window.get_top_left_frame_offset()
                if x > 0 or y > 0:
                    frame = crop_image(frame, x, y)

            if frame is not None:
                new_height, new_width = frame.shape[:2]
                if new_width <= 0 or new_width <= 0:
                    logger.warning(f"get_frame size <=0 {new_width}x{new_height}")
                    frame = None
                else:
                    self._size = (new_width, new_height)
                    if frame.shape[2] == 4:
                        frame = frame[:, :, :3]
            if latency > 1:
                logger.warning(f"latency too large return None frame: {latency}")
                return None
            else:
                return frame

    @property
    def width(self):
        if self._size[0] == 0:
            self.do_get_frame()
        return self._size[0]

    @property
    def height(self):
        if self._size[1] == 0:
            self.do_get_frame()
        return self._size[1]

    def reset_framepool(self, size, reset_device=False):
        if reset_device:
            self.create_device()
        self.frame_pool.Recreate(self.rtdevice,
                                 DirectXPixelFormat.B8G8R8A8UIntNormalized, 1, size)

    def get_abs_cords(self, x, y):
        return self.hwnd_window.get_abs_cords(x, y)

    def clickable(self):
        return self.hwnd_window is not None and self.hwnd_window.visible


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
