import colorsys
import unittest

from ok.gui.common.accent_color import (
    QFLUENT_DARK_SATURATION_FACTOR,
    qfluent_theme_source_color,
)


def _render_qfluent_dark_primary(rgb):
    hue, saturation, _ = colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))
    rendered = colorsys.hsv_to_rgb(
        hue,
        saturation * QFLUENT_DARK_SATURATION_FACTOR,
        1.0,
    )
    return tuple(round(channel * 255) for channel in rendered)


class TestAccentColor(unittest.TestCase):

    def test_light_theme_uses_system_fill_without_compensation(self):
        self.assertEqual(
            qfluent_theme_source_color(0, 103, 192, dark=False),
            (0, 103, 192),
        )

    def test_dark_theme_compensates_qfluent_color_transformation(self):
        system_accent_light_2 = (76, 194, 255)

        source = qfluent_theme_source_color(*system_accent_light_2, dark=True)
        rendered = _render_qfluent_dark_primary(source)

        self.assertTrue(all(
            abs(actual - expected) <= 1
            for actual, expected in zip(rendered, system_accent_light_2)
        ))


if __name__ == '__main__':
    unittest.main()
