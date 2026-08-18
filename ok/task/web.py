"""Framework-neutral task-backed web tab declarations.

This module deliberately has no FastAPI or browser dependencies. Tasks can
declare a web tab without making the headless or Qt installations depend on
the web UI stack.
"""

from __future__ import annotations

import inspect
import importlib
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from ok.task.task import BaseTask


_TAB_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_OPERATION_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


@dataclass(frozen=True)
class WebTabConfig:
    """Metadata for a browser page owned by a task instance."""

    id: str
    name: str
    asset_dir: str | Path
    entrypoint: str = "index.js"
    icon: str = "code"
    position: Literal["scroll", "bottom"] = "scroll"
    add_after_default_tabs: bool = True
    task_controls: bool = True

    def __post_init__(self) -> None:
        if not _TAB_ID.fullmatch(self.id):
            raise ValueError(
                "WebTabConfig id must contain lowercase letters, digits, and single hyphens"
            )
        if not self.name.strip():
            raise ValueError("WebTabConfig name is required")
        if self.position not in {"scroll", "bottom"}:
            raise ValueError(f"Unsupported WebTabConfig position: {self.position}")
        entrypoint = Path(self.entrypoint)
        if entrypoint.is_absolute() or ".." in entrypoint.parts:
            raise ValueError("WebTabConfig entrypoint must stay inside asset_dir")

    @property
    def resolved_asset_dir(self) -> Path:
        return Path(self.asset_dir).resolve()

    @property
    def resolved_entrypoint(self) -> Path:
        return (self.resolved_asset_dir / self.entrypoint).resolve()


def _task_tab_operation(kind: Literal["query", "action"], name: str):
    if not _OPERATION_NAME.fullmatch(name):
        raise ValueError(f"Invalid task tab operation name: {name}")

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        setattr(function, "__task_tab_operation__", (kind, name))
        return function

    return decorate


def task_tab_query(name: str):
    """Expose a read-only, explicitly named task method to its web tab."""

    return _task_tab_operation("query", name)


def task_tab_action(name: str):
    """Expose a mutating, explicitly named task method to its web tab."""

    return _task_tab_operation("action", name)


def task_tab_operations(task: BaseTask) -> dict[tuple[str, str], Callable[..., Any]]:
    """Return only methods explicitly allowlisted with the decorators above."""

    operations: dict[tuple[str, str], Callable[..., Any]] = {}
    # Static inspection is important here. BaseTask exposes properties such as
    # ``frame`` whose getters wait for device capture; evaluating every member
    # during web startup can therefore block before the server/window opens.
    for attribute_name, descriptor in inspect.getmembers_static(task):
        function = descriptor
        if isinstance(function, (staticmethod, classmethod)):
            function = function.__func__
        function = getattr(function, "__func__", function)
        operation = getattr(function, "__task_tab_operation__", None)
        if operation is None:
            continue
        method = getattr(task, attribute_name)
        if operation in operations:
            raise ValueError(
                f"Duplicate task tab operation {operation[0]}/{operation[1]} "
                f"on {task.__class__.__name__}"
            )
        operations[operation] = method
    return operations


def call_task_tab_operation(
    task: BaseTask,
    kind: Literal["query", "action"],
    name: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Invoke one allowlisted operation with either zero args or one payload."""

    method = task_tab_operations(task).get((kind, name))
    if method is None:
        raise ValueError(f"Unknown task tab {kind}: {name}")
    parameters = list(inspect.signature(method).parameters.values())
    if not parameters:
        return method()
    if len(parameters) == 1:
        return method(payload or {})
    raise TypeError(
        f"Task tab operation {task.__class__.__name__}.{method.__name__} "
        "must accept zero arguments or one payload argument"
    )


class WebCustomTab(BaseTask):
    """A non-runnable task-shaped service that owns a browser-only page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visible = False
        self.support_schedule_task = False


def configured_web_custom_tabs(web_tabs) -> list[list[str]]:
    """Validate task-backed pages from the web-only ``web_tabs`` config."""

    resolved: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in web_tabs or []:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError("Each web_tabs entry must be [module, class_name]")
        task_module, task_class = entry
        if not isinstance(task_module, str) or not isinstance(task_class, str):
            raise TypeError("web_tabs module and class_name must be strings")
        identity = (task_module, task_class)
        if identity in seen:
            continue
        if importlib.util.find_spec(task_module) is None:
            raise ModuleNotFoundError(f"Configured web tab module not found: {task_module}")
        candidate = getattr(importlib.import_module(task_module), task_class, None)
        if not isinstance(candidate, type) or not issubclass(candidate, WebCustomTab):
            raise TypeError(
                f"Configured web tab {task_module}.{task_class} must extend WebCustomTab"
            )
        seen.add(identity)
        resolved.append([task_module, task_class])
    return resolved
