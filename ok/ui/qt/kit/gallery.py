"""Every kit widget on one page, for checking the look in light and dark.

Run standalone with ``python -m ok.ui.qt.kit.gallery [light|dark]``.
"""

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QProgressBar, QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card, SettingGroup, SettingRow
from ok.ui.qt.kit.dialogs import Dialog, confirm
from ok.ui.qt.kit.feedback import Pill, ProgressRing, StatusDot, show_toast
from ok.ui.qt.kit.icons import ICON_NAMES, icon
from ok.ui.qt.kit.inputs import ComboBox, NumberBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.layout import FlowLayout
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.kit.tabs import TabStrip
from ok.ui.qt.kit.theme import Theme, theme

ACCENTS = ("#7C5CFF", "#2F81F7", "#D946A6", "#16A34A")


def _row(*widgets, spacing: int = 8) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return layout


class GalleryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kitRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        scroll.setWidget(contents)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.column = QVBoxLayout(contents)
        self.column.setContentsMargins(28, 24, 28, 28)
        self.column.setSpacing(18)
        self._header()
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self._buttons(), 0, 0)
        grid.addWidget(self._status(), 0, 1)
        grid.addWidget(self._tabs(), 1, 0, 1, 2)
        grid.addWidget(self._settings(), 2, 0)
        grid.addWidget(self._inputs(), 2, 1)
        grid.addWidget(self._icons(), 3, 0, 1, 2)
        self.column.addLayout(grid)
        self.column.addStretch(1)

    def _section(self, title: str):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(Label(title, "subtitle"))
        return card, layout

    def _header(self) -> None:
        title = Label("Kit gallery", "display")
        self.theme_tabs = TabStrip()
        for mode, text in ((Theme.AUTO, "System"), (Theme.LIGHT, "Light"), (Theme.DARK, "Dark")):
            self.theme_tabs.add_tab(mode.value, text)
        self.theme_tabs.set_current(theme.mode.value)
        self.theme_tabs.current_changed.connect(lambda key: theme.set_theme(Theme(key)))

        accents = QHBoxLayout()
        accents.setSpacing(6)
        for color in ACCENTS:
            swatch = Button(variant="subtle", size="small")
            swatch.setToolTip(color)
            swatch.setFixedSize(26, 26)
            swatch.setStyleSheet(f"Button {{ background: {color}; border: 2px solid transparent; border-radius: 13px; }}"
                                 f"Button:hover {{ border-color: rgba(255, 255, 255, 120); }}")
            swatch.clicked.connect(lambda _=False, c=color: theme.set_accent(c))
            accents.addWidget(swatch)

        header = QHBoxLayout()
        header.setSpacing(16)
        header.addWidget(title)
        header.addStretch(1)
        header.addLayout(accents)
        header.addWidget(self.theme_tabs)
        self.column.addLayout(header)

    def _buttons(self) -> QWidget:
        card, layout = self._section("Buttons")
        layout.addLayout(_row(Button("Run task", "play", "primary"), Button("Reset", "reset"),
                              Button("Start", "power", "tonal", hint="F11"), Button("Pause", "pause", hint="F11")))
        layout.addLayout(_row(Button("Open folder", "folder", "subtle"), Button("Stop", "stop", "danger"),
                              Button(icon="refresh"), Button(icon="x", variant="subtle")))
        layout.addLayout(_row(Button("Small", size="small"), Button("Export logs", "export", size="small"),
                              Button("Primary", variant="primary", size="small")))
        disabled = [Button("Disabled", "play", "primary"), Button("Disabled", "camera"), Button(icon="refresh")]
        for button in disabled:
            button.setEnabled(False)
        layout.addLayout(_row(*disabled))
        layout.addStretch(1)
        return card

    def _status(self) -> QWidget:
        card, layout = self._section("Status and feedback")
        layout.addLayout(_row(Pill("Idle"), Pill("Queued", "accent"), Pill("Succeeded", "success"),
                              Pill("Launching", "warning"), Pill("Failed", "danger")))
        dots = QHBoxLayout()
        dots.setSpacing(16)
        for tone, text in (("success", "Connected"), ("warning", "Launching"), ("danger", "Blocked"),
                           ("neutral", "Not running")):
            dots.addWidget(StatusDot(tone))
            dots.addWidget(Label(text, "secondary"))
        dots.addStretch(1)
        layout.addLayout(dots)

        progress = QProgressBar()
        progress.setValue(62)
        ring = ProgressRing(22)
        ring_value = ProgressRing(22, 62)
        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)
        progress_row.addWidget(ring)
        progress_row.addWidget(ring_value)
        progress_row.addWidget(Label("Tacet Field · run 3 of 4", "secondary"))
        progress_row.addWidget(progress, 1)
        progress_row.addWidget(Label("03:42", "mono"))
        layout.addLayout(progress_row)

        toast_buttons = []
        for tone, message in (("neutral", "Task queued"), ("success", "Daily Task finished in 11m 40s"),
                              ("warning", "Auto HDR is on; capture may look washed out"),
                              ("danger", "Game window lost")):
            button = Button(tone.capitalize(), size="small")
            button.clicked.connect(lambda _=False, t=tone, m=message: show_toast(self, m, t.capitalize(), t))
            toast_buttons.append(button)
        layout.addLayout(_row(Label("Toasts", "secondary"), *toast_buttons))

        dialog_button = Button("Open dialog", "info", size="small")
        dialog_button.clicked.connect(self._open_dialog)
        confirm_button = Button("Confirm delete", "x", "danger", size="small")
        confirm_button.clicked.connect(lambda: confirm(self, "Delete this schedule?",
                                                       "The task stays; only its schedule is removed.",
                                                       ok_text="Delete", danger=True))
        layout.addLayout(_row(Label("Dialogs", "secondary"), dialog_button, confirm_button))
        layout.addStretch(1)
        return card

    def _open_dialog(self) -> None:
        dialog = Dialog(self, "Create schedule", "Run a task at a fixed time while the app is open.",
                        ok_text="Create")
        dialog.body.addWidget(Label("Task", "secondary"))
        dialog.body.addWidget(ComboBox(["Daily Task", "Nightmare Nest", "Tacet Field"]))
        dialog.body.addWidget(Label("Time", "secondary"))
        dialog.body.addWidget(QLineEdit("04:30"))
        dialog.exec()
        dialog.deleteLater()

    def _tabs(self) -> QWidget:
        card, layout = self._section("Tabs")
        groups = TabStrip()
        groups.add_tab("all", "All", 15)
        groups.add_tab("on_demand", "On-demand", 9, "bolt")
        groups.add_tab("triggers", "Triggers", 6, "timer")
        groups.add_separator()
        groups.add_tab("daily", "Daily", 3, "calendar")
        groups.add_tab("farming", "Farming", 6, "layers")
        layout.addLayout(_row(groups))
        pages = TabStrip("underline")
        pages.add_tab("settings", "Settings", icon="gear")
        pages.add_tab("history", "History", icon="history")
        pages.add_tab("log", "Log", icon="file")
        layout.addWidget(pages)
        return card

    def _settings(self) -> QWidget:
        card, layout = self._section("Setting rows")
        farming = SettingGroup("Farming")
        farming.add_row(SettingRow("Farm target", "Where stamina is spent after the dailies are done.",
                                   ComboBox(["Tacet Field", "Forgery Challenge", "Simulation Challenge"])))
        farming.add_row(SettingRow("Tacet Field index", "Position of the Tacet Field in the F2 list.",
                                   NumberBox(7, 1, 20), indent=True))
        farming.add_row(SettingRow("Use Nightmare Nest for daily echoes",
                                   "Go to a Nightmare Nest when echoes are needed to finish the dailies.",
                                   Switch()))
        layout.addWidget(farming)

        afterwards = SettingGroup("Afterwards")
        extras = QWidget()
        flow = FlowLayout(extras)
        for text, checked in (("Weekly park", True), ("Merge echoes > 1000", True),
                              ("All Nightmare Nests", False), ("Farm 4C echoes", False)):
            box = QCheckBox(text)
            box.setChecked(checked)
            flow.addWidget(box)
        extras_row = SettingRow("Extra tasks after daily", "Nightmare Nest runs before stamina is used.", extras,
                                control_width=300)
        afterwards.add_row(extras_row)
        afterwards.add_row(SettingRow("Exit when finished", "Close the game and the app afterwards.", Switch(True)))
        layout.addWidget(afterwards)
        return card

    def _inputs(self) -> QWidget:
        card, layout = self._section("Inputs")
        line = QLineEdit()
        line.setPlaceholderText("Placeholder text")
        disabled_line = QLineEdit("Disabled")
        disabled_line.setEnabled(False)
        combo = ComboBox(["English", "简体中文", "日本語"])
        disabled_combo = ComboBox(["Disabled"])
        disabled_combo.setEnabled(False)
        number = NumberBox(0.5, 0, 10, 0.1, decimals=1)
        layout.addLayout(_row(line, disabled_line))
        layout.addLayout(_row(combo, disabled_combo, number))
        checks = [QCheckBox("Checked"), QCheckBox("Unchecked"), QCheckBox("Disabled")]
        checks[0].setChecked(True)
        checks[2].setEnabled(False)
        radios = [QRadioButton("WGC"), QRadioButton("BitBlt")]
        radios[0].setChecked(True)
        layout.addLayout(_row(*checks, *radios, spacing=16))
        switches = [Switch(True), Switch(False), Switch(True), Switch(False)]
        switches[2].setEnabled(False)
        switches[3].setEnabled(False)
        layout.addLayout(_row(*switches, spacing=16))
        log = QPlainTextEdit("08:12:04 login ok\n08:12:31 claimed monthly card\n08:14:02 Tacet Field #7 · 4 runs")
        log.setFixedHeight(96)
        layout.addWidget(log)
        layout.addStretch(1)
        return card

    def _icons(self) -> QWidget:
        card, layout = self._section("Bundled icons")
        holder = QWidget()
        flow = FlowLayout(holder, spacing=6)
        for name in ICON_NAMES:
            button = Button(icon=name, variant="subtle")
            button.setToolTip(name)
            flow.addWidget(button)
        layout.addWidget(holder)
        return card


def create_window() -> QWidget:
    window = GalleryPage()
    window.setWindowTitle("ok-script kit gallery")
    window.setWindowIcon(icon("grid", "accent"))
    window.resize(QSize(1320, 1000))
    theme.install(window)
    return window


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    app.setStyle("Fusion")
    if len(argv) > 1:
        theme.set_theme(Theme(argv[1]))
    window = create_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
