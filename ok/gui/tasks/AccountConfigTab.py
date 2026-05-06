from __future__ import annotations

import copy
from typing import Any, Dict

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    FluentIcon,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    SwitchButton,
    TextEdit,
)

from ok import Logger, og
from ok.gui.tasks.ConfigCard import ConfigCard
from ok.gui.tasks.LabelAndWidget import LabelAndWidget
from ok.gui.widget.CustomTab import CustomTab
from ok.task.account_scope_store import (
    load_overrides,
    parse_account_list_text,
    save_overrides,
    sync_account_list_text,
)

logger = Logger.get_logger(__name__)


class _InMemoryConfig(dict):
    """Lightweight config proxy used by ConfigCard to represent per-account overrides."""

    def __init__(self, initial: Dict[str, Any], defaults: Dict[str, Any]):
        super().__init__(initial)
        self._defaults = defaults

    def get_default(self, key):
        return self._defaults.get(key)

    def has_user_config(self):
        return any(not str(k).startswith("_") for k in self.keys())

    def reset_to_default(self):
        for key, value in self._defaults.items():
            self[key] = copy.deepcopy(value)


class AccountConfigTab(CustomTab):
    """
    A GUI tab for managing per-account task configuration overrides.

    Users can:
    1. Maintain an account list (username per line, optional comma-separated password).
    2. Select an account and a task to view / modify that task's per-account parameters.
    3. Save or clear per-account overrides.

    Tasks opt-in by setting ``task.support_multi_account = True``.
    """

    def __init__(self):
        super().__init__()
        self._loaded_once = False
        self._building = False

        self._overrides: Dict[str, Any] = {"accounts": {}}
        self._task_map: Dict[str, Any] = {}
        self._current_virtual_config: _InMemoryConfig | None = None
        self._active_task = None
        self._active_account_key = ""
        self._active_account_name = ""
        self._current_editable_keys: list[str] = []
        self._current_base_values: Dict[str, Any] = {}
        self._account_display_to_key: Dict[str, str] = {}
        self._account_display_to_name: Dict[str, str] = {}

        self._build_ui()

    # ------------------------------------------------------------------
    # CustomTab interface
    # ------------------------------------------------------------------

    @property
    def name(self):
        return self.tr("Account Config")

    @property
    def position(self):
        return NavigationItemPosition.TOP

    @property
    def add_after_default_tabs(self):
        return False

    @property
    def icon(self):
        return FluentIcon.PEOPLE

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- tip ----
        tip_widget = QWidget()
        tip_layout = QVBoxLayout(tip_widget)
        tip_layout.setContentsMargins(0, 0, 0, 0)
        tip = BodyLabel(
            self.tr(
                "Configure per-account task parameters.\n"
                "Select an account, then select a task — the task's config widgets will appear below.\n"
                "Only tasks with support_multi_account=True are listed."
            )
        )
        tip.setWordWrap(True)
        tip_layout.addWidget(tip)
        self.add_card(self.tr("Account Config Center"), tip_widget)

        # ---- account list ----
        base_widget = QWidget()
        base_layout = QVBoxLayout(base_widget)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_layout.setSpacing(8)

        account_list_row = LabelAndWidget(
            self.tr("Account List"),
            self.tr("One account per line: username or username,password"),
        )
        self.account_list_edit = TextEdit()
        self.account_list_edit.setMinimumHeight(120)
        self.account_list_edit.setPlaceholderText("account1\naccount2,password2")
        account_list_row.add_widget(self.account_list_edit, stretch=1)
        base_layout.addWidget(account_list_row)

        action_row = LabelAndWidget(self.tr("Account List Actions"))
        btn_layout = QHBoxLayout()
        self.save_base_btn = PrimaryPushButton(self.tr("Save Account List"))
        self.refresh_btn = PushButton(self.tr("Refresh"))
        btn_layout.addWidget(self.save_base_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch(1)
        action_row.add_layout(btn_layout, stretch=1)
        base_layout.addWidget(action_row)

        self.add_card(self.tr("Account Base Settings"), base_widget)

        # ---- account/task selector ----
        selector_widget = QWidget()
        selector_layout = QVBoxLayout(selector_widget)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(8)

        account_row = LabelAndWidget(
            self.tr("Account"),
            self.tr("Select from account list or existing overrides"),
        )
        account_row_inner = QHBoxLayout()
        self.account_selector = ComboBox()
        self.account_selector.setMinimumWidth(220)
        self.refresh_account_btn = PushButton(self.tr("Refresh"))
        self.clear_account_btn = PushButton(self.tr("Clear All Overrides for Account"))
        account_row_inner.addWidget(self.account_selector)
        account_row_inner.addWidget(self.refresh_account_btn)
        account_row_inner.addWidget(self.clear_account_btn)
        account_row_inner.addStretch(1)
        account_row.add_layout(account_row_inner, stretch=1)
        selector_layout.addWidget(account_row)

        task_row = LabelAndWidget(
            self.tr("Task"),
            self.tr("Select task to auto-render config widgets"),
        )
        task_row_inner = QHBoxLayout()
        self.task_selector = ComboBox()
        self.task_selector.setMinimumWidth(280)
        self.refresh_task_btn = PushButton(self.tr("Refresh"))
        task_row_inner.addWidget(self.task_selector)
        task_row_inner.addWidget(self.refresh_task_btn)
        task_row_inner.addStretch(1)
        task_row.add_layout(task_row_inner, stretch=1)
        selector_layout.addWidget(task_row)

        view_row = LabelAndWidget(
            self.tr("View"),
            self.tr("Show only items that differ from the base config"),
        )
        self.diff_switch = SwitchButton()
        self.diff_switch.setOnText(self.tr("Diff Only"))
        self.diff_switch.setOffText(self.tr("All"))
        view_row.add_widget(self.diff_switch, stretch=0)
        selector_layout.addWidget(view_row)

        override_action_row = LabelAndWidget(self.tr("Override Actions"))
        override_action_inner = QHBoxLayout()
        self.save_override_btn = PrimaryPushButton(self.tr("Save Override for Account+Task"))
        self.clear_task_override_btn = PushButton(self.tr("Clear Override for Task"))
        override_action_inner.addWidget(self.save_override_btn)
        override_action_inner.addWidget(self.clear_task_override_btn)
        override_action_inner.addStretch(1)
        override_action_row.add_layout(override_action_inner, stretch=1)
        selector_layout.addWidget(override_action_row)

        self.add_card(self.tr("Account & Task Selector"), selector_widget)

        # ---- editor area ----
        editor_widget = QWidget()
        self._editor_layout = QVBoxLayout(editor_widget)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)
        self._editor_layout.setSpacing(8)
        self._editor_layout.addWidget(BodyLabel(self.tr("Please select an account and a task first")))
        self.add_card(self.tr("Task Property Editor"), editor_widget)

        # ---- status ----
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = BodyLabel(self.tr("Ready"))
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        self.add_card(self.tr("Status"), status_widget)

        # ---- connect ----
        self.save_base_btn.clicked.connect(self._on_save_base)
        self.refresh_btn.clicked.connect(self._refresh_from_source)
        self.refresh_account_btn.clicked.connect(self._rebuild_account_selector)
        self.refresh_task_btn.clicked.connect(self._rebuild_task_selector)
        self.clear_account_btn.clicked.connect(self._clear_current_account_overrides)
        self.account_selector.currentTextChanged.connect(self._on_account_changed)
        self.task_selector.currentTextChanged.connect(self._on_task_changed)
        self.diff_switch.checkedChanged.connect(self._on_view_mode_changed)
        self.save_override_btn.clicked.connect(self._on_save_override)
        self.clear_task_override_btn.clicked.connect(self._on_clear_task_override)

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded_once and self.executor is not None:
            self._loaded_once = True
            self._refresh_from_source()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _collect_multi_account_tasks(self):
        if self.executor is None:
            return []
        tasks = []
        seen = set()
        for task in list(getattr(self.executor, "onetime_tasks", [])) + list(
                getattr(self.executor, "trigger_tasks", [])
        ):
            if not getattr(task, "support_multi_account", False):
                continue
            class_name = task.__class__.__name__
            if class_name in seen:
                continue
            seen.add(class_name)
            tasks.append(task)
        return tasks

    @staticmethod
    def _is_supported_value(value: Any) -> bool:
        return isinstance(value, (bool, int, float, str, list))

    @staticmethod
    def _coerce(base_value: Any, value: Any) -> Any:
        if base_value is None or value is None:
            return value
        if isinstance(base_value, bool):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                t = value.strip().lower()
                if t in {"true", "1", "yes", "on"}:
                    return True
                if t in {"false", "0", "no", "off"}:
                    return False
            return base_value
        if isinstance(base_value, int) and not isinstance(base_value, bool):
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                try:
                    return int(value.strip())
                except ValueError:
                    return base_value
            return base_value
        if isinstance(base_value, float):
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.strip())
                except ValueError:
                    return base_value
            return base_value
        if isinstance(base_value, list):
            return value if isinstance(value, list) else base_value
        if isinstance(base_value, str):
            return str(value)
        return value if isinstance(value, type(base_value)) else base_value

    def _resolve_account_key_from_display(self, display: str) -> str:
        return self._account_display_to_key.get(display.strip(), "")

    def _resolve_account_name_from_display(self, display: str) -> str:
        return self._account_display_to_name.get(display.strip(), "")

    def _current_account_key(self) -> str:
        return self._resolve_account_key_from_display(self.account_selector.currentText())

    def _current_account_name(self) -> str:
        return self._resolve_account_name_from_display(self.account_selector.currentText())

    def _current_task(self):
        return self._task_map.get(self.task_selector.currentText().strip())

    def _get_account_name_by_key(self, account_key: str) -> str:
        if not account_key:
            return ""
        registry = self._overrides.get("account_registry") or {}
        meta = registry.get(account_key)
        if isinstance(meta, dict):
            username = str(meta.get("username", "") or "").strip()
            if username:
                return username
        return account_key

    def _resolve_key_for_username(self, username: str) -> str:
        username = username.strip()
        if not username:
            return ""
        registry = self._overrides.get("account_registry") or {}
        for account_id, meta in registry.items():
            if not isinstance(meta, dict):
                continue
            if str(meta.get("username", "") or "").strip() == username:
                return account_id
        return username

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_from_source(self):
        if self.executor is None:
            self._set_status(self.tr("Executor not ready"))
            return
        self._building = True
        try:
            self._overrides = load_overrides(force=True)
            self.account_list_edit.setPlainText(
                str(self._overrides.get("account_list_text", "") or "")
            )
            self._rebuild_account_selector(keep_selection=False)
            self._rebuild_task_selector(keep_selection=False)
            self._render_task_editor()
            tasks = self._collect_multi_account_tasks()
            if not tasks:
                self._set_status(self.tr("No tasks with support_multi_account=True found"))
            else:
                self._set_status(self.tr("Refreshed account and task config"))
        finally:
            self._building = False

    # ------------------------------------------------------------------
    # Account list management
    # ------------------------------------------------------------------

    def _on_save_base(self):
        if self.executor is None:
            self._set_status(self.tr("Executor not ready"))
            return
        account_list_text = self.account_list_edit.toPlainText().strip()
        summary = sync_account_list_text(account_list_text)
        self._overrides = load_overrides(force=True)
        self._rebuild_account_selector()
        msg = (
            self.tr("Account list saved")
            + f" (reused: {summary.get('reused_count', 0)}, "
            + f"created: {summary.get('created_count', 0)})"
        )
        inv = int(summary.get("invalid_count", 0) or 0)
        if inv:
            msg += self.tr(f"; {inv} invalid lines skipped")
        self._set_status(msg)

    # ------------------------------------------------------------------
    # Selectors
    # ------------------------------------------------------------------

    def _rebuild_account_selector(self, keep_selection: bool = True):
        current_key = self._current_account_key() if keep_selection else ""

        raw_items: list[tuple[str, str]] = []
        for entry in parse_account_list_text(self.account_list_edit.toPlainText()):
            username = str(entry.get("username", "")).strip()
            if not username:
                continue
            account_key = self._resolve_key_for_username(username) or username
            raw_items.append((account_key, username))

        for account_key in (self._overrides.get("accounts") or {}).keys():
            display_name = self._get_account_name_by_key(account_key)
            raw_items.append((str(account_key), display_name))

        dedup: list[tuple[str, str]] = []
        seen_keys: set[str] = set()
        for account_key, account_name in raw_items:
            if not account_key or account_key in seen_keys:
                continue
            seen_keys.add(account_key)
            dedup.append((account_key, account_name))

        self._account_display_to_key = {}
        self._account_display_to_name = {}

        self.account_selector.blockSignals(True)
        self.account_selector.clear()

        used_display: set[str] = set()
        for account_key, account_name in dedup:
            display = account_name or account_key
            if display in used_display:
                display = f"{display} ({account_key[-6:]})"
            used_display.add(display)
            self.account_selector.addItem(display)
            self._account_display_to_key[display] = account_key
            self._account_display_to_name[display] = account_name or account_key

        self.account_selector.blockSignals(False)

        if current_key:
            for display, key in self._account_display_to_key.items():
                if key == current_key:
                    self.account_selector.setCurrentText(display)
                    break

        if self.account_selector.count() > 0 and self.account_selector.currentIndex() < 0:
            self.account_selector.setCurrentIndex(0)

    def _rebuild_task_selector(self, keep_selection: bool = True):
        current_class_name = ""
        if keep_selection:
            current_task = self._current_task()
            if current_task is not None:
                current_class_name = current_task.__class__.__name__

        self._task_map = {}
        displays = []
        for task in self._collect_multi_account_tasks():
            display = f"{task.name} ({task.__class__.__name__})"
            self._task_map[display] = task
            displays.append(display)

        self.task_selector.blockSignals(True)
        self.task_selector.clear()
        for display in displays:
            self.task_selector.addItem(display)
        self.task_selector.blockSignals(False)

        if current_class_name:
            for display, task in self._task_map.items():
                if task.__class__.__name__ == current_class_name:
                    self.task_selector.setCurrentText(display)
                    return

        if displays:
            self.task_selector.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_account_changed(self, _):
        if not self._building:
            self._render_task_editor()

    def _on_task_changed(self, _):
        if not self._building:
            self._render_task_editor()

    def _on_view_mode_changed(self, _):
        if not self._building:
            self._render_task_editor()

    # ------------------------------------------------------------------
    # Editor rendering
    # ------------------------------------------------------------------

    def _build_virtual_config(self, task, account_key: str, account_name: str, only_diff: bool):
        task_class = task.__class__.__name__
        accounts = self._overrides.get("accounts") or {}
        account_map = accounts.get(account_key, {})
        if account_name and (
                not isinstance(account_map, dict)
                or (not account_map and account_name in accounts)
        ):
            legacy = accounts.get(account_name, {})
            if isinstance(legacy, dict):
                account_map = legacy
        task_override = account_map.get(task_class, {}) if isinstance(account_map, dict) else {}

        defaults: Dict[str, Any] = {}
        initial: Dict[str, Any] = {}
        base_values: Dict[str, Any] = {}
        editable_keys: list[str] = []
        total = 0

        _MULTI_ACCOUNT_INTERNAL_KEYS = {
            "Multi Account Mode",
            "Multi Account Independent Config",
            "Account List",
        }

        for key, default_value in task.default_config.items():
            if str(key).startswith("_"):
                continue
            if key in _MULTI_ACCOUNT_INTERNAL_KEYS:
                continue
            type_meta = task.config_type.get(key) if task.config_type else None
            if type_meta and type_meta.get("type") == "global":
                continue
            if not self._is_supported_value(default_value):
                continue

            total += 1
            base_value = task.config.get(key, default_value)
            override_value = task_override.get(key, base_value)
            value = self._coerce(base_value, override_value)

            if only_diff and value == base_value:
                continue

            defaults[key] = default_value
            initial[key] = value
            base_values[key] = base_value
            editable_keys.append(key)

        config_group = self._filter_config_group(
            getattr(task, "default_config_group", None),
            set(editable_keys),
            _MULTI_ACCOUNT_INTERNAL_KEYS,
        )

        return _InMemoryConfig(initial, defaults), editable_keys, base_values, total, config_group

    def _filter_config_group(self, config_group, allowed_keys: set[str], excluded_keys: set[str]):
        if not isinstance(config_group, dict) or not config_group:
            return {}

        def group_has_allowed(group_key: str) -> bool:
            children = config_group.get(group_key)
            if not isinstance(children, (list, tuple)):
                return False
            for child in children:
                if not isinstance(child, str) or child.startswith("_"):
                    continue
                if child in excluded_keys:
                    continue
                if child in allowed_keys:
                    return True
                if child in config_group and group_has_allowed(child):
                    return True
            return False

        filtered = {}
        for parent_key, children in config_group.items():
            if not isinstance(parent_key, str) or parent_key.startswith("_"):
                continue
            if parent_key in excluded_keys:
                continue
            if not group_has_allowed(parent_key):
                continue
            if not isinstance(children, (list, tuple)):
                continue
            filtered_children = []
            for child in children:
                if not isinstance(child, str) or child.startswith("_"):
                    continue
                if child in excluded_keys:
                    continue
                if child in allowed_keys:
                    filtered_children.append(child)
                    continue
                if child in config_group and group_has_allowed(child):
                    filtered_children.append(child)
            if filtered_children:
                filtered[parent_key] = filtered_children

        return filtered

    def _render_task_editor(self):
        self._clear_layout(self._editor_layout)
        self._current_virtual_config = None
        self._active_task = None
        self._active_account_key = ""
        self._active_account_name = ""
        self._current_editable_keys = []
        self._current_base_values = {}

        account_key = self._current_account_key()
        account_name = self._current_account_name()
        if not account_key:
            self._editor_layout.addWidget(BodyLabel(self.tr("Please select an account first")))
            return

        task = self._current_task()
        if task is None:
            self._editor_layout.addWidget(BodyLabel(self.tr("Please select a task first")))
            return

        only_diff = bool(self.diff_switch.isChecked())
        virtual_config, editable_keys, base_values, total, config_group = self._build_virtual_config(
            task, account_key, account_name, only_diff
        )

        if not editable_keys:
            if only_diff:
                self._editor_layout.addWidget(
                    BodyLabel(self.tr("No diff items for this account/task"))
                )
            else:
                self._editor_layout.addWidget(
                    BodyLabel(self.tr("No editable config for this task"))
                )
            return

        summary = (
            self.tr("View: ")
            + (self.tr("Diff Only") if only_diff else self.tr("All"))
            + f" | {len(editable_keys)} / {total} "
            + self.tr("items shown")
        )
        self._editor_layout.addWidget(BodyLabel(summary))

        card = ConfigCard(
            None,
            og.app.tr(task.name) + " - " + (account_name or account_key),
            virtual_config,
            self.tr("Override task config for this account. Unset keys fall back to task defaults."),
            {},
            task.config_description,
            task.config_type,
            getattr(task, "icon", None),
            config_group=config_group,
        )
        self._editor_layout.addWidget(card)

        self._current_virtual_config = virtual_config
        self._active_task = task
        self._active_account_key = account_key
        self._active_account_name = account_name
        self._current_editable_keys = editable_keys
        self._current_base_values = base_values

    # ------------------------------------------------------------------
    # Save / clear overrides
    # ------------------------------------------------------------------

    def _on_save_override(self):
        if (
                self._current_virtual_config is None
                or self._active_task is None
                or not self._active_account_key
        ):
            self._set_status(self.tr("Please select an account and a task first"))
            return

        diff: Dict[str, Any] = {}
        for key in self._current_editable_keys:
            current_value = self._current_virtual_config.get(key)
            base_value = self._current_base_values.get(key)
            if current_value != base_value:
                diff[key] = current_value

        accounts = self._overrides.setdefault("accounts", {})
        account_map = accounts.setdefault(self._active_account_key, {})
        task_class = self._active_task.__class__.__name__

        if diff:
            account_map[task_class] = diff
            self._set_status(
                self.tr("Saved")
                + f": {self._active_account_name or self._active_account_key}"
                + f" / {self._active_task.name}"
                + f" ({len(diff)} "
                + self.tr("items overridden")
                + ")"
            )
        else:
            account_map.pop(task_class, None)
            self._set_status(
                self.tr("No diff — override cleared:")
                + f" {self._active_account_name or self._active_account_key}"
                + f" / {self._active_task.name}"
            )

        if not account_map:
            accounts.pop(self._active_account_key, None)

        self._overrides = save_overrides(self._overrides)
        self._rebuild_account_selector()

    def _on_clear_task_override(self):
        account_key = self._current_account_key()
        account_name = self._current_account_name()
        task = self._current_task()
        if not account_key or task is None:
            self._set_status(self.tr("Please select an account and a task first"))
            return

        accounts = self._overrides.get("accounts", {})
        account_map = accounts.get(account_key, {})
        if account_name and (
                not isinstance(account_map, dict)
                or (not account_map and account_name in accounts)
        ):
            legacy = accounts.get(account_name, {})
            if isinstance(legacy, dict):
                account_map = legacy
                account_key = account_name

        task_class = task.__class__.__name__
        account_map.pop(task_class, None)
        if not account_map:
            accounts.pop(account_key, None)

        self._overrides = save_overrides(self._overrides)
        self._render_task_editor()
        self._rebuild_account_selector()
        self._set_status(
            self.tr("Override cleared:")
            + f" {account_name or account_key} / {task.name}"
        )

    def _clear_current_account_overrides(self):
        account_key = self._current_account_key()
        account_name = self._current_account_name()
        if not account_key:
            self._set_status(self.tr("Please select an account first"))
            return

        accounts = self._overrides.get("accounts", {})
        for key in (account_key, account_name):
            if key and key in accounts:
                accounts.pop(key, None)

        self._overrides = save_overrides(self._overrides)
        self._rebuild_account_selector()
        self._render_task_editor()
        self._set_status(
            self.tr("All overrides cleared for account:")
            + f" {account_name or account_key}"
        )
