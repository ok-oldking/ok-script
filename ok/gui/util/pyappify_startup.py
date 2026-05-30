import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import NamedTuple, Optional

import pyappify

logger = logging.getLogger("ok")

APP_VERSION_ENV = "PYAPPIFY_APP_VERSION"
APP_STARTING_VERSION_ENV = "PYAPPIFY_APP_STARTING_VERSION"
UPDATE_NOTE_ENV = "PYAPPIFY_UPDATE_NOTE"


class StartupVersionChange(NamedTuple):
    title: str
    content: str
    action: str
    from_version: str
    to_version: str


def _get_pyappify_value(pyappify_module, attr_name, env_name):
    return getattr(pyappify_module, attr_name, None) or os.environ.get(env_name) or ""


def _is_greater_version(pyappify_module, version1, version2):
    compare = getattr(pyappify_module, "is_greater_version", None)
    if callable(compare):
        try:
            return bool(compare(version1, version2))
        except Exception:
            logger.error(
                "pyappify_startup:get_startup_version_change failed to compare versions with pyappify",
                exc_info=True,
            )

    try:
        version1 = version1.lstrip("v")
        version2 = version2.lstrip("v")
        v1_parts = [int(part) for part in version1.split(".")]
        v2_parts = [int(part) for part in version2.split(".")]
        return v1_parts > v2_parts
    except (ValueError, AttributeError):
        return False


def _get_update_state(pyappify_module, from_version, to_version):
    is_app_updated = getattr(pyappify_module, "is_app_updated", None)
    is_app_downgraded = getattr(pyappify_module, "is_app_downgraded", None)
    if callable(is_app_updated) and callable(is_app_downgraded):
        try:
            return bool(is_app_updated()), bool(is_app_downgraded())
        except Exception:
            logger.error("pyappify_startup:get_startup_version_change failed to read update state", exc_info=True)

    can_compare_legacy_state = (
        callable(getattr(pyappify_module, "is_greater_version", None)) or
        APP_VERSION_ENV in os.environ or
        APP_STARTING_VERSION_ENV in os.environ
    )
    if not can_compare_legacy_state:
        return False, False

    return (
        _is_greater_version(pyappify_module, to_version, from_version),
        _is_greater_version(pyappify_module, from_version, to_version),
    )


def _get_update_notes(pyappify_module):
    get_update_notes = getattr(pyappify_module, "get_update_notes", None)
    if callable(get_update_notes):
        try:
            return get_update_notes()
        except Exception:
            logger.error("pyappify_startup:get_startup_version_change failed to read update notes", exc_info=True)

    update_note = getattr(pyappify_module, "update_note", None) or os.environ.get(UPDATE_NOTE_ENV)
    if not update_note:
        return []
    try:
        notes = json.loads(update_note)
    except (TypeError, ValueError):
        return []
    if isinstance(notes, list):
        return [str(note) for note in notes]
    return []


def get_startup_version_change(pyappify_module=pyappify) -> Optional[StartupVersionChange]:
    """Return the startup update/downgrade message described by pyappify."""
    from_version = _get_pyappify_value(pyappify_module, "app_starting_version", APP_STARTING_VERSION_ENV)
    to_version = _get_pyappify_value(pyappify_module, "app_version", APP_VERSION_ENV)
    is_updated, is_downgraded = _get_update_state(pyappify_module, from_version, to_version)
    logger.info(
        "pyappify_startup:get_startup_version_change "
        f"from_version={from_version}, to_version={to_version}, "
        f"is_updated={is_updated}, is_downgraded={is_downgraded}"
    )

    if not is_updated and not is_downgraded:
        return None

    action = "update" if is_updated else "downgrade"
    notes = _get_update_notes(pyappify_module)
    content = "\n".join(str(note) for note in notes)
    title = f"{action.capitalize()} success {from_version} -> {to_version}"
    return StartupVersionChange(
        title=title,
        content=content,
        action=action,
        from_version=from_version,
        to_version=to_version,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the OK GUI with a simulated pyappify update note.")
    parser.add_argument("--from-version", default="1.0.2")
    parser.add_argument("--to-version", default="1.0.3")
    parser.add_argument(
        "--note",
        action="append",
        dest="notes",
        default=None,
        help="Update note line. Can be passed more than once.",
    )
    args = parser.parse_args(argv)

    notes = args.notes or [
        "Updated successfully through pyappify.",
        "This dialog is shown because pyappify detected an app version change.",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change.",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change.",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change.",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change. 汉字",
        "This dialog is shown because pyappify detected an app version change. 汉字This dialog is shown because pyappify detected an app version change. 汉字This dialog is shown because pyappify detected an app version change. 汉字This dialog is shown because pyappify detected an app version change. 汉字This dialog is shown because pyappify detected an app version change. 汉字",
    ]
    os.environ["PYAPPIFY_APP_STARTING_VERSION"] = args.from_version
    os.environ["PYAPPIFY_APP_VERSION"] = args.to_version
    os.environ["PYAPPIFY_UPDATE_NOTE"] = json.dumps(notes)
    importlib.reload(pyappify)

    project_root = Path(__file__).resolve().parents[3]
    os.chdir(project_root)
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    from ok import OK

    config = {
        "debug": False,
        "use_gui": True,
        "gui_title": "pyappify startup update demo",
        "gui_icon": ":/icon/icon.ico",
        "version": args.to_version,
        "window_size": {
            "width": 1000,
            "height": 800,
            "min_width": 600,
            "min_height": 450,
        },
        "onetime_tasks": [],
        "trigger_tasks": [],
    }
    ok = OK(config)
    ok.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
