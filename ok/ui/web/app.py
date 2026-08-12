from __future__ import annotations

import asyncio
import ast
import dataclasses
import json
import re
import shutil
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from ok.core.events import EventMessage, communicate


LOG_LINE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
)
LOG_LEVELS = {"ALL": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
SCRIPT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.py$")
TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _script_templates():
    """Extract the same BaseTask helper palette used by Qt without importing Qt."""
    source_path = Path(__file__).parents[2] / "task" / "task.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    target_classes = {"ExecutorOperation", "FindFeature", "OCR", "BaseTask"}
    categories = [
        ("Mouse", ("click", "scroll", "mouse", "swipe", "move")),
        ("Key", ("key", "press", "release", "input", "back")),
        ("Control", ("sleep", "reset_scene", "next_frame", "disable", "wait_until", "enable", "unpause", "pause", "wait_scene")),
        ("OCR", ("ocr", "text_fix")),
        ("Template Matching", ("find", "feature", "match", "exists")),
        ("Box", ("box", "width", "height")),
        ("Window", ("window", "ensure_in_front", "hwnd")),
        ("ADB", ("adb",)),
        ("Logging", ("log", "info_", "screenshot")),
    ]
    templates = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name not in target_classes:
            continue
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or method.name.startswith("_") or method.name in seen:
                continue
            if any(isinstance(item, ast.Name) and item.id == "property" for item in method.decorator_list):
                continue
            seen.add(method.name)
            args = method.args.args[1:] if method.args.args and method.args.args[0].arg in {"self", "cls"} else method.args.args
            defaults = [None] * (len(args) - len(method.args.defaults)) + list(method.args.defaults)
            params = []
            for argument, default in zip(args, defaults):
                params.append({"name": argument.arg, "default": ast.unparse(default) if default is not None else None})
            lowered = method.name.lower()
            category = next((name for name, words in categories if any(word in lowered for word in words)), "Other")
            doc = ast.get_docstring(method) or ""
            templates.append({
                "name": method.name, "template_name": method.name.replace("_", " ").title(),
                "category": category, "doc": doc.splitlines()[0] if doc else "", "full_doc": doc,
                "class_name": node.name, "is_static": any(isinstance(item, ast.Name) and item.id == "staticmethod" for item in method.decorator_list),
                "params": params,
            })
    return sorted(templates, key=lambda item: (item["category"], item["template_name"]))


def _color_hex(red, green, blue):
    return f"#{red:02x}{green:02x}{blue:02x}"


def _windows_system_accents():
    """Return Windows primary fills for light and dark UI modes."""
    try:
        from ok.rotypes.Windows.UI.ViewManagement import UIColorType, get_color_value

        light = get_color_value(UIColorType.AccentDark1)
        dark = get_color_value(UIColorType.AccentLight2)
        return {
            "light": _color_hex(light.red, light.green, light.blue),
            "dark": _color_hex(dark.red, dark.green, dark.blue),
        }
    except (ImportError, OSError, TypeError, AttributeError):
        pass

    try:
        import ctypes
        from ctypes import wintypes

        colorization_color = wintypes.DWORD()
        opaque_blend = wintypes.BOOL()
        result = ctypes.windll.dwmapi.DwmGetColorizationColor(
            ctypes.byref(colorization_color), ctypes.byref(opaque_blend)
        )
        if result != 0:
            return None
        argb = colorization_color.value
        accent = _color_hex((argb >> 16) & 0xff, (argb >> 8) & 0xff, argb & 0xff)
        return {"light": accent, "dark": accent}
    except (AttributeError, OSError):
        return None


def _copy_web_icon(config, static_dir):
    """Copy the configured application icon into the served web assets."""
    configured = config.get("gui_icon")
    if not configured or str(configured).startswith(":/"):
        return None

    source = Path(configured)
    if not source.is_absolute():
        from ok.util.file import get_path_relative_to_exe
        source = Path(get_path_relative_to_exe(str(configured)))
    if not source.is_file():
        return None

    static_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower() or ".ico"
    destination = static_dir / f"app-icon{suffix}"
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return f"/static/{destination.name}?version={destination.stat().st_mtime_ns}"


def _json_value(value: Any):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value):
        return _json_value(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        return {
            "type": value.__class__.__name__,
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }
    if hasattr(value, "name"):
        return {"name": str(value.name), "type": value.__class__.__name__}
    return str(value)


def _config_fields(config, descriptions=None, config_types=None, defaults=None):
    """Return the editable fields shared by Qt and web config cards."""
    fields = []
    if not config:
        return fields
    descriptions = descriptions or {}
    config_types = config_types or {}
    defaults = defaults or {}

    def normalize_keys(keys):
        if keys is None:
            return []
        return [keys] if isinstance(keys, str) else list(keys)

    def active_keys(rules, value):
        if isinstance(value, list):
            return {
                key for choice in value
                for key in normalize_keys(rules.get(choice))
            }
        try:
            return set(normalize_keys(rules.get(value)))
        except TypeError:
            return set()

    def is_visible(key, checking=None):
        checking = set(checking or ())
        if key in checking:
            return False
        checking.add(key)
        for parent_key, parent_type in config_types.items():
            rules = parent_type.get("sub_configs") if isinstance(parent_type, dict) else None
            if not isinstance(rules, dict):
                continue
            controlled = {
                controlled_key for keys in rules.values()
                for controlled_key in normalize_keys(keys)
            }
            if key in controlled and (
                    not is_visible(parent_key, checking)
                    or key not in active_keys(rules, config.get(parent_key))):
                return False
        return True

    for key, value in config.items():
        if str(key).startswith("_"):
            continue
        field_type = config_types.get(key)
        if isinstance(field_type, dict) and field_type.get("hidden"):
            continue
        if not is_visible(key):
            continue
        resolved_type = field_type.get("type") if isinstance(field_type, dict) else None
        if resolved_type in {"button", "global"} or (
                isinstance(field_type, dict) and ("buttons" in field_type or "callback" in field_type)):
            continue
        options = field_type.get("options") if isinstance(field_type, dict) else None
        options_available = field_type.get("options_available") if isinstance(field_type, dict) else None
        if options is not None:
            kind = "multi_selection" if isinstance(value, list) else "select"
        elif isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, int):
            kind = "integer"
        elif isinstance(value, float):
            kind = "number"
        elif isinstance(value, list):
            kind = "list"
        else:
            kind = "text"
        fields.append({
            "key": str(key),
            "value": _json_value(value),
            "default": _json_value(defaults.get(key)),
            "description": str(descriptions.get(key) or ""),
            "kind": kind,
            "options": _json_value(options if options is not None else options_available),
            "allow_duplication": bool(field_type.get("allow_duplication", False)) if isinstance(field_type, dict) else False,
            "minimum": field_type.get("min") if isinstance(field_type, dict) else None,
            "maximum": field_type.get("max") if isinstance(field_type, dict) else None,
        })
    return fields


def _task_config_fields(task):
    """Return the editable config surface exposed by the Qt ConfigCard."""
    return _config_fields(
        getattr(task, "config", None),
        getattr(task, "config_description", None),
        getattr(task, "config_type", None),
        getattr(task, "default_config", None),
    )


def _task_payload(task):
    waiting_for = task.executor.waiting_for_task(task) if task in task.executor.onetime_tasks else None
    return {
        "name": task.name,
        "class_name": task.__class__.__name__,
        "enabled": bool(task.enabled),
        "running": bool(task.running),
        "paused": bool(task.paused),
        "trigger": task in task.executor.trigger_tasks,
        "description": getattr(task, "description", "") or "",
        "visible": bool(getattr(task, "visible", True)),
        "group_name": getattr(task, "group_name", None),
        "instructions": getattr(task, "instructions", None),
        "waiting_for": waiting_for.name if waiting_for else None,
        "start_time": float(getattr(task, "start_time", 0) or 0),
        "info": _json_value(getattr(task, "info", {}) or {}),
        "config": _task_config_fields(task),
    }


def _method_name(method):
    return method.__name__ if isinstance(method, type) else str(method)


def _device_payload(device, preferred_id):
    kind = str(device.get("device") or "")
    kind_label = {
        "windows": "PC",
        "adb": "Android",
        "browser": "Browser",
    }.get(kind, kind.title() or "Device")
    connected = bool(device.get("connected"))
    state = "Connected" if connected else "Disconnected"
    details = " ".join(str(value) for value in (
        device.get("nick"), device.get("address"), device.get("resolution")
    ) if value)
    return {
        "id": str(device.get("imei") or ""),
        "label": f"{kind_label} {state}: {details}".strip(),
        "kind": kind,
        "connected": connected,
        "resolution": str(device.get("resolution") or ""),
        "selected": device.get("imei") == preferred_id,
        "keywords": " ".join(str(value) for value in (
            device.get("nick"), device.get("exe"), device.get("address"), device.get("full_path")
        ) if value),
    }


def _read_log(path, level="ALL", query="", max_lines=5000):
    """Read and filter the active log without importing the Qt LogWindow."""
    level = level.upper()
    if level not in LOG_LEVELS:
        raise ValueError(f"Unknown log level: {level}")
    if not path.is_file():
        return {"path": str(path), "text": "", "line_count": 0, "modified": None}

    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        chunks = []
        line_count = 0
        while position > 0 and line_count <= max_lines * 2:
            size = min(1024 * 1024, position)
            position -= size
            file.seek(position)
            chunk = file.read(size)
            chunks.insert(0, chunk)
            line_count += chunk.count(b"\n")

    lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
    records = []
    current = None
    for line in lines:
        match = LOG_LINE_PATTERN.match(line)
        if match or current is None:
            current = {"level": match.group("level") if match else "INFO", "lines": [line]}
            records.append(current)
        else:
            current["lines"].append(line)

    threshold = LOG_LEVELS[level]
    query = query.strip().lower()
    visible = []
    for record in records:
        block = "\n".join(record["lines"])
        if LOG_LEVELS.get(record["level"], 0) < threshold or (query and query not in block.lower()):
            continue
        visible.extend(record["lines"])
    visible = visible[-max_lines:]
    return {
        "path": str(path),
        "text": "\n".join(visible) + ("\n" if visible else ""),
        "line_count": len(visible),
        "modified": path.stat().st_mtime,
    }


class WebRuntime:
    def __init__(self, config, icon_url=None):
        from ok import OK

        web_config = dict(config)
        web_config["use_gui"] = False
        self.ok = OK(web_config)
        self.last_capture_path = None
        self.icon_url = icon_url
        self._schedule_manager = None

    @property
    def executor(self):
        return self.ok.task_executor

    @property
    def task_manager(self):
        manager = getattr(self.ok, "task_manager", None)
        if manager is None:
            from ok import og
            manager = getattr(og, "task_manager", None)
        return manager

    @property
    def schedule_manager(self):
        if self._schedule_manager is None:
            from ok.util.windows_schedule import WindowsScheduleManager
            self._schedule_manager = WindowsScheduleManager(config=self.ok.config)
        return self._schedule_manager

    def status(self):
        current = self.executor.current_task
        hotkey = self.executor.basic_options.get("Start/Stop")
        return {
            "paused": bool(self.executor.paused),
            "running": self.executor.thread is not None and self.executor.thread.is_alive(),
            "current_task": current.name if current else None,
            "task_count": len(self.executor.get_all_tasks()),
            "hotkey": hotkey if hotkey and hotkey != "None" else None,
        }

    @property
    def device_manager(self):
        return self.ok.device_manager

    def _capture_methods(self, device):
        if not device:
            return []
        if device.get("device") == "windows":
            configured = (self.device_manager.windows_capture_config or {}).get("capture_method", [])
            methods = configured if isinstance(configured, list) else [configured]
            methods = methods or ["windows"]
        elif device.get("device") == "browser":
            methods = ["browser"]
        elif device.get("emulator") is not None:
            methods = ["adb", "ipc"] if device.get("emulator") else ["adb"]
        else:
            methods = ["adb"]
        selected = self.device_manager.get_preferred_capture()
        return [{
            "id": _method_name(method),
            "label": self.ok.headless_app.tr(_method_name(method)),
            "selected": _method_name(method) == selected,
        } for method in methods if method]

    def _interaction_methods(self, device):
        if not device:
            return []
        kind = device.get("device")
        if kind == "windows":
            configured = (self.device_manager.windows_capture_config or {}).get("interaction", [])
            methods = configured if isinstance(configured, list) else [configured]
            methods = methods or ["Pynput"]
        elif kind == "browser":
            methods = ["BrowserInteraction"]
        elif kind == "adb":
            methods = ["ADBInteraction"]
        else:
            methods = ["Default Interaction"]
        selected = self.device_manager.config.get("interaction")
        return [{
            "id": _method_name(method),
            "label": self.ok.headless_app.tr(_method_name(method)),
            "selected": _method_name(method) == selected or (not selected and index == 0),
        } for index, method in enumerate(methods) if method]

    def capture_ui(self):
        preferred = self.device_manager.get_preferred_device()
        preferred_id = preferred.get("imei") if preferred else None
        return {
            "title": self.ok.config.get("gui_title", "ok-script"),
            "version": self.ok.config.get("version") or "dev",
            "icon_url": self.icon_url,
            "status": self.status(),
            "devices": [_device_payload(device, preferred_id) for device in self.device_manager.get_devices()],
            "capture_methods": self._capture_methods(preferred),
            "interaction_methods": self._interaction_methods(preferred),
            "overlay": self.ok.headless_app.overlay_state(),
        }

    def theme_ui(self):
        return {"system_accent": _windows_system_accents()}

    def refresh_devices(self):
        # DeviceManager owns the worker and publishes adb_devices when done.
        return bool(self.device_manager.refresh())

    def start(self):
        return self.ok.start_runtime()

    def select_device(self, device_id):
        if device_id not in {device.get("imei") for device in self.device_manager.get_devices()}:
            raise ValueError(f"Unknown device: {device_id}")
        self.device_manager.set_preferred_device(imei=device_id)
        return self.capture_ui()

    def select_capture(self, method):
        allowed = {item["id"] for item in self._capture_methods(self.device_manager.get_preferred_device())}
        if method not in allowed:
            raise ValueError(f"Unknown capture method: {method}")
        self.device_manager.set_capture(method)
        return self.capture_ui()

    def select_interaction(self, method):
        allowed = {item["id"] for item in self._interaction_methods(self.device_manager.get_preferred_device())}
        if method not in allowed:
            raise ValueError(f"Unknown interaction method: {method}")
        self.device_manager.set_interaction(method)
        return self.capture_ui()

    def set_overlay(self, name, value):
        self.ok.headless_app.set_overlay_setting(name, value)
        return self.capture_ui()

    def run_tool(self, action):
        from ok.util.explorer import open_explorer_folder, reveal_in_explorer

        if action == "install-folder":
            open_explorer_folder(Path.cwd())
            return {"message": "Install folder opened", "kind": "folder"}
        if action == "log-folder":
            open_explorer_folder(Path.cwd() / "logs")
            return {"message": "Log folder opened", "kind": "folder"}
        if action == "screenshot-folder":
            folder = Path(getattr(self.ok.screenshot, "screenshot_folder", None) or "screenshots")
            open_explorer_folder(folder)
            return {"message": "Screenshot folder opened", "kind": "folder"}
        if action == "export-logs":
            from ok.util.file import get_downloads_folder
            archive = Path(get_downloads_folder()) / f"{self.ok.config.get('gui_title', 'ok-script')}-log.zip"
            archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for folder_name in ("screenshots", "logs"):
                    folder = Path.cwd() / folder_name
                    if folder.is_dir():
                        for file_path in folder.rglob("*"):
                            if file_path.is_file():
                                output.write(file_path, file_path.relative_to(Path.cwd()))
            reveal_in_explorer(archive)
            return {"message": f"Logs exported to {archive}", "kind": "export"}
        if action == "capture":
            method = self.device_manager.capture_method
            if method is None:
                raise RuntimeError("No capture method is active")
            frame = method.get_frame()
            if frame is None:
                raise RuntimeError("Could not capture a frame")
            folder = Path(getattr(self.ok.screenshot, "screenshot_folder", None) or "screenshots")
            folder.mkdir(parents=True, exist_ok=True)
            name = "manual_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.ok.screenshot.generate_screen_shot(
                frame,
                self.ok.screenshot.ui_dict,
                str(folder),
                name,
                True,
                None,
                processor=self.ok.config.get("screenshot_processor"),
            )
            if not path:
                raise RuntimeError("Could not save the captured frame")
            self.last_capture_path = Path(path).resolve()
            return {
                "message": f"Screenshot saved to {self.last_capture_path}",
                "kind": "capture",
                "resource_url": f"/api/capture/image?version={self.last_capture_path.stat().st_mtime_ns}",
            }
        if action == "ocr":
            if self.executor.paused:
                raise RuntimeError("Please start the executor first")
            tasks = self.executor.get_all_tasks()
            if not tasks:
                raise RuntimeError("No task is available for OCR")
            result = tasks[0].ocr(log=True, screenshot=True)
            folder = Path(getattr(self.ok.screenshot, "screenshot_folder", None) or "screenshots").resolve()
            folder.mkdir(parents=True, exist_ok=True)
            if result:
                output = folder / "ocr_result.txt"
                output.write_text(
                    "".join(f"{box.name}, {box}, {box.confidence}\n" for box in result),
                    encoding="utf-8",
                )
            open_explorer_folder(folder)
            return {"message": f"OCR completed: {len(result or [])} result(s)", "kind": "ocr"}
        raise ValueError(f"Unknown tool action: {action}")

    def logs(self, level="ALL", query=""):
        return _read_log(Path.cwd() / "logs" / "ok-script.log", level=level, query=query)

    def tasks(self):
        return [_task_payload(task) for task in self.executor.get_all_tasks()]

    def settings(self):
        """Return global config groups and whether Qt shows them as tabs."""
        from ok.util.GlobalConfig import APP_LAUNCHER_OPTION_NAME

        groups = self.executor.global_config.get_all_visible_configs()
        groups.sort(key=lambda item: item[0] != APP_LAUNCHER_OPTION_NAME)
        return [{
            "name": name,
            "description": str(getattr(option, "description", "") or ""),
            "expanded": name == "Basic Options",
            "top_level": bool(getattr(option, "show_at_tab", False)),
            "fields": _config_fields(
                config,
                getattr(option, "config_description", None),
                getattr(option, "config_type", None),
                getattr(option, "default_config", None),
            ),
        } for name, config, option in groups]

    def set_setting(self, group, key, value):
        config = self.executor.global_config.get_config(group)
        if key.startswith("_") or key not in config:
            raise ValueError(f"Unknown setting: {key}")
        previous = config.get(key)
        config[key] = value
        if config.get(key) == previous and value != previous:
            raise ValueError(f"Invalid value for {key}")
        return next(item for item in self.settings() if item["name"] == group)

    def reset_settings(self, group):
        config = self.executor.global_config.get_config(group)
        config.reset_to_default()
        return next(item for item in self.settings() if item["name"] == group)

    def navigation(self):
        tasks = list(self.executor.get_all_tasks())
        trigger_tasks = list(self.executor.trigger_tasks or [])
        onetime_tasks = list(self.executor.onetime_tasks or [])
        manager = self.task_manager
        return {
            "triggers": any(task in trigger_tasks and getattr(task, "visible", True) for task in tasks),
            "tasks": any(task in onetime_tasks and getattr(task, "visible", True) for task in tasks),
            "script": bool(manager and getattr(manager, "has_custom", False)),
            "templates": bool((manager and getattr(manager, "has_custom", False)) or self.ok.config.get("debug")),
            "schedule": any(getattr(task, "support_schedule_task", False) and getattr(task, "visible", True) for task in tasks),
        }

    def about(self):
        links = self.ok.config.get("links") or {}
        projects = [
            {"name": "ok-py Automation Tool", "url": "https://github.com/ok-oldking/ok-py", "website": "https://ok-script.com/"},
            {"name": "ok-script App Template", "url": "https://github.com/ok-oldking/ok-script-app", "website": "https://ok-script.com/app/en/"},
            {"name": "Wuthering Waves", "url": "https://github.com/ok-oldking/ok-wuthering-waves", "website": "https://ok-script.com/ok-ww/en/"},
            {"name": "Girls' Frontline 2", "url": "https://github.com/ok-oldking/ok-gf2"},
            {"name": "Star Resonance", "url": "https://github.com/Sanheiii/ok-star-resonance", "website": "https://ok-script.com/ok-star-resonance/"},
            {"name": "Duet Night Abyss", "url": "https://github.com/BnanZ0/ok-duet-night-abyss"},
            {"name": "Chaos Zero Nightmare", "url": "https://github.com/baoxin1100/ok-kes", "website": "https://ok-script.com/ok-kes/en/"},
            {"name": "Onmyoji", "url": "https://github.com/YunLiuZ/ok-Onmyoji", "website": "https://ok-script.com/ok-onmyoji/"},
            {"name": "Arknights: Endfield", "url": "https://github.com/AliceJump/ok-end-field", "website": "https://ok-script.com/ok-end-field/en/"},
            {"name": "Neverness to Everness", "url": "https://github.com/BnanZ0/ok-neverness-to-everness", "website": "https://ok-script.com/ok-nte/en/"},
        ]

        def first_url(value):
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                return next((url for item in value.values() if (url := first_url(item))), "")
            return ""

        current_github = first_url(links.get("github")).strip().lower().rstrip("/")
        return {
            "title": self.ok.config.get("gui_title", "ok-script"),
            "version": self.ok.config.get("version") or "dev",
            "debug": bool(self.ok.config.get("debug")),
            "icon_url": self.icon_url,
            "about": str(self.ok.config.get("about") or ""),
            "links": {str(key): _json_value(value) for key, value in links.items()},
            "projects": [project for project in projects if project["url"].lower().rstrip("/") != current_github],
        }

    def script_templates(self):
        return _script_templates()

    def _script_folder(self):
        manager = self.task_manager
        folder = getattr(manager, "task_folder", None) if manager else None
        if not folder:
            raise RuntimeError("Custom scripts are not enabled")
        root = Path(folder).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _script_path(self, name):
        name = str(name or "")
        if not SCRIPT_NAME_PATTERN.fullmatch(name):
            raise ValueError("Invalid script name")
        root = self._script_folder()
        path = (root / name).resolve()
        if path.parent != root:
            raise ValueError("Invalid script path")
        return path

    def scripts(self):
        root = self._script_folder()
        return [{"name": path.name, "modified": path.stat().st_mtime} for path in sorted(root.glob("*.py"), key=lambda item: item.name.lower())]

    def read_script(self, name):
        path = self._script_path(name)
        if not path.is_file():
            raise ValueError("Script not found")
        return {"name": path.name, "code": path.read_text(encoding="utf-8"), "modified": path.stat().st_mtime}

    def save_script(self, name, code):
        path = self._script_path(name)
        if not path.is_file():
            raise ValueError("Script not found")
        if not isinstance(code, str) or len(code.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Script is too large")
        path.write_text(code, encoding="utf-8")
        manager = self.task_manager
        matching_task = next((task for task, data in manager.task_map.items() if Path(data[0]).resolve() == path), None)
        if matching_task is not None:
            manager.reload_task_code(matching_task)
        else:
            manager.load_single_user_task(str(path))
        error = manager.task_errors.get(str(path)) or manager.task_errors.get(path)
        return {**self.read_script(name), "error": str(error) if error else None}

    def create_script(self, class_name, task_name, description=""):
        class_name = str(class_name or "").strip()
        task_name = str(task_name or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", class_name):
            raise ValueError("Invalid class name")
        if not task_name:
            raise ValueError("Task name is required")
        path = self._script_path(f"{class_name}.py")
        if path.exists():
            raise ValueError("Script already exists")
        code = (
            "from ok import BaseTask\n\n"
            f"class {class_name}(BaseTask):\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        super().__init__(*args, **kwargs)\n"
            f"        self.name = {task_name!r}\n"
            f"        self.description = {str(description or '')!r}\n\n"
            "    def run(self):\n"
            "        pass\n"
        )
        path.write_text(code, encoding="utf-8")
        self.task_manager.load_single_user_task(str(path))
        return self.read_script(path.name)

    def delete_script(self, name):
        path = self._script_path(name)
        if not path.is_file():
            raise ValueError("Script not found")
        manager = self.task_manager
        matching_task = next((task for task, data in manager.task_map.items() if Path(data[0]).resolve() == path), None)
        if matching_task is not None:
            manager.delete_task(matching_task)
        else:
            path.unlink()
        return {"deleted": name}

    def copy_script(self, name):
        source = self._script_path(name)
        if not source.is_file():
            raise ValueError("Script not found")
        stem = source.stem
        destination = self._script_path(f"{stem}_copy.py")
        counter = 1
        while destination.exists():
            destination = self._script_path(f"{stem}_copy_{counter}.py")
            counter += 1
        code = re.sub(
            r"(self\.name\s*=\s*)([\"'])(.*?)(\2)",
            lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}_copy{match.group(4)}",
            source.read_text(encoding="utf-8"), count=1,
        )
        destination.write_text(code, encoding="utf-8")
        self.task_manager.load_single_user_task(str(destination))
        return self.read_script(destination.name)

    def run_script(self, name, code):
        document = self.save_script(name, code)
        if document.get("error"):
            return document
        path = self._script_path(name)
        manager = self.task_manager
        task = next((task for task, data in manager.task_map.items() if Path(data[0]).resolve() == path), None)
        if task is None:
            raise RuntimeError("Task could not be loaded")
        if not self.ok.headless_app.start_controller.do_start(task):
            raise RuntimeError("Start task failed")
        return document

    def _template_folder(self):
        folder = (Path.cwd() / "ok_templates").resolve()
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _template_path(self, name):
        name = Path(str(name or "")).name
        if not name or Path(name).suffix.lower() not in TEMPLATE_EXTENSIONS:
            raise ValueError("Invalid template image")
        root = self._template_folder()
        path = (root / name).resolve()
        if path.parent != root:
            raise ValueError("Invalid template path")
        return path

    def templates(self):
        root = self._template_folder()
        coco_path = root / "coco_annotations.json"
        try:
            coco = json.loads(coco_path.read_text(encoding="utf-8")) if coco_path.is_file() else {}
        except (OSError, ValueError):
            coco = {}
        categories = {item.get("id"): str(item.get("name", "")) for item in coco.get("categories", [])}
        image_ids = {str(item.get("file_name", "")).casefold(): item.get("id") for item in coco.get("images", [])}
        annotations = {}
        for item in coco.get("annotations", []):
            annotations.setdefault(item.get("image_id"), []).append(categories.get(item.get("category_id"), ""))
        return [{
            "name": path.name,
            "url": f"/api/templates/image/{path.name}",
            "modified": path.stat().st_mtime,
            "categories": [name for name in annotations.get(image_ids.get(path.name.casefold()), []) if name],
        } for path in sorted((item for item in root.iterdir() if item.suffix.lower() in TEMPLATE_EXTENSIONS), key=lambda item: item.stat().st_mtime, reverse=True)]

    def delete_template(self, name):
        path = self._template_path(name)
        if not path.is_file():
            raise ValueError("Template not found")
        path.unlink()
        coco_path = self._template_folder() / "coco_annotations.json"
        if coco_path.is_file():
            coco = json.loads(coco_path.read_text(encoding="utf-8"))
            image_ids = {item.get("id") for item in coco.get("images", []) if str(item.get("file_name", "")).casefold() == path.name.casefold()}
            coco["images"] = [item for item in coco.get("images", []) if item.get("id") not in image_ids]
            coco["annotations"] = [item for item in coco.get("annotations", []) if item.get("image_id") not in image_ids]
            coco_path.write_text(json.dumps(coco, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"deleted": name}

    def template_annotations(self, name):
        path = self._template_path(name)
        if not path.is_file():
            raise ValueError("Template not found")
        coco_path = self._template_folder() / "coco_annotations.json"
        coco = json.loads(coco_path.read_text(encoding="utf-8")) if coco_path.is_file() else {"images": [], "annotations": [], "categories": []}
        image = next((item for item in coco.get("images", []) if str(item.get("file_name", "")).casefold() == path.name.casefold()), None)
        width = int((image or {}).get("width") or 0)
        height = int((image or {}).get("height") or 0)
        if width <= 0 or height <= 0:
            import cv2
            frame = cv2.imread(str(path))
            if frame is not None:
                height, width = frame.shape[:2]
        categories = {item.get("id"): item.get("name", "") for item in coco.get("categories", [])}
        annotations = [] if image is None else [{
            "id": item.get("id"), "category": categories.get(item.get("category_id"), ""), "bbox": item.get("bbox", [0, 0, 0, 0]),
        } for item in coco.get("annotations", []) if item.get("image_id") == image.get("id")]
        return {
            "name": path.name,
            "url": f"/api/templates/image/{path.name}",
            "width": width,
            "height": height,
            "annotations": annotations,
        }

    def save_template_annotations(self, name, annotations):
        path = self._template_path(name)
        if not path.is_file() or not isinstance(annotations, list):
            raise ValueError("Invalid annotations")
        root = self._template_folder()
        coco_path = root / "coco_annotations.json"
        coco = json.loads(coco_path.read_text(encoding="utf-8")) if coco_path.is_file() else {"images": [], "annotations": [], "categories": []}
        image = next((item for item in coco.get("images", []) if str(item.get("file_name", "")).casefold() == path.name.casefold()), None)
        if image is None:
            image_id = max((int(item.get("id", 0)) for item in coco.get("images", [])), default=0) + 1
            import cv2
            frame = cv2.imread(str(path))
            height, width = frame.shape[:2] if frame is not None else (0, 0)
            image = {"id": image_id, "file_name": path.name, "width": width, "height": height}
            coco.setdefault("images", []).append(image)
        coco["annotations"] = [item for item in coco.get("annotations", []) if item.get("image_id") != image["id"]]
        category_by_name = {str(item.get("name", "")): item for item in coco.get("categories", [])}
        next_category = max((int(item.get("id", 0)) for item in coco.get("categories", [])), default=0) + 1
        next_annotation = max((int(item.get("id", 0)) for item in coco.get("annotations", [])), default=0) + 1
        for annotation in annotations:
            category_name = str(annotation.get("category", "")).strip()
            bbox = annotation.get("bbox")
            if not category_name or not isinstance(bbox, list) or len(bbox) != 4:
                raise ValueError("Invalid bounding box")
            values = [max(0, float(value)) for value in bbox]
            category = category_by_name.get(category_name)
            if category is None:
                category = {"id": next_category, "name": category_name, "supercategory": ""}
                next_category += 1
                coco.setdefault("categories", []).append(category)
                category_by_name[category_name] = category
            coco.setdefault("annotations", []).append({
                "id": next_annotation, "image_id": image["id"], "category_id": category["id"],
                "bbox": values, "area": values[2] * values[3], "iscrowd": 0,
            })
            next_annotation += 1
        coco_path.write_text(json.dumps(coco, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.template_annotations(name)

    def save_templates(self, destination="tasks", generate_label_enum=False, enum_path="ok_tasks/LabelEnum.py"):
        from ok.feature.FeatureSet import compress_copy_coco
        root = self._template_folder()
        coco_path = root / "coco_annotations.json"
        if not coco_path.is_file():
            raise ValueError("No annotations to save")
        if destination == "assets" and not self.ok.config.get("debug"):
            raise ValueError("Standalone assets are only available in debug mode")
        target = (Path.cwd() / ("assets" if destination == "assets" else "ok_tasks/assets")).resolve()
        enum_module = None
        if generate_label_enum:
            normalized = str(enum_path or "").strip().replace("\\", "/")
            if normalized.lower().endswith(".py"):
                normalized = normalized[:-3]
            parts = normalized.strip("/").split("/")
            if not parts or any(not part.isidentifier() for part in parts):
                raise ValueError("Invalid label enum path")
            enum_module = ".".join(parts)
        compress_copy_coco(str(coco_path), str(target), str(root), generate_label_enmu=enum_module)
        return {"message": f"Save completed successfully to: {target}"}

    def capture_template(self):
        capture_method = getattr(self.ok.device_manager, "capture_method", None)
        if capture_method is None:
            raise RuntimeError("No capture method available. Please start capture first.")
        frame = capture_method.get_frame()
        if frame is None:
            raise RuntimeError("Failed to capture frame")
        import cv2
        root = self._template_folder()
        used = {int(path.stem) for path in root.iterdir() if path.stem.isdigit() and path.suffix.lower() in TEMPLATE_EXTENSIONS}
        index = 0
        while index in used:
            index += 1
        path = root / f"{index}.png"
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError("Failed to save template image")
        return self.templates()

    def schedule_tasks(self):
        available = [{"index": index + 1, "name": task.name} for index, task in enumerate(self.executor.onetime_tasks or []) if getattr(task, "support_schedule_task", False) and getattr(task, "visible", True)]
        return {"available_tasks": available, "tasks": [_json_value(task) for task in self.schedule_manager.query_all_tasks(force_sync=True)]}

    def create_schedule_task(self, body):
        from ok.util.windows_schedule import TriggerType
        task_index = int(body.get("task_index", 0))
        available_indices = {
            index + 1 for index, task in enumerate(self.executor.onetime_tasks or [])
            if getattr(task, "support_schedule_task", False) and getattr(task, "visible", True)
        }
        if task_index not in available_indices:
            raise ValueError("Invalid scheduled task")
        try:
            trigger = TriggerType(str(body.get("trigger_type", "Daily")))
        except ValueError as exc:
            raise ValueError("Invalid trigger type") from exc
        success = self.schedule_manager.create_task(
            task_name=str(body.get("name") or ""), task_index=task_index, trigger_type=trigger,
            timeout_hours=int(body.get("timeout_hours", 0)), start_hour=int(body.get("start_hour", 9)),
            start_minute=int(body.get("start_minute", 0)), auto_exit=bool(body.get("auto_exit", True)), enabled=True,
            interval_days=int(body.get("interval_days", 0)), interval_hours=int(body.get("interval_hours", 0)),
        )
        if not success:
            raise RuntimeError("Failed to create scheduled task")
        return self.schedule_tasks()

    def schedule_action(self, name, action):
        if action == "delete":
            success = self.schedule_manager.delete_task(name)
        elif action == "enable":
            success = self.schedule_manager.enable_task(name)
        elif action == "disable":
            success = self.schedule_manager.disable_task(name)
        else:
            raise ValueError("Unknown schedule action")
        if not success:
            raise RuntimeError(f"Failed to {action} scheduled task")
        return self.schedule_tasks()

    def update_schedule_task(self, name, body):
        from ok.util.windows_schedule import TriggerType
        current = self.schedule_manager.cache.get(name)
        if current is None:
            current = next((item for item in self.schedule_manager.cache.values() if item.path == name or item.name == name), None)
        if current is None or current.read_only:
            raise ValueError("Scheduled task is not editable")
        task_index = int(body.get("task_index", current.task_index))
        available_indices = {
            index + 1 for index, task in enumerate(self.executor.onetime_tasks or [])
            if getattr(task, "support_schedule_task", False) and getattr(task, "visible", True)
        }
        if task_index not in available_indices:
            raise ValueError("Invalid scheduled task")
        try:
            trigger = TriggerType(str(body.get("trigger_type", current.trigger_type or "Daily")))
        except ValueError as exc:
            raise ValueError("Invalid trigger type") from exc
        if not self.schedule_manager.delete_task(name):
            raise RuntimeError("Failed to replace scheduled task")
        success = self.schedule_manager.create_task(
            task_name=current.name, task_index=task_index, trigger_type=trigger,
            timeout_hours=int(body.get("timeout_hours", 0)), start_hour=int(body.get("start_hour", 9)),
            start_minute=int(body.get("start_minute", 0)), auto_exit=bool(body.get("auto_exit", True)), enabled=current.enabled,
            description=current.description, interval_days=int(body.get("interval_days", current.interval_days)),
            interval_hours=int(body.get("interval_hours", current.interval_hours)),
        )
        if not success:
            raise RuntimeError("Failed to modify scheduled task")
        return self.schedule_tasks()

    def start_task(self, name):
        task, _is_trigger = self.ok.get_task(name)
        if not self.ok.headless_app.start_controller.do_start(task):
            raise RuntimeError(f"Start task failed: {task.name}")
        return _task_payload(task)

    def task_action(self, name, action):
        task, is_trigger = self.ok.get_task(name)
        if action == "enable" and is_trigger:
            task.enable()
        elif action == "disable" and is_trigger:
            task.disable()
        elif action == "pause" and not is_trigger:
            task.pause()
        elif action == "stop" and not is_trigger:
            task.disable()
            task.unpause()
        elif action == "resume" and not is_trigger and task.enabled and task.paused:
            task.unpause()
        else:
            raise ValueError(f"Unsupported {task.name} action: {action}")
        return _task_payload(task)

    def set_task_config(self, name, key, value):
        task, _is_trigger = self.ok.get_task(name)
        if key.startswith("_") or key not in task.config:
            raise ValueError(f"Unknown task config: {key}")
        previous = task.config.get(key)
        task.config[key] = value
        if task.config.get(key) == previous and value != previous:
            raise ValueError(f"Invalid value for {key}")
        return _task_payload(task)

    def reset_task_config(self, name):
        task, _is_trigger = self.ok.get_task(name)
        task.config.reset_to_default()
        return _task_payload(task)

    def pause(self):
        if not self.executor.paused:
            self.executor.pause()
        return self.status()

    def resume(self):
        if not self.ok.headless_app.start_controller.do_start():
            raise RuntimeError("Start failed")
        return self.status()

    def stop_task(self):
        self.executor.stop_current_task()
        return self.status()

    def close(self):
        self.ok.quit()


def create_web_app(config):
    try:
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(
            "The web UI requires FastAPI and Uvicorn. Install ok-script[web]."
        ) from exc

    # FastAPI resolves postponed endpoint annotations from module globals.
    globals()["WebSocket"] = WebSocket

    static_dir = Path(__file__).with_name("static")
    icon_url = _copy_web_icon(config, static_dir)
    runtime = WebRuntime(config, icon_url=icon_url)

    @asynccontextmanager
    async def lifespan(_app):
        runtime.start()
        yield
        await asyncio.to_thread(runtime.close)

    app = FastAPI(title=config.get("gui_title", "ok-script"), lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.state.runtime = runtime

    @app.get("/")
    async def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
    async def status():
        return runtime.status()

    @app.get("/api/ui/capture")
    async def capture_ui():
        return runtime.capture_ui()

    @app.get("/api/ui/theme")
    async def theme_ui():
        return await asyncio.to_thread(runtime.theme_ui)

    @app.post("/api/devices/refresh")
    async def refresh_devices():
        # Completion and state are published through communicate.adb_devices.
        return {"accepted": runtime.refresh_devices()}

    @app.post("/api/devices/select")
    async def select_device(body: dict):
        try:
            return await asyncio.to_thread(runtime.select_device, str(body.get("id", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/capture-methods/select")
    async def select_capture(body: dict):
        try:
            return await asyncio.to_thread(runtime.select_capture, str(body.get("id", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/interaction-methods/select")
    async def select_interaction(body: dict):
        try:
            return await asyncio.to_thread(runtime.select_interaction, str(body.get("id", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/overlay")
    async def set_overlay(body: dict):
        try:
            return runtime.set_overlay(str(body.get("name", "")), bool(body.get("value")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tools/{action}")
    async def run_tool(action: str):
        try:
            result = await asyncio.to_thread(runtime.run_tool, action)
            return {"ok": True, **result}
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/capture/image")
    async def capture_image():
        path = runtime.last_capture_path
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="No captured image is available")
        return FileResponse(path)

    @app.get("/api/logs")
    async def logs(level: str = "ALL", query: str = ""):
        try:
            return await asyncio.to_thread(runtime.logs, level, query)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/tasks")
    async def tasks():
        return runtime.tasks()

    @app.get("/api/settings")
    async def settings():
        return runtime.settings()

    @app.get("/api/navigation")
    async def navigation():
        return runtime.navigation()

    @app.get("/api/about")
    async def about():
        return runtime.about()

    @app.get("/api/scripts")
    async def scripts():
        try:
            return runtime.scripts()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/script-templates")
    async def script_templates():
        return await asyncio.to_thread(runtime.script_templates)

    @app.get("/api/scripts/{name}")
    async def read_script(name: str):
        try:
            return runtime.read_script(name)
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/scripts")
    async def create_script(body: dict):
        try:
            return await asyncio.to_thread(runtime.create_script, body.get("class_name"), body.get("task_name"), body.get("description", ""))
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/scripts/{name}")
    async def save_script(name: str, body: dict):
        try:
            return await asyncio.to_thread(runtime.save_script, name, body.get("code"))
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/scripts/{name}/delete")
    async def delete_script(name: str):
        try:
            return await asyncio.to_thread(runtime.delete_script, name)
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/scripts/{name}/copy")
    async def copy_script(name: str):
        try:
            return await asyncio.to_thread(runtime.copy_script, name)
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/scripts/{name}/run")
    async def run_script(name: str, body: dict):
        try:
            return await asyncio.to_thread(runtime.run_script, name, body.get("code"))
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/templates")
    async def templates():
        return await asyncio.to_thread(runtime.templates)

    @app.get("/api/templates/image/{name}")
    async def template_image(name: str):
        try:
            path = runtime._template_path(name)
            if not path.is_file():
                raise ValueError("Template not found")
            return FileResponse(path)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/templates/{name}/delete")
    async def delete_template(name: str):
        try:
            return await asyncio.to_thread(runtime.delete_template, name)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/templates/capture")
    async def capture_template():
        try:
            return await asyncio.to_thread(runtime.capture_template)
        except (RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/templates/{name}/annotations")
    async def template_annotations(name: str):
        try:
            return await asyncio.to_thread(runtime.template_annotations, name)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/templates/{name}/annotations")
    async def save_template_annotations(name: str, body: dict):
        try:
            return await asyncio.to_thread(runtime.save_template_annotations, name, body.get("annotations"))
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/templates/save")
    async def save_templates(body: dict):
        try:
            return await asyncio.to_thread(runtime.save_templates, body.get("destination", "tasks"), bool(body.get("generate_label_enum")), body.get("enum_path", "ok_tasks/LabelEnum.py"))
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/schedule")
    async def schedule_tasks():
        try:
            return await asyncio.to_thread(runtime.schedule_tasks)
        except (RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/schedule")
    async def create_schedule_task(body: dict):
        try:
            return await asyncio.to_thread(runtime.create_schedule_task, body)
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/schedule/{name}/action")
    async def schedule_action(name: str, body: dict):
        try:
            return await asyncio.to_thread(runtime.schedule_action, name, str(body.get("action", "")))
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/schedule/{name}")
    async def update_schedule_task(name: str, body: dict):
        try:
            return await asyncio.to_thread(runtime.update_schedule_task, name, body)
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/settings/{group}/config")
    async def set_setting(group: str, body: dict):
        try:
            return await asyncio.to_thread(
                runtime.set_setting, group, str(body.get("key", "")), body.get("value")
            )
        except (ValueError, RuntimeError, StopIteration) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/settings/{group}/reset")
    async def reset_settings(group: str):
        try:
            return await asyncio.to_thread(runtime.reset_settings, group)
        except (ValueError, RuntimeError, StopIteration) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tasks/{name}/start")
    async def start_task(name: str):
        try:
            return await asyncio.to_thread(runtime.start_task, name)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tasks/{name}/action")
    async def task_action(name: str, body: dict):
        try:
            return await asyncio.to_thread(runtime.task_action, name, str(body.get("action", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tasks/{name}/config")
    async def set_task_config(name: str, body: dict):
        try:
            return await asyncio.to_thread(
                runtime.set_task_config, name, str(body.get("key", "")), body.get("value")
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tasks/{name}/config/reset")
    async def reset_task_config(name: str):
        try:
            return await asyncio.to_thread(runtime.reset_task_config, name)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/executor/pause")
    async def pause():
        return runtime.pause()

    @app.post("/api/executor/resume")
    async def resume():
        try:
            return await asyncio.to_thread(runtime.resume)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/executor/stop-task")
    async def stop_task():
        return runtime.stop_task()

    @app.websocket("/api/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[EventMessage] = asyncio.Queue(maxsize=200)

        def receive(message):
            def enqueue():
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(message)
            loop.call_soon_threadsafe(enqueue)

        communicate.any.connect(receive)
        try:
            while True:
                message = await queue.get()
                payload = {
                    "event": message.name,
                    "args": _json_value(message.args),
                    "kwargs": _json_value(message.kwargs),
                }
                if message.name in {
                    "adb_devices", "executor_paused", "starting_emulator",
                    "task", "task_list_updated",
                }:
                    payload["ui"] = await asyncio.to_thread(runtime.capture_ui)
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            communicate.any.disconnect(receive)

    return app
