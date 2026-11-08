import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt, QTimer
from qt_helpers import mouse_click
from PySide6.QtWidgets import QApplication, QCheckBox

from ok import og
from ok.ui.qt.kit import Dialog
from ok.ui.qt.tasks import tasks_page as page_module
from ok.ui.qt.tasks.config_editors import (DropDownEditor, ListEditor, LineEditEditor, MultiSelectionEditor,
                                           NumberEditor, SwitchEditor, TextEditEditor, config_editor)
from ok.ui.qt.tasks.config_form import ConfigForm
from ok.ui.qt.tasks.tasks_page import (KIND_ALL, KIND_ONETIME, KIND_TRIGGER, TasksPage, matches_filter, monogram,
                                       task_groups, task_status, visible_tasks)
from ok.util.config import Config


class FakeConfig(dict):
    def __init__(self, default):
        super().__init__(default)
        self.default = dict(default)

    def get_default(self, key):
        return self.default.get(key)

    def has_user_config(self):
        return not all(key.startswith("_") for key in self)

    def reset_to_default(self):
        self.clear()
        self.update(self.default)


class FakeTask:
    def __init__(self, name, group=None, enabled=False, config=None, config_type=None, visible=True,
                 description="", first_run_alert=None):
        self.name = name
        self.description = description or f"{name} description"
        self.icon = None
        self.group_name = group
        self.group_icon = None
        self.visible = visible
        self.enabled = enabled
        self.paused = False
        self.running = False
        self.info = {}
        self.start_time = 0
        default = config if config is not None else {}
        self.config = FakeConfig(default)
        self.default_config = default
        self.config_description = {}
        self.config_type = config_type or {}
        self.first_run_alert = first_run_alert
        self.instructions = None
        self.is_custom = False
        self.show_create_shortcut = False
        self.enable_calls = 0

    def enable(self):
        self.enable_calls += 1
        self.enabled = True

    def disable(self):
        self.enabled = False

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    def __repr__(self):
        return f"FakeTask({self.name})"


class QtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._og = {name: getattr(og, name, None) for name in ("app", "executor", "task_manager")}
        og.app = SimpleNamespace(tr=lambda text: text, start_controller=Mock())
        og.executor = SimpleNamespace(onetime_tasks=[], trigger_tasks=[], waiting_for_task=lambda task: None)
        og.task_manager = SimpleNamespace(imported_scripts={})
        # Page state (the remembered filter tab) goes to a throwaway folder.
        self.config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.config_dir.cleanup)
        folder = patch.object(Config, "config_folder", self.config_dir.name)
        folder.start()
        self.addCleanup(folder.stop)

    def tearDown(self):
        for name, value in self._og.items():
            setattr(og, name, value)
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def show(self, widget, width=1100, height=760):
        widget.resize(width, height)
        widget.show()
        QApplication.processEvents()

        def dispose():
            if hasattr(widget, "dispose"):
                widget.dispose()
            widget.close()
            widget.deleteLater()

        self.addCleanup(dispose)
        return widget


class TestHelpers(unittest.TestCase):
    def test_visible_tasks_skip_hidden_and_imported_groups(self):
        shown = FakeTask("Shown")
        hidden = FakeTask("Hidden", visible=False)
        imported = FakeTask("Plugin", group="Plugin Script")
        grouped = FakeTask("Grouped", group="Daily")
        trigger = FakeTask("Combat")
        executor = SimpleNamespace(onetime_tasks=[shown, hidden, imported, grouped], trigger_tasks=[trigger])
        manager = SimpleNamespace(imported_scripts={"plugin": {"script_name": "Plugin Script"}})
        self.assertEqual(([shown, grouped], [trigger]), visible_tasks(executor, manager))

    def test_groups_and_filters(self):
        daily = FakeTask("A", group="Daily")
        farming = FakeTask("B", group="Farming")
        plain = FakeTask("C")
        self.assertEqual(["Daily", "Farming"], list(task_groups([daily, plain, farming, daily])))
        self.assertTrue(matches_filter(plain, KIND_ALL, False))
        self.assertTrue(matches_filter(plain, KIND_ONETIME, False))
        self.assertFalse(matches_filter(plain, KIND_TRIGGER, False))
        self.assertTrue(matches_filter(daily, "group:Daily", False))
        self.assertFalse(matches_filter(plain, "group:Daily", False))

    def test_leading_emoji_is_split_off_the_name(self):
        from ok.ui.qt.tasks.tasks_page import split_leading_symbol
        self.assertEqual(("📅", "Daily Task"), split_leading_symbol("📅 Daily Task"))
        self.assertEqual((None, "Daily Task"), split_leading_symbol("Daily Task"))
        self.assertEqual((None, "3124"), split_leading_symbol("3124"))
        self.assertEqual((None, "C3 PO"), split_leading_symbol("C3 PO"))

    def test_monogram(self):
        self.assertEqual("DT", monogram("Daily Task"))
        self.assertEqual("NE", monogram("Nest"))
        self.assertEqual("自", monogram("自动周常乐园"))

    def test_status(self):
        executor = SimpleNamespace(waiting_for_task=lambda task: None)
        task = FakeTask("A")
        self.assertIsNone(task_status(task, executor))
        task.enabled = True
        self.assertEqual("Queued", task_status(task, executor)[0])
        task.running = True
        self.assertEqual(("Running", "success"), task_status(task, executor)[:2])
        task.paused = True
        self.assertEqual("Paused", task_status(task, executor)[0])
        other = FakeTask("Other")
        task.running = task.paused = False
        waiting = SimpleNamespace(waiting_for_task=lambda t: other)
        self.assertIn("Other", task_status(task, waiting)[2])

    def test_task_waiting_for_game_launch_is_queued_and_stoppable(self):
        task = FakeTask("A")
        controller = Mock()
        controller.is_task_pending = lambda t: t is task
        executor = SimpleNamespace(waiting_for_task=lambda t: None)
        with patch.object(og, "app", SimpleNamespace(tr=lambda text: text, start_controller=controller)), \
                patch.object(og, "config", {"game_name": "Game X"}, create=True):
            status = task_status(task, executor)
            self.assertEqual(("Queued", "accent"), status[:2])
            self.assertIn("Game X", status[2])
            self.assertTrue(page_module.task_active(task))
            self.assertIsNone(task_status(FakeTask("B"), executor))
            page_module.stop_task(task)
        controller.cancel_task.assert_called_once_with(task)


class TestConfigForm(QtTestCase):
    def test_editor_types(self):
        config = FakeConfig({"Flag": True, "Count": 3, "Ratio": 0.5, "Name": "abc", "Long": "x" * 30,
                             "Pick": "B", "Many": ["A"], "Items": ["one"]})
        config_type = {"Pick": {"type": "drop_down", "options": ["A", "B"]},
                       "Many": {"type": "multi_selection", "options": ["A", "B"]}}
        expected = {"Flag": SwitchEditor, "Count": NumberEditor, "Ratio": NumberEditor, "Name": LineEditEditor,
                    "Long": TextEditEditor, "Pick": DropDownEditor, "Many": MultiSelectionEditor, "Items": ListEditor}
        for key, cls in expected.items():
            editor = config_editor(config_type, {}, config, key, config[key], None)
            self.assertIsInstance(editor, cls, key)
            editor.deleteLater()

    def test_editors_write_back_and_reload(self):
        config = FakeConfig({"Flag": False, "Count": 3, "Pick": "A"})
        flag = config_editor({}, {}, config, "Flag", False, None)
        flag.switch_button.click()
        self.assertTrue(config["Flag"])
        count = config_editor({}, {}, config, "Count", 3, None)
        count.spin_box.plus_button.click()
        self.assertEqual(4, config["Count"])
        pick = config_editor({"Pick": {"type": "drop_down", "options": ["A", "B"]}}, {}, config, "Pick", "A", None)
        pick.combo_box.setCurrentIndex(1)
        self.assertEqual("B", config["Pick"])
        config["Pick"] = "A"
        pick.update_value()
        self.assertEqual(0, pick.combo_box.currentIndex())
        for editor in (flag, count, pick):
            editor.deleteLater()

    def test_sub_configs_follow_the_controlling_value(self):
        default = {"Target": "Tacet", "Tacet Index": 7, "Nest": False}
        config_type = {"Target": {"type": "drop_down", "options": ["Tacet", "Forgery"],
                                  "sub_configs": {"Tacet": ["Tacet Index"]}}}
        task = FakeTask("Daily", config=default, config_type=config_type)
        form = self.show(ConfigForm(task, task.config, task.default_config, {}, config_type), 700, 500)
        index_row = form.config_widget_by_key["Tacet Index"]
        self.assertFalse(index_row.isHidden())
        form.config_widget_by_key["Target"].combo_box.setCurrentIndex(1)
        QApplication.processEvents()
        self.assertTrue(index_row.isHidden())
        self.assertEqual("Forgery", task.config["Target"])
        rows = [form.viewLayout.itemAt(i).widget() for i in range(form.viewLayout.count())]
        visible = [row for row in rows if not row.isHidden()]
        self.assertTrue(visible[0].property("first"))
        self.assertFalse(visible[1].property("first"))

    def test_multi_selection_controls_sub_configs(self):
        default = {"Features": ["A"], "A Setting": True, "B Setting": True}
        config_type = {"Features": {"type": "multi_selection", "options": ["A", "B"],
                                    "sub_configs": {"A": ["A Setting"], "B": ["B Setting"]}}}
        task = FakeTask("T", config=default, config_type=config_type)
        form = self.show(ConfigForm(task, task.config, task.default_config, {}, config_type), 700, 500)
        self.assertTrue(form.config_widget_by_key["B Setting"].isHidden())
        boxes = form.config_widget_by_key["Features"].check_boxes
        boxes[1].click()
        QApplication.processEvents()
        self.assertEqual(["A", "B"], task.config["Features"])
        self.assertFalse(form.config_widget_by_key["B Setting"].isHidden())
        self.assertIsInstance(boxes[0], QCheckBox)

    def test_empty_config_shows_a_note(self):
        task = FakeTask("Empty", config={})
        form = self.show(ConfigForm(task, task.config, {}, {}, {}), 500, 200)
        self.assertTrue(form.is_empty)
        self.assertTrue(form.empty_label.isVisibleTo(form))

    def test_only_hidden_keys_counts_as_empty(self):
        default = {"_private": 1, "Hidden": True}
        task = FakeTask("Hidden", config=default, config_type={"Hidden": {"hidden": True}})
        form = self.show(ConfigForm(task, task.config, default, {}, task.config_type), 500, 200)
        self.assertTrue(form.is_empty)
        self.assertTrue(form.card.isHidden())


class TestTaskRow(QtTestCase):
    def test_title_without_description_is_centered_with_icon_and_switch(self):
        task = FakeTask("Skip Dialog")
        task.description = ""
        row = self.show(page_module.TaskRow(task, is_trigger=True), 372, 58)
        self.assertTrue(row.description_label.isHidden())
        title_center = row.name_label.mapTo(row, row.name_label.rect().center()).y()
        for widget in (row.tile, row.switch):
            center = widget.mapTo(row, widget.rect().center()).y()
            self.assertLessEqual(abs(title_center - center), 1)

    def test_description_remains_visible_below_title(self):
        row = self.show(page_module.TaskRow(FakeTask("Auto Login"), is_trigger=True), 372, 58)
        self.assertTrue(row.description_label.isVisible())
        self.assertLess(row.name_label.geometry().bottom(), row.description_label.geometry().top())


class TestTasksPage(QtTestCase):
    def make_page(self, onetime, triggers=()):
        og.executor.onetime_tasks = list(onetime)
        og.executor.trigger_tasks = list(triggers)
        return self.show(TasksPage())

    def test_lists_tasks_and_selects_the_first(self):
        daily, nest = FakeTask("Daily", config={"Flag": True}), FakeTask("Nest")
        combat = FakeTask("Combat")
        page = self.make_page([daily, nest], [combat])
        self.assertEqual([daily, nest], [row.task for row in page.onetime_section.rows])
        self.assertEqual([combat], [row.task for row in page.trigger_section.rows])
        self.assertIs(daily, page.selected_task)
        self.assertTrue(page.rows[daily].property("selected"))
        self.assertEqual("Daily", page.detail.title_label.text())
        self.assertIn("Flag", page.detail.form.config_widget_by_key)

    def test_clicking_a_row_opens_it(self):
        daily, nest = FakeTask("Daily"), FakeTask("Nest")
        page = self.make_page([daily, nest])
        mouse_click(page.rows[nest], Qt.MouseButton.LeftButton)
        self.assertIs(nest, page.selected_task)
        self.assertFalse(page.rows[daily].property("selected"))
        self.assertEqual("Nest", page.detail.title_label.text())

    def test_row_button_runs_and_stops_in_one_click(self):
        daily, nest = FakeTask("Daily"), FakeTask("Nest")
        page = self.make_page([daily, nest])
        page.rows[nest].action_button.click()
        og.app.start_controller.start.assert_called_once_with(nest)
        self.assertIs(daily, page.selected_task)
        nest.enabled = True
        page.rows[nest].refresh()
        self.assertEqual("Queued", page.rows[nest].status_pill.text())
        page.rows[nest].action_button.click()
        self.assertFalse(nest.enabled)

    def test_first_run_alert_is_confirmed_once(self):
        task = FakeTask("Daily", first_run_alert="Careful")
        page = self.make_page([task])

        def accept():
            dialog = next(w for w in page.window().findChildren(Dialog) if w.isVisible())
            dialog.ok_button.click()

        QTimer.singleShot(0, accept)
        page.rows[task].action_button.click()
        og.app.start_controller.start.assert_called_once_with(task)
        self.assertEqual("Careful", task.config["_first_run_alert"])
        page.rows[task].action_button.click()
        self.assertEqual(2, og.app.start_controller.start.call_count)

    def test_trigger_switch_enables_and_disables(self):
        combat = FakeTask("Combat")
        page = self.make_page([FakeTask("Daily")], [combat])
        page.rows[combat].switch.click()
        deadline = time.time() + 2
        while combat.enable_calls == 0 and time.time() < deadline:
            QApplication.processEvents()
        self.assertTrue(combat.enabled)
        page.rows[combat].switch.click()
        self.assertFalse(combat.enabled)

    def test_detail_actions_follow_task_state(self):
        task = FakeTask("Daily", config={"Flag": True})
        page = self.make_page([task])
        detail = page.detail
        self.assertTrue(detail.run_button.isVisibleTo(detail))
        self.assertFalse(detail.stop_button.isVisibleTo(detail))
        task.enabled = task.running = True
        task.start_time = time.time() - 65
        detail.refresh()
        self.assertFalse(detail.run_button.isVisibleTo(detail))
        self.assertTrue(detail.pause_button.isVisibleTo(detail))
        self.assertIn("01:05", detail.status_label.text())
        task.paused = True
        detail.refresh()
        self.assertEqual("Resume", detail.run_button.text())

    def test_reset_restores_defaults_in_the_form(self):
        task = FakeTask("Daily", config={"Flag": True})
        page = self.make_page([task])
        editor = page.detail.form.config_widget_by_key["Flag"]
        editor.switch_button.click()
        self.assertFalse(task.config["Flag"])
        page.detail.reset_button.click()
        self.assertTrue(task.config["Flag"])
        self.assertTrue(editor.switch_button.isChecked())

    def test_running_task_opens_on_info(self):
        idle, running = FakeTask("Idle", config={"Flag": True}), FakeTask("Running", config={"Flag": True})
        running.enabled = running.running = True
        page = self.make_page([idle, running])
        self.assertEqual("settings", page.detail.tabs.current_key())
        page.select_task(running)
        self.assertEqual("info", page.detail.tabs.current_key())
        self.assertIs(page.detail.info_table, page.detail.pages.currentWidget())
        self.assertFalse(page.detail.reset_button.isVisibleTo(page.detail))
        page.select_task(idle)
        self.assertEqual("settings", page.detail.tabs.current_key())
        self.assertTrue(page.detail.reset_button.isVisibleTo(page.detail))

    def test_selected_task_switches_to_info_when_it_starts(self):
        task = FakeTask("Daily", config={"Flag": True})
        page = self.make_page([task])
        self.assertEqual("settings", page.detail.tabs.current_key())
        task.enabled = task.running = True
        page.detail.refresh()
        self.assertEqual("info", page.detail.tabs.current_key())
        page.detail.tabs.set_current("settings")
        page.detail.refresh()
        self.assertEqual("settings", page.detail.tabs.current_key())

    def test_info_tab_appears_with_task_info(self):
        task = FakeTask("Daily")
        page = self.make_page([task])
        self.assertFalse(page.detail.tabs.item("info").isVisibleTo(page.detail))
        task.info = {"Runs": 3}
        page.detail.refresh()
        self.assertTrue(page.detail.tabs.item("info").isVisibleTo(page.detail))
        page.detail.tabs.set_current("info")
        self.assertEqual("3", page.detail.info_table.item(0, 1).text())

    def test_filter_tabs_follow_kinds_and_groups(self):
        daily = FakeTask("Daily", group="Daily")
        farm = FakeTask("Farm", group="Farming")
        combat = FakeTask("Combat")
        page = self.make_page([daily, farm], [combat])
        self.assertEqual(["all", "onetime", "trigger", "group:Daily", "group:Farming"], page.filter_tabs.keys())
        page.set_filter("group:Farming")
        QApplication.processEvents()
        self.assertTrue(page.rows[daily].isHidden())
        self.assertFalse(page.rows[farm].isHidden())
        self.assertTrue(page.trigger_section.isHidden())
        self.assertIs(farm, page.selected_task)
        page.set_filter(KIND_TRIGGER)
        self.assertTrue(page.onetime_section.isHidden())
        self.assertIs(combat, page.selected_task)

    def test_single_kind_without_groups_hides_the_tabs(self):
        page = self.make_page([FakeTask("Daily"), FakeTask("Nest")])
        self.assertTrue(page.filter_tabs.isHidden())
        self.assertTrue(page.trigger_section.isHidden())

    def test_collapsing_a_section_hides_its_rows(self):
        page = self.make_page([FakeTask("Daily")], [FakeTask("Combat")])
        page.onetime_section.header.click()
        self.assertFalse(page.onetime_section.is_expanded())
        self.assertTrue(page.onetime_section.scroll.isHidden())

    def test_collapsed_sections_stay_at_the_top(self):
        page = self.make_page([FakeTask("Daily")], [FakeTask("Combat")])
        page.onetime_section.header.click()
        page.trigger_section.header.click()
        QApplication.processEvents()
        self.assertEqual(0, page.onetime_section.y())
        self.assertLess(page.trigger_section.geometry().bottom(), 200)

    def test_sections_collapse_only_in_the_all_view(self):
        daily = FakeTask("Daily", group="Daily")
        page = self.make_page([daily, FakeTask("Nest")], [FakeTask("Combat")])
        page.onetime_section.header.click()
        page.set_filter(KIND_ONETIME)
        QApplication.processEvents()
        self.assertTrue(page.onetime_section.is_expanded())
        self.assertFalse(page.onetime_section.scroll.isHidden())
        self.assertTrue(page.onetime_section.chevron.isHidden())
        page.onetime_section.header.click()
        self.assertTrue(page.onetime_section.is_expanded())
        page.set_filter(KIND_ALL)
        self.assertFalse(page.onetime_section.is_expanded())

    def test_switching_to_triggers_does_not_scroll_the_list(self):
        daily = FakeTask("Daily", group="Daily")
        triggers = [FakeTask(f"Trigger {index}") for index in range(6)]
        page = self.make_page([daily], triggers)
        page.set_filter("group:Daily")
        QApplication.processEvents()
        scroll_bar = page.trigger_section.scroll.verticalScrollBar()
        values = []
        scroll_bar.valueChanged.connect(values.append)
        page.set_filter(KIND_TRIGGER)
        QApplication.processEvents()
        self.assertIs(triggers[0], page.selected_task)
        self.assertEqual([], values)
        self.assertEqual(0, scroll_bar.value())

    def test_single_category_section_shows_the_category(self):
        daily = FakeTask("Daily", group="Daily Activities")
        page = self.make_page([daily], [FakeTask("Combat")])
        page.set_filter("group:Daily Activities")
        self.assertEqual("Daily Activities", page.onetime_section.title_label.text())
        page.set_filter(KIND_ALL)
        self.assertEqual("On-demand", page.onetime_section.title_label.text())

    def test_last_filter_is_restored(self):
        tasks = [FakeTask("Daily", group="Daily")], [FakeTask("Combat")]
        page = self.make_page(*tasks)
        page.set_filter("group:Daily")
        reopened = self.make_page(*tasks)
        self.assertEqual("group:Daily", reopened.current_filter())
        self.assertTrue(reopened.trigger_section.isHidden())

    def test_task_list_updates_rebuild_the_page(self):
        daily = FakeTask("Daily")
        page = self.make_page([daily])
        added = FakeTask("Added")
        og.executor.onetime_tasks.append(added)
        page.refresh_tasks()
        self.assertIn(added, page.rows)
        self.assertIs(daily, page.selected_task)


if __name__ == "__main__":
    unittest.main()


class TestImportedTaskTab(QtTestCase):
    def test_lists_only_its_plugins_tasks_under_the_plugin_name(self):
        from ok.ui.qt.plugins.imported_tabs import ImportedTaskTab
        built_in = FakeTask("Built In")
        mine, hidden = FakeTask("Farm"), FakeTask("Hidden", visible=False)
        og.executor.onetime_tasks = [built_in]
        og.task_manager.imported_scripts = {"demo": {"tasks": [mine, hidden], "script_name": "Demo"}}
        tab = self.show(ImportedTaskTab("demo", "Demo"))
        self.assertEqual("Demo", tab.title_label.text())
        self.assertEqual(([mine], []), (tab.onetime_tasks, tab.trigger_tasks))
        self.assertTrue(tab.has_task(mine))
        self.assertFalse(tab.has_task(built_in))
        self.assertIs(mine, tab.detail.task)
        self.assertTrue(tab.in_current_list(mine))
        self.assertFalse(tab.in_current_list(built_in))
