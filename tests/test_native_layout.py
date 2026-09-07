from types import SimpleNamespace as NS
from unittest.mock import Mock

import numpy as np
import pytest

from ok.feature.layout import anchored_point, anchored_box
from ok.feature.FeatureSet import adjust_coordinates
from ok.task.task import ExecutorOperation, FindFeature, OCR
from ok.feature.Box import Box
from ok.task.TaskExecutor import TaskExecutor


@pytest.mark.parametrize('width,height', [(1280, 800), (1352, 845), (1512, 945), (2560, 1600)])
def test_native_16_10_corners_and_center(width, height):
    for x, y in [(0, 0), (1, 0), (0, 1), (1, 1), (.5, .5)]:
        assert anchored_point(x, y, width, height, 16/9) == (round(x*width), round(y*height))
    assert anchored_box(0, 0, 1, 1, 0, 0, width, height, 16/9) == (0, 0, width, height)


def test_edge_center_and_size_are_uniformly_scaled():
    assert anchored_point(.1, .1, 1280, 800, 16/9) == (128, 72)
    assert anchored_point(.9, .9, 1280, 800, 16/9) == (1152, 728)
    assert anchored_point(.1, .1, 1280, 800, 16/9, vcenter=True) == (128, 112)
    assert anchored_box(.1, .1, 1, 1, .2, .2, 1280, 800, 16/9) == (128, 72, 256, 144)
    assert anchored_box(.1, .1, .9, .9, 0, 0, 1280, 800, 16/9) == (128, 72, 1024, 656)


@pytest.mark.parametrize('width,height', [(1920, 1080), (1280, 720), (1600, 900)])
def test_16_9_reference_is_identity(width, height):
    for x, y in [(0, 0), (.1, .2), (.5, .5), (.9, .8), (1, 1)]:
        assert anchored_point(x, y, width, height, 16/9) == (round(x*width), round(y*height))


def make_operation(mode='anchored', width=1280, height=800):
    op = object.__new__(ExecutorOperation)
    op._executor = NS(method=NS(width=width, height=height), device_manager=NS(
        supported_ratio=16/9, coordinate_mode=mode))
    op.click = Mock()
    return op


def test_task_center_and_full_screen_roi_use_native_canvas():
    op = make_operation()
    op.click_relative(.5, .5)
    assert op.click.call_args.args[:2] == (640, 400)
    box = op.box_of_screen(0, 0)
    assert (box.x, box.y, box.width, box.height) == (0, 0, 1280, 800)


def test_legacy_mapping_is_unchanged():
    op = make_operation('legacy')
    op.click_relative(.5, .5)
    assert op.click.call_args.args[:2] == (640, 360)
    box = op.box_of_screen(0, 0)
    assert box.height == 720


def test_template_mapping_preserves_uniform_scale():
    x, y, w, h, scale = adjust_coordinates(1728, 972, 96, 54, 1280, 800, 1920, 1080)
    assert (x, y, w, h) == (1152, 728, 64, 36)
    assert scale == pytest.approx(2/3)


@pytest.mark.parametrize('size,allowed,expected', [
    ((1280, 800), ['16:9', '16:10'], True),
    ((1352, 845), ['16:9', '16:10'], True),
    ((1512, 945), ['16:9', '16:10'], True),
    ((1920, 1080), ['16:9', '16:10'], True),
    ((1512, 982), ['16:9', '16:10'], False),
    ((1024, 640), ['16:9', '16:10'], False),
    ((1280, 800), None, False),
    ((1280, 800), [], False),
])
def test_allowed_ratios_keep_minimum_size_and_legacy_gate(size, allowed, expected):
    width, height = size
    executor = object.__new__(TaskExecutor)
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    executor.device_manager = NS(update_resolution_for_hwnd=Mock(), capture_method=NS(
        width=width, height=height, get_frame=Mock(return_value=frame)))
    passed, actual = executor.check_frame_and_resolution('16:9', (1280, 720), allowed_ratios=allowed)
    assert bool(passed) is expected
    assert actual == f'{width}x{height}'
    assert frame.shape == (height, width, 3)  # Gate never resamples the image.


@pytest.mark.parametrize('dimensions', [(0, 800, 16/9), (1280, -1, 16/9), (1280, 800, 0)])
def test_invalid_geometry_is_rejected(dimensions):
    with pytest.raises(ValueError):
        anchored_point(.5, .5, *dimensions)


@pytest.mark.parametrize('mode,expected_y', [('anchored', 85), ('legacy', 94)])
def test_direct_ocr_roi_and_result_coordinates(mode, expected_y):
    op = object.__new__(OCR)
    image = np.zeros((945, 1512, 3), dtype=np.uint8)
    result = Box(800, 500, 20, 20, name='result')
    recognize = Mock(return_value=([result], [result]))
    op._executor = NS(frame=image, paused=False, device_manager=NS(
        coordinate_mode=mode, supported_ratio=16/9))
    op.ocr_default_threshold = .2
    op.fix_match_regex = lambda value: value
    op.ocr_fun = lambda lib: recognize
    op.log_debug = False
    actual = op.ocr(x=.49, y=.1, to_x=.9, to_y=.9)
    roi = recognize.call_args.args[0]
    assert roi.y == expected_y
    assert actual == [result] and actual[0].x == 800 and actual[0].y == 500
    op.ocr(box=result)
    assert recognize.call_args.args[0] is result


def test_direct_feature_roi_is_anchored_but_explicit_box_is_not_remapped():
    op = object.__new__(FindFeature)
    find = Mock(return_value=[])
    op._executor = NS(frame=np.zeros((945, 1512, 3), dtype=np.uint8),
                      feature_set=NS(find_feature=find), device_manager=NS(
                          coordinate_mode='anchored', supported_ratio=16/9))
    op.find_feature('test', x=.49, y=.1, to_x=.9, to_y=.9)
    assert find.call_args.kwargs['box'].y == 85
    box = Box(100, 100, 200, 200)
    op.find_feature('test', box=box)
    assert find.call_args.kwargs['box'] is box
    op.find_feature('test')
    assert find.call_args.kwargs['box'] is None  # Preserve template's own anchored search.
