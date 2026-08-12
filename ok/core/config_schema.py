"""Headless config-field resolution shared by Qt and web renderers."""

from __future__ import annotations


def resolve_config_type(type_spec, default_value):
    if not isinstance(type_spec, dict):
        return None
    resolved = type_spec.get("type")
    if resolved:
        return resolved
    if "buttons" in type_spec or "callback" in type_spec:
        return "button"
    if "options" in type_spec:
        return "multi_selection" if isinstance(default_value, list) else "drop_down"
    return None


def normalize_config_keys(keys):
    if keys is None:
        return []
    return [keys] if isinstance(keys, str) else list(keys)


def config_visibility(config, config_types):
    types = config_types or {}

    def active_keys(rules, value):
        if isinstance(value, list):
            return {key for choice in value for key in normalize_config_keys(rules.get(choice))}
        try:
            return set(normalize_config_keys(rules.get(value)))
        except TypeError:
            return set()

    def visible(key, checking=None):
        checking = set(checking or ())
        if key in checking:
            return False
        checking.add(key)
        for parent_key, parent_type in types.items():
            rules = parent_type.get("sub_configs") if isinstance(parent_type, dict) else None
            if not isinstance(rules, dict):
                continue
            controlled = {item for keys in rules.values() for item in normalize_config_keys(keys)}
            if key in controlled and (
                    not visible(parent_key, checking)
                    or key not in active_keys(rules, config.get(parent_key))):
                return False
        return True

    return visible


def build_config_fields(config, descriptions=None, config_types=None, defaults=None,
                        serialize=lambda value: value):
    if not config:
        return []
    descriptions = descriptions or {}
    config_types = config_types or {}
    defaults = defaults or {}
    sub_config_keys = {
        key
        for parent_type in config_types.values()
        for rules in [parent_type.get("sub_configs") if isinstance(parent_type, dict) else None]
        if isinstance(rules, dict)
        for controlled in rules.values()
        for key in normalize_config_keys(controlled)
    }
    visible = config_visibility(config, config_types)
    fields = []
    for key, value in config.items():
        if str(key).startswith("_"):
            continue
        type_spec = config_types.get(key)
        if isinstance(type_spec, dict) and type_spec.get("hidden"):
            continue
        if not visible(key):
            continue
        default = defaults.get(key, value)
        resolved = resolve_config_type(type_spec, default)
        if resolved in {"button", "global"}:
            continue
        options = type_spec.get("options") if isinstance(type_spec, dict) else None
        options_available = type_spec.get("options_available") if isinstance(type_spec, dict) else None
        if resolved == "drop_down":
            kind = "list" if isinstance(default, list) and options_available is not None else "select"
        elif resolved == "multi_selection":
            kind = "multi_selection"
        elif resolved == "text_edit":
            kind = "multiline"
        elif resolved == "file_selector":
            kind = "file"
        elif resolved == "line_edit":
            kind = "text"
        elif isinstance(default, bool):
            kind = "boolean"
        elif isinstance(default, int):
            kind = "integer"
        elif isinstance(default, float):
            kind = "number"
        elif isinstance(default, list):
            kind = "list"
        elif isinstance(default, str) and (len(default) > 16 or "\n" in default):
            kind = "multiline"
        else:
            kind = "text"
        fields.append({
            "key": str(key),
            "value": serialize(value),
            "default": serialize(defaults.get(key)),
            "description": str(descriptions.get(key) or ""),
            "kind": kind,
            "options": serialize(options if options is not None else options_available),
            "allow_duplication": bool(type_spec.get("allow_duplication", False)) if isinstance(type_spec, dict) else False,
            "minimum": type_spec.get("min") if isinstance(type_spec, dict) else None,
            "maximum": type_spec.get("max") if isinstance(type_spec, dict) else None,
            "sub_config": key in sub_config_keys,
        })
    return fields
