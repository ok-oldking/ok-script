from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QScrollBar,
    QSlider,
    QTextEdit,
    QWidget,
    QVBoxLayout,
)
from qfluentwidgets import CardWidget, FluentIcon, TransparentToolButton


def collect_group_children(config, config_group):
    children = set()
    # Only collect children for groups whose parent key exists in the current config.
    # This lets a group dissolve automatically if the main option is removed.
    for parent_key, grouped in config_group.items():
        if parent_key not in config:
            continue
        if not isinstance(grouped, (list, tuple)):
            continue
        for child_key in grouped:
            if isinstance(child_key, str):
                children.add(child_key)
    return children


def valid_group_child_keys(children, config, added_keys):
    if not isinstance(children, (list, tuple)):
        return []

    return [
        child_key
        for child_key in children
        if isinstance(child_key, str)
        and not child_key.startswith("_")
        and child_key not in added_keys
        and child_key in config
    ]


class ConfigGroupWidget(CardWidget):
    def __init__(self, parent_widget, toggle_tooltip: str, on_height_changed=None, parent=None):
        super().__init__(parent)
        self._on_height_changed = on_height_changed
        self._child_count = 0
        self.setObjectName("config_group_frame")

        self.group_layout = QVBoxLayout(self)
        self.group_layout.setContentsMargins(10, 8, 10, 8)
        self.group_layout.setSpacing(0)

        self.header = QWidget(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_layout.addWidget(parent_widget, 1)

        self.toggle_btn = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED)
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toggle_btn.setFixedSize(40, 40)
        self.toggle_btn.setMinimumSize(40, 40)
        self.toggle_btn.setIconSize(QSize(16, 16))
        self.toggle_btn.setStyleSheet("""
            TransparentToolButton {
                background-color: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            TransparentToolButton:hover {
                background-color: transparent;
                border: none;
            }
            TransparentToolButton:pressed {
                background-color: transparent;
                border: none;
            }
        """)
        self.toggle_btn.setToolTip(toggle_tooltip)
        header_layout.addWidget(self.toggle_btn, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.group_layout.addWidget(self.header, 0)

        self.panel = QWidget(self)
        self.panel_layout = QVBoxLayout(self.panel)
        self.panel_layout.setContentsMargins(12, 6, 0, 0)
        self.panel_layout.setSpacing(4)
        self.panel.setMaximumHeight(0)
        self.panel.setVisible(True)
        self.group_layout.addWidget(self.panel, 0)

        self.animation = QPropertyAnimation(self.panel, b"maximumHeight", self)
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.valueChanged.connect(self._notify_height_changed)
        self.animation.finished.connect(self._notify_height_changed)
        self.toggle_btn.clicked.connect(self.toggle_children)
        self._install_toggle_filters(self.header)

    def add_child_widget(self, widget):
        self.panel_layout.addWidget(widget)
        self._child_count += 1

    def has_children(self):
        return self._child_count > 0

    def toggle_children(self):
        self.animation.stop()

        if self.panel.maximumHeight() > 0:
            self.animation.setStartValue(self.panel.height())
            self.animation.setEndValue(0)
            self.toggle_btn.setIcon(FluentIcon.CHEVRON_DOWN_MED)
        else:
            self.panel.setMaximumHeight(16777215)
            self.animation.setStartValue(0)
            self.animation.setEndValue(self.panel.sizeHint().height())
            self.toggle_btn.setIcon(FluentIcon.CARE_UP_SOLID)

        self.animation.start()

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
            and self._is_header_widget(obj)
        ):
            self.toggle_children()
            return True
        return super().eventFilter(obj, event)

    def _install_toggle_filters(self, widget):
        if self._is_interactive_widget(widget):
            return

        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            self._install_toggle_filters(child)

    def _is_interactive_widget(self, widget):
        return isinstance(widget, (
            QAbstractButton,
            QAbstractSpinBox,
            QComboBox,
            QLineEdit,
            QPlainTextEdit,
            QScrollBar,
            QSlider,
            QTextEdit,
        ))

    def _is_header_widget(self, widget):
        while widget is not None:
            if widget is self.header:
                return True
            widget = widget.parentWidget()
        return False

    def _notify_height_changed(self, *_):
        if self._on_height_changed:
            self._on_height_changed()
