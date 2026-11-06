"""Stylesheet for kit roots, generated from the current theme tokens."""

from PySide6.QtGui import QColor

from ok.ui.qt.kit.icons import icon_file
from ok.ui.qt.kit.theme import FONT_FAMILY, MONO_FONT_FAMILY, Backdrop, rgba

_TEMPLATE = """
QWidget {{
    color: {text};
    font-family: {font};
    font-size: 13px;
}}
QWidget#kitRoot, KitWindow {{
    background: {window_bg};
}}
QWidget#kitSidebar {{
    background: {sidebar_bg};
    border-right: 1px solid {frame_separator};
}}

QLabel {{ background: transparent; }}
QLabel[role="display"] {{ font-size: 24px; font-weight: 700; }}
QLabel[role="title"] {{ font-size: 20px; font-weight: 700; }}
QLabel[role="subtitle"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="strong"] {{ font-weight: 600; }}
QLabel[role="secondary"] {{ color: {text_secondary}; font-size: 12.5px; }}
QLabel[role="caption"] {{ color: {text_tertiary}; font-size: 12px; }}
QLabel[role="section"] {{ color: {text_tertiary}; font-size: 11.5px; font-weight: 600; letter-spacing: 0.6px; }}
QLabel[tone="danger"] {{ color: {danger}; }}
QLabel[tone="warning"] {{ color: {warning}; }}
QLabel[tone="success"] {{ color: {success}; }}
QLabel[role="mono"] {{ font-family: {mono}; font-size: 12px; }}
QLabel[role="kbd"] {{
    font-family: {mono}; font-size: 11px; font-weight: 500; color: {text_secondary};
    background: {control_hover}; border-radius: 4px; padding: 0 6px;
}}
QLabel:disabled {{ color: {text_disabled}; }}

Card {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}
Card[look="inset"] {{
    background: {surface_alt};
    border-radius: 10px;
}}
SettingRow {{ background: transparent; }}
SettingRow[first="false"] {{ border-top: 1px solid {border}; }}

Button {{
    background: {control};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 0;
}}
Button:hover {{ background: {control_hover}; }}
Button:pressed {{ background: {control_pressed}; }}
Button:disabled {{ background: transparent; border-color: {border}; }}
Button QLabel#buttonText {{ font-weight: 500; }}
Button QLabel#buttonText:disabled {{ color: {text_disabled}; }}
Button[variant="primary"] {{ background: {accent}; border-color: {accent}; }}
Button[variant="primary"]:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
Button[variant="primary"]:pressed {{ background: {accent_pressed}; border-color: {accent_pressed}; }}
Button[variant="primary"]:disabled {{ background: {control_hover}; border-color: {control_hover}; }}
Button[variant="primary"] QLabel#buttonText {{ color: #FFFFFF; font-weight: 600; }}
Button[variant="primary"] QLabel#buttonText:disabled {{ color: {text_disabled}; }}
Button[variant="primary"] QLabel[role="kbd"] {{ color: #FFFFFF; background: rgba(255, 255, 255, 40); }}
Button[variant="tonal"] {{ background: {accent_soft}; border-color: {accent_line}; }}
Button[variant="tonal"]:hover {{ background: {accent_soft_hover}; }}
Button[variant="tonal"] QLabel#buttonText {{ font-weight: 600; }}
Button[variant="subtle"] {{ background: transparent; border-color: transparent; }}
Button[variant="subtle"]:hover {{ background: {control_hover}; }}
Button[variant="subtle"]:pressed {{ background: {control_pressed}; }}
Button[variant="danger"] {{ background: {danger_soft}; border-color: {danger_line}; }}
Button[variant="danger"]:hover {{ background: {danger_soft_hover}; }}
Button[variant="danger"] QLabel#buttonText {{ color: {danger}; font-weight: 600; }}

TabStrip {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
}}
TabStrip[look="underline"] {{
    background: transparent;
    border: 0;
    border-bottom: 1px solid {separator};
    border-radius: 0;
}}
QFrame#tabSeparator {{ background: {border_strong}; }}
TabItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
}}
TabItem:hover {{ background: {control_hover}; }}
/* One outline only: the strip's. TabStrip paints the selected tab's fill (or
   underline) so it can travel between tabs. */
TabItem:checked {{ background: transparent; }}
TabItem[look="underline"] {{ border: 0; border-radius: 0; border-bottom: 2px solid transparent; }}
TabItem[look="underline"]:hover {{ background: transparent; }}
TabItem[look="underline"]:checked {{ background: transparent; }}
TabItem QLabel#tabText {{ color: {text_secondary}; }}
TabItem QLabel#tabText[selected="true"] {{ color: {text}; font-weight: 600; }}
TabItem QLabel#tabCount {{
    font-size: 11px; color: {text_secondary}; background: {control_hover}; border-radius: 5px; padding: 0 6px;
}}
TabItem QLabel#tabCount[selected="true"] {{ color: #FFFFFF; background: {accent_count}; }}

Pill {{
    font-size: 11.5px; font-weight: 500; border-radius: 6px; padding: 1px 8px;
    color: {text_secondary}; background: transparent; border: 1px solid transparent;
}}
Pill[tone="accent"] {{ color: {text}; }}
Pill[tone="success"] {{ color: {success}; }}
Pill[tone="warning"] {{ color: {warning}; }}
Pill[tone="danger"] {{ color: {danger}; }}

QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit {{
    background: {control};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 0 10px;
    selection-background-color: {accent};
    selection-color: #FFFFFF;
}}
QLineEdit, QAbstractSpinBox {{ min-height: 34px; }}
QTextEdit, QPlainTextEdit {{ padding: 6px 8px; }}
QLineEdit:focus, QAbstractSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {accent}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    color: {text_disabled}; background: transparent; border-color: {border};
}}
QAbstractSpinBox {{ padding-right: 24px; }}
/* Default positions only: explicit subcontrol-position collapses the edit field of NoButtons spin boxes. */
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 22px; border: 0; background: transparent;
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {control_hover}; border-radius: 4px; }}
QAbstractSpinBox::up-arrow {{ image: url({chevron_up}); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url({chevron_down}); width: 12px; height: 12px; }}
NumberBox {{
    background: {control};
    border: 1px solid {border_strong};
    border-radius: 8px;
}}
NumberBox QAbstractSpinBox {{ border: 0; background: transparent; min-height: 32px; padding: 0 4px; }}NumberBox Button {{ border: 0; border-radius: 0; background: transparent; }}
NumberBox Button:hover {{ background: {control_hover}; }}
NumberBox Button#numberMinus {{ border-right: 1px solid {border_strong}; border-top-left-radius: 7px; border-bottom-left-radius: 7px; }}
NumberBox Button#numberPlus {{ border-left: 1px solid {border_strong}; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }}

QComboBox {{
    background: {control};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 0 30px 0 12px;
    min-height: 34px;
}}
QComboBox:hover {{ background: {control_hover}; }}
QComboBox:focus, QComboBox:on {{ border-color: {accent}; }}
QComboBox:disabled {{ color: {text_disabled}; background: transparent; border-color: {border}; }}
QComboBox::drop-down {{ border: 0; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({chevron_down}); width: 14px; height: 14px; }}
QComboBox::down-arrow:disabled {{ image: url({chevron_down_disabled}); }}
QComboBox QAbstractItemView {{
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    selection-background-color: {accent_soft_strong};
    selection-color: {text};
}}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 0 8px; border-radius: 6px; }}
QComboBox QAbstractItemView::item:hover {{ background: {control_hover}; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {text_disabled}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {switch_off};
    background: {control};
}}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({check_white}); }}
QRadioButton::indicator:checked {{ border: 5px solid {accent}; background: #FFFFFF; width: 8px; height: 8px; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {border}; background: transparent; }}

QProgressBar {{
    background: {border_strong};
    border: 0;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

QScrollArea, QScrollArea > QWidget > QWidget#scrollContents {{ background: transparent; border: 0; }}
QScrollArea > QWidget#qt_scrollarea_viewport {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 2px; }}
QScrollBar::handle:vertical {{ background: {border_strong}; border-radius: 3px; min-height: 32px; margin: 0 2px; }}
QScrollBar::handle:horizontal {{ background: {border_strong}; border-radius: 3px; min-width: 32px; margin: 2px 0; }}
QScrollBar::handle:hover {{ background: {text_tertiary}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QAbstractItemView {{
    background: {surface};
    alternate-background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: 10px;
    gridline-color: {border};
    selection-background-color: {accent_soft_strong};
    selection-color: {text};
    outline: 0;
}}
QTableView::item {{ padding: 0 12px; }}
QHeaderView::section {{
    background: {surface_alt};
    color: {text_secondary};
    border: 0;
    border-bottom: 1px solid {border};
    padding: 6px 12px;
    font-weight: 600;
}}

QMenu {{
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {control_hover}; }}
QMenu::item:disabled {{ color: {text_disabled}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}

QToolTip {{
    color: {text};
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 4px 8px;
}}

Toast {{
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 10px;
}}

QWidget#kitTitleBar {{
    background: {sidebar_bg};
    border-bottom: 1px solid {separator};
}}
QLabel#titleBadge {{
    color: {text_secondary}; border: 1px solid {border_strong}; border-radius: 5px; padding: 0 7px;
}}
QFrame#navSeparator {{ background: {separator}; }}
NavItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}}
NavItem:hover {{ background: {control_hover}; }}
/* NavigationView paints the selection highlight so it can travel between items. */
NavItem:checked {{ background: transparent; border-color: transparent; }}
NavItem QLabel#navText {{ color: {text_nav}; font-size: 13.5px; }}
NavItem QLabel#navText[selected="true"] {{ color: {text}; font-weight: 600; }}
NavItem QLabel#navDot {{ background: {accent}; border-radius: 3px; }}
Popover {{
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 14px;
}}
OptionCard {{
    background: transparent;
    border: 1px solid {border};
    border-radius: 9px;
}}
OptionCard:hover {{ border-color: {border_strong}; }}
OptionCard[selected="true"] {{ background: {accent_soft_weak}; border-color: {accent_line}; }}
QWidget#kitTitleBar[fused="true"] {{ border-bottom: 0; }}
RunBar {{
    background: {sidebar_bg};
    border: 0;
    border-bottom: 1px solid {frame_separator};
}}
ConnectionPill {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
}}
ConnectionPill:hover {{ background: {control_hover}; }}
ConnectionPill[open="true"] {{ background: {control_hover}; border-color: {border_strong}; }}
QFrame#loadingPanel {{
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 14px;
}}
Button:checked {{ background: {accent_soft_strong}; border-color: {accent_line}; }}
Button:checked QLabel#buttonText {{ font-weight: 600; }}
QListWidget#featureList {{ background: transparent; border: 0; }}
QListWidget#featureList::item {{ padding: 6px 8px; margin-bottom: 2px; border-radius: 8px; color: {text}; }}
QListWidget#featureList::item:hover {{ background: {control_hover}; }}
QListWidget#featureList::item:selected {{ background: {accent_soft_strong}; color: {text}; }}
QFrame#scheduleRow {{ background: transparent; }}
QFrame#scheduleRow[first="false"] {{ border-top: 1px solid {separator}; }}
QTimeEdit {{ padding-left: 10px; }}
QPlainTextEdit#codeEditor {{
    background: transparent;
    border: 0;
    border-radius: 0;
    padding: 6px 4px;
    font-family: {mono};
    font-size: 13px;
}}
QLabel#editorFileBar {{
    padding: 8px 14px;
    border-bottom: 1px solid {border};
}}
QLabel#errorBanner {{
    color: {danger};
    background: {danger_soft};
    border: 1px solid {danger_line};
    border-radius: 10px;
    padding: 10px 14px;
}}
QTreeWidget#templateTree {{ background: transparent; border: 0; }}
QTreeWidget#templateTree::item {{ min-height: 28px; border-radius: 6px; padding-left: 2px; }}
QTreeWidget#templateTree::item:hover {{ background: {control_hover}; }}
QTreeWidget#templateTree::item:selected {{ background: {accent_soft}; color: {text}; }}
QTreeWidget#templateTree::branch:selected, QTreeWidget#templateTree::branch:hover {{ background: transparent; }}
QFrame#templateCard {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}
QFrame#templateCard:hover {{ border-color: {border_strong}; background: {surface_alt}; }}
QFrame#templateCard[selected="true"] {{ border: 2px solid {accent}; background: {accent_soft}; }}
QLabel#templateThumb {{ background: {window}; border-radius: 8px; }}
QFrame#noticeBanner {{
    background: {warning_soft};
    border: 1px solid {warning_line};
    border-radius: 10px;
}}
QListWidget#shotList {{ padding: 6px; }}
QListWidget#shotList::item {{
    padding: 4px 10px;
    margin-bottom: 2px;
    border-radius: 8px;
    color: {text};
}}
QListWidget#shotList::item:hover {{ background: {control_hover}; }}
QListWidget#shotList::item:selected {{ background: {accent_soft_strong}; color: {text}; }}
QPlainTextEdit#logView {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 8px 4px 8px 10px;
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 13px;
}}
AnchorItem {{
    background: transparent;
    border: 0;
    border-radius: 7px;
    padding: 0 12px;
    text-align: left;
    color: {text_secondary};
}}
AnchorItem:hover {{ background: {control_hover}; color: {text}; }}
AnchorItem[current="true"] {{ background: {control_hover}; color: {text}; font-weight: 600; }}
TaskRow {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
}}
TaskRow:hover {{ background: {control_hover}; }}
TaskRow[selected="true"] {{ background: {accent_soft}; border-color: {accent_line_soft}; }}
QLabel#taskTile {{
    background: {control_hover};
    border-radius: 9px;
    color: {text_secondary};
    font-size: 12px;
    font-weight: 600;
}}
TaskIconTile#taskTile {{
    background: transparent;
    border: 0;
    border-radius: 0;
}}
QPushButton#sectionHeader {{
    background: transparent;
    border: 0;
    border-bottom: 1px solid {separator};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}}
QPushButton#sectionHeader:hover {{ background: {control_hover}; }}
QLabel[role="chip"] {{
    font-size: 11.5px; color: {text_secondary}; background: {control}; border: 1px solid {border_strong};
    border-radius: 6px; padding: 1px 8px;
}}
DialogPanel {{
    background: {surface_alt};
    border: 1px solid {border_strong};
    border-radius: 14px;
}}
"""


def _shift(color: QColor, amount: float) -> str:
    h, s, l, a = color.getHslF()
    return QColor.fromHslF(h, s, min(1.0, max(0.0, l + amount)), a).name()


def build_stylesheet(manager) -> str:
    tokens = manager.tokens()
    accent = manager.accent()
    dark = manager.is_dark()
    success, warning, danger = (QColor(tokens[name]) for name in ("success", "warning", "danger"))
    window_bg, sidebar_bg = (manager.background(name) for name in ("window", "sidebar"))
    return _TEMPLATE.format(
        window_bg=rgba(window_bg, window_bg.alphaF()),
        sidebar_bg=rgba(sidebar_bg, sidebar_bg.alphaF()),
        # With a backdrop the content layer's own edge separates it from the frame.
        frame_separator=tokens["separator"] if manager.backdrop() == Backdrop.NONE else "transparent",
        font=FONT_FAMILY,
        mono=MONO_FONT_FAMILY,
        accent=accent.name(),
        accent_hover=_shift(accent, 0.06 if dark else -0.05),
        accent_pressed=_shift(accent, -0.05 if dark else -0.1),
        accent_soft=rgba(accent, 0.14),
        accent_soft_hover=rgba(accent, 0.22),
        accent_soft_strong=rgba(accent, 0.18),
        accent_line=rgba(accent, 0.6),
        accent_line_soft=rgba(accent, 0.55),
        accent_soft_weak=rgba(accent, 0.1),
        text_nav=tokens["text"] if not dark else "#CFCFDA",
        accent_count=rgba(accent, 0.45 if dark else 0.9),
        success_soft=rgba(success, 0.1),
        success_line=rgba(success, 0.3),
        warning_soft=rgba(warning, 0.12),
        warning_line=rgba(warning, 0.35),
        danger_soft=rgba(danger, 0.12),
        danger_soft_hover=rgba(danger, 0.2),
        danger_line=rgba(danger, 0.45),
        chevron_down=icon_file("chevron-down", tokens["text_secondary"], 2),
        chevron_down_disabled=icon_file("chevron-down", tokens["text_disabled"], 2),
        chevron_up=icon_file("chevron-up", tokens["text_secondary"], 2),
        check_white=icon_file("check", "#FFFFFF", 2.6),
        **tokens,
    )
