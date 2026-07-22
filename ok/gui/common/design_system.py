"""Shared layout tokens for the desktop UI.

The UI follows a small, reusable hierarchy: page -> section/card -> row ->
control.  Keeping the measurements here prevents individual screens from
slowly developing different spacing and control widths.
"""

from PySide6.QtWidgets import QLayout, QWidget


class DesignToken:
    """The app's 8-point-grid-derived layout and sizing tokens."""

    PAGE_MARGIN = 24
    PAGE_SPACING = 12

    SECTION_SPACING = 12
    CARD_PADDING = 16

    ROW_HORIZONTAL_PADDING = 14
    ROW_VERTICAL_PADDING = 10
    ROW_SPACING = 16
    ROW_MIN_HEIGHT = 56

    CONTROL_WIDTH = 180
    CONTROL_MIN_WIDTH = 160
    CONTROL_MAX_WIDTH = 320


def configure_page_layout(layout: QLayout) -> None:
    """Apply the shared page rhythm to a top-level tab layout."""

    margin = DesignToken.PAGE_MARGIN
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(DesignToken.PAGE_SPACING)


def configure_card_layout(layout: QLayout) -> None:
    """Apply consistent padding inside a passive content card."""

    padding = DesignToken.CARD_PADDING
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(DesignToken.SECTION_SPACING)


def configure_row(widget: QWidget, layout: QLayout) -> None:
    """Turn a label/control pair into the standard settings row pattern."""

    widget.setObjectName("configRow")
    widget.setMinimumHeight(DesignToken.ROW_MIN_HEIGHT)
    layout.setContentsMargins(
        DesignToken.ROW_HORIZONTAL_PADDING,
        DesignToken.ROW_VERTICAL_PADDING,
        DesignToken.ROW_HORIZONTAL_PADDING,
        DesignToken.ROW_VERTICAL_PADDING,
    )
    layout.setSpacing(DesignToken.ROW_SPACING)


def control_width(content_width: int = 0) -> int:
    """Return an aligned control width while allowing genuinely long values."""

    return max(
        DesignToken.CONTROL_MIN_WIDTH,
        min(DesignToken.CONTROL_MAX_WIDTH, max(DesignToken.CONTROL_WIDTH, content_width)),
    )
