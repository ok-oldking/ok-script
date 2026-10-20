"""FP16 WGC capture with BetterGI's fixed HDR-to-SDR exposure conversion."""

from functools import lru_cache
import ctypes

import numpy as np

from ok.device.capture_methods.bitblt_utils import PBYTE
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod


@lru_cache(maxsize=1)
def _half_float_tables():
    """Map every binary16 encoding to an SDR color or linear alpha byte.

    Algorithm reference: BetterGI HdrToSdrShader at commit
    4118e28f3d0e071d49dadf56762441342680f321:
    https://github.com/babalae/better-genshin-impact/blob/4118e28f3d0e071d49dadf56762441342680f321/Fischless.GameCapture/Graphics/Helpers/HdrToSdrShader.cs
    Uses quarter exposure and Chilliant's linear-to-sRGB approximation.
    This independent NumPy implementation tabulates the math once, avoiding
    full-frame floating-point temporaries and square roots on every capture.
    """
    values = np.arange(65536, dtype=np.uint16).view(np.float16).astype(np.float32)
    np.nan_to_num(values, copy=False, nan=0.0, posinf=65504.0, neginf=0.0)
    alpha = np.rint(np.clip(values, 0, 1) * 255).astype(np.uint8)
    linear = np.clip(values * 0.25, 0, 1)
    root = np.sqrt(linear)
    fourth_root = np.sqrt(root)
    eighth_root = np.sqrt(fourth_root)
    srgb = (0.662002687 * root + 0.684122060 * fourth_root
            - 0.323583601 * eighth_root - 0.0225411470 * linear)
    color = np.rint(np.clip(srgb, 0, 1) * 255).astype(np.uint8)
    color.flags.writeable = alpha.flags.writeable = False
    return color, alpha


class WindowsGraphicsCaptureHDRMethod(WindowsGraphicsCaptureMethod):
    name = "Windows Graphics Capture HDR"
    description = "Only use when using Windows AutoHDR (Not Recommended)"

    @property
    def pixel_format(self):
        from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
        return DirectXPixelFormat.R16G16B16A16Float

    def read_mapped_frame(self, mapinfo):
        height, width = self.last_size.Height, self.last_size.Width
        # RowPitch includes driver padding. The buffer is only valid until
        # Unmap, so return an owned BGRA array just like the SDR capture path.
        buffer = np.ctypeslib.as_array(ctypes.cast(mapinfo.pData, PBYTE),
                                      (height * mapinfo.RowPitch,))
        rgba_bits = np.ndarray((height, width, 4), dtype=np.uint16,
                               buffer=buffer, strides=(mapinfo.RowPitch, 8, 2))
        color, alpha = _half_float_tables()
        bgra = np.empty((height, width, 4), dtype=np.uint8)
        for destination, source in enumerate((2, 1, 0)):
            bgra[:, :, destination] = color[rgba_bits[:, :, source]]
        bgra[:, :, 3] = alpha[rgba_bits[:, :, 3]]
        return bgra
