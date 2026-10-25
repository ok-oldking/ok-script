from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageFont

from ok.core.screenshot import Screenshot, screenshot_file_stem, unique_screenshot_stem
from ok.feature.Box import Box


def test_screenshot_file_stem_is_sortable_and_named():
    now = datetime(2026, 10, 25, 14, 3, 7, 123456)

    assert screenshot_file_stem('find one', now) == '2026-10-25_14-03-07-123_find_one'
    assert screenshot_file_stem(None, now) == '2026-10-25_14-03-07-123_screenshot'


def test_unique_screenshot_stem_appends_counter(tmp_path):
    stem = '2026-10-25_14-03-07-123_fail'
    assert unique_screenshot_stem(tmp_path, stem) == stem

    (tmp_path / f'{stem}_original.png').touch()
    assert unique_screenshot_stem(tmp_path, stem) == f'{stem}_2'

    (tmp_path / f'{stem}_2_original.png').touch()
    assert unique_screenshot_stem(tmp_path, stem) == f'{stem}_3'


def test_duplicate_screenshots_keep_original_and_boxed_paired(tmp_path):
    screenshot = Screenshot.__new__(Screenshot)
    screenshot.pil_font = ImageFont.load_default()
    ui_dict = {'button': [[Box(1, 1, 5, 5, name='button')], 0, (255, 0, 0, 255)]}
    stem = '2026-10-25_14-03-07-123_fail'

    with patch.object(Screenshot, 'to_pil_image', side_effect=lambda *a, **k: Image.new('RGB', (10, 10))):
        first = screenshot.generate_screen_shot(object(), ui_dict, str(tmp_path), stem, True, None)
        second = screenshot.generate_screen_shot(object(), ui_dict, str(tmp_path), stem, True, None)

    assert Path(first).name == f'{stem}_original.png'
    assert Path(second).name == f'{stem}_2_original.png'
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        f'{stem}_2_boxed.png',
        f'{stem}_2_original.png',
        f'{stem}_boxed.png',
        f'{stem}_original.png',
    ]
