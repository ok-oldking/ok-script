import ctypes

import cv2
import numpy as np
import win32con
import win32gui
import win32ui

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

PW_CLIENT_ONLY = 1 << 0

PW_RENDERFULLCONTENT = 0x00000002

PBYTE = ctypes.POINTER(ctypes.c_ubyte)

BGRA_CHANNEL_COUNT = 4


def try_delete_dc(dc):
    if dc is not None:
        try:
            dc.DeleteDC()
            return True
        except win32ui.error:
            pass



def clean_up_bitblt(context):
    try_delete_dc(context.dc_object)
    try_delete_dc(context.compatible_dc)
    if context.window_dc and context.last_hwnd > 0:
        try:
            win32gui.ReleaseDC(context.last_hwnd, context.window_dc)
        except Exception:
            pass
    if context.bitmap:
        try:
            win32gui.DeleteObject(context.bitmap.GetHandle())
        except Exception:
            pass
    context.window_dc = None
    context.dc_object = None
    context.compatible_dc = None
    context.bitmap = None
    context.last_hwnd = 0
    context.last_width = 0
    context.last_height = 0



def capture_by_bitblt(context, hwnd, width, height, x, y, render_full_content):
    if hwnd <= 0 or width <= 0 or height <= 0:
        logger.error(f'capture_by_bitblt invalid params: hwnd={hwnd}, w={width}, h={height}')
        return None

    #logger.debug(f'capture_by_bitblt hwnd={hwnd} size={width}x{height} offset={x},{y} render={render_full_content}')

    try:
        if context.last_hwnd != hwnd or context.last_height != height or context.last_width != width:
            if context.last_hwnd > 0:
                clean_up_bitblt(context)

            context.last_hwnd = hwnd

            context.window_dc = win32gui.GetWindowDC(hwnd)
            context.dc_object = win32ui.CreateDCFromHandle(context.window_dc)
            context.compatible_dc = context.dc_object.CreateCompatibleDC()
            context.bitmap = win32ui.CreateBitmap()
            context.bitmap.CreateCompatibleBitmap(context.dc_object, width, height)
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
        clean_up_bitblt(context)
        return None

    image.shape = (height, width, BGRA_CHANNEL_COUNT)
    return image



def clean_up_desktop_bitblt(context):
    try_delete_dc(context.dc_object)
    try_delete_dc(context.compatible_dc)
    if context.window_dc:
        try:
            win32gui.ReleaseDC(0, context.window_dc)
        except Exception:
            pass
    if context.bitmap:
        try:
            win32gui.DeleteObject(context.bitmap.GetHandle())
        except Exception:
            pass
    context.window_dc = None
    context.dc_object = None
    context.compatible_dc = None
    context.bitmap = None
    context.last_width = 0
    context.last_height = 0



def capture_desktop_by_bitblt(context, width, height, x, y):
    if width <= 0 or height <= 0:
        logger.error(f'capture_desktop_by_bitblt invalid params: w={width}, h={height}')
        return None

    try:
        if context.last_height != height or context.last_width != width:
            clean_up_desktop_bitblt(context)

            context.window_dc = win32gui.GetDC(0)
            context.dc_object = win32ui.CreateDCFromHandle(context.window_dc)
            context.compatible_dc = context.dc_object.CreateCompatibleDC()
            context.bitmap = win32ui.CreateBitmap()
            context.bitmap.CreateCompatibleBitmap(context.dc_object, width, height)
            context.last_width = width
            context.last_height = height

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
        logger.error(f'capture_desktop_by_bitblt exception: {e}')
        clean_up_desktop_bitblt(context)
        return None

    image.shape = (height, width, BGRA_CHANNEL_COUNT)
    return image



class BitBltCtxDummy:
    def __init__(self):
        self.dc_object = None
        self.bitmap = None
        self.window_dc = None
        self.compatible_dc = None
        self.last_hwnd = 0
        self.last_width = 0
        self.last_height = 0



def get_crop_point(frame_width, frame_height, target_width, target_height):
    x = round((frame_width - target_width) / 2)
    y = (frame_height - target_height) - x
    return x, y



def composite_hwnds(bg, hwnd_window, contexts, render_full):
    hwnds = getattr(hwnd_window, 'hwnds', None)

    if bg is not None and hwnds and len(hwnds) > 1:
        bg = bg.copy()
        bg_client_x = hwnd_window.x
        bg_client_y = hwnd_window.y

        height = bg.shape[0]
        width = bg.shape[1]

        for w in reversed(hwnds):
            w_hwnd = w[0]
            if w_hwnd == hwnd_window.hwnd:
                continue

            # Determine the virtualization ratio by comparing window DPI to monitor DPI
            m_scaling = w[8]
            w_scaling = m_scaling
            try:
                # GetDpiForWindow tells us if the application is per-monitor aware or virtualized (96)
                w_scaling = ctypes.windll.user32.GetDpiForWindow(w_hwnd) / 96.0
            except Exception:
                pass

            # The virtualization ratio determines how much the OS is stretching the logical DC
            ratio = 1.0
            if w_scaling < m_scaling and w_scaling != 0:
                ratio = m_scaling / w_scaling

            # Capture sub-windows at logical resolution. Coordinates are already physical because the process is DPI-aware.
            w_w = w[2]
            w_h = w[3]
            w_client_x = w[4]
            w_client_y = w[5]

            # Calculate the offset between the top-left of the whole window and the top-left of the client area
            off_x = 0
            off_y = 0
            try:
                wr = win32gui.GetWindowRect(w_hwnd)
                # w_client_x and wr[0] are both in the process's current DPI units (physical pixels)
                off_x = w_client_x - wr[0]
                off_y = w_client_y - wr[1]
            except Exception:
                pass

            if w_hwnd not in contexts:
                contexts[w_hwnd] = BitBltCtxDummy()

            # Capturing the logical buffer (Physical / Ratio) and upscaling back to Physical
            w_w_to_capture = int(w_w / ratio)
            w_h_to_capture = int(w_h / ratio)
            off_x_to_capture = int(off_x / ratio)
            off_y_to_capture = int(off_y / ratio)

            # logger.debug(
            #    f'composite_hwnds bitblt {w_hwnd} m_scaling={m_scaling} w_scaling={w_scaling} ratio={ratio} capture_size={w_w_to_capture}x{w_h_to_capture} target={w_w}x{w_h} offset={off_x_to_capture},{off_y_to_capture}')
            img = capture_by_bitblt(contexts[w_hwnd], w_hwnd, w_w_to_capture, w_h_to_capture, off_x_to_capture,
                                    off_y_to_capture, render_full)
            if img is not None:
                if ratio != 1.0:
                    img = cv2.resize(img, (w_w, w_h), interpolation=cv2.INTER_LINEAR)

                paste_x = w_client_x - bg_client_x
                paste_y = w_client_y - bg_client_y

                # logger.debug(
                #    f'composite_hwnds pasting {w_hwnd} to {paste_x},{paste_y} size={img.shape[1]}x{img.shape[0]} bg_size={width}x{height}')

                x1 = max(0, paste_x)
                y1 = max(0, paste_y)
                x2 = min(width, paste_x + img.shape[1])
                y2 = min(height, paste_y + img.shape[0])

                src_x1 = x1 - paste_x
                src_y1 = y1 - paste_y
                src_x2 = src_x1 + (x2 - x1)
                src_y2 = src_y1 + (y2 - y1)

                if x2 > x1 and y2 > y1:
                    channels = min(bg.shape[2], img.shape[2])
                    bg[y1:y2, x1:x2, :channels] = img[src_y1:src_y2, src_x1:src_x2, :channels]
    return bg



def parse_reg_flag(value, flag_name):
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
