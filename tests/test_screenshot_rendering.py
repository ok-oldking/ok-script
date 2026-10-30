from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from ok.core.screenshot import Screenshot
from ok.feature.Box import Box


def test_screenshot_keeps_annotations_when_live_boxes_change_during_drawing(tmp_path):
    screenshot = Screenshot.__new__(Screenshot)
    screenshot.pil_font = ImageFont.load_default()
    screenshot.ui_dict = {
        'first': [[Box(1, 1, 5, 5, name='first')], 0, (255, 0, 0, 255)],
        'second': [[Box(12, 1, 5, 5, name='second')], 0, (0, 255, 0, 255)],
    }
    rectangle = ImageDraw.ImageDraw.rectangle

    def draw_rectangle(draw, *args, **kwargs):
        rectangle(draw, *args, **kwargs)
        # Task events can clear and replace the live boxes during rendering.
        screenshot.clear_box()
        screenshot.ui_dict['new'] = [[Box(25, 1, 5, 5)], 0, (0, 0, 255, 255)]

    with patch.object(Screenshot, 'to_pil_image', return_value=Image.new('RGB', (40, 40))), \
            patch.object(ImageDraw.ImageDraw, 'rectangle', autospec=True, side_effect=draw_rectangle):
        original = screenshot.generate_screen_shot(
            object(), screenshot.ui_dict, str(tmp_path), 'capture', True, None)

    assert original == str(tmp_path / 'capture_original.png')
    assert set(screenshot.ui_dict) == {'new'}
    with Image.open(tmp_path / 'capture_boxed.png') as boxed:
        assert boxed.getpixel((1, 1)) == (255, 0, 0)
        assert boxed.getpixel((12, 1)) == (0, 255, 0)
        assert boxed.getpixel((25, 1)) == (0, 0, 0)
