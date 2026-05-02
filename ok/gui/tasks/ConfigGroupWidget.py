from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QEvent, QObject, Property
from PySide6.QtGui import QIcon, QPixmap, QTransform
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


class _AngleObject(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0

    def getAngle(self):
        return self._angle

    def setAngle(self, v):
        self._angle = v
        parent = self.parent()
        if parent is not None:
            parent._set_rotated_icon(v)

    angle = Property(float, getAngle, setAngle)


def collect_group_children(config_group):
    children = set()
    # A group parent may be a real config item or a title-only header.
    # In both cases, grouped children should stay inside the group.
    for grouped in config_group.values():
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
        self.toggle_btn.setIconSize(QSize(12, 12))
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

        # 保存原始图标并准备旋转动画（展开/收起时旋转原图标，而不是替换为另一个图标）
        self._base_icon = self.toggle_btn.icon() if not self.toggle_btn.icon().isNull() else QIcon()
        self._icon_angle = 0

        # 使用 QPropertyAnimation 动画自定义的 angle 属性，保证在不同平台行为一致
        self._angle_obj = _AngleObject(self)
        self._icon_anim = QPropertyAnimation(self._angle_obj, b"angle", self)
        self._icon_anim.setDuration(200)
        self._icon_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._icon_anim.finished.connect(self._on_icon_anim_finished)

        # 确保初始图标被设置为基准图标的像素（避免某些环境下 icon() 为空或大小不一致）
        self._set_rotated_icon(0)

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
            # 收起：将图标旋转回原位（0度）
            self._icon_anim.stop()
            self._icon_anim.setStartValue(self._icon_angle)
            self._icon_anim.setEndValue(0)
            self._icon_anim.start()
        else:
            self.panel.setMaximumHeight(16777215)
            self.animation.setStartValue(0)
            self.animation.setEndValue(self.panel.sizeHint().height())
            # 展开：将原图标反方向旋转 180 度（朝上）
            self._icon_anim.stop()
            self._icon_anim.setStartValue(self._icon_angle)
            self._icon_anim.setEndValue(-180)
            self._icon_anim.start()

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

    def _set_rotated_icon(self, angle):
        try:
            angle = float(angle)
        except Exception:
            return
        # 只有在有基础图标时才处理
        if self._base_icon.isNull():
            return
        size = self.toggle_btn.iconSize()
        pix = self._base_icon.pixmap(size)
        if pix.isNull():
            return
        transform = QTransform().rotate(angle)
        rotated = pix.transformed(transform, Qt.SmoothTransformation)
        self.toggle_btn.setIcon(QIcon(rotated))
        self._icon_angle = angle

    def _on_icon_anim_finished(self):
        # 将图标修正为动画目标角度的像素，保证最终状态一致
        end = self._icon_anim.endValue()
        try:
            end_angle = float(end)
        except Exception:
            end_angle = self._icon_angle
        # 如果目标为 0 度，恢复为基准图标以避免像素误差
        if abs(end_angle) < 1e-3:
            if not self._base_icon.isNull():
                self.toggle_btn.setIcon(self._base_icon)
            self._icon_angle = 0
        else:
            # 否则使用精确的角度渲染一次
            self._set_rotated_icon(end_angle)

    def _notify_height_changed(self, *_):
        if self._on_height_changed:
            self._on_height_changed()
