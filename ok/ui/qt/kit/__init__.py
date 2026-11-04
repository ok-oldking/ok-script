"""ok-script's own PySide6 widget kit.

Built only on the Qt modules ok-pyside-minimal ships (QtCore, QtGui,
QtWidgets, QtSvg). Call ``theme.install(root)`` on a top-level widget to style it and
its children; plain Qt inputs inside it are styled too.
"""

from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card, SettingGroup, SettingRow
from ok.ui.qt.kit.dialogs import Dialog, confirm
from ok.ui.qt.kit.feedback import Pill, ProgressRing, StatusDot, Toast, set_toast_anchor, set_toast_top_margin, show_toast
from ok.ui.qt.kit.icons import ICON_NAMES, icon, load_icon
from ok.ui.qt.kit.inputs import ComboBox, NumberBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.layout import FlowLayout
from ok.ui.qt.kit.navigation import NavigationView, NavItem
from ok.ui.qt.kit.options import OptionCard, OptionGroup
from ok.ui.qt.kit.popover import Popover
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.kit.tabs import TabItem, TabStrip
from ok.ui.qt.kit.theme import Theme, theme
from ok.ui.qt.kit.window import ContentLayer, KitWindow, TitleBar

__all__ = [
    "Button", "Card", "ComboBox", "ContentLayer", "Dialog", "FlowLayout", "ICON_NAMES", "KitWindow", "Label",
    "NavItem",
    "NavigationView", "NumberBox", "OptionCard", "OptionGroup", "Pill", "Popover", "ProgressRing", "SettingGroup",
    "SettingRow", "StatusDot", "Switch", "TabItem", "TabStrip", "Theme", "TitleBar", "Toast", "confirm", "icon",
    "load_icon", "set_toast_anchor", "set_toast_top_margin", "show_toast", "theme",
]
