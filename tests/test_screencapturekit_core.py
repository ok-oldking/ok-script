import numpy as np
import pytest

from ok.device.capture_methods.screencapturekit_core import (
    CaptureGeometry,
    LatestFrameSlot,
    PixelRect,
    PublishedFrame,
    bgra_to_owned_bgr,
    content_rect_to_pixels,
)
from ok.device.window_target import WindowCoordinateSpace, WindowGeometry


MAC_POINTS = WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS


def geometry(*, target_generation=1, capture_generation=1):
    return CaptureGeometry(
        target_generation=target_generation,
        capture_generation=capture_generation,
        outer_geometry=WindowGeometry(100, 200, 800, 600, MAC_POINTS),
        global_content_geometry=WindowGeometry(110, 230, 780, 550, MAC_POINTS),
        raw_frame_width=1600,
        raw_frame_height=1200,
        content_rect_pixels=PixelRect(20, 60, 1560, 1100),
        frame_width=1560,
        frame_height=1100,
        display_scale=2.0,
    )


def test_bgra_to_bgr_handles_padding_crop_and_owns_memory():
    width, height, stride = 3, 2, 16
    source = bytearray(stride * height)
    pixels = [
        (1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12),
        (13, 14, 15, 16), (17, 18, 19, 20), (21, 22, 23, 24),
    ]
    for index, pixel in enumerate(pixels):
        row, column = divmod(index, width)
        offset = row * stride + column * 4
        source[offset:offset + 4] = bytes(pixel)

    frame = bgra_to_owned_bgr(
        source,
        width=width,
        height=height,
        bytes_per_row=stride,
        crop=PixelRect(1, 0, 2, 2),
    )

    assert frame.dtype == np.uint8
    assert frame.shape == (2, 2, 3)
    assert frame.flags.c_contiguous
    assert frame.tolist() == [
        [[5, 6, 7], [9, 10, 11]],
        [[17, 18, 19], [21, 22, 23]],
    ]
    source[4:7] = b'\xff\xff\xff'
    assert frame[0, 0].tolist() == [5, 6, 7]


@pytest.mark.parametrize(
    ('scale', 'expected'),
    [
        (1.0, PixelRect(2, 3, 10, 5)),
        (2.0, PixelRect(4, 6, 20, 10)),
        (1.5, PixelRect(3, 4, 15, 8)),
    ],
)
def test_content_rect_points_to_pixels_supports_non_integer_scales(scale, expected):
    rect = WindowGeometry(2, 3, 10, 5)
    assert content_rect_to_pixels(rect, scale, 100, 100) == expected


def test_content_rect_is_clamped_to_surface_and_rejects_empty_crop():
    rect = WindowGeometry(-1, -2, 10, 10)
    assert content_rect_to_pixels(rect, 2, 12, 12) == PixelRect(0, 0, 12, 12)
    with pytest.raises(ValueError, match='empty or outside'):
        content_rect_to_pixels(WindowGeometry(20, 20, 1, 1), 1, 10, 10)


def test_geometry_maps_cropped_content_pixels_to_global_logical_points():
    current = geometry()
    assert current.frame_pixel_to_global_point(0, 0) == (110, 230)
    assert current.frame_pixel_to_global_point(780, 550) == (500, 505)
    assert current.frame_pixel_to_global_point(1560, 1100) == (890, 780)
    with pytest.raises(ValueError, match='outside'):
        current.frame_pixel_to_global_point(1561, 0)


def test_geometry_rejects_zero_or_non_macos_global_mapping():
    values = geometry().__dict__
    with pytest.raises(ValueError, match='dimensions must be positive'):
        CaptureGeometry(**{
            **values,
            'global_content_geometry': WindowGeometry(110, 230, 0, 550, MAC_POINTS),
        })
    with pytest.raises(ValueError, match='macOS logical points'):
        CaptureGeometry(**{
            **values,
            'outer_geometry': WindowGeometry(100, 200, 800, 600),
        })


def test_latest_frame_slot_is_bounded_overwrites_unread_and_rejects_stale():
    slot = LatestFrameSlot()
    first_array = np.zeros((1100, 1560, 3), dtype=np.uint8)
    second_array = np.ones((1100, 1560, 3), dtype=np.uint8)
    first = PublishedFrame(first_array, geometry(), 1, 1.0)
    second = PublishedFrame(second_array, geometry(), 2, 2.0)

    slot.publish(first)
    slot.publish(second)

    assert slot.storage_size == 1
    assert slot.published == 2
    assert slot.overwritten == 1
    assert slot.read(target_generation=1, capture_generation=1) is second
    assert slot.read(target_generation=2, capture_generation=1) is None
    assert slot.storage_size == 0


def test_latest_frame_slot_keeps_owned_frame_stable_after_replacement():
    slot = LatestFrameSlot()
    first_array = np.zeros((1100, 1560, 3), dtype=np.uint8)
    first = PublishedFrame(first_array, geometry(), 1, 1.0)
    slot.publish(first)
    held = slot.read(target_generation=1, capture_generation=1)

    slot.publish(PublishedFrame(
        np.ones((1100, 1560, 3), dtype=np.uint8), geometry(), 2, 2.0))

    assert held is not None
    assert held.frame[0, 0].tolist() == [0, 0, 0]
