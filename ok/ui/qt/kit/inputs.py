"""Input widgets.

Plain Qt inputs (QLineEdit, QCheckBox, QRadioButton, QTextEdit, ...) are
styled by the kit stylesheet and are used directly. This module adds the
inputs that need structure beyond a stylesheet.
"""

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QListView, QSpinBox,
                               QStyle, QStyledItemDelegate, QStyleOptionComboBox, QStyleOptionViewItem, QStylePainter,
                               QWidget)

from ok.ui.qt.kit.buttons import Button

POPUP_ANIMATION_DURATION = 160
POPUP_GAP = 2
POPUP_SCREEN_WIDTH_INSET = 100


class _FocusedWheelFilter(QObject):
    """Ignores wheel events on widgets that do not have keyboard focus.

    The ignored event propagates to the parent, so hovering an input inside
    a scroll area scrolls the page instead of changing the value.
    """

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(obj, QWidget) and not obj.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(obj, event)


_focused_wheel_filter = None


def require_focus_for_wheel(widget: QWidget) -> None:
    """Make ``widget`` respond to the mouse wheel only while it has focus."""
    global _focused_wheel_filter
    if _focused_wheel_filter is None:
        _focused_wheel_filter = _FocusedWheelFilter()
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.installEventFilter(_focused_wheel_filter)


class _ComboItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        option = QStyleOptionViewItem(option)
        # Some styles give rows their natural width even when the viewport is narrower.
        rect = option.rect
        viewport = self.parent().viewport().rect()
        rect.setLeft(max(rect.left(), viewport.left()))
        rect.setRight(min(rect.right(), viewport.right()))
        option.rect = rect
        super().paint(painter, option, index)


class ComboBox(QComboBox):
    """A combo box whose popup items can be styled (rounded, padded rows)."""

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        require_focus_for_wheel(self)
        self._reveal_pending = False
        self._popup_rest_position = None
        self._popup_animation = QVariantAnimation(self)
        self._popup_animation.setDuration(POPUP_ANIMATION_DURATION)
        self._popup_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._popup_animation.valueChanged.connect(self._step_popup)
        self._popup_animation.finished.connect(self._finish_popup_animation)
        view = QListView(self)
        self.setView(view)
        view.setItemDelegate(_ComboItemDelegate(view))
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if items:
            self.addItems(list(items))

    def setView(self, item_view) -> None:
        self._finish_popup_animation()
        super().setView(item_view)
        self._configure_popup()

    def _configure_popup(self) -> None:
        view = self.view()
        if view is None:
            return
        popup = view.window()
        flags = popup.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        if popup.windowFlags() != flags:
            popup.setWindowFlags(flags)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.installEventFilter(self)

    def showPopup(self) -> None:
        self._configure_popup()
        view = self.view()
        popup = view.window()
        if popup.isVisible():
            return

        effect = Qt.UIEffect.UI_AnimateCombo
        effect_enabled = QApplication.isEffectEnabled(effect)
        animate = effect_enabled and self.count() > 0 and self.isVisible() and self._popup_animation.duration() > 0
        if animate:
            # Keep the window invisible during ShowWindow so stale backing-store
            # pixels at y=0 cannot flash before the slide animation starts.
            popup.setWindowOpacity(0.0)
        # Bypass Qt's QRollEffect: it uses a temporary window and flashes on handoff.
        if effect_enabled:
            QApplication.setEffectEnabled(effect, False)
        try:
            super().showPopup()
            if popup.isVisible():
                self._adjust_popup_geometry(view, popup)
                if animate and view.height() > 0:
                    self._animate_popup(view, popup)
        finally:
            if effect_enabled:
                QApplication.setEffectEnabled(effect, True)
            if animate and self._popup_rest_position is None:
                # No slide running (not shown, overlapping, or an exception): never leave it transparent.
                popup.setWindowOpacity(1.0)

    def _adjust_popup_geometry(self, view, popup) -> None:
        screen = self.screen().availableGeometry()
        margins = popup.width() - view.viewport().width()
        content_width = view.sizeHintForColumn(self.modelColumn())
        width_limit = max(1, screen.width() - POPUP_SCREEN_WIDTH_INSET)
        width = min(width_limit, max(self.width(), content_width + margins))
        anchor = self.rect().translated(self.mapToGlobal(QPoint()))
        x = anchor.left() + (anchor.width() - width) // 2
        x = max(screen.left(), min(x, screen.right() - width + 1))
        # Keep Qt's chosen side and height. Use the gap that fits on that side.
        y = popup.y()
        if popup.geometry().top() >= anchor.bottom():
            y = min(anchor.bottom() + 1 + POPUP_GAP, screen.bottom() - popup.height() + 1)
        elif popup.geometry().bottom() <= anchor.top():
            y = max(anchor.top() - popup.height() - POPUP_GAP, screen.top())
        popup.setGeometry(x, y, width, popup.height())

    def _label_option(self) -> QStyleOptionComboBox:
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        if self.currentIndex() < 0 and self.placeholderText():
            option.currentText = self.placeholderText()
            option.palette.setBrush(QPalette.ColorRole.ButtonText, option.palette.placeholderText())
        return option

    def _elided_text(self, option: QStyleOptionComboBox) -> str:
        field = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                            QStyle.SubControl.SC_ComboBoxEditField, self)
        width = field.width()
        if not option.currentIcon.isNull():
            width -= option.iconSize.width() + 4
        return option.fontMetrics.elidedText(option.currentText, Qt.TextElideMode.ElideRight, max(0, width))

    def paintEvent(self, event) -> None:
        if self.isEditable() or self.labelDrawingMode() == QComboBox.LabelDrawingMode.UseDelegate:
            super().paintEvent(event)
            return
        option = self._label_option()
        elided = self._elided_text(option)
        if elided == option.currentText:
            super().paintEvent(event)
            return
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        option.currentText = elided
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def _animate_popup(self, view, popup) -> None:
        combo_top = self.mapToGlobal(QPoint(0, 0)).y()
        popup_center_y = popup.y() + popup.height() / 2
        if popup_center_y >= combo_top + self.height():
            offset = -view.height()
        elif popup_center_y <= combo_top:
            offset = view.height()
        else:
            # The style centered the popup over the combo; there is no side to slide in from.
            return
        rest = view.pos()
        start = rest + QPoint(0, offset)
        self._popup_rest_position = rest
        popup.layout().setEnabled(False)
        view.move(start)
        self._reveal_pending = True
        popup.setWindowOpacity(0.004)
        self._popup_animation.setStartValue(start)
        self._popup_animation.setEndValue(rest)
        self._popup_animation.start()

    def _step_popup(self, value) -> None:
        view = self.view()
        if view is None or not view.window().isVisible():
            self._finish_popup_animation()
            return
        view.move(value)

    def _reveal_popup(self) -> None:
        # Runs once after the first paint; _finish_popup_animation is the fallback.
        if self._popup_rest_position is not None:
            self.view().window().setWindowOpacity(1.0)

    def _finish_popup_animation(self) -> None:
        rest = self._popup_rest_position
        if rest is None:
            return
        self._popup_rest_position = None
        self._reveal_pending = False
        self._popup_animation.stop()
        view = self.view()
        popup = view.window()
        view.move(rest)
        popup.layout().setEnabled(True)
        popup.setWindowOpacity(1.0)

    def eventFilter(self, obj, event) -> bool:
        view = self.view()
        if view is not None and obj is view.window():
            event_type = event.type()
            if event_type == QEvent.Type.Paint and self._reveal_pending:
                self._reveal_pending = False
                QTimer.singleShot(0, self, self._reveal_popup)
            elif event_type == QEvent.Type.Hide:
                self._finish_popup_animation()
        return super().eventFilter(obj, event)


class NumberBox(QFrame):
    """A spin box with − and + buttons on either side.

    ``decimals`` > 0 makes it a floating point box. ``valueChanged`` carries
    an int or float accordingly.
    """

    valueChanged = Signal(object)

    def __init__(self, value=0, minimum=0, maximum=99, step=1, decimals: int = 0, parent=None):
        super().__init__(parent)
        self._spin = QDoubleSpinBox(self) if decimals else QSpinBox(self)
        if decimals:
            self._spin.setDecimals(decimals)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setValue(value)
        self._spin.setKeyboardTracking(False)
        require_focus_for_wheel(self._spin)

        self.minus_button = Button(icon="minus", variant="subtle")
        self.minus_button.setObjectName("numberMinus")
        self.plus_button = Button(icon="plus", variant="subtle")
        self.plus_button.setObjectName("numberPlus")
        for button in (self.minus_button, self.plus_button):
            button.setFixedSize(38, 34)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAutoRepeat(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.minus_button)
        layout.addWidget(self._spin, 1)
        layout.addWidget(self.plus_button)
        self.setFixedHeight(36)

        self.minus_button.clicked.connect(self._spin.stepDown)
        self.plus_button.clicked.connect(self._spin.stepUp)
        self._spin.valueChanged.connect(self._on_value_changed)
        self._sync_buttons()

    @property
    def spin_box(self):
        return self._spin

    def value(self):
        return self._spin.value()

    def setValue(self, value) -> None:
        self._spin.setValue(value)

    def setRange(self, minimum, maximum) -> None:
        self._spin.setRange(minimum, maximum)
        self._sync_buttons()

    def _on_value_changed(self, value) -> None:
        self._sync_buttons()
        self.valueChanged.emit(value)

    def _sync_buttons(self) -> None:
        value = self._spin.value()
        self.minus_button.setEnabled(self.isEnabled() and value > self._spin.minimum())
        self.plus_button.setEnabled(self.isEnabled() and value < self._spin.maximum())

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.EnabledChange:
            self._sync_buttons()
