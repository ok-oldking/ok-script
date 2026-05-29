import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple, Optional

import pyappify


class StartupVersionChange(NamedTuple):
    title: str
    content: str


def get_startup_version_change(pyappify_module=pyappify) -> Optional[StartupVersionChange]:
    """Return the startup update/downgrade message described by pyappify."""
    try:
        is_updated = bool(pyappify_module.is_app_updated())
        is_downgraded = bool(pyappify_module.is_app_downgraded())
    except Exception:
        return None

    if not is_updated and not is_downgraded:
        return None

    action = "update" if is_updated else "downgrade"
    from_version = getattr(pyappify_module, "app_starting_version", "") or ""
    to_version = getattr(pyappify_module, "app_version", "") or ""
    try:
        notes = pyappify_module.get_update_notes()
    except Exception:
        notes = []
    content = "\n".join(str(note) for note in notes)
    title = f"{action} success {from_version} -> {to_version}"
    return StartupVersionChange(title=title, content=content)


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

    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

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
