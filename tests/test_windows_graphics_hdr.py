from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from ok import WindowsGraphicsCaptureHDRMethod
from ok.device.capture_methods import update
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod
from ok.device.capture_methods.windows_graphics_hdr import _half_float_tables
from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat


def test_hdr_padded_rows_convert_rgba_to_owned_bgra():
    method = object.__new__(WindowsGraphicsCaptureHDRMethod)
    method.last_size = SimpleNamespace(Height=2, Width=2)
    # A third pixel represents row padding, which must not enter the image.
    source = np.array([
        [[4, 0, 0, 1], [0, 4, 0, .5], [99, 99, 99, 99]],
        [[0, 0, 4, 1], [1, 1, 1, 0], [99, 99, 99, 99]],
    ], dtype=np.float16)
    mapped = SimpleNamespace(pData=source.ctypes.data, RowPitch=24)
    result = method.read_mapped_frame(mapped)
    np.testing.assert_array_equal(result, [
        [[0, 0, 255, 255], [0, 255, 0, 128]],
        [[255, 0, 0, 255], [137, 137, 137, 0]],
    ])
    source[:] = 0
    assert result[0, 0, 2] == 255
    assert result.dtype == np.uint8
    assert result.flags.c_contiguous


def test_color_table_matches_shader_math_and_clamps_invalid_values():
    color, alpha = _half_float_tables()
    samples = np.array([-np.inf, -1, 0, .0001, .01, .1, .5, 1, 2, 4, 100, np.inf, np.nan],
                       dtype=np.float16)
    expected = []
    for value in samples:
        value = float(value)
        x = 0 if np.isnan(value) else min(1, max(0, value / 4))
        srgb = (.662002687 * x ** .5 + .684122060 * x ** .25
                - .323583601 * x ** .125 - .0225411470 * x)
        expected.append(round(min(1, max(0, srgb)) * 255))
    np.testing.assert_array_equal(color[samples.view(np.uint16)], expected)
    np.testing.assert_array_equal(alpha[samples[[0, 1, 2, -3, -2, -1]].view(np.uint16)],
                                  [0, 0, 0, 255, 255, 0])


def test_hdr_resize_and_device_reset_keep_float_pixel_format():
    method = object.__new__(WindowsGraphicsCaptureHDRMethod)
    method.cputex = Mock()
    old_texture = method.cputex
    method.frame_pool = Mock()
    method.rtdevice = object()
    method.create_device = Mock()
    size = object()
    method.reset_framepool(size, reset_device=True)
    old_texture.Release.assert_called_once()
    method.create_device.assert_called_once()
    method.frame_pool.Recreate.assert_called_once_with(
        method.rtdevice, DirectXPixelFormat.R16G16B16A16Float, 2, size)
    assert method.cputex is None
    assert object.__new__(WindowsGraphicsCaptureMethod).pixel_format == DirectXPixelFormat.B8G8R8A8UIntNormalized


def test_config_selects_hdr_and_failed_hdr_uses_configured_fallback():
    hdr = Mock(spec=WindowsGraphicsCaptureHDRMethod)
    hdr.start_or_stop.return_value = False
    fallback = object()
    with patch.object(update, 'windows_graphics_available', return_value=True), \
            patch.object(update, 'get_capture', side_effect=[hdr, fallback]) as select:
        result = update.update_capture_method({'capture_method': ['WGC_HDR', 'BitBlt']}, None, None)
    assert result is fallback
    assert select.call_args_list[0].args[1] is WindowsGraphicsCaptureHDRMethod
    hdr.close.assert_called_once()


def test_switching_hdr_back_to_sdr_replaces_the_frame_pool():
    hdr = Mock(spec=WindowsGraphicsCaptureHDRMethod)
    sdr = Mock(spec=WindowsGraphicsCaptureMethod)
    sdr.start_or_stop.return_value = True
    with patch.object(update, 'windows_graphics_available', return_value=True), \
            patch.object(update, 'get_capture', return_value=sdr) as select, \
            patch.object(update, '_capture_can_produce_frame', return_value=True):
        assert update.get_win_graphics_capture(hdr, None, None) is sdr
    select.assert_called_once_with(None, WindowsGraphicsCaptureMethod, None, None)
    hdr.close.assert_called_once()
