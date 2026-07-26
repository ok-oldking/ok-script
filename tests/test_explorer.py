from pathlib import Path
from unittest.mock import patch

from ok.util import explorer


def test_open_explorer_folder_explores_exact_onedrive_directory(tmp_path):
    screenshots = (
        tmp_path / "Users" / "ok" / "OneDrive" / "Documents" / "screenshots"
    )

    with (
        patch.object(explorer.sys, "platform", "win32"),
        patch.object(explorer, "_focus_existing_explorer_window", return_value=False),
        patch.object(explorer.os, "startfile", create=True) as startfile,
    ):
        assert explorer.open_explorer_folder(screenshots)

    assert screenshots.is_dir()
    startfile.assert_called_once_with(str(screenshots.resolve()), "explore")


def test_open_explorer_folder_only_focuses_existing_window(tmp_path):
    screenshots = Path(tmp_path, "screenshots")

    with (
        patch.object(explorer.sys, "platform", "win32"),
        patch.object(explorer, "_focus_existing_explorer_window", return_value=True),
        patch.object(explorer.os, "startfile", create=True) as startfile,
    ):
        assert explorer.open_explorer_folder(screenshots)

    startfile.assert_not_called()


def test_reveal_in_explorer_uses_native_shell_selection(tmp_path):
    screenshot = tmp_path / "screenshots" / "capture.png"
    screenshot.parent.mkdir()
    screenshot.touch()

    with (
        patch.object(explorer.sys, "platform", "win32"),
        patch.object(explorer, "_focus_existing_explorer_window", return_value=False),
        patch.object(explorer, "_open_and_select_item", return_value=True) as select_item,
        patch.object(explorer.os, "startfile", create=True) as startfile,
    ):
        assert explorer.reveal_in_explorer(screenshot)

    select_item.assert_called_once_with(screenshot.resolve())
    startfile.assert_not_called()


def test_reveal_in_explorer_opens_parent_when_native_selection_fails(tmp_path):
    screenshot = tmp_path / "screenshots" / "capture.png"
    screenshot.parent.mkdir()
    screenshot.touch()

    with (
        patch.object(explorer.sys, "platform", "win32"),
        patch.object(explorer, "_focus_existing_explorer_window", return_value=False),
        patch.object(explorer, "_open_and_select_item", return_value=False),
        patch.object(explorer.os, "startfile", create=True) as startfile,
    ):
        assert explorer.reveal_in_explorer(screenshot)

    startfile.assert_called_once_with(str(screenshot.parent.resolve()), "explore")
