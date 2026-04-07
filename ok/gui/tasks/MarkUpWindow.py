import json
import os
from typing import TypedDict

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QSize, QRectF
from PySide6.QtGui import (QPainter, QPen, QColor, QPixmap, QMouseEvent,
                            QKeyEvent, QBrush, QFont, QCursor, QTransform,
                            QWheelEvent, QImage)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QScrollArea, QSizePolicy, QDialog,
                               QFormLayout, QApplication)
from qfluentwidgets import (PushButton, PrimaryPushButton, FluentIcon,
                             LineEdit, MessageBox, BodyLabel, SpinBox,
                             MessageBoxBase, SubtitleLabel, ToolButton,
                             isDarkTheme, qconfig, SplitTitleBar)

from ok.gui.widget.BaseWindow import BaseWindow

from ok.gui.tasks.TemplateTab import (load_coco, save_coco, ensure_template_folder,
                                       TEMPLATE_FOLDER)
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# Edge detection margin in pixels (in widget/screen space)
EDGE_MARGIN = 8

# Resize handle identifiers
HANDLE_NONE = 0
HANDLE_TOP = 1
HANDLE_BOTTOM = 2
HANDLE_LEFT = 3
HANDLE_RIGHT = 4
HANDLE_TL = 5  # top-left corner
HANDLE_TR = 6  # top-right corner
HANDLE_BL = 7  # bottom-left corner
HANDLE_BR = 8  # bottom-right corner


def _detect_handle(pos, rect, margin=EDGE_MARGIN):
    """Detect which resize handle the position is near. rect is in widget coords."""
    x, y = pos.x(), pos.y()
    rx, ry, rw, rh = rect.x(), rect.y(), rect.width(), rect.height()
    r_right = rx + rw
    r_bottom = ry + rh

    near_left = abs(x - rx) <= margin and ry - margin <= y <= r_bottom + margin
    near_right = abs(x - r_right) <= margin and ry - margin <= y <= r_bottom + margin
    near_top = abs(y - ry) <= margin and rx - margin <= x <= r_right + margin
    near_bottom = abs(y - r_bottom) <= margin and rx - margin <= x <= r_right + margin

    # Corners first (both edges near)
    if near_top and near_left:
        return HANDLE_TL
    if near_top and near_right:
        return HANDLE_TR
    if near_bottom and near_left:
        return HANDLE_BL
    if near_bottom and near_right:
        return HANDLE_BR
    # Edges
    if near_top:
        return HANDLE_TOP
    if near_bottom:
        return HANDLE_BOTTOM
    if near_left:
        return HANDLE_LEFT
    if near_right:
        return HANDLE_RIGHT
    return HANDLE_NONE


def _cursor_for_handle(handle):
    """Return the appropriate cursor for a resize handle."""
    if handle in (HANDLE_TL, HANDLE_BR):
        return Qt.SizeFDiagCursor
    if handle in (HANDLE_TR, HANDLE_BL):
        return Qt.SizeBDiagCursor
    if handle in (HANDLE_TOP, HANDLE_BOTTOM):
        return Qt.SizeVerCursor
    if handle in (HANDLE_LEFT, HANDLE_RIGHT):
        return Qt.SizeHorCursor
    return Qt.ArrowCursor

class Annotation(TypedDict):
    id: int
    category: str
    x: float
    y: float
    w: float
    h: float


class BBoxDialog(MessageBoxBase):
    """Dialog for entering/editing bbox category and coordinates."""

    def __init__(self, parent, category="", x=0, y=0, w=0, h=0, existing_categories=None,
                 current_image_name="", editing_original_name=""):
        super().__init__(parent)
        self.existing_categories = existing_categories or {}
        self.current_image_name = current_image_name
        self.editing_original_name = editing_original_name

        self.titleLabel = SubtitleLabel(self.tr("Bounding Box"), self)
        self.viewLayout.addWidget(self.titleLabel)

        form = QFormLayout()

        # Category row with error label
        cat_layout = QHBoxLayout()
        self.category_input = LineEdit(self)
        self.category_input.setText(category)
        self.category_input.setPlaceholderText(self.tr("Category name"))
        self.category_input.textChanged.connect(self._validate_category)
        cat_layout.addWidget(self.category_input)

        self.cat_error_label = BodyLabel("")
        self.cat_error_label.setStyleSheet("color: red; font-size: 11px;")
        self.cat_error_label.setVisible(False)
        cat_layout.addWidget(self.cat_error_label)

        form.addRow(self.tr("Category:"), cat_layout)

        self.x_input = SpinBox(self)
        self.x_input.setRange(0, 99999)
        self.x_input.setValue(int(round(x)))
        form.addRow("X:", self.x_input)

        self.y_input = SpinBox(self)
        self.y_input.setRange(0, 99999)
        self.y_input.setValue(int(round(y)))
        form.addRow("Y:", self.y_input)

        self.w_input = SpinBox(self)
        self.w_input.setRange(0, 99999)
        self.w_input.setValue(int(round(w)))
        form.addRow(self.tr("Width:"), self.w_input)

        self.h_input = SpinBox(self)
        self.h_input.setRange(0, 99999)
        self.h_input.setValue(int(round(h)))
        form.addRow(self.tr("Height:"), self.h_input)

        self.viewLayout.addLayout(form)

        self.yesButton.setText(self.tr("OK"))
        self.cancelButton.setText(self.tr("Cancel"))
        self.widget.setMinimumWidth(380)

        self.category_input.setFocus()
        self._validate_category(category)

    def _validate_category(self, text):
        name = text.strip()
        if not name:
            self.cat_error_label.setText(self.tr("Name required"))
            self.cat_error_label.setVisible(True)
            self.yesButton.setEnabled(False)
            return
        # Check uniqueness: if the name exists in another image
        if name != self.editing_original_name and name in self.existing_categories:
            owner = self.existing_categories[name]
            self.cat_error_label.setText(self.tr("Already exists in '{}'").format(owner))
            self.cat_error_label.setVisible(True)
            self.yesButton.setEnabled(False)
            return
        self.cat_error_label.setVisible(False)
        self.yesButton.setEnabled(True)

    def get_values(self):
        return (self.category_input.text().strip(),
                self.x_input.value(),
                self.y_input.value(),
                self.w_input.value(),
                self.h_input.value())


class AnnotationCanvas(QWidget):
    """Canvas that displays a scaled image and handles bbox drawing/editing/resizing.

    All annotations store coordinates in *original image* space.
    Mouse events are converted between widget space and image space using self.scale.
    """

    annotations_changed = Signal()

    MODE_NONE = 0
    MODE_DRAW = 1
    MODE_DELETE = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.markup_window = parent
        self.pixmap = None      # original full-size pixmap
        self._image = None      # QImage for pixel color sampling
        self.scale = 1.0        # widget_size / image_size
        self._fit_scale = 1.0   # scale that fits the image to the widget
        self.offset_x = 0       # x offset to center the image
        self.offset_y = 0       # y offset to center the image
        self.annotations: list[Annotation] = []   # list of dicts: {id, category, x, y, w, h} in IMAGE coords
        self.mode = self.MODE_NONE
        self.selected_ann_index = -1
        self.hovered_ann_index = -1
        self.hovered_handle = HANDLE_NONE

        # Drawing state (image coords)
        self.draw_start = None
        self.draw_preview = None  # widget coords for preview

        # Dragging bbox state
        self.dragging = False
        self.drag_start_pos = None       # widget coords
        self.drag_original_rect = None   # image coords QRect

        # Resizing state
        self.resizing = False
        self.resize_handle = HANDLE_NONE
        self.resize_start_pos = None     # widget coords
        self.resize_original_rect = None  # image coords QRect

        # Pan (drag-move the image) state
        self.panning = False
        self.pan_start_pos = None        # widget coords
        self.pan_start_offset = None     # (offset_x, offset_y) at drag start

        # Current mouse color info
        self._current_color_text = ""

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_image(self, image_path):
        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            logger.error(f"Failed to load image: {image_path}")
            self._image = None
            return
        self._image = self.pixmap.toImage()
        self.annotations = []
        self.selected_ann_index = -1
        self.hovered_ann_index = -1
        self.hovered_handle = HANDLE_NONE
        self.draw_start = None
        self.draw_preview = None
        self.dragging = False
        self.resizing = False
        self.panning = False
        self._current_color_text = ""
        self._recalc_fit_scale()
        self.scale = self._fit_scale
        self._recalc_offset()
        self.update()

    def _recalc_fit_scale(self):
        """Calculate the scale that fits the image to the widget (minimum allowed zoom)."""
        if not self.pixmap or self.pixmap.isNull():
            self._fit_scale = 1.0
            return
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        ww = self.width()
        wh = self.height()
        if iw <= 0 or ih <= 0 or ww <= 0 or wh <= 0:
            self._fit_scale = 1.0
            return
        self._fit_scale = min(ww / iw, wh / ih)

    def _recalc_offset(self):
        """Recalculate offset to keep the image centered / clamped within view."""
        if not self.pixmap or self.pixmap.isNull():
            self.offset_x = 0
            self.offset_y = 0
            return
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        ww = self.width()
        wh = self.height()
        scaled_w = iw * self.scale
        scaled_h = ih * self.scale

        # If the scaled image fits within the widget, center it
        if scaled_w <= ww:
            self.offset_x = (ww - scaled_w) / 2.0
        else:
            # Clamp so we don't scroll past image edges
            self.offset_x = min(0, max(ww - scaled_w, self.offset_x))

        if scaled_h <= wh:
            self.offset_y = (wh - scaled_h) / 2.0
        else:
            self.offset_y = min(0, max(wh - scaled_h, self.offset_y))

    def _is_zoomed_beyond_window(self):
        """Return True if the scaled image is larger than the widget in any dimension."""
        if not self.pixmap or self.pixmap.isNull():
            return False
        return (self.pixmap.width() * self.scale > self.width() or
                self.pixmap.height() * self.scale > self.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_fit_scale()
        # Clamp zoom so it never goes below fit scale
        if self.scale < self._fit_scale:
            self.scale = self._fit_scale
        self._recalc_offset()
        self.update()

    def set_annotations(self, annotations: Annotation):
        """Set annotations list. Each: {id, category, x, y, w, h} in image coords."""
        self.annotations = annotations
        self.selected_ann_index = -1
        self.hovered_ann_index = -1
        self.update()

    # ---------- coordinate conversion ----------
    def _img_to_widget(self, ix, iy):
        """Convert image coords to widget coords."""
        return ix * self.scale + self.offset_x, iy * self.scale + self.offset_y

    def _widget_to_img(self, wx, wy):
        """Convert widget coords to image coords."""
        if self.scale == 0:
            return wx, wy
        return (wx - self.offset_x) / self.scale, (wy - self.offset_y) / self.scale

    def _ann_widget_rect(self, ann):
        """Get QRect in widget coordinates for an annotation (image-space coords)."""
        wx, wy = self._img_to_widget(ann['x'], ann['y'])
        ww = ann['w'] * self.scale
        wh = ann['h'] * self.scale
        return QRect(int(wx), int(wy), int(ww), int(wh))

    def _find_ann_at(self, pos):
        """Find annotation index at widget position. Returns -1 if none."""
        for i in range(len(self.annotations) - 1, -1, -1):
            r = self._ann_widget_rect(self.annotations[i])
            if r.contains(pos):
                return i
        return -1

    def _find_handle_at(self, pos):
        """Find which annotation edge/corner the position is near (widget coords)."""
        for i in range(len(self.annotations) - 1, -1, -1):
            r = self._ann_widget_rect(self.annotations[i])
            handle = _detect_handle(pos, r)
            if handle != HANDLE_NONE:
                return i, handle
        return -1, HANDLE_NONE

    # ---------- painting ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Fill background
        dark = isDarkTheme()
        bg = QColor(30, 30, 30) if dark else QColor(245, 245, 245)
        painter.fillRect(self.rect(), bg)

        if self.pixmap and not self.pixmap.isNull():
            # Draw scaled image centered
            dest = QRectF(self.offset_x, self.offset_y,
                          self.pixmap.width() * self.scale,
                          self.pixmap.height() * self.scale)
            painter.drawPixmap(dest, self.pixmap, QRectF(self.pixmap.rect()))

        # Draw annotations
        for i, ann in enumerate(self.annotations):
            is_selected = (i == self.selected_ann_index)
            is_hovered = (i == self.hovered_ann_index)

            if is_selected:
                pen_color = QColor(0, 120, 212)
                fill = QColor(0, 120, 212, 40)
            elif is_hovered:
                pen_color = QColor(255, 165, 0)
                fill = QColor(255, 165, 0, 30)
            else:
                pen_color = QColor(255, 60, 60)
                fill = QColor(255, 60, 60, 20)

            rect = self._ann_widget_rect(ann)
            painter.setPen(QPen(pen_color, 2, Qt.SolidLine))
            painter.setBrush(QBrush(fill))
            painter.drawRect(rect)

            # Highlight specific edges/corners when hovered
            if is_hovered and self.hovered_handle != HANDLE_NONE:
                highlight_pen = QPen(QColor(0, 200, 0), 3, Qt.SolidLine)
                painter.setPen(highlight_pen)
                rx, ry = rect.x(), rect.y()
                rr = rect.x() + rect.width()
                rb = rect.y() + rect.height()

                h = self.hovered_handle
                if h == HANDLE_TOP or h in (HANDLE_TL, HANDLE_TR):
                    painter.drawLine(rx, ry, rr, ry)
                if h == HANDLE_BOTTOM or h in (HANDLE_BL, HANDLE_BR):
                    painter.drawLine(rx, rb, rr, rb)
                if h == HANDLE_LEFT or h in (HANDLE_TL, HANDLE_BL):
                    painter.drawLine(rx, ry, rx, rb)
                if h == HANDLE_RIGHT or h in (HANDLE_TR, HANDLE_BR):
                    painter.drawLine(rr, ry, rr, rb)

                # Draw corner dots
                if h in (HANDLE_TL, HANDLE_TR, HANDLE_BL, HANDLE_BR):
                    corner_size = 5
                    painter.setBrush(QBrush(QColor(0, 200, 0)))
                    painter.setPen(Qt.NoPen)
                    if h == HANDLE_TL:
                        painter.drawEllipse(QPoint(rx, ry), corner_size, corner_size)
                    elif h == HANDLE_TR:
                        painter.drawEllipse(QPoint(rr, ry), corner_size, corner_size)
                    elif h == HANDLE_BL:
                        painter.drawEllipse(QPoint(rx, rb), corner_size, corner_size)
                    elif h == HANDLE_BR:
                        painter.drawEllipse(QPoint(rr, rb), corner_size, corner_size)

            # Draw label
            painter.setPen(QPen(pen_color))
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            label = ann.get('category', '')
            painter.drawText(rect.x() + 2, rect.y() - 4, label)

        # Draw preview while drawing
        if self.mode == self.MODE_DRAW and self.draw_start is not None and self.draw_preview is not None:
            pen = QPen(QColor(0, 200, 0), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(0, 200, 0, 30)))
            # draw_start is widget coords, draw_preview is widget coords
            x1, y1 = int(self.draw_start.x()), int(self.draw_start.y())
            x2, y2 = int(self.draw_preview.x()), int(self.draw_preview.y())
            rect = QRect(QPoint(min(x1, x2), min(y1, y2)),
                         QPoint(max(x1, x2), max(y1, y2)))
            painter.drawRect(rect)

        painter.end()

    # ---------- mouse events ----------
    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()

        if event.button() == Qt.RightButton:
            # Copy current color text to clipboard
            if self._current_color_text:
                QApplication.clipboard().setText(self._current_color_text)
            return

        if event.button() == Qt.LeftButton:
            if self.mode == self.MODE_DRAW:
                event.accept()
                if self.draw_start is None:
                    self.draw_start = pos  # widget coords
                else:
                    self._finish_drawing(pos)
            elif self.mode == self.MODE_DELETE:
                event.accept()
                idx = self._find_ann_at(pos)
                if idx >= 0:
                    self.selected_ann_index = idx
                    self.delete_selected()
            else:
                # Check for resize handle first
                idx, handle = self._find_handle_at(pos)
                if handle != HANDLE_NONE and idx >= 0:
                    self.selected_ann_index = idx
                    self.resizing = True
                    self.resize_handle = handle
                    self.resize_start_pos = pos
                    ann = self.annotations[idx]
                    self.resize_original_rect = QRect(int(ann['x']), int(ann['y']),
                                                      int(ann['w']), int(ann['h']))
                else:
                    # Selection / drag start
                    idx = self._find_ann_at(pos)
                    self.selected_ann_index = idx
                    if idx >= 0:
                        self.dragging = True
                        self.drag_start_pos = pos
                        ann = self.annotations[idx]
                        self.drag_original_rect = QRect(int(ann['x']), int(ann['y']),
                                                        int(ann['w']), int(ann['h']))
                    elif self._is_zoomed_beyond_window():
                        # Start panning
                        self.panning = True
                        self.pan_start_pos = pos
                        self.pan_start_offset = (self.offset_x, self.offset_y)
                        self.setCursor(Qt.ClosedHandCursor)
                self.update()

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        idx = self._find_ann_at(pos)
        if idx >= 0:
            self.selected_ann_index = idx
            # Restore original position if drag was started by the first click
            if self.dragging and self.drag_original_rect is not None and idx == self.selected_ann_index:
                ann = self.annotations[idx]
                ann['x'] = self.drag_original_rect.x()
                ann['y'] = self.drag_original_rect.y()
            self.dragging = False
            self.drag_start_pos = None
            self.drag_original_rect = None
            self.resizing = False
            self.resize_start_pos = None
            self.resize_original_rect = None
            self.resize_handle = HANDLE_NONE
            self.update()
            self._edit_annotation(idx)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()

        # Update color info at mouse position
        self._update_color_at(pos)

        if self.mode == self.MODE_DRAW:
            event.accept()
            if self.draw_start is not None:
                self.draw_preview = pos
                self.update()
        elif self.resizing and self.selected_ann_index >= 0 and self.resize_start_pos:
            self._do_resize(pos)
            self.update()
        elif self.dragging and self.selected_ann_index >= 0 and self.drag_start_pos:
            # Convert widget-space delta to image-space delta
            dx_widget = pos.x() - self.drag_start_pos.x()
            dy_widget = pos.y() - self.drag_start_pos.y()
            dx_img = dx_widget / self.scale if self.scale else 0
            dy_img = dy_widget / self.scale if self.scale else 0

            ann = self.annotations[self.selected_ann_index]
            new_x = self.drag_original_rect.x() + dx_img
            new_y = self.drag_original_rect.y() + dy_img

            # Clamp to image bounds
            if self.pixmap:
                new_x = max(0, min(new_x, self.pixmap.width() - ann['w']))
                new_y = max(0, min(new_y, self.pixmap.height() - ann['h']))

            ann['x'] = int(round(new_x))
            ann['y'] = int(round(new_y))
            self.update()
        elif self.panning and self.pan_start_pos:
            dx = pos.x() - self.pan_start_pos.x()
            dy = pos.y() - self.pan_start_pos.y()
            self.offset_x = self.pan_start_offset[0] + dx
            self.offset_y = self.pan_start_offset[1] + dy
            self._recalc_offset()  # clamp
            self.update()
        else:
            # Hover detection
            if self.mode == self.MODE_NONE:
                idx, handle = self._find_handle_at(pos)
                if handle != HANDLE_NONE:
                    self.hovered_ann_index = idx
                    self.hovered_handle = handle
                    self.setCursor(_cursor_for_handle(handle))
                else:
                    hover_idx = self._find_ann_at(pos)
                    if hover_idx >= 0:
                        self.hovered_ann_index = hover_idx
                        self.hovered_handle = HANDLE_NONE
                        self.setCursor(Qt.SizeAllCursor)
                    else:
                        if self.hovered_ann_index != -1:
                            self.hovered_ann_index = -1
                            self.hovered_handle = HANDLE_NONE
                        # Show hand cursor if zoomed beyond window
                        if self._is_zoomed_beyond_window():
                            self.setCursor(Qt.OpenHandCursor)
                        else:
                            self.setCursor(Qt.ArrowCursor)
                self.update()
            elif self.mode == self.MODE_DRAW:
                self.setCursor(Qt.CrossCursor)
                if self.hovered_ann_index != -1:
                    self.hovered_ann_index = -1
                    self.hovered_handle = HANDLE_NONE
                    self.update()
            elif self.mode == self.MODE_DELETE:
                idx = self._find_ann_at(pos)
                if idx >= 0:
                    self.setCursor(Qt.PointingHandCursor)
                    if self.hovered_ann_index != idx:
                        self.hovered_ann_index = idx
                        self.hovered_handle = HANDLE_NONE
                        self.update()
                else:
                    self.setCursor(Qt.ArrowCursor)
                    if self.hovered_ann_index != -1:
                        self.hovered_ann_index = -1
                        self.hovered_handle = HANDLE_NONE
                        self.update()

        super().mouseMoveEvent(event)

    def delete_selected(self):
        idx = self.selected_ann_index
        if idx >= 0:
            ann = self.annotations[idx]
            cat = ann.get('category', '')
            w = MessageBox(self.tr('Confirm Delete'),
                           self.tr("Are you sure you want to delete '{}'?").format(cat),
                           self.window())
            if w.exec():
                self.annotations.pop(idx)
                self.selected_ann_index = -1
                self.hovered_ann_index = -1
                self.annotations_changed.emit()
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.dragging:
            self.dragging = False
            self.drag_start_pos = None
            self.drag_original_rect = None
            self.annotations_changed.emit()
        if self.resizing:
            self.resizing = False
            self.resize_start_pos = None
            self.resize_original_rect = None
            self.resize_handle = HANDLE_NONE
            self.annotations_changed.emit()
        if self.panning:
            self.panning = False
            self.pan_start_pos = None
            self.pan_start_offset = None
            # Restore open-hand cursor if still zoomed
            if self._is_zoomed_beyond_window():
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _do_resize(self, pos):
        """Apply resize based on handle being dragged. Uses image coords."""
        ann = self.annotations[self.selected_ann_index]
        orig = self.resize_original_rect
        # Convert widget delta to image delta
        dx_widget = pos.x() - self.resize_start_pos.x()
        dy_widget = pos.y() - self.resize_start_pos.y()
        dx = dx_widget / self.scale if self.scale else 0
        dy = dy_widget / self.scale if self.scale else 0

        ox, oy, ow, oh = orig.x(), orig.y(), orig.width(), orig.height()
        nx, ny, nw, nh = float(ox), float(oy), float(ow), float(oh)

        h = self.resize_handle
        if h in (HANDLE_LEFT, HANDLE_TL, HANDLE_BL):
            nx = ox + dx
            nw = ow - dx
        if h in (HANDLE_RIGHT, HANDLE_TR, HANDLE_BR):
            nw = ow + dx
        if h in (HANDLE_TOP, HANDLE_TL, HANDLE_TR):
            ny = oy + dy
            nh = oh - dy
        if h in (HANDLE_BOTTOM, HANDLE_BL, HANDLE_BR):
            nh = oh + dy

        # Minimum size
        min_size = 5
        if nw < min_size:
            if h in (HANDLE_LEFT, HANDLE_TL, HANDLE_BL):
                nx = ox + ow - min_size
            nw = min_size
        if nh < min_size:
            if h in (HANDLE_TOP, HANDLE_TL, HANDLE_TR):
                ny = oy + oh - min_size
            nh = min_size

        # Clamp to image bounds
        if self.pixmap:
            nx = max(0, nx)
            ny = max(0, ny)
            if nx + nw > self.pixmap.width():
                nw = self.pixmap.width() - nx
            if ny + nh > self.pixmap.height():
                nh = self.pixmap.height() - ny

        ann['x'] = int(round(nx))
        ann['y'] = int(round(ny))
        ann['w'] = int(round(nw))
        ann['h'] = int(round(nh))

    def _finish_drawing(self, end_pos):
        """end_pos is in widget coords. Convert to image coords for the annotation."""
        start = self.draw_start  # widget coords

        # Convert both points to image coords
        ix1, iy1 = self._widget_to_img(start.x(), start.y())
        ix2, iy2 = self._widget_to_img(end_pos.x(), end_pos.y())

        x = int(min(ix1, ix2))
        y = int(min(iy1, iy2))
        w = int(abs(ix2 - ix1))
        h = int(abs(iy2 - iy1))

        self.draw_start = None
        self.draw_preview = None

        if w < 3 or h < 3:
            self.update()
            return

        # Build category->image map for uniqueness validation
        existing_cats = self._build_existing_categories_map()
        current_image = ""
        if self.markup_window and self.markup_window.image_list:
            current_image = os.path.basename(self.markup_window.image_list[self.markup_window.current_index])

        # Show dialog for category
        dialog = BBoxDialog(self.window(), "", x, y, w, h,
                            existing_categories=existing_cats,
                            current_image_name=current_image,
                            editing_original_name="")
        if dialog.exec():
            cat, bx, by, bw, bh = dialog.get_values()
            if cat:
                existing_ids = {a.get('id', 0) for a in self.annotations}
                new_id = 1
                while new_id in existing_ids:
                    new_id += 1
                self.annotations.append({
                    'id': new_id,
                    'category': cat,
                    'x': bx,
                    'y': by,
                    'w': bw,
                    'h': bh
                })
                self.annotations_changed.emit()

        # End draw mode after finishing a box
        if self.markup_window:
            self.markup_window.end_draw_mode()

        self.update()

    def _update_color_at(self, pos):
        """Sample the original image pixel color at the widget position and update the label."""
        if not self._image or self._image.isNull():
            self._current_color_text = ""
            if self.markup_window:
                self.markup_window.update_color_label("")
            return
        ix, iy = self._widget_to_img(pos.x(), pos.y())
        ix, iy = int(ix), int(iy)
        if 0 <= ix < self._image.width() and 0 <= iy < self._image.height():
            color = self._image.pixelColor(ix, iy)
            text = f"R:{color.red()} G:{color.green()} B:{color.blue()}"
            self._current_color_text = f"({color.red()},{color.green()},{color.blue()})"
            if self.markup_window:
                self.markup_window.update_color_label(text, color)
        else:
            self._current_color_text = ""
            if self.markup_window:
                self.markup_window.update_color_label("")

    def wheelEvent(self, event: QWheelEvent):
        """Zoom in/out with mouse wheel, anchored at mouse position."""
        if not self.pixmap or self.pixmap.isNull():
            return

        pos = event.position()
        # Image coords under the mouse before zoom
        ix, iy = self._widget_to_img(pos.x(), pos.y())

        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1 / 1.1
        new_scale = self.scale * factor

        # Clamp: don't zoom out smaller than fit-to-window
        if new_scale < self._fit_scale:
            new_scale = self._fit_scale
        # Reasonable upper limit
        if new_scale > 50.0:
            new_scale = 50.0

        self.scale = new_scale

        # Adjust offset so the point under the mouse stays fixed
        self.offset_x = pos.x() - ix * self.scale
        self.offset_y = pos.y() - iy * self.scale
        self._recalc_offset()  # clamp within bounds
        self.update()
        event.accept()

    def _build_existing_categories_map(self):
        """Build a dict of category_name -> image_filename for all annotations across all images."""
        coco_data = load_coco()
        cat_map = {}
        cat_id_to_name = {cat['id']: cat['name'] for cat in coco_data.get('categories', [])}
        img_id_to_name = {img['id']: img['file_name'] for img in coco_data.get('images', [])}

        current_image = ""
        if self.markup_window and self.markup_window.image_list:
            current_image = os.path.basename(self.markup_window.image_list[self.markup_window.current_index])

        for ann in coco_data.get('annotations', []):
            img_name = img_id_to_name.get(ann['image_id'], '')
            cat_name = cat_id_to_name.get(ann['category_id'], '')
            if cat_name and img_name != current_image:
                cat_map[cat_name] = img_name

        # From current canvas annotations (for the current image)
        for can_ann in self.annotations:
            cat_name = can_ann.get('category', '')
            if cat_name:
                cat_map[cat_name] = current_image

        return cat_map

    def _edit_annotation(self, idx):
        ann = self.annotations[idx]
        existing_cats = self._build_existing_categories_map()
        current_image = ""
        if self.markup_window and self.markup_window.image_list:
            current_image = os.path.basename(self.markup_window.image_list[self.markup_window.current_index])

        original_name = ann.get('category', '')

        dialog = BBoxDialog(self.window(),
                            original_name,
                            ann['x'], ann['y'], ann['w'], ann['h'],
                            existing_categories=existing_cats,
                            current_image_name=current_image,
                            editing_original_name=original_name)
        if dialog.exec():
            cat, x, y, w, h = dialog.get_values()
            if cat:
                ann['category'] = cat
                ann['x'] = x
                ann['y'] = y
                ann['w'] = w
                ann['h'] = h
                self.annotations_changed.emit()
                self.update()

    def modify_selected(self):
        if self.selected_ann_index >= 0:
            self._edit_annotation(self.selected_ann_index)


class MarkUpWindow(BaseWindow):
    closed = Signal()

    def __init__(self, image_path, image_list, parent=None):
        super().__init__(parent)
        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()
        self.setWindowTitle(self.tr("Markup Editor"))
        self.titleBar.setIcon(self.windowIcon())
        self.setMinimumSize(1600, 900)

        self.image_list = image_list
        self.current_index = 0
        if image_path in image_list:
            self.current_index = image_list.index(image_path)

        self.coco_data = load_coco()

        # Layout directly on self (BaseWindow is FramelessWindow, not QMainWindow)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 40, 8, 8)  # top=40 for title bar
        main_layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.draw_btn = PrimaryPushButton(FluentIcon.EDIT, self.tr("Draw (R)"))
        self.draw_btn.setCheckable(True)
        self.draw_btn.clicked.connect(self.toggle_draw_mode)
        toolbar.addWidget(self.draw_btn)

        self.delete_box_btn = PushButton(FluentIcon.DELETE, self.tr("Delete (D)"))
        self.delete_box_btn.setCheckable(True)
        self.delete_box_btn.clicked.connect(self.toggle_delete_mode)
        toolbar.addWidget(self.delete_box_btn)

        self.modify_btn = PushButton(FluentIcon.SETTING, self.tr("Modify (Double Click)"))
        self.modify_btn.clicked.connect(self.modify_selected)
        toolbar.addWidget(self.modify_btn)

        # Color swatch + RGB text label (right after modify button)
        color_layout = QHBoxLayout()
        color_layout.setSpacing(4)
        self.color_swatch = QLabel()
        self.color_swatch.setFixedSize(16, 16)
        self.color_swatch.setStyleSheet(
            "background-color: transparent; border: 1px solid gray; border-radius: 2px;"
        )
        color_layout.addWidget(self.color_swatch)
        self.color_label = BodyLabel("")
        color_layout.addWidget(self.color_label)
        toolbar.addLayout(color_layout)

        toolbar.addStretch(1)

        self.image_name_label = BodyLabel("")
        toolbar.addWidget(self.image_name_label)

        toolbar.addStretch(1)

        main_layout.addLayout(toolbar)

        # Content area with left/right arrows and image canvas
        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)

        # Left arrow - icon-only ToolButton, vertically centered
        left_wrapper = QVBoxLayout()
        left_wrapper.addStretch(1)
        self.left_btn = ToolButton(FluentIcon.LEFT_ARROW, self)
        self.left_btn.setFixedSize(36, 36)
        self.left_btn.clicked.connect(self.prev_image)
        left_wrapper.addWidget(self.left_btn)
        left_wrapper.addStretch(1)
        content_layout.addLayout(left_wrapper)

        # Canvas directly in layout (no scroll area — it scales to fit)
        self.canvas = AnnotationCanvas(self)
        self.canvas.annotations_changed.connect(self.on_annotations_changed)
        content_layout.addWidget(self.canvas, 1)

        # Right arrow - icon-only ToolButton, vertically centered
        right_wrapper = QVBoxLayout()
        right_wrapper.addStretch(1)
        self.right_btn = ToolButton(FluentIcon.RIGHT_ARROW, self)
        self.right_btn.setFixedSize(36, 36)
        self.right_btn.clicked.connect(self.next_image)
        right_wrapper.addWidget(self.right_btn)
        right_wrapper.addStretch(1)
        content_layout.addLayout(right_wrapper)

        main_layout.addLayout(content_layout, 1)

        self.load_current_image()
        self._update_nav_buttons()

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2
            )

    def load_current_image(self):
        if not self.image_list:
            return

        image_path = self.image_list[self.current_index]
        self.canvas.set_image(image_path)

        filename = os.path.basename(image_path)
        self.image_name_label.setText(filename)

        # Load annotations for this image
        self.coco_data = load_coco()
        image_id = self._get_image_id(filename)
        annotations = []
        if image_id is not None:
            for ann in self.coco_data.get('annotations', []):
                if ann['image_id'] == image_id:
                    bbox = ann['bbox']  # [x, y, w, h]
                    cat_name = self._get_category_name(ann['category_id'])
                    annotations.append({
                        'id': ann['id'],
                        'category': cat_name,
                        'x': int(round(bbox[0])),
                        'y': int(round(bbox[1])),
                        'w': int(round(bbox[2])),
                        'h': int(round(bbox[3]))
                    })
        self.canvas.set_annotations(annotations)
        self._update_nav_buttons()

    def _get_image_id(self, filename):
        for img in self.coco_data.get('images', []):
            if img['file_name'] == filename:
                return img['id']
        return None

    def _get_category_name(self, cat_id):
        for cat in self.coco_data.get('categories', []):
            if cat['id'] == cat_id:
                return cat['name']
        return str(cat_id)

    def _get_or_create_category_id(self, name):
        for cat in self.coco_data.get('categories', []):
            if cat['name'] == name:
                return cat['id']
        # Create new category
        existing_ids = {cat['id'] for cat in self.coco_data.get('categories', [])}
        new_id = 1
        while new_id in existing_ids:
            new_id += 1
        self.coco_data['categories'].append({
            'id': new_id,
            'name': name,
            'supercategory': ''
        })
        return new_id

    def update_color_label(self, text, color=None):
        """Update the RGB color label and swatch in the toolbar."""
        if color and text:
            display = f"{text} ({self.tr('Right click to copy color')})"
            self.color_label.setText(display)
            self.color_swatch.setStyleSheet(
                f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                f"border: 1px solid gray; border-radius: 2px;"
            )
        else:
            self.color_label.setText("")
            self.color_swatch.setStyleSheet(
                "background-color: transparent; border: 1px solid gray; border-radius: 2px;"
            )

    def on_annotations_changed(self):
        """Auto-save annotations whenever they change."""
        self.save_annotations()

    def save_annotations(self):
        if not self.image_list:
            return
        
        logger.info('save annotations')

        image_path = self.image_list[self.current_index]
        filename = os.path.basename(image_path)
        self.coco_data = load_coco()

        image_id = self._get_image_id(filename)
        if image_id is None:
            # Add image entry
            existing_ids = {img['id'] for img in self.coco_data.get('images', [])}
            image_id = 1
            while image_id in existing_ids:
                image_id += 1
            import cv2
            img = cv2.imread(image_path)
            h, w = (img.shape[:2]) if img is not None else (0, 0)
            self.coco_data['images'].append({
                'id': image_id,
                'file_name': filename,
                'width': w,
                'height': h
            })

        # Remove old annotations for this image
        self.coco_data['annotations'] = [
            ann for ann in self.coco_data.get('annotations', [])
            if ann['image_id'] != image_id
        ]

        # Find max annotation id
        existing_ann_ids = {ann['id'] for ann in self.coco_data.get('annotations', [])}
        next_ann_id = 1

        # Add current canvas annotations
        for can_ann in self.canvas.annotations:
            while next_ann_id in existing_ann_ids:
                next_ann_id += 1
            cat_id = self._get_or_create_category_id(can_ann['category'])
            self.coco_data['annotations'].append({
                'id': next_ann_id,
                'image_id': image_id,
                'category_id': cat_id,
                'bbox': [can_ann['x'], can_ann['y'], can_ann['w'], can_ann['h']],
                'area': can_ann['w'] * can_ann['h'],
                'iscrowd': 0
            })
            existing_ann_ids.add(next_ann_id)

        # Clean up orphaned categories
        used_cat_ids = set(ann['category_id'] for ann in self.coco_data.get('annotations', []))
        self.coco_data['categories'] = [
            cat for cat in self.coco_data.get('categories', [])
            if cat['id'] in used_cat_ids
        ]

        save_coco(self.coco_data)

    def end_draw_mode(self):
        """Called after finishing drawing a box to exit draw mode."""
        self.draw_btn.setChecked(False)
        self.canvas.mode = AnnotationCanvas.MODE_NONE
        self.canvas.draw_start = None
        self.canvas.draw_preview = None
        if self.canvas._is_zoomed_beyond_window():
            self.canvas.setCursor(Qt.OpenHandCursor)
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
        self.canvas.update()

    def toggle_draw_mode(self, checked):
        if checked:
            self.delete_box_btn.setChecked(False)
            self.canvas.mode = AnnotationCanvas.MODE_DRAW
            self.canvas.dragging = False
            self.canvas.resizing = False
            self.canvas.panning = False
            self.canvas.drag_start_pos = None
            self.canvas.resize_start_pos = None
            self.canvas.pan_start_pos = None
            self.canvas.setCursor(Qt.CrossCursor)
        else:
            self.canvas.mode = AnnotationCanvas.MODE_NONE
            if self.canvas._is_zoomed_beyond_window():
                self.canvas.setCursor(Qt.OpenHandCursor)
            else:
                self.canvas.setCursor(Qt.ArrowCursor)
        self.canvas.draw_start = None
        self.canvas.draw_preview = None
        self.canvas.update()

    def toggle_delete_mode(self, checked):
        if checked:
            self.draw_btn.setChecked(False)
            self.canvas.mode = AnnotationCanvas.MODE_DELETE
            self.canvas.dragging = False
            self.canvas.resizing = False
            self.canvas.panning = False
            self.canvas.drag_start_pos = None
            self.canvas.resize_start_pos = None
            self.canvas.pan_start_pos = None
            self.canvas.setCursor(Qt.ArrowCursor)
        else:
            self.canvas.mode = AnnotationCanvas.MODE_NONE
            if self.canvas._is_zoomed_beyond_window():
                self.canvas.setCursor(Qt.OpenHandCursor)
            else:
                self.canvas.setCursor(Qt.ArrowCursor)
        self.canvas.draw_start = None
        self.canvas.draw_preview = None
        self.canvas.update()

    def modify_selected(self):
        self.canvas.modify_selected()

    def prev_image(self):
        if self.current_index > 0:
            self._navigate(self.current_index - 1)

    def next_image(self):
        if self.current_index < len(self.image_list) - 1:
            self._navigate(self.current_index + 1)

    def _navigate(self, new_index):
        self.current_index = new_index
        self.canvas.mode = AnnotationCanvas.MODE_NONE
        self.draw_btn.setChecked(False)
        self.delete_box_btn.setChecked(False)
        self.load_current_image()

    def _update_nav_buttons(self):
        self.left_btn.setEnabled(self.current_index > 0)
        self.right_btn.setEnabled(self.current_index < len(self.image_list) - 1)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_R:
            self.draw_btn.setChecked(not self.draw_btn.isChecked())
            self.toggle_draw_mode(self.draw_btn.isChecked())
        elif event.key() == Qt.Key_Delete and self.canvas.selected_ann_index >= 0 and self.canvas.mode == AnnotationCanvas.MODE_NONE:
            self.canvas.delete_selected()
        elif event.key() in (Qt.Key_D, Qt.Key_Delete):
            self.delete_box_btn.setChecked(not self.delete_box_btn.isChecked())
            self.toggle_delete_mode(self.delete_box_btn.isChecked())
        elif event.key() == Qt.Key_Left:
            self.prev_image()
        elif event.key() == Qt.Key_Right:
            self.next_image()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
