import importlib
import importlib.util
import json
import os
import sys
import unittest
from types import SimpleNamespace
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HELPER_PATH = PROJECT_ROOT / "ok" / "gui" / "util" / "pyappify_startup.py"
PYAPPIFY_ENV_KEYS = [
    "PYAPPIFY_APP_VERSION",
    "PYAPPIFY_APP_STARTING_VERSION",
    "PYAPPIFY_UPDATE_NOTE",
]


def load_helper():
    spec = importlib.util.spec_from_file_location("pyappify_startup_under_test", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def simulated_pyappify_env(app_version, starting_version, notes=None):
    previous = {key: os.environ.get(key) for key in PYAPPIFY_ENV_KEYS}
    os.environ["PYAPPIFY_APP_VERSION"] = app_version
    os.environ["PYAPPIFY_APP_STARTING_VERSION"] = starting_version
    os.environ["PYAPPIFY_UPDATE_NOTE"] = json.dumps(notes or [])
    try:
        import pyappify
        yield importlib.reload(pyappify)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import pyappify
        importlib.reload(pyappify)


class TestPyappifyStartupUpdate(unittest.TestCase):
    def test_update_env_builds_update_success_dialog_text(self):
        with simulated_pyappify_env("1.0.3", "1.0.2", ["Added update notice", "Fixed startup notes"]) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertEqual("Update success 1.0.2 -> 1.0.3", version_change.title)
        self.assertEqual("Added update notice\nFixed startup notes", version_change.content)

    def test_downgrade_env_builds_downgrade_success_dialog_text(self):
        with simulated_pyappify_env("1.0.2", "1.0.3", ["Rolled back unstable release"]) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertEqual("Downgrade success 1.0.3 -> 1.0.2", version_change.title)
        self.assertEqual("Rolled back unstable release", version_change.content)

    def test_same_version_env_does_not_show_dialog(self):
        with simulated_pyappify_env("1.0.3", "1.0.3", ["No visible change"]) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertIsNone(version_change)

    def test_missing_pyappify_update_api_is_treated_as_not_updated(self):
        old_pyappify = SimpleNamespace(
            app_version="1.0.3",
            app_starting_version="1.0.2",
            get_update_notes=lambda: ["Would have been an update"],
        )

        version_change = load_helper().get_startup_version_change(old_pyappify)

        self.assertIsNone(version_change)

    def test_legacy_pyappify_reads_launcher_env_update_note(self):
        notes = ["更新ok-script版本 (ok-oldking)", "重命名agent文件夹 (ok-oldking)"]

        with simulated_pyappify_env("v3.3.60", "v3.3.56", notes) as pyappify:
            legacy_pyappify = SimpleNamespace(
                app_version=pyappify.app_version,
                is_greater_version=pyappify.is_greater_version,
            )
            version_change = load_helper().get_startup_version_change(legacy_pyappify)

        self.assertEqual("Update success v3.3.56 -> v3.3.60", version_change.title)
        self.assertEqual("\n".join(notes), version_change.content)

    def test_chinese_and_extra_long_update_notes_are_preserved(self):
        long_note = "很长的更新说明：" + "修复启动提示、关于页面跳转和更新日志展示。" * 120
        notes = [
            "新增：升级后自动打开关于页面。",
            "修复：降级后也会显示对应的更新说明。",
            long_note,
        ]

        with simulated_pyappify_env("1.0.4", "1.0.3", notes) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertEqual("Update success 1.0.3 -> 1.0.4", version_change.title)
        self.assertEqual("\n".join(notes), version_change.content)
        self.assertIn("新增：升级后自动打开关于页面。", version_change.content)
        self.assertIn(long_note, version_change.content)

    def test_beta_version_vs_release_version_follows_pyappify_api(self):
        with simulated_pyappify_env("1.0.3", "1.0.3-beta", ["Release build is available"]) as pyappify:
            self.assertFalse(pyappify.is_app_updated())
            self.assertFalse(pyappify.is_app_downgraded())
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertIsNone(version_change)

    def test_about_tab_shows_update_note_above_other_projects(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        long_note = "很长的更新说明：" + "修复启动提示、关于页面跳转和更新日志展示。" * 40
        notes = ["新增：升级后自动打开关于页面。", long_note]

        with simulated_pyappify_env("1.0.4", "1.0.3", notes):
            from PySide6.QtWidgets import QApplication
            from ok.ui.qt.about.AboutTab import AboutTab

            app = QApplication.instance() or QApplication([])
            tab = AboutTab({
                "gui_icon": ":/icon/icon.ico",
                "gui_title": "demo",
                "version": "1.0.4",
                "debug": False,
            })

        widgets = [
            item.widget()
            for i in range(tab.vBoxLayout.count())
            if (item := tab.vBoxLayout.itemAt(i)) and item.widget()
        ]
        titled_widgets = [
            widget
            for widget in widgets
            if hasattr(widget, "titleLabel")
        ]
        titles = [widget.titleLabel.text() for widget in titled_widgets]
        update_index = titles.index("Update success 1.0.3 -> 1.0.4")
        projects_index = titles.index("Other Projects")

        self.assertLess(update_index, projects_index)
        self.assertEqual("\n".join(notes), titled_widgets[update_index].widget.text())
        app.processEvents()

    def test_version_card_does_not_show_legacy_update_button(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.VersionCard import VersionCard

        app = QApplication.instance() or QApplication([])
        card = VersionCard(
            {},
            ":/icon/icon.ico",
            "demo",
            "1.0.4",
            False,
        )

        self.assertFalse(hasattr(card, "check_update_button"))
        card.deleteLater()
        app.processEvents()

    def test_version_card_hides_update_button_without_pyappify_app_version(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.VersionCard import VersionCard

        app = QApplication.instance() or QApplication([])
        card = VersionCard(
            {},
            ":/icon/icon.ico",
            "demo",
            "1.0.4",
            False,
        )

        self.assertFalse(hasattr(card, "check_update_button"))
        card.deleteLater()
        app.processEvents()

    def test_about_tab_places_update_card_directly_below_version_card(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.AboutTab import AboutTab

        app = QApplication.instance() or QApplication([])
        module = SimpleNamespace(
            app_version="v1.1.0",
            get_version_list=Mock(return_value=[]),
            update_to_version=Mock(),
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
        )
        tab = AboutTab({
            "gui_icon": ":/icon/icon.ico",
            "gui_title": "demo",
            "version": "v1.1.0",
            "debug": False,
            "about": "Test disclaimer",
        }, pyappify_module=module)

        self.assertIs(tab.vBoxLayout.itemAt(0).widget(), tab.version_card)
        self.assertIs(tab.vBoxLayout.itemAt(1).widget().widget, tab.update_card)
        self.assertEqual("Check for updates", tab.update_card.check_button.text())
        self.assertEqual("Click to check for updates", tab.update_card.status_label.text())
        self.assertTrue(tab.update_card.version_label.isHidden())
        self.assertTrue(tab.update_card.version_combo.isHidden())
        self.assertTrue(tab.update_card.notes_edit.isHidden())
        titled_widgets = [
            item.widget() for index in range(tab.vBoxLayout.count())
            if (item := tab.vBoxLayout.itemAt(index)) and item.widget()
            and hasattr(item.widget(), "titleLabel")
        ]
        titles = [widget.titleLabel.text() for widget in titled_widgets]
        self.assertLess(titles.index("Disclaimer"), titles.index("Other Projects"))
        disclaimer = titled_widgets[titles.index("Disclaimer")]
        projects = titled_widgets[titles.index("Other Projects")]
        self.assertEqual(disclaimer.titleLabel.font().pointSizeF(), projects.titleLabel.font().pointSizeF())
        tab.deleteLater()
        app.processEvents()

    def test_project_cards_constrain_long_urls_and_match_link_button_spacing(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.ProjectCard import ProjectCard

        app = QApplication.instance() or QApplication([])
        url = "https://github.com/example/a-very-long-project-name-that-must-not-expand-the-about-window"
        card = ProjectCard("Example", url, "https://example.com")
        app.processEvents()

        self.assertEqual(6, card.hBoxLayout.spacing())
        self.assertEqual(11, card.hBoxLayout.itemAt(card.hBoxLayout.count() - 1).spacerItem().sizeHint().width())
        self.assertLessEqual(card.sizeHint().width(), 520)
        self.assertEqual(url, card.contentLabel.toolTip())
        card.deleteLater()
        app.processEvents()

    def test_update_download_button_is_primary_and_precedes_test_version_control(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from qfluentwidgets import PrimaryPushButton
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        card = UpdateCard("v1.0.0", SimpleNamespace(), download_url="https://example.com/download")
        widgets = [
            card.controls_layout.itemAt(index).widget()
            for index in range(card.controls_layout.count())
            if card.controls_layout.itemAt(index).widget() is not None
        ]

        self.assertIsInstance(card.download_button, PrimaryPushButton)
        self.assertLess(widgets.index(card.download_button), widgets.index(card.test_version_checkbox))
        card.deleteLater()
        app.processEvents()

    def test_update_card_calculates_upgrade_and_downgrade_notes(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QSizePolicy
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        calculate_notes = Mock(side_effect=self._calculate_update_notes)
        module = SimpleNamespace(
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
            calculate_update_notes=calculate_notes,
        )
        card = UpdateCard("v1.1.0", module)
        availability = []
        card.update_available_changed.connect(availability.append)
        card._apply_versions((True, [
            {"version": "v1.3.0", "previous_version": "v1.2.0", "update_note": ["three"]},
            {"version": "v1.2.0", "previous_version": "v1.1.0", "update_note": ["two"]},
            {"version": "v1.1.0", "previous_version": "v1.0.0", "update_note": ["one"]},
            {"version": "v1.0.0", "previous_version": "v0.9.0", "update_note": ["zero"]},
        ]))

        self.assertEqual("v1.3.0", card.version_combo.currentText())
        self.assertEqual([True], availability)
        self.assertEqual("", card.status_label.text())
        self.assertEqual(Qt.TextInteractionFlag.NoTextInteraction, card.notes_edit.textInteractionFlags())
        self.assertEqual(QSizePolicy.Policy.Minimum, card.notes_edit.sizePolicy().verticalPolicy())
        self.assertTrue(card.notes_edit.hasHeightForWidth())
        self.assertEqual(
            "• three\n• two\n• one",
            card.notes_edit.toPlainText(),
        )
        self.assertFalse(card.notes_edit.isHidden())
        calculate_notes.assert_called_with(card.versions, "v1.1.0", "v1.3.0")
        card.version_combo.setCurrentIndex(3)
        self.assertEqual("Downgrade", card.update_button.text())
        self.assertEqual("• one\n• zero", card.notes_edit.toPlainText())
        self.assertGreaterEqual(card.version_combo.width(), card.VERSION_COMBO_MIN_WIDTH)
        self.assertLessEqual(card.version_combo.width(), card.VERSION_COMBO_MAX_WIDTH)
        self.assertEqual("Check Test Version", card.test_version_checkbox.text())
        self.assertFalse(card.test_version_checkbox.isChecked())
        self.assertIs(card.status_label, card.controls_layout.itemAt(2).widget())
        self.assertIsNone(card.controls_layout.itemAt(3).widget())
        card.deleteLater()
        app.processEvents()

    def test_missing_current_version_excludes_logs_above_selected_version(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        module = SimpleNamespace(
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
            calculate_update_notes=self._calculate_update_notes,
        )
        card = UpdateCard("v1.0.0", module)
        card._apply_versions((True, [
            {"version": "v3.0.0", "update_note": ["three"]},
            {"version": "v2.0.0", "update_note": ["two"]},
            {"version": "v1.5.0", "update_note": ["one point five"]},
        ]))

        card.version_combo.setCurrentIndex(1)
        self.assertEqual("v2.0.0", card.version_combo.currentText())
        self.assertEqual("• two\n• one point five", card.notes_edit.toPlainText())
        card.deleteLater()
        app.processEvents()

    def test_check_test_version_controls_release_filter(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import threading
        import time
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        module = SimpleNamespace(
            get_version_list=Mock(return_value=[]),
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
        )
        exit_event = threading.Event()
        card = UpdateCard("v1.0.0", module, exit_event=exit_event)

        for checked, expected_release_only in ((False, True), (True, False)):
            card.test_version_checkbox.setChecked(checked)
            card.check_for_updates()
            for _ in range(100):
                app.processEvents()
                if not card._busy:
                    break
                time.sleep(0.01)
            self.assertFalse(card._busy)
            self.assertEqual(expected_release_only, module.get_version_list.call_args.kwargs["release_only"])
            self.assertIs(exit_event, module.get_version_list.call_args.kwargs["exit_event"])

        card.deleteLater()
        app.processEvents()

    def test_check_button_disables_and_duplicate_request_is_ignored(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import threading
        import time
        from PySide6.QtCore import QAbstractAnimation
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        release_request = threading.Event()
        request_started = threading.Event()
        def wait_for_versions(**_kwargs):
            request_started.set()
            release_request.wait(1)
            return []
        get_versions = Mock(side_effect=wait_for_versions)
        module = SimpleNamespace(
            get_version_list=get_versions,
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
        )
        card = UpdateCard("v1.0.0", module)

        card.check_for_updates()
        self.assertFalse(card.check_button.isEnabled())
        self.assertFalse(card.check_button.icon().isNull())
        self.assertTrue(card.check_button.property("hasIcon"))
        self.assertFalse(card.check_progress.isHidden())
        self.assertEqual(QAbstractAnimation.State.Running, card.check_progress.aniGroup.state())
        self.assertTrue(request_started.wait(1))
        card.check_for_updates()
        self.assertEqual(1, get_versions.call_count)

        release_request.set()
        for _ in range(100):
            app.processEvents()
            if not card._busy:
                break
            time.sleep(0.01)
        self.assertTrue(card.check_button.isEnabled())
        self.assertTrue(card.check_progress.isHidden())
        self.assertEqual(QAbstractAnimation.State.Stopped, card.check_progress.aniGroup.state())
        self.assertEqual(1, get_versions.call_count)
        card.deleteLater()
        app.processEvents()

    def test_update_to_version_receives_exit_event(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import threading
        import time
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        exit_event = threading.Event()
        update_to_version = Mock(return_value={"updated": True, "version": "v1.1.0"})
        module = SimpleNamespace(
            update_to_version=update_to_version,
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
            calculate_update_notes=self._calculate_update_notes,
        )
        card = UpdateCard("v1.0.0", module, exit_event=exit_event)
        card._apply_versions((True, [{"version": "v1.1.0", "update_note": ["one"]}]))

        card.update_to_selected_version()
        for _ in range(100):
            app.processEvents()
            if not card._busy:
                break
            time.sleep(0.01)

        self.assertFalse(card._busy)
        update_to_version.assert_called_once_with("v1.1.0", exit_event=exit_event)
        card.deleteLater()
        app.processEvents()

    def test_failed_request_shows_visible_error(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import time
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        module = SimpleNamespace(
            get_version_list=Mock(side_effect=RuntimeError("launcher unavailable")),
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
        )
        card = UpdateCard("v1.0.0", module)
        card.check_for_updates()
        for _ in range(100):
            app.processEvents()
            if not card._busy:
                break
            time.sleep(0.01)

        self.assertEqual("", card.notes_edit.text())
        self.assertTrue(card.notes_edit.isHidden())
        self.assertIn("Failed to check for updates: launcher unavailable", card.status_label.text())
        self.assertIn("#d13438", card.status_label.styleSheet())
        self.assertTrue(card.version_label.isHidden())
        self.assertTrue(card.version_combo.isHidden())
        card.deleteLater()
        app.processEvents()

    def test_long_failed_request_error_wraps_without_widening_status_label(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        card = UpdateCard("v1.0.0", SimpleNamespace())
        message = "Failed to check for updates: " + ("launcher executable path is invalid; " * 20)
        card._set_status(message, error=True)
        app.processEvents()

        self.assertTrue(card.status_label.wordWrap())
        self.assertLessEqual(card.status_label.minimumSizeHint().width(), 400)
        self.assertEqual(message, card.status_label.toolTip())
        card.deleteLater()
        app.processEvents()

    def test_update_card_logs_pyappify_call_and_result(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import time
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        versions = [{"version": "v1.2.0", "update_note": ["two"]}]
        module = SimpleNamespace(
            get_version_list=Mock(return_value=versions),
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
            calculate_update_notes=self._calculate_update_notes,
        )
        card = UpdateCard("v1.1.0", module)

        with patch("ok.ui.qt.about.UpdateCard.logger") as update_logger:
            card._run_in_background(
                module.get_version_list,
                card._versions_loaded,
                "pyappify.get_version_list",
            )
            for _ in range(100):
                app.processEvents()
                if card.version_combo.count():
                    break
                time.sleep(0.01)

        self.assertEqual(1, card.version_combo.count())
        update_logger.info.assert_any_call("calling pyappify.get_version_list")
        update_logger.info.assert_any_call(f"pyappify.get_version_list result={versions!r}")
        card.deleteLater()
        app.processEvents()

    def test_update_card_treats_dev_as_old_version_in_test_mode(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.about.UpdateCard import UpdateCard

        app = QApplication.instance() or QApplication([])
        module = SimpleNamespace(
            is_greater_version=lambda left, right: self._version_tuple(left) > self._version_tuple(right),
            calculate_update_notes=self._calculate_update_notes,
        )
        with patch.dict(os.environ, {"PYAPPIFY_PYTHON_TEST": ""}):
            card = UpdateCard("dev", module)

        self.assertEqual("v0.0.0", card.current_version)
        card._apply_versions((True, [{
            "version": "v100.1.1",
            "previous_version": "v100.1.0",
            "update_note": ["test update"],
        }]))
        self.assertTrue(card.update_button.isEnabled())
        self.assertEqual("Update", card.update_button.text())
        card.deleteLater()
        app.processEvents()

    @staticmethod
    def _version_tuple(version):
        return tuple(int(part) for part in version.lstrip("v").split("."))

    @staticmethod
    def _calculate_update_notes(update_notes, current_version, target_version):
        normalize = lambda version: str(version).lstrip("v")
        current_index = next(
            (index for index, item in enumerate(update_notes)
             if normalize(item["version"]) == normalize(current_version)),
            None,
        )
        target_index = next(
            (index for index, item in enumerate(update_notes)
             if normalize(item["version"]) == normalize(target_version)),
            None,
        )
        if target_index is None:
            return []
        selected = update_notes[target_index:] if current_index is None else update_notes[
            min(current_index, target_index):max(current_index, target_index) + 1
        ]
        return [note for item in selected for note in item.get("update_note", [])]


if __name__ == "__main__":
    unittest.main()
