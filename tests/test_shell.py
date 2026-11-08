import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QIcon
from qt_helpers import mouse_click, wait
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ok.core.icons import Icon
from ok.ui.qt.kit import KitWindow, NavigationView, OptionGroup, Popover, theme
from ok.ui.qt.shell.connection import capture_options, device_details, device_label, interaction_options, \
    split_label
from ok.ui.qt.shell.nav_icons import FALLBACK, nav_icon
from ok.ui.qt.shell.run_bar import compute_run_state, format_elapsed


def make_executor(**overrides):
    executor = SimpleNamespace(exclusive_owner=None, paused=True, current_task=None, onetime_tasks=[],
                               onetime_task_queue=[], connected=lambda: True, can_capture=lambda: True,
                               active_trigger_task_count=lambda: 0)
    for key, value in overrides.items():
        setattr(executor, key, value)
    return executor


def make_device_manager(device=None, capture=None, interaction=None, methods=None):
    return SimpleNamespace(
        get_preferred_device=lambda: device,
        get_preferred_capture=lambda: capture,
        windows_capture_config=methods or {},
        config={"interaction": interaction, "capture": capture},
    )


class TestRunState(unittest.TestCase):
    def test_stopped_with_running_game_starts_the_app(self):
        state = compute_run_state(make_executor(), make_device_manager({"device": "windows", "connected": True}),
                                  game_name="Wuthering Waves", app_name="OK-WW")
        self.assertEqual("start", state.button)
        self.assertEqual("Start OK-WW", state.button_text)
        self.assertEqual("", state.message)

    def test_stopped_with_closed_game_starts_the_game(self):
        device = {"device": "windows", "connected": False, "full_path": "C:/game.exe"}
        state = compute_run_state(make_executor(), make_device_manager(device), game_name="Wuthering Waves",
                                  app_name="OK-WW")
        self.assertEqual("start", state.button)
        self.assertEqual("Start Wuthering Waves", state.button_text)
        self.assertEqual("", state.message)

    def test_running_pauses_the_app(self):
        executor = make_executor(paused=False, active_trigger_task_count=lambda: 1)
        state = compute_run_state(executor, make_device_manager(), app_name="OK-WW")
        self.assertEqual("Pause OK-WW", state.button_text)

    def test_starting_offers_cancel(self):
        state = compute_run_state(make_executor(), make_device_manager(), starting=True, game_name="Wuthering Waves")
        self.assertEqual("cancel", state.button)
        self.assertEqual("Launching Wuthering Waves", state.message)
        self.assertTrue(state.starting)

    def test_game_name_comes_from_config_with_a_generic_fallback(self):
        from ok import og
        from ok.ui.qt.shell.run_bar import game_display_name
        with patch.object(og, "app", None):
            self.assertEqual("Wuthering Waves", game_display_name({"game_name": "Wuthering Waves"}))
            self.assertEqual("Game", game_display_name({}))
            self.assertEqual("Game", game_display_name(None))
        app = SimpleNamespace(tr=Mock(return_value="鸣潮"))
        with patch.object(og, "app", app):
            name = game_display_name({"game_name": "Wuthering Waves"})
            app.tr.assert_called_once_with("Wuthering Waves")
            self.assertEqual("鸣潮", name)
            state = compute_run_state(make_executor(), make_device_manager({"connected": False}), game_name=name)
            self.assertEqual("Start 鸣潮", state.button_text)
            state = compute_run_state(make_executor(), make_device_manager(), starting=True, game_name=name)
            self.assertEqual("Launching 鸣潮", state.message)
            self.assertEqual("Game", game_display_name({"game_name": ""}))
            app.tr.assert_called_once()

    def test_exclusive_owner_disables_the_button(self):
        state = compute_run_state(make_executor(exclusive_owner="MCP"), make_device_manager())
        self.assertEqual("disabled", state.button)
        self.assertIn("MCP", state.message)

    def test_running_task_shows_the_task_and_queue(self):
        task = SimpleNamespace(name="Daily", enabled=True)
        queued = SimpleNamespace(name="Nest", enabled=True)
        disabled = SimpleNamespace(name="Off", enabled=False)
        executor = make_executor(paused=False, current_task=task, onetime_tasks=[task, queued, disabled],
                                 onetime_task_queue=[task, queued, disabled])
        state = compute_run_state(executor, make_device_manager())
        self.assertEqual("pause", state.button)
        self.assertIs(task, state.task)
        self.assertEqual(1, state.queued)

    def test_running_triggers_without_task(self):
        executor = make_executor(paused=False, active_trigger_task_count=lambda: 3)
        state = compute_run_state(executor, make_device_manager())
        self.assertEqual("pause", state.button)
        self.assertIsNone(state.task)
        self.assertEqual("", state.message)

    def test_disconnected_and_blocked_are_danger(self):
        state = compute_run_state(make_executor(paused=False, connected=lambda: False), make_device_manager())
        self.assertEqual("danger", state.tone)
        task = SimpleNamespace(name="Daily", enabled=True)
        executor = make_executor(paused=False, current_task=task, onetime_tasks=[task], can_capture=lambda: False)
        self.assertEqual("danger", compute_run_state(executor, make_device_manager()).tone)

    def test_trigger_task_is_not_shown_as_running_task(self):
        trigger = SimpleNamespace(name="Auto combat", enabled=True)
        executor = make_executor(paused=False, current_task=trigger, active_trigger_task_count=lambda: 1)
        self.assertIsNone(compute_run_state(executor, make_device_manager()).task)

    def test_format_elapsed(self):
        self.assertEqual("00:05", format_elapsed(5.9))
        self.assertEqual("03:42", format_elapsed(222))
        self.assertEqual("1:00:01", format_elapsed(3601))
        self.assertEqual("00:00", format_elapsed(-3))


class TestConnectionOptions(unittest.TestCase):
    def test_split_label(self):
        self.assertEqual(("WGC", "Fast, support HDR"), split_label("WGC - Fast, support HDR"))
        self.assertEqual(("PostMessage", ""), split_label("PostMessage"))

    def test_windows_capture_and_interaction_options(self):
        class WGC:
            pass

        device = {"device": "windows"}
        manager = make_device_manager(device, capture="BitBlt", interaction="PostMessage",
                                      methods={"capture_method": [WGC, "BitBlt"], "interaction": "PostMessage"})
        options, index, names = capture_options(manager, device)
        self.assertEqual(["WGC", "BitBlt"], names)
        self.assertEqual(1, index)
        self.assertEqual("WGC", options[0][0])
        self.assertTrue(options[0][1])
        options, index, names = interaction_options(manager, device)
        self.assertEqual((["PostMessage"], 0), (names, index))

    def test_device_without_methods_uses_defaults(self):
        device = {"device": "windows"}
        manager = make_device_manager(device)
        self.assertEqual([None], capture_options(manager, device)[2])
        self.assertEqual([None], interaction_options(manager, device)[2])
        self.assertEqual(["browser"], capture_options(manager, {"device": "browser"})[2])

    def test_device_details_joins_executable_lists(self):
        self.assertEqual("1920x1080 · a.exe, b.exe",
                         device_details({"resolution": "1920x1080", "exe": ["a.exe", "b.exe"]}))
        self.assertEqual("Client.exe", device_details({"exe": "Client.exe"}))

    def test_device_label(self):
        label = device_label({"device": "windows", "nick": "Wuthering Waves", "address": "Client.exe"})
        self.assertEqual("PC · Wuthering Waves · Client.exe", label)


class TestNavIcons(unittest.TestCase):
    def test_resolves_known_sources(self):
        self.assertEqual("gamepad", nav_icon(Icon.GAME))
        self.assertEqual("users", nav_icon("people"))
        self.assertEqual("tasks", nav_icon("tasks"))
        self.assertEqual(FALLBACK, nav_icon(None))
        self.assertEqual(FALLBACK, nav_icon("missing.svg"))
        # Fluent icon enums are no longer mapped; anything unknown falls back.
        self.assertEqual(FALLBACK, nav_icon(SimpleNamespace(name="STOP_WATCH")))
        icon = QIcon()
        self.assertIs(icon, nav_icon(icon))
        self.assertEqual(FALLBACK, nav_icon(Path("missing.svg")))


class TestStartControllerCancel(unittest.TestCase):
    def test_cancel_stops_waiting_for_the_game(self):
        from ok.core import start_controller as module
        controller = module.StartController.__new__(module.StartController)
        controller.exit_event = threading.Event()
        controller.start_timeout = 60
        controller.check_device_error = Mock(return_value="not ready")
        controller.cancel_start()
        events = []
        with patch.object(module.og, "device_manager", SimpleNamespace(do_refresh=Mock()), create=True), \
                module.communicate.starting_emulator.subscribed(lambda *args: events.append(args)):
            self.assertFalse(controller._wait_until_device_ready())
        controller.check_device_error.assert_not_called()
        self.assertEqual([(True, None, 0)], events)

    def test_task_is_pending_until_the_game_is_ready_and_can_be_cancelled(self):
        from ok.core import start_controller as module
        controller = module.StartController.__new__(module.StartController)
        controller.handler = SimpleNamespace(post=Mock())
        task, other = object(), object()
        controller.start(task)
        controller.start(other)
        self.assertTrue(controller.is_task_pending(task))
        self.assertTrue(controller.is_task_pending(other))

        # Cancelling the task whose launch is in progress stops waiting for the game.
        controller.__dict__['_active_task'] = task
        self.assertTrue(controller.cancel_task(task))
        self.assertFalse(controller.is_task_pending(task))
        self.assertTrue(controller._cancel_requested.is_set())
        self.assertFalse(controller.cancel_task(task))

        # A cancelled request is skipped when its queued start runs.
        controller.__dict__['_active_task'] = None
        controller._do_start = Mock()
        self.assertFalse(controller.do_start(task, from_queue=True))
        controller._do_start.assert_not_called()

        # The run bar's Cancel drops every waiting task.
        controller.cancel_start()
        self.assertFalse(controller.is_task_pending(other))


class ShellWidgetTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def tearDown(self):
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def show(self, widget):
        widget.resize(900, 600)
        theme.install(widget)
        widget.show()
        QApplication.processEvents()

        def dispose():
            widget.close()
            widget.deleteLater()

        self.addCleanup(dispose)
        return widget


class TestNavigationView(ShellWidgetTestCase):
    def test_sections_items_and_selection(self):
        nav = NavigationView()
        nav.add_section("run", "Run")
        nav.add_item("tasks", "Tasks", "tasks", "run")
        nav.add_item("about", "About", "info", bottom=True)
        self.show(nav)
        picked = []
        nav.current_changed.connect(picked.append)
        mouse_click(nav.item("about"), Qt.MouseButton.LeftButton)
        self.assertEqual(["about"], picked)
        self.assertEqual("about", nav.current_key())
        nav.set_current("tasks")
        self.assertEqual("tasks", nav.current_key())
        with self.assertRaises(ValueError):
            nav.add_item("tasks", "Again")
        nav.set_badge("about", True)
        self.assertTrue(nav.item("about").dot.isVisibleTo(nav.item("about")))
        nav.remove_item("tasks")
        self.assertFalse(nav.has_item("tasks"))


class TestNavItemIcon(ShellWidgetTestCase):
    def test_icon_stays_put_when_the_label_hides(self):
        from ok.ui.qt.kit.navigation import COMPACT_WIDTH, SIDEBAR_PADDING
        nav = NavigationView()
        nav.add_item("tasks", "Tasks", "tasks", "run")
        self.show(nav)
        item = nav.item("tasks")
        expanded_x = item.icon_label.x()
        nav.set_compact(True, animate=False)
        QApplication.processEvents()
        self.assertEqual(expanded_x, item.icon_label.x())
        rail_inner = COMPACT_WIDTH - 2 * SIDEBAR_PADDING
        self.assertAlmostEqual(rail_inner / 2, item.icon_label.x() + item.icon_label.width() / 2, delta=1)

    def _png(self, *colors):
        """A PNG of vertical stripes in ``colors`` on a transparent background."""
        from PySide6.QtGui import QImage, QPainter
        image = QImage(32, 32, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        width = 24 // len(colors)
        for index, color in enumerate(colors):
            painter.fillRect(4 + index * width, 4, width, 24, QColor(color))
        painter.end()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = Path(folder) / "icon.png"
        self.assertTrue(image.save(str(path)))
        return path

    def _center_color(self, item):
        image = item.icon_label.pixmap().toImage()
        return image.pixelColor(image.width() // 2, image.height() // 2)

    def test_single_color_artwork_takes_theme_colors(self):
        nav = NavigationView()
        nav.add_item("a", "A", nav_icon(self._png("#000000")))
        nav.add_item("b", "B", "tasks")
        self.show(nav)
        item = nav.item("a")
        self.assertEqual(theme.color("text_secondary").rgb(), self._center_color(item).rgb())
        nav.set_current("a")
        QApplication.processEvents()
        wait(400)
        self.assertEqual(theme.color("accent").rgb(), self._center_color(item).rgb())

    def test_multicolor_artwork_keeps_its_colors(self):
        nav = NavigationView()
        nav.add_item("logo", "Logo", nav_icon(self._png("#ff0000", "#00ff00", "#0000ff")))
        self.show(nav)
        item = nav.item("logo")
        unselected = item.icon_label.pixmap().toImage()
        nav.set_current("logo")
        QApplication.processEvents()
        wait(400)
        self.assertEqual(unselected, item.icon_label.pixmap().toImage())
        self.assertEqual(QColor("#00ff00").rgb(), self._center_color(item).rgb())


class TestNavigationCollapse(ShellWidgetTestCase):
    def test_collapse_animates_and_hides_text_first(self):
        from ok.ui.qt.kit.navigation import COLLAPSE_DURATION, COMPACT_WIDTH, EXPANDED_WIDTH
        nav = NavigationView()
        nav.add_section("run", "Run")
        nav.add_item("tasks", "Tasks", "tasks", "run")
        self.show(nav)
        item = nav.item("tasks")
        header = nav._sections["run"][2]
        header_height = header.height()

        nav.set_compact(True)
        self.assertFalse(item.text_label.isVisibleTo(item))
        self.assertEqual("", header.text())
        wait(COLLAPSE_DURATION // 3)
        self.assertGreater(nav.width(), COMPACT_WIDTH)
        wait(COLLAPSE_DURATION * 2)
        self.assertEqual(COMPACT_WIDTH, nav.width())
        self.assertEqual(header_height, header.height())

        nav.set_compact(False)
        self.assertFalse(item.text_label.isVisibleTo(item))
        wait(COLLAPSE_DURATION * 2)
        self.assertEqual(EXPANDED_WIDTH, nav.width())
        self.assertTrue(item.text_label.isVisibleTo(item))
        self.assertEqual("RUN", header.text())

    def test_without_animation_resizes_at_once(self):
        from ok.ui.qt.kit.navigation import COMPACT_WIDTH
        nav = NavigationView()
        self.show(nav)
        nav.set_compact(True, animate=False)
        self.assertEqual(COMPACT_WIDTH, nav.width())


class TestPopover(ShellWidgetTestCase):
    def test_opens_above_anchor_and_closes_on_outside_click(self):
        host = self.show(QWidget())
        anchor = QLabel("anchor", host)
        anchor.setGeometry(20, 540, 120, 30)
        other = QLabel("other", host)
        other.setGeometry(400, 100, 120, 30)
        anchor.show()
        other.show()
        detached = QWidget()  # built before it joins the window, like the run bar's popover
        self.addCleanup(detached.deleteLater)
        popover = Popover(detached)
        popover.setFixedWidth(300)
        content = QVBoxLayout(popover)
        text = QLabel("A long description that wraps onto several lines inside the popover. " * 4)
        text.setWordWrap(True)
        content.addWidget(text)
        popover.popup(anchor)
        QApplication.processEvents()
        self.assertTrue(popover.isVisible())
        self.assertIs(host, popover.parentWidget())
        self.assertLess(popover.geometry().bottom(), anchor.y())
        self.assertGreaterEqual(popover.height(), text.heightForWidth(300 - 18))
        closed = []
        popover.closed.connect(lambda: closed.append(True))
        mouse_click(popover, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        self.assertTrue(popover.isVisible())
        mouse_click(other, Qt.MouseButton.LeftButton)
        self.assertFalse(popover.isVisible())
        self.assertEqual([True], closed)


class TestOptionGroup(ShellWidgetTestCase):
    def test_pick_emits_index_once(self):
        group = OptionGroup()
        group.set_options([("WGC", "Fast", None), ("BitBlt", "Slow", None)], 0)
        self.show(group)
        picked = []
        group.selected.connect(picked.append)
        mouse_click(group.cards[1], Qt.MouseButton.LeftButton)
        mouse_click(group.cards[1], Qt.MouseButton.LeftButton)
        self.assertEqual([1], picked)
        self.assertEqual(1, group.current())
        group.set_options([("Only", "", None)])
        self.assertEqual(1, len(group.cards))
        self.assertEqual(0, group.current())


class TestKitWindow(ShellWidgetTestCase):
    def test_title_bar_drag_area_excludes_buttons(self):
        window = self.show(KitWindow())
        window.setWindowTitle("App")
        bar = window.title_bar
        self.assertEqual("App", bar.title_label.text())
        self.assertTrue(bar.is_drag_area(QPoint(300, 10)))
        self.assertFalse(bar.is_drag_area(bar.close_button.geometry().center()))


if __name__ == "__main__":
    unittest.main()
