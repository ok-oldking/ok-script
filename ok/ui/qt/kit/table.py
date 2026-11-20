"""Table widget with the kit theme, rounded headers and overlay scrolling."""

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import (
    QHeaderView,
    QScrollBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionSlider,
    QStyleOptionViewItem,
    QTableWidget,
)

from ok.ui.qt.kit.theme import theme

FRAME_WIDTH = 1
FRAME_RADIUS = 10
INNER_RADIUS = FRAME_RADIUS - FRAME_WIDTH
SELECTION_ALPHA = 0.18  # Matches the stylesheet's accent_soft_strong selection.


def _rounded_path(rect: QRectF, top_left: bool, top_right: bool, bottom_left: bool, bottom_right: bool,
                  radius: float = INNER_RADIUS) -> QPainterPath:
    """Return ``rect`` with only the requested corners rounded."""
    path = QPainterPath()
    path.addRect(rect)
    diameter = radius * 2
    corners = (
        (top_left, QRectF(rect.left(), rect.top(), radius, radius),
         QRectF(rect.left(), rect.top(), diameter, diameter)),
        (top_right, QRectF(rect.right() - radius, rect.top(), radius, radius),
         QRectF(rect.right() - diameter, rect.top(), diameter, diameter)),
        (bottom_left, QRectF(rect.left(), rect.bottom() - radius, radius, radius),
         QRectF(rect.left(), rect.bottom() - diameter, diameter, diameter)),
        (bottom_right, QRectF(rect.right() - radius, rect.bottom() - radius, radius, radius),
         QRectF(rect.right() - diameter, rect.bottom() - diameter, diameter, diameter)),
    )
    for rounded, square, circle in corners:
        if rounded:
            outside = QPainterPath()
            outside.addRect(square)
            arc = QPainterPath()
            arc.addEllipse(circle)
            path = path.subtracted(outside.subtracted(arc))
    return path


class Table(QTableWidget):
    """A styled table that keeps the native QTableWidget model and interaction.

    Colors, frame and padding come from the kit stylesheet; this class only
    adds the rounded clipping, row hover and the overlay vertical scrollbar.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hovered_row = -1
        self._round_top = False
        self._round_bottom = False
        self._viewport_clip = None
        self._scrollbar_overlay = _TableScrollBar(self)
        self._scrollbar_overlay.hide()
        self.setMouseTracking(True)
        self.setShowGrid(False)
        self.setVerticalScrollMode(self.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll = self.verticalScrollBar()
        scroll.rangeChanged.connect(self._sync_scrollbar)
        scroll.valueChanged.connect(self._scrollbar_overlay.setValue)
        self._scrollbar_overlay.valueChanged.connect(scroll.setValue)
        self.setHorizontalHeader(_TableHeader(self))
        self.setItemDelegate(_TableItemDelegate(self))
        # The stylesheet would paint selections unclipped; the delegate draws them inside the frame.
        self.setStyleSheet("QTableWidget { selection-background-color: transparent; }")

    def viewportEvent(self, event):
        if event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove):
            self._set_hovered_row(self.rowAt(event.position().toPoint().y()))
        elif event.type() == QEvent.Type.Leave:
            self._set_hovered_row(-1)
        return super().viewportEvent(event)

    def updateGeometries(self):
        super().updateGeometries()
        self._sync_scrollbar()
        overlay = self._scrollbar_overlay
        bounds = self.viewport().geometry()
        width = overlay.sizeHint().width()
        overlay.setGeometry(bounds.right() + 1 - width, bounds.top(), width, bounds.height())
        overlay.raise_()
        self._update_viewport_clip()

    def _sync_scrollbar(self, *_):
        # Mirror the table's vertical controller in a scrollbar over its right edge.
        scroll = self.verticalScrollBar()
        overlay = self._scrollbar_overlay
        with QSignalBlocker(overlay):
            overlay.setPageStep(scroll.pageStep())
            overlay.setSingleStep(scroll.singleStep())
            overlay.setRange(scroll.minimum(), scroll.maximum())
            overlay.setValue(scroll.value())
        visible = scroll.maximum() > scroll.minimum()
        if visible == overlay.isHidden():
            overlay.setVisible(visible)
            # Cells under the scrollbar inset their content while it is shown.
            self.viewport().update()

    def _update_viewport_clip(self):
        # Round only the viewport corners that meet the frame's rounded corners.
        no_left = not self.verticalHeader().isVisibleTo(self)
        self._round_top = not self.horizontalHeader().isVisibleTo(self)
        self._round_bottom = not self.horizontalScrollBar().isVisibleTo(self)
        if not (self._round_top or self._round_bottom):
            self._viewport_clip = None
            return
        self._viewport_clip = _rounded_path(
            QRectF(self.viewport().rect()),
            self._round_top and no_left, self._round_top,
            self._round_bottom and no_left, self._round_bottom,
        )

    def _cell_clip(self, cell: QRect):
        """The rounded clip for a cell touching a rounded corner, else None."""
        if self._viewport_clip is None:
            return None
        height = self.viewport().height()
        if (self._round_top and cell.top() < INNER_RADIUS) or (
                self._round_bottom and cell.bottom() >= height - INNER_RADIUS):
            return self._viewport_clip
        return None

    def _overlay_inset(self, cell: QRect) -> int:
        """Pixels of ``cell`` covered by the overlay scrollbar."""
        overlay = self._scrollbar_overlay
        if overlay.isHidden():
            return 0
        return max(0, cell.right() + 1 - (self.viewport().width() - overlay.width()))

    def _is_last_column(self, column: int) -> bool:
        header = self.horizontalHeader()
        for visual in range(header.count() - 1, -1, -1):
            logical = header.logicalIndex(visual)
            if not header.isSectionHidden(logical):
                return logical == column
        return False

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        viewport = self.viewport()
        if self._viewport_clip is not None:
            # Qt blits scrolled pixels, carrying clipped corners into the view; repaint those bands.
            if dx:
                viewport.update()
            elif dy:
                band = INNER_RADIUS + abs(dy)
                width, height = viewport.width(), viewport.height()
                if self._round_top:
                    viewport.update(0, 0, width, band)
                if self._round_bottom:
                    viewport.update(0, height - band, width, band)
        if viewport.underMouse():
            self._set_hovered_row(self.rowAt(viewport.mapFromGlobal(QCursor.pos()).y()))

    def _set_hovered_row(self, row):
        if self._hovered_row != row:
            self._hovered_row = row
            self.viewport().update()


class _TableScrollBar(QScrollBar):
    """Use Qt's scroll controls with a compact thumb and a track on hover."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        # Keep the hit areas and slider geometry identical in both visual states.
        self.setStyleSheet("""
            QScrollBar:vertical { background: transparent; width: 14px; margin: 14px 0; }
            QScrollBar::handle:vertical { min-height: 24px; margin: 0; }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                subcontrol-origin: margin; width: 14px; height: 14px;
            }
            QScrollBar::sub-line:vertical { subcontrol-position: top; }
            QScrollBar::add-line:vertical { subcontrol-position: bottom; }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.sliderReleased.connect(self.update)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, _event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        control = QStyle.ComplexControl.CC_ScrollBar
        sub = QStyle.SubControl
        style = self.style()
        slider = QRectF(style.subControlRect(control, option, sub.SC_ScrollBarSlider, self))
        expanded = self.underMouse() or self.isSliderDown()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if expanded:
            painter.setBrush(theme.color("control" if theme.is_dark() else "control_hover"))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 1, 0, -1), 7, 7)
            for button, direction, limit in (
                (sub.SC_ScrollBarSubLine, -1, self.minimum()),
                (sub.SC_ScrollBarAddLine, 1, self.maximum()),
            ):
                center = QRectF(style.subControlRect(control, option, button, self)).center()
                x, y = center.x(), center.y()
                painter.setBrush(
                    theme.color("text_disabled" if self.value() == limit else "text_secondary")
                )
                painter.drawPolygon(
                    QPolygonF(
                        [
                            QPointF(x - 4, y - direction * 2.5),
                            QPointF(x + 4, y - direction * 2.5),
                            QPointF(x, y + direction * 2.5),
                        ]
                    )
                )
        width = 6 if expanded else 2
        center_x = slider.center().x() if expanded else slider.right() - 4
        slider = QRectF(center_x - width / 2, slider.top(), width, slider.height())
        painter.setBrush(theme.color("text_secondary" if expanded else "text_tertiary"))
        painter.drawRoundedRect(slider, slider.width() / 2, slider.width() / 2)


class _TableItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        table = self.parent()
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        cell = QRect(option.rect)
        viewport = table.viewport().rect()
        painter.save()
        clip = table._cell_clip(cell)
        if clip is not None:
            antialiasing = QPainter.RenderHint.Antialiasing
            was_antialiased = painter.testRenderHint(antialiasing)
            painter.setRenderHint(antialiasing)
            painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(antialiasing, was_antialiased)

        # Paint the background across the whole cell, then the content beside the scrollbar.
        state = QStyle.StateFlag
        features = QStyleOptionViewItem.ViewItemFeature
        if option.state & state.State_Selected:
            background = QColor(theme.accent())
            background.setAlphaF(SELECTION_ALPHA)
            background = QBrush(background)
        elif index.row() == table._hovered_row:
            background = QBrush(theme.color("control" if theme.is_dark() else "control_hover"))
        elif option.backgroundBrush.style() != Qt.BrushStyle.NoBrush:
            background = option.backgroundBrush
        elif option.features & features.Alternate:
            background = option.palette.alternateBase()
        else:
            background = None
        if background is not None:
            painter.fillRect(cell, background)
        option.state &= ~(state.State_Selected | state.State_HasFocus | state.State_MouseOver)
        option.features &= ~features.Alternate
        option.backgroundBrush = QBrush()
        option.rect = cell.adjusted(0, 0, -table._overlay_inset(cell), 0)
        option.widget.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget
        )

        # Inner dividers only: none right of the last column or along the frame.
        painter.setPen(theme.color("border"))
        if not table._is_last_column(index.column()) and cell.right() < viewport.right():
            painter.drawLine(cell.topRight(), cell.bottomRight())
        if cell.bottom() < viewport.bottom():
            painter.drawLine(cell.bottomLeft(), cell.bottomRight())
        painter.restore()


class _TableHeader(QHeaderView):
    """Header with a rounded top surface and no dividers between sections."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        # Sections keep Qt's painting (text, icons, sort indicator) over a surface drawn below.
        self.setStyleSheet(
            "QHeaderView { background: transparent; border: 0; border-radius: 0; }"
            "QHeaderView::section { background: transparent; border: 0; }"
        )
        self.viewport().setAutoFillBackground(False)

    def paintEvent(self, event):
        rect = self.viewport().rect()
        table = self.parentWidget()
        round_left = table is None or not table.verticalHeader().isVisibleTo(table)
        path = _rounded_path(QRectF(rect), round_left, True, False, False)
        # Paint the rounded surface in viewport coordinates, independently of section widths.
        with QPainter(self.viewport()) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillPath(path, theme.color("surface_alt"))
            # A 1px line on integer coordinates must not be antialiased, or it blurs over two rows.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(theme.color("border"))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        super().paintEvent(event)
