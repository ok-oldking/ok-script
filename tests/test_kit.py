import ast
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from ok.ui.qt.kit import (Button, ComboBox, Dialog, FlowLayout, ICON_NAMES, Label, NumberBox, Pill, ProgressRing,
                          SettingGroup, SettingRow, StatusDot, Switch, TabStrip, Theme, Toast, icon, load_icon,
                          show_toast, theme)
from ok.ui.qt.kit.theme import contrast_ratio, readable_accent

KIT_DIR = Path(__file__).resolve().parents[1] / "ok" / "ui" / "qt" / "kit"
ESSENTIALS_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtSvg", "QtTest"}

SAMPLE_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
              '<rect width="10" height="10" fill="#FF0000"/></svg>')


def center_color(qicon: QIcon, size: int = 24) -> QColor:
    image = qicon.pixmap(QSize(size, size)).toImage()
    return image.pixelColor(size // 2, size // 2)


class KitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._mode = theme.mode
        self._accent = theme._accent
        theme.set_theme(Theme.DARK)

    def tearDown(self):
        theme.set_theme(self._mode)
        theme.set_accent(self._accent)
        # Delete windows now rather than during interpreter teardown, after QApplication.
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def dispose(self, widget: QWidget) -> None:
        widget.close()
        widget.deleteLater()

    def host(self, widget: QWidget = None) -> QWidget:
        host = QWidget()
        host.resize(800, 600)
        if widget is not None:
            widget.setParent(host)
        theme.install(host)
        host.show()
        QApplication.processEvents()
        self.addCleanup(self.dispose, host)
        return host


class TestEssentialsOnly(unittest.TestCase):
    def test_kit_imports_only_pyside6_essentials_modules(self):
        used = set()
        for path in KIT_DIR.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("PySide6"):
                    used.add(node.module.split(".")[1])
                elif isinstance(node, ast.Import):
                    used.update(alias.name.split(".")[1] for alias in node.names
                                if alias.name.startswith("PySide6."))
        self.assertTrue(used)
        self.assertLessEqual(used, ESSENTIALS_MODULES)

    def test_kit_does_not_import_qfluentwidgets(self):
        for path in KIT_DIR.glob("*.py"):
            self.assertNotIn("qfluentwidgets", path.read_text(encoding="utf-8"), path.name)


class TestTheme(KitTestCase):
    def test_tokens_follow_mode(self):
        dark_window = theme.color("window")
        theme.set_theme(Theme.LIGHT)
        self.assertFalse(theme.is_dark())
        self.assertNotEqual(dark_window, theme.color("window"))
        self.assertGreater(theme.color("window").lightness(), dark_window.lightness())

    def test_set_theme_emits_changed_and_restyles_installed_roots(self):
        root = QWidget()
        theme.install(root)
        seen = []
        theme.changed.connect(lambda: seen.append(True))
        theme.set_theme(Theme.LIGHT)
        self.assertEqual([True], seen)
        self.assertIn(theme.color("window").name().upper(), root.styleSheet().upper())

    def test_accent_reaches_stylesheet(self):
        theme.set_accent("#2F81F7")
        self.assertIn("#2f81f7", theme.stylesheet().lower())

    def test_light_theme_accent_keeps_white_text_readable(self):
        theme.set_theme(Theme.LIGHT)
        for color in ("#7C5CFF", "#4ADE80", "#F5B83D"):
            theme.set_accent(color)
            self.assertGreaterEqual(contrast_ratio(theme.accent(), QColor("#FFFFFF")), 4.5, color)

    def test_readable_accent_keeps_dark_colors(self):
        self.assertEqual(QColor("#123456"), readable_accent(QColor("#123456")))

    def test_uninstalled_roots_are_left_alone(self):
        root = QWidget()
        theme.install(root)
        theme.uninstall(root)
        before = root.styleSheet()
        theme.set_theme(Theme.LIGHT)
        self.assertEqual(before, root.styleSheet())

    def test_deleted_roots_are_skipped(self):
        root = QWidget()
        theme.install(root)
        root.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        theme.set_theme(Theme.LIGHT)

    def test_unknown_token_raises(self):
        with self.assertRaises(KeyError):
            theme.color("nope")


class TestIcons(KitTestCase):
    def test_bundled_icon_is_tinted(self):
        color = center_color(icon("play", "#FF0000"))
        self.assertEqual((255, 0, 0, 255), (color.red(), color.green(), color.blue(), color.alpha()))

    def test_token_icon_follows_theme(self):
        qicon = icon("stop", "text")
        dark = center_color(qicon)
        theme.set_theme(Theme.LIGHT)
        self.assertNotEqual(dark, center_color(qicon))

    def test_high_dpi_pixmap(self):
        pixmap = icon("play").pixmap(QSize(16, 16), 2.0)
        self.assertEqual(QSize(32, 32), pixmap.size())

    def test_every_bundled_icon_renders(self):
        for name in ICON_NAMES:
            image = icon(name, "#FFFFFF").pixmap(QSize(24, 24)).toImage()
            painted = any(image.pixelColor(x, y).alpha() for x in range(24) for y in range(24))
            self.assertTrue(painted, name)

    def test_unknown_icon_raises(self):
        with self.assertRaises(KeyError):
            icon("missing")

    def test_load_svg_icon_keeps_its_colors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "task.svg"
            path.write_text(SAMPLE_SVG, encoding="utf-8")
            color = center_color(load_icon("task.svg", base_dir=folder), 32)
        self.assertEqual("#ff0000", color.name())

    def test_load_png_icon(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "task.png"
            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(QColor("#00FF00"))
            image.save(str(path))
            self.assertEqual("#00ff00", center_color(load_icon(path), 16).name())

    def test_load_icon_errors(self):
        self.assertTrue(load_icon(None).isNull())
        with self.assertRaises(FileNotFoundError):
            load_icon("does-not-exist.svg")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.svg"
            path.write_text("not svg", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_icon(path)


class TestWidgets(KitTestCase):
    def test_kit_class_names_are_visible_to_stylesheets(self):
        self.assertEqual("Button", Button("x").metaObject().className())
        self.assertEqual("SettingRow", SettingRow("x").metaObject().className())

    def test_button_text_icon_and_hint(self):
        button = Button("Start", "power", "tonal", hint="F11")
        self.host(button)
        self.assertEqual("Start", button.text())
        self.assertEqual("F11", button.hint())
        self.assertGreater(button.sizeHint().width(), 90)
        clicks = []
        button.clicked.connect(lambda: clicks.append(True))
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.assertEqual([True], clicks)

    def test_icon_only_button_is_square(self):
        button = Button(icon="refresh")
        self.assertEqual(button.height(), button.width())

    def test_button_variant_validation_and_switching(self):
        with self.assertRaises(ValueError):
            Button("x", variant="loud")
        button = Button("Stop")
        button.set_variant("danger")
        self.assertEqual("danger", button.property("variant"))

    def test_section_label_is_upper_case(self):
        self.assertEqual("FARMING", Label("Farming", "section").text())
        with self.assertRaises(ValueError):
            Label("x", "huge")

    def test_switch_toggles_on_click_and_animates_to_end(self):
        switch = Switch()
        self.host(switch)
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
        self.assertTrue(switch.isChecked())
        QTest.qWait(250)
        self.assertAlmostEqual(1.0, switch.position)

    def test_switch_checked_with_signals_blocked_draws_on(self):
        switch = Switch()
        self.host(switch)
        switch.blockSignals(True)
        switch.setChecked(True)
        switch.blockSignals(False)
        switch.repaint()
        self.assertEqual(1.0, switch.position)

    def test_hidden_switch_jumps_without_animation(self):
        switch = Switch()
        switch.setChecked(True)
        self.assertEqual(1.0, switch.position)

    def test_number_box_steps_and_clamps(self):
        box = NumberBox(1, 1, 3)
        self.host(box)
        values = []
        box.valueChanged.connect(values.append)
        self.assertFalse(box.minus_button.isEnabled())
        box.plus_button.click()
        box.plus_button.click()
        self.assertEqual([2, 3], values)
        self.assertFalse(box.plus_button.isEnabled())
        self.assertGreater(box.spin_box.lineEdit().width(), 20)

    def test_float_number_box(self):
        box = NumberBox(0.5, 0, 1, 0.1, decimals=1)
        box.plus_button.click()
        self.assertAlmostEqual(0.6, box.value())

    def test_combo_box_items(self):
        combo = ComboBox(["A", "B"])
        self.assertEqual(2, combo.count())

    def test_setting_group_marks_first_row(self):
        group = SettingGroup("Farming")
        first = group.add_row(SettingRow("One", control=ComboBox(["A"])))
        second = group.add_row(SettingRow("Two", "Description", Switch()))
        self.assertTrue(first.property("first"))
        self.assertFalse(second.property("first"))
        self.assertEqual(240, first.control.width())
        self.assertNotEqual(240, second.control.width())
        self.assertTrue(second.description_label.isVisibleTo(second))
        self.assertFalse(first.description_label.isVisibleTo(first))

    def test_tab_strip_selection_counts_and_separator(self):
        strip = TabStrip()
        strip.add_tab("all", "All", 15)
        strip.add_tab("triggers", "Triggers", 6, "timer")
        strip.add_separator()
        strip.add_tab("daily", "Daily", 3, "calendar")
        self.host(strip)
        self.assertEqual("all", strip.current_key())
        changes = []
        strip.current_changed.connect(changes.append)
        QTest.mouseClick(strip.item("daily"), Qt.MouseButton.LeftButton)
        self.assertEqual(["daily"], changes)
        self.assertTrue(strip.item("daily").text_label.property("selected"))
        self.assertFalse(strip.item("all").text_label.property("selected"))
        strip.set_count("daily", 4)
        self.assertEqual("4", strip.item("daily").count_label.text())
        with self.assertRaises(ValueError):
            strip.add_tab("all", "Again")

    def test_pill_and_dot_tones(self):
        pill = Pill("Running", "success")
        pill.set_tone("danger")
        self.assertEqual("danger", pill.property("tone"))
        with self.assertRaises(ValueError):
            StatusDot("purple")

    def test_progress_ring_spins_only_when_indeterminate_and_visible(self):
        ring = ProgressRing()
        self.assertFalse(ring.is_spinning())
        self.host(ring)
        self.assertTrue(ring.is_spinning())
        ring.set_value(150)
        self.assertEqual(100, ring.value())
        self.assertFalse(ring.is_spinning())

    def test_flow_layout_wraps(self):
        holder = QWidget()
        flow = FlowLayout(holder)
        labels = [QLabel("x" * 20) for _ in range(6)]
        for label in labels:
            flow.addWidget(label)
        width = labels[0].sizeHint().width() * 2 + 30
        self.assertGreater(flow.heightForWidth(width), flow.heightForWidth(width * 10))


class _WindowShowRecorder(QObject):
    def __init__(self):
        super().__init__()
        self.windows = []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and obj.isWidgetType() and obj.isWindow():
            self.windows.append(type(obj).__name__)
        return False


class TestNoStrayWindows(KitTestCase):
    """Building widgets must never show a child as its own top-level window."""

    def test_constructors_do_not_flash_windows(self):
        from ok.ui.qt.kit import NavigationView, OptionCard, SettingGroup
        recorder = _WindowShowRecorder()
        QApplication.instance().installEventFilter(recorder)
        self.addCleanup(QApplication.instance().removeEventFilter, recorder)
        widgets = [
            SettingRow("Title", "A description", Switch()),
            SettingGroup("Group"),
            OptionCard("WGC", "Fast", "Recommended"),
            Toast("Message", "Title", "success"),
        ]
        nav = NavigationView()
        nav.add_section("run", "Run")
        nav.add_item("tasks", "Tasks", "tasks", "run")
        widgets.append(nav)
        host = QWidget()
        widgets.append(Dialog(host, "Title", "Message"))
        widgets.append(host)
        QApplication.processEvents()
        self.assertEqual([], recorder.windows)
        for widget in widgets:
            widget.deleteLater()


class TestFeedback(KitTestCase):
    def test_toasts_stack_and_expire(self):
        host = self.host()
        first = show_toast(host, "First", duration=150)
        second = show_toast(host, "Second", "Title", "success", duration=0)
        QApplication.processEvents()
        self.assertTrue(first.isVisible())
        self.assertLess(first.y(), second.y())
        self.assertLessEqual(second.geometry().bottom(), host.height())
        QTest.qWait(300)
        self.assertTrue(second.isVisible())
        second.close_button.click()
        QApplication.processEvents()
        self.assertFalse(second.isVisible())

    def test_dialog_exec_returns_answer(self):
        host = self.host()
        for button, expected in (("ok_button", True), ("cancel_button", False)):
            dialog = Dialog(host, "Delete?", "Really")
            QTimer.singleShot(0, getattr(dialog, button).click)
            self.assertIs(expected, dialog.exec())
            self.assertFalse(dialog.isVisible())

    def test_dialog_covers_window_and_escape_rejects(self):
        host = self.host()
        dialog = Dialog(host, "Title")
        dialog.open()
        QApplication.processEvents()
        self.assertEqual(host.rect(), dialog.geometry())
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.result())
        self.assertFalse(dialog.isVisible())


class TestGallery(KitTestCase):
    def test_gallery_builds_in_both_themes(self):
        from ok.ui.qt.kit.gallery import create_window
        for mode in (Theme.DARK, Theme.LIGHT):
            theme.set_theme(mode)
            window = create_window()
            window.show()
            QApplication.processEvents()
            self.assertGreater(len(window.findChildren(Button)), 40)
            self.dispose(window)
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
