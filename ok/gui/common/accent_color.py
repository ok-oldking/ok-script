import colorsys


# PySide6-Fluent-Widgets applies this saturation multiplier to every theme
# color in dark mode before using ThemeColorPrimary.
QFLUENT_DARK_SATURATION_FACTOR = 0.84


def qfluent_theme_source_color(red, green, blue, dark):
    """Return the qfluent theme source that renders as the requested fill.

    In light mode ThemeColorPrimary is the configured color itself. In dark
    mode qfluent forces the value channel to 1 and multiplies saturation by
    0.84, so reverse that transformation before calling setThemeColor().
    """
    if not dark:
        return red, green, blue

    hue, saturation, _ = colorsys.rgb_to_hsv(
        red / 255.0, green / 255.0, blue / 255.0
    )
    source_saturation = min(saturation / QFLUENT_DARK_SATURATION_FACTOR, 1.0)
    source_red, source_green, source_blue = colorsys.hsv_to_rgb(
        hue, source_saturation, 1.0
    )
    return tuple(round(channel * 255) for channel in (
        source_red, source_green, source_blue
    ))
