"""Windows Shell thumbnail cache integration.

The public ``IThumbnailCache`` API returns thumbnails shared with Windows
Explorer.  This module deliberately has no effect outside Windows and keeps
all Win32/COM details out of the UI code.
"""

import os
import sys

from PySide6.QtGui import QImage


if sys.platform == 'win32':
    import ctypes
    import uuid
    from ctypes import wintypes

    _S_OK = 0
    _S_FALSE = 1
    _COINIT_APARTMENTTHREADED = 0x2
    _CLSCTX_INPROC_SERVER = 0x1
    _WTS_INCACHEONLY = 0x1
    _WTS_EXTRACT = 0x0
    _WTS_FORCEEXTRACTION = 0x4
    _HRESULT = ctypes.c_long

    class _GUID(ctypes.Structure):
        _fields_ = [
            ('Data1', wintypes.DWORD),
            ('Data2', wintypes.WORD),
            ('Data3', wintypes.WORD),
            ('Data4', ctypes.c_ubyte * 8),
        ]

    class _BITMAP(ctypes.Structure):
        _fields_ = [
            ('bmType', wintypes.LONG),
            ('bmWidth', wintypes.LONG),
            ('bmHeight', wintypes.LONG),
            ('bmWidthBytes', wintypes.LONG),
            ('bmPlanes', wintypes.WORD),
            ('bmBitsPixel', wintypes.WORD),
            ('bmBits', ctypes.c_void_p),
        ]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', wintypes.DWORD),
            ('biWidth', wintypes.LONG),
            ('biHeight', wintypes.LONG),
            ('biPlanes', wintypes.WORD),
            ('biBitCount', wintypes.WORD),
            ('biCompression', wintypes.DWORD),
            ('biSizeImage', wintypes.DWORD),
            ('biXPelsPerMeter', wintypes.LONG),
            ('biYPelsPerMeter', wintypes.LONG),
            ('biClrUsed', wintypes.DWORD),
            ('biClrImportant', wintypes.DWORD),
        ]

    class _DIBSECTION(ctypes.Structure):
        _fields_ = [
            ('dsBm', _BITMAP),
            ('dsBmih', _BITMAPINFOHEADER),
            ('dsBitfields', wintypes.DWORD * 3),
            ('dshSection', wintypes.HANDLE),
            ('dsOffset', wintypes.DWORD),
        ]

    def _guid(value):
        return _GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    _CLSID_LOCAL_THUMBNAIL_CACHE = _guid('{50EF4544-AC9F-4A8E-B21B-8A26180DB13F}')
    _IID_ISHELL_ITEM = _guid('{43826D1E-E718-42EE-BC55-A1E261C37BFE}')
    _IID_ITHUMBNAIL_CACHE = _guid('{F676C15D-596A-4CE2-8234-33996F445DB1}')

    _ole32 = ctypes.WinDLL('ole32')
    _shell32 = ctypes.WinDLL('shell32')
    _gdi32 = ctypes.WinDLL('gdi32')

    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _ole32.CoInitializeEx.restype = _HRESULT
    _ole32.CoUninitialize.argtypes = []
    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    _ole32.CoCreateInstance.restype = _HRESULT
    _shell32.SHCreateItemFromParsingName.argtypes = [
        wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p)]
    _shell32.SHCreateItemFromParsingName.restype = _HRESULT
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
    _gdi32.GetObjectW.restype = ctypes.c_int

    def _com_method(interface, index, restype, *argtypes):
        vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        address = vtable[index]
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(address)

    def _release(interface):
        if interface:
            _com_method(interface, 2, wintypes.ULONG)(interface)


class WindowsThumbnailReader:
    """Retrieve a requested-size thumbnail from the Windows shared cache.

    The caller first reads cached thumbnails, then can request extraction when
    it has verified that this Windows session retains cache entries.  The
    caller must create this reader in a worker thread.
    """

    def __init__(self, size):
        self.size = size
        self._cache = None
        self._co_initialized = False

    @property
    def available(self):
        return self._cache is not None

    def open(self):
        if sys.platform != 'win32':
            return False

        result = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        if result not in (_S_OK, _S_FALSE):
            return False
        self._co_initialized = True

        cache = ctypes.c_void_p()
        result = _ole32.CoCreateInstance(
            ctypes.byref(_CLSID_LOCAL_THUMBNAIL_CACHE), None,
            _CLSCTX_INPROC_SERVER, ctypes.byref(_IID_ITHUMBNAIL_CACHE),
            ctypes.byref(cache))
        if result != _S_OK:
            self.close()
            return False
        self._cache = cache
        return True

    def close(self):
        if sys.platform != 'win32':
            return
        if self._cache is not None:
            _release(self._cache)
            self._cache = None
        if self._co_initialized:
            _ole32.CoUninitialize()
            self._co_initialized = False

    def get_thumbnail(self, path):
        """Return a cached thumbnail, or ``None`` when the cache misses."""
        return self._get_thumbnail(path, _WTS_INCACHEONLY)

    def extract_thumbnail(self, path, force=False):
        """Extract a thumbnail through the Shell and let Windows cache it."""
        flags = _WTS_FORCEEXTRACTION if force else _WTS_EXTRACT
        return self._get_thumbnail(path, flags)

    def _get_thumbnail(self, path, flags):
        if not self.available or not os.path.isfile(path):
            return None, False

        item = ctypes.c_void_p()
        shared_bitmap = ctypes.c_void_p()
        try:
            result = _shell32.SHCreateItemFromParsingName(
                path, None, ctypes.byref(_IID_ISHELL_ITEM), ctypes.byref(item))
            if result != _S_OK:
                return None, False

            cache_flags = wintypes.DWORD()
            result = _com_method(
                self._cache, 3, _HRESULT, ctypes.c_void_p, wintypes.UINT,
                wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)(
                self._cache, item, self.size, flags,
                    ctypes.byref(shared_bitmap), ctypes.byref(cache_flags), None)
            if result != _S_OK or not shared_bitmap:
                return None, False

            bitmap = wintypes.HBITMAP()
            # Detach returns a private copy when the cache bitmap lives in
            # shared memory, making it safe to convert with GDI and release.
            result = _com_method(
                shared_bitmap, 7, _HRESULT,
                ctypes.POINTER(wintypes.HBITMAP))(
                    shared_bitmap, ctypes.byref(bitmap))
            if result != _S_OK or not bitmap:
                return None, False
            try:
                image = self._qimage_from_hbitmap(bitmap)
            finally:
                _gdi32.DeleteObject(bitmap)
            return image, True
        except OSError:
            return None, False
        finally:
            _release(shared_bitmap)
            _release(item)

    @staticmethod
    def _qimage_from_hbitmap(bitmap):
        section = _DIBSECTION()
        if _gdi32.GetObjectW(bitmap, ctypes.sizeof(section), ctypes.byref(section)) != ctypes.sizeof(section):
            return None
        bitmap_info = section.dsBm
        width = bitmap_info.bmWidth
        height = abs(bitmap_info.bmHeight)
        if width <= 0 or height <= 0 or bitmap_info.bmBitsPixel != 32 or not bitmap_info.bmBits:
            return None
        image = QImage(
            ctypes.string_at(bitmap_info.bmBits, bitmap_info.bmWidthBytes * height),
            width, height, bitmap_info.bmWidthBytes, QImage.Format_ARGB32).copy()
        return image
