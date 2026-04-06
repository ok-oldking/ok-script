import copy
import json
import os
import threading
import uuid
from typing import Any, Dict

from ok.util.file import ensure_dir_for_file, get_relative_path

_STORE_PATH = get_relative_path("configs", "account_scoped_overrides.json")
_LOCK = threading.Lock()
_CACHE_MTIME = object()
_EMPTY_STORE: Dict[str, Any] = {
    "account_list_text": "",
    "account_registry": {},
    "accounts": {},
}
_CACHE_DATA: Dict[str, Any] = copy.deepcopy(_EMPTY_STORE)


def _new_store() -> Dict[str, Any]:
    return copy.deepcopy(_EMPTY_STORE)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _clean_username(value: Any) -> str:
    return _clean_text(value).strip()


def _normalize_registry(raw_registry: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw_registry, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_account_id, raw_meta in raw_registry.items():
        if not isinstance(raw_account_id, str):
            continue
        account_id = raw_account_id.strip()
        if not account_id:
            continue

        username = ""
        aliases = []
        if isinstance(raw_meta, dict):
            username = _clean_username(raw_meta.get("username", ""))
            raw_aliases = raw_meta.get("aliases", [])
            if isinstance(raw_aliases, list):
                for raw_alias in raw_aliases:
                    alias = _clean_username(raw_alias)
                    if alias and alias not in aliases:
                        aliases.append(alias)
        elif isinstance(raw_meta, str):
            username = _clean_username(raw_meta)

        if username and username not in aliases:
            aliases.insert(0, username)
        if not username and aliases:
            username = aliases[0]
        if not username:
            continue

        normalized[account_id] = {"username": username, "aliases": aliases}

    return normalized


def _normalize_accounts(raw_accounts: Any) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not isinstance(raw_accounts, dict):
        return {}

    result: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for raw_account_key, raw_task_map in raw_accounts.items():
        if not isinstance(raw_account_key, str) or not isinstance(raw_task_map, dict):
            continue
        account_key = raw_account_key.strip()
        if not account_key:
            continue
        normalized_task_map: Dict[str, Dict[str, Any]] = {}
        for raw_task_name, raw_override_map in raw_task_map.items():
            if not isinstance(raw_task_name, str) or not isinstance(raw_override_map, dict):
                continue
            task_name = raw_task_name.strip()
            if not task_name:
                continue
            normalized_task_map[task_name] = dict(raw_override_map)
        if normalized_task_map:
            result[account_key] = normalized_task_map
    return result


def _find_account_id_by_username(
        registry: Dict[str, Dict[str, Any]],
        username: str,
        include_aliases: bool = False,
) -> str:
    if not username:
        return ""

    exact_matches = []
    alias_matches = []
    for account_id, meta in registry.items():
        current_username = _clean_username(meta.get("username", ""))
        if current_username == username:
            exact_matches.append(account_id)
            continue
        if include_aliases:
            aliases = meta.get("aliases", [])
            if isinstance(aliases, list) and username in aliases:
                alias_matches.append(account_id)

    if exact_matches:
        return sorted(exact_matches)[0]
    if include_aliases and alias_matches:
        return sorted(alias_matches)[0]
    return ""


def _generate_account_id(registry: Dict[str, Dict[str, Any]]) -> str:
    while True:
        account_id = f"acc_{uuid.uuid4().hex[:12]}"
        if account_id not in registry:
            return account_id


def _ensure_registry_entry(
        registry: Dict[str, Dict[str, Any]],
        username: str,
        account_id: str | None = None,
) -> str:
    username = _clean_username(username)
    if not username:
        return ""

    if account_id:
        account_id = account_id.strip()
    if not account_id:
        account_id = _generate_account_id(registry)

    meta = registry.setdefault(account_id, {"username": username, "aliases": [username]})
    aliases = meta.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []
    if username not in aliases:
        aliases.append(username)
    meta["aliases"] = aliases
    meta["username"] = username
    return account_id


def _normalize(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return _new_store()
    return {
        "account_list_text": _clean_text(data.get("account_list_text", "")),
        "account_registry": _normalize_registry(data.get("account_registry")),
        "accounts": _normalize_accounts(data.get("accounts")),
    }


def load_overrides(force: bool = False) -> Dict[str, Any]:
    global _CACHE_DATA, _CACHE_MTIME
    with _LOCK:
        current_mtime = os.path.getmtime(_STORE_PATH) if os.path.exists(_STORE_PATH) else None
        if not force and current_mtime == _CACHE_MTIME:
            return copy.deepcopy(_CACHE_DATA)

        if current_mtime is None:
            data = _new_store()
        else:
            try:
                with open(_STORE_PATH, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except Exception:
                data = _new_store()

        normalized = _normalize(data)
        _CACHE_DATA = normalized
        _CACHE_MTIME = current_mtime
        return copy.deepcopy(normalized)


def save_overrides(data: Dict[str, Any]) -> Dict[str, Any]:
    global _CACHE_DATA, _CACHE_MTIME
    normalized = _normalize(data)
    with _LOCK:
        ensure_dir_for_file(_STORE_PATH)
        with open(_STORE_PATH, "w", encoding="utf-8") as fp:
            json.dump(normalized, fp, ensure_ascii=False, indent=2)
        _CACHE_DATA = normalized
        _CACHE_MTIME = os.path.getmtime(_STORE_PATH)
    return copy.deepcopy(normalized)


def resolve_account_id(username: str, create_if_missing: bool = False) -> str:
    account_name = _clean_username(username)
    if not account_name:
        return ""

    data = load_overrides(force=create_if_missing)
    registry = data.setdefault("account_registry", {})
    account_id = _find_account_id_by_username(registry, account_name)
    if account_id or not create_if_missing:
        return account_id

    account_id = _ensure_registry_entry(registry, account_name)
    save_overrides(data)
    return account_id


def parse_account_list_text(text: str) -> list:
    """
    Parse a plain-text account list where each line is "username" or "username,password".

    Returns:
        List of dicts with keys "username" and "password".
    """
    entries = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "," in line:
            username_part, password_part = line.split(",", 1)
        else:
            username_part, password_part = line, ""
        username = username_part.strip()
        if not username:
            continue
        entries.append({"username": username, "password": password_part.strip()})
    return entries


def sync_account_list_text(account_list_text: str) -> Dict[str, Any]:
    """
    Persist account_list_text and update account_registry so each username is
    assigned a stable account-id.

    Returns summary dict with keys:
        - reused_count:   number of usernames that already had an account-id
        - created_count:  number of new account-ids created
        - invalid_count:  number of lines that were skipped
    """
    data = load_overrides(force=True)
    registry = data.setdefault("account_registry", {})

    data["account_list_text"] = account_list_text

    reused = 0
    created = 0
    invalid = 0

    for raw_line in (account_list_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "," in line:
            username_part = line.split(",", 1)[0].strip()
        else:
            username_part = line.strip()
        if not username_part:
            invalid += 1
            continue
        existing_id = _find_account_id_by_username(registry, username_part)
        if existing_id:
            reused += 1
        else:
            _ensure_registry_entry(registry, username_part)
            created += 1

    save_overrides(data)
    return {"reused_count": reused, "created_count": created, "invalid_count": invalid}


def get_account_task_overrides(account: str, task_name: str, account_name: str = "") -> Dict[str, Any]:
    if not account or not task_name:
        return {}

    data = load_overrides()
    accounts = data.get("accounts") or {}
    registry = data.get("account_registry") or {}

    account_key = _clean_username(account)
    name_key = _clean_username(account_name)

    resolved_key = ""
    if account_key in accounts:
        resolved_key = account_key
    elif account_key in registry:
        resolved_key = account_key
    elif account_key:
        resolved_key = _find_account_id_by_username(registry, account_key)
    if not resolved_key and name_key:
        resolved_key = _find_account_id_by_username(registry, name_key)

    if resolved_key and isinstance(accounts.get(resolved_key), dict):
        return dict(accounts.get(resolved_key, {}).get(task_name, {}))

    legacy_key = name_key or account_key
    if legacy_key and isinstance(accounts.get(legacy_key), dict):
        return dict(accounts.get(legacy_key, {}).get(task_name, {}))
    return {}
