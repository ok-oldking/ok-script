"""
计划任务索引启动时校正 (schedule_index_sync)

背景
----
ok-script 的 Windows 计划任务通过 `-t N`（1-based 索引）定位 onetime_tasks。
当 config.py 中 onetime_tasks 顺序被重排（例如业务任务前置、测试任务后置）后，
已创建的计划任务仍指向旧索引，导致计划任务执行到错误任务（如 -t 15 从
「启动一次游戏」跑到 TestDemoGraphic）。

方案
----
启动时先从本地缓存解析本次启动参数；Windows 计划任务迁移在后台线程执行，
不会阻塞窗口显示。自动校正并把 -t 目标统一迁移为稳定标识（模块路径.类名，如
``src.tasks.onetime.DailyTask``，对排序免疫）：

1. 读取 schedule_tasks_cache.json；
2. 只处理本应用（如 ``\\ok-ef\\``）下的任务，其它 ok-* 应用的只读任务不动；
3. 解析缓存任务当前的 -t 目标（数字索引 / 历史任务名 / 模块路径.类名），
   以缓存任务名（创建时选择的任务名，不随排序变化）或已缓存的稳定标识为权威身份，
   在当前 ``onetime_tasks`` 中定位目标任务；
4. 把 `-t X` 统一改写为当前实际的 ``模块路径.类名``（旧数字索引、历史任务名、
   过期模块路径均迁移），并同步更新缓存 / xml_config / Windows 计划任务
   （COM，失败回退 schtasks）；同时回填缓存的 ``task_index`` / ``task_identifier``
   元数据（无需改写 Windows 时仅回填元数据）；
5. GUI 在启动前从本地缓存改写本次进程参数；后台迁移不再改写运行中进程参数；
6. 幂等：每次进程只校正一次，目标与元数据均已正确时不写文件、不调 COM，
   找不到 name 的任务跳过。

调用点
------
- ``MainWindow.__init__``：仅调用 resolve_current_schedule_task 解析本地参数；
- ``ScheduleTaskTab``：后台迁移后重载缓存，再查询 Windows 计划任务；
- ``fix_schedule_task_refs.py``：headless 无法启动 GUI 时的手动校正，复用本模块。
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# 每次进程只校正一次
_SYNCED = False

# Windows 任务计划 RegisterTaskDefinition 的注册模式：CREATE_OR_UPDATE
_TASK_CREATE_OR_UPDATE = 6

# 匹配 -t 参数（值可为数字索引或历史迁移成的任务名；
# [^\s<] 保证 XML 中 `<Arguments>main.py -t 15</Arguments>` 也能正确截取）
_TASK_ARG_PATTERN = re.compile(r"(^|\s)-t\s+([^\s<]+)")


def reset_sync_guard():
    """重置进程级幂等 guard（仅测试使用）。"""
    global _SYNCED
    _SYNCED = False


def _onetime_tasks() -> List:
    """获取当前 onetime_tasks（测试可 monkeypatch）。"""
    try:
        from ok import og

        executor = getattr(og, "executor", None)
        if executor is not None:
            tasks = getattr(executor, "onetime_tasks", None)
            if tasks:
                return list(tasks)
    except Exception:
        logger.exception("schedule index sync: failed to read onetime_tasks")
    return []


def _cache_file() -> Optional[Path]:
    """返回 schedule_tasks_cache.json 路径（测试可 monkeypatch）。"""
    try:
        from ok import og

        config = getattr(og, "config", None) or {}
        config_folder = config.get("config_folder", "configs")
        return Path(config_folder) / "schedule_tasks_cache.json"
    except Exception:
        logger.exception("schedule index sync: failed to resolve cache file")
        return None


def _load_cache_data(cache_file: Path) -> Optional[dict]:
    """读取计划任务缓存并校验为有效字典；非字典或为空时返回 None。

    JSON 解析异常交由调用方统一处理（保持原有日志与返回值不变）。
    """
    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not data:
        return None
    return data


def _schedule_root_path() -> str:
    """返回本应用的 Windows 计划任务根路径（如 \\ok-ef），测试可 monkeypatch。"""
    try:
        from ok import og

        config = getattr(og, "config", None) or {}
        gui_title = config.get("gui_title", "ok-script")
        return f"\\{gui_title}"
    except Exception:
        return "\\ok-script"


def _is_own_task_path(path: str, root_path: str) -> bool:
    """判断任务路径是否属于本应用（与 WindowsScheduleManager._is_own_task_path 一致）。"""
    normalized_path = (path or "").rstrip("\\").lower()
    normalized_root = (root_path or "").rstrip("\\").lower()
    return normalized_path == normalized_root or normalized_path.startswith(f"{normalized_root}\\")


def _name_to_index_map(onetime_tasks: Sequence) -> Dict[str, int]:
    """构建任务标识 -> 当前 1-based 索引 的映射。

    一个任务会注册多个键：任务名、类名、模块路径.类名（稳定标识）。
    任务名重复（重名）时从映射中移除并记录警告，避免把缓存条目静默迁移到
    错误的同名任务；类名/模块路径重复时保持第一个（与既有行为一致）。
    重名检测使用独立的任务名集合，避免任务名与其它任务的类名/模块路径
    相同时被误判为重名。
    """
    id_to_index = {}
    seen_names = set()
    duplicated_names = set()
    for index, task in enumerate(onetime_tasks, start=1):
        name = getattr(task, "name", None)
        class_name = task.__class__.__name__
        module_path = f"{task.__class__.__module__}.{class_name}"
        if name:
            str_name = str(name)
            if str_name in seen_names:
                duplicated_names.add(str_name)
            else:
                seen_names.add(str_name)
                id_to_index[str_name] = index
        id_to_index.setdefault(class_name, index)
        id_to_index.setdefault(module_path, index)
    for name in duplicated_names:
        logger.warning(
            f"schedule index sync: duplicate task name {name!r}, skip name-based match"
        )
        id_to_index.pop(name, None)
    return id_to_index


def _task_at_index(onetime_tasks: Sequence, index: Optional[int]):
    """按 1-based 索引取 onetime_tasks 中的任务实例；越界/空返回 None。"""
    tasks = list(onetime_tasks or [])
    if index is None or not (1 <= index <= len(tasks)):
        return None
    return tasks[index - 1]


def _resolve_identifier_index(
        onetime_tasks: Sequence, identifier: str
) -> Optional[int]:
    """给定标识（模块路径.类名）在当前 onetime_tasks 中解析索引。

    优先按"模块路径.类名"精确匹配；匹配失败（项目重构/模块移动/目录重命名）
    时回退到按类名匹配当前任务，视为同一任务类。
    """
    if not identifier:
        return None
    identifier = str(identifier).strip()
    tasks = list(onetime_tasks or [])
    if not tasks:
        return None

    def full_match(candidate, target):
        return f"{candidate.__class__.__module__}.{candidate.__class__.__name__}".lower() == target.lower()

    def class_match(candidate, target):
        return candidate.__class__.__name__.lower() == target.rsplit(".", 1)[-1].lower()

    exact = [i for i, t in enumerate(tasks, start=1) if full_match(t, identifier)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        logger.warning(
            f"schedule index sync: multiple tasks match identifier {identifier!r}, skip"
        )
        return None

    # 模块路径匹配失败：回退到类名（兼容模块路径变化）
    by_class = [i for i, t in enumerate(tasks, start=1) if class_match(t, identifier)]
    if len(by_class) == 1:
        return by_class[0]
    if len(by_class) > 1:
        logger.warning(
            f"schedule index sync: multiple tasks match class {identifier.rsplit('.', 1)[-1]!r}, skip"
        )
        return None
    return None


def _extract_task_target(item: dict) -> Optional[str]:
    """从缓存的 actions / xml_config 中提取当前 -t 的目标（索引或任务名）。"""
    for field in ("actions", "xml_config"):
        value = item.get(field)
        if isinstance(value, str):
            match = _TASK_ARG_PATTERN.search(value)
            if match:
                return match.group(2).strip()
    return None


def _replace_task_target(value: str, new_target) -> str:
    """把字符串中的 `-t X` 改写为 `-t {new_target}`（数字索引或模块路径.类名）。"""
    if not value:
        return value
    return _TASK_ARG_PATTERN.sub(lambda m: f"{m.group(1)}-t {new_target}", value)


def _register_task_xml_via_schtasks(path: str, new_xml: str) -> bool:
    """通过 schtasks 命令用新 XML 更新计划任务（COM 不可用时的回退）。

    返回是否注册成功。
    """
    import subprocess
    import tempfile

    xml_file: Optional[Path] = None
    try:
        # UTF-16 LE with BOM（Windows 任务计划要求）
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-16", suffix=".xml", prefix="ok_task_sync_", delete=False) as f:
            f.write(new_xml)
            xml_file = Path(f.name)

        cmd = ["schtasks", "/Create", "/XML", str(xml_file), "/TN", path, "/F"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            logger.info(f"schedule index sync: updated task {path} via schtasks")
            return True
        logger.error(f"schedule index sync: schtasks update failed for {path}: {result.stderr}")
        return False
    except Exception:
        logger.exception(f"schedule index sync: schtasks update failed for {path}")
        return False
    finally:
        if xml_file and xml_file.exists():
            try:
                xml_file.unlink()
            except Exception:
                pass


def _register_task_xml(path: str, new_xml: str) -> bool:
    """用更新后的 XML 重新注册 Windows 计划任务（测试可 monkeypatch）。

    优先 COM（RegisterTaskDefinition CREATE_OR_UPDATE），失败时回退 schtasks。
    返回是否注册成功；path 或 new_xml 为空时返回 False。
    """
    if not path or not new_xml:
        return False
    pythoncom = None
    try:
        import pythoncom as com
        import win32com.client

        com.CoInitialize()
        pythoncom = com
        service = win32com.client.Dispatch("Schedule.Service")
        service.Connect()
        folder_path, task_file_name = path.rsplit("\\", 1)
        task_def = service.NewTask(0)
        task_def.XmlText = new_xml
        folder = service.GetFolder(folder_path or "\\")
        # logonType 传 0（TASK_LOGON_NONE）：让 Task Scheduler 使用 XML 中的
        # LogonType，保留原任务的运行身份（Password/S4U 等），避免被强制改为
        # InteractiveToken
        folder.RegisterTaskDefinition(
            task_file_name, task_def, _TASK_CREATE_OR_UPDATE, None, None, 0
        )
        logger.info(f"schedule index sync: updated task {path} via COM")
        return True
    except Exception as e:
        logger.warning(f"schedule index sync: COM update failed for {path}: {e}")
    finally:
        if pythoncom is not None:
            folder = task_def = service = None
            pythoncom.CoUninitialize()
    return _register_task_xml_via_schtasks(path, new_xml)


def _apply_correction(item: dict, new_target, index=None) -> bool:
    """改写单个缓存任务的 -t 目标为稳定标识，并同步 Windows 计划任务。

    new_target 为模块路径.类名（str）；index 为对应的 1-based 数字索引（可选）。
    仅当 Windows 计划任务（若存在）成功用新 XML 重新注册后，才改写缓存字段
    （xml_config / actions / task_index / task_identifier）并返回 True；
    注册失败或无法改写时返回 False，保持缓存不变，下次启动会重试。
    """
    old_xml = item.get("xml_config") or ""
    old_actions = item.get("actions") or ""
    new_xml = _replace_task_target(old_xml, new_target)
    new_actions = _replace_task_target(old_actions, new_target)

    path = item.get("path") or ""
    if not path:
        # 无 path 无法定位 Windows 计划任务：跳过并保持缓存不变，下次启动重试，
        # 避免缓存被改写但系统任务未同步、永久不一致
        logger.warning("schedule index sync: cache entry has no path, skip")
        return False
    if not old_xml:
        logger.error(f"schedule index sync: no xml_config to rewrite task {path}, skip")
        return False
    if new_xml == old_xml:
        # -t 目标可能只存在于 actions，xml_config 无可替换的 -t：
        # 此时无法通过 XML 更新 Windows 任务，跳过并保持缓存不变，避免缓存与系统不一致
        logger.error(
            f"schedule index sync: xml_config has no replaceable -t target for {path}, skip"
        )
        return False
    if not _register_task_xml(path, new_xml):
        logger.error(f"schedule index sync: failed to update task {path}, keep cache unchanged")
        return False

    item["xml_config"] = new_xml
    item["actions"] = new_actions
    if isinstance(new_target, int):
        item["task_index"] = new_target
    else:
        item["task_identifier"] = new_target
    if isinstance(index, int):
        item["task_index"] = index
    return True


def _collect_corrections(
        data: dict, name_to_index: Dict[str, int], root_path: str,
        onetime_tasks: Sequence = (),
) -> Tuple[List[Tuple[str, dict, object, object, int]], List[Tuple[str, dict, int, str]]]:
    """收集需要修正 / 回填的缓存任务。

    返回 (corrections, metadata_updates)：
      corrections: [(task_key, item, new_identifier, old_target, index), ...]
        -t 目标需要改写为稳定标识（需重新注册 Windows 计划任务）的条目；
      metadata_updates: [(task_key, item, index, identifier), ...]
        -t 目标已是稳定标识、仅需回填 task_index / task_identifier 元数据的条目。

    仅处理本应用（root_path）下的任务，统一迁移规则：
      - 旧格式 `-t N`（数字索引）：按任务名（缺失时回退缓存的稳定标识）定位
        当前任务，迁移为模块路径.类名；
      - 历史任务名格式（如 `-t 日常任务`）：按任务名定位，迁移为模块路径.类名；
      - `-t 模块路径.类名`：模块路径匹配失败（模块移动/重命名）且类名唯一匹配时，
        修正为当前实际的模块路径.类名。
    """
    corrections: List[Tuple[str, dict, object, object, int]] = []
    metadata_updates: List[Tuple[str, dict, int, str]] = []
    for task_key, item in data.items():
        if not isinstance(item, dict):
            continue
        # 只处理本应用（如 ok-ef）下的任务，其它 ok-* 应用只读任务不动
        if not _is_own_task_path(str(item.get("path") or task_key), root_path):
            continue
        old_target = _extract_task_target(item)
        if old_target is None:
            continue

        index: Optional[int] = None
        if "." in old_target:
            # 稳定标识格式（可能因模块移动而过期）
            index = _resolve_identifier_index(onetime_tasks, old_target)
        elif old_target.isdigit():
            # 旧数字索引格式：索引会漂移，优先按任务名定位当前任务
            name = item.get("name")
            if name and str(name) in name_to_index:
                index = name_to_index[str(name)]
            else:
                # 任务名缺失时回退缓存中的稳定标识
                cached_identifier = str(item.get("task_identifier") or "").strip()
                if cached_identifier:
                    index = _resolve_identifier_index(onetime_tasks, cached_identifier)
        else:
            # 历史任务名格式（如 -t 日常任务）：按任务名定位当前任务
            name = item.get("name")
            if not name or str(name) not in name_to_index:
                continue
            index = name_to_index[str(name)]

        if index is None:
            # 任务在当前 onetime_tasks 中找不到（已删除或无法唯一匹配），跳过
            continue
        task = _task_at_index(onetime_tasks, index)
        if task is None:
            continue
        identifier = f"{task.__class__.__module__}.{task.__class__.__name__}"

        if str(old_target) != identifier:
            corrections.append((task_key, item, identifier, old_target, index))
        elif item.get("task_index") != index or item.get("task_identifier") != identifier:
            metadata_updates.append((task_key, item, index, identifier))
    return corrections, metadata_updates


def _perform_corrections(corrections) -> Tuple[int, Dict[str, str]]:
    """逐项应用修正，返回 (成功修正数, 旧 -t 目标 -> 新目标 的 argv 映射)。

    new_target 为模块路径.类名（str）。仅统计并记录真正注册成功的修正；
    失败的条目保持缓存原样，下次启动会重试。
    """
    changed = 0
    argv_target_map: Dict[str, str] = {}
    for task_key, item, new_target, old_target, index in corrections:
        try:
            if _apply_correction(item, new_target, index):
                changed += 1
                argv_target_map.setdefault(str(old_target), str(new_target))
        except Exception:
            logger.exception(f"schedule index sync failed for {task_key}")
    return changed, argv_target_map


def _apply_metadata_updates(metadata_updates) -> int:
    """仅回填缓存元数据（task_index / task_identifier），不触碰 Windows 计划任务。

    适用于 -t 目标已是稳定标识、但缓存缺少定位元数据的条目（如旧版本创建、
    或被强制同步冲掉过）。返回回填的条目数。
    """
    changed = 0
    for task_key, item, index, identifier in metadata_updates:
        try:
            item["task_index"] = index
            item["task_identifier"] = identifier
            changed += 1
            logger.info(
                f"schedule index sync: backfilled metadata for {task_key} "
                f"(task_index={index}, task_identifier={identifier})"
            )
        except Exception:
            logger.exception(f"schedule index sync metadata backfill failed for {task_key}")
    return changed


def _rewrite_current_process_argv(argv_target_map: Dict[str, str]):
    """改写本次进程的 -t 目标，使本次启动也使用新目标（稳定标识）。

    同时改写 sys.argv，并把 ``og.ok.args['task']``（在 OK.__init__ 已解析）同步为
    新目标，否则 start_runtime 读取到的仍是旧目标。
    """
    if not argv_target_map:
        return
    args = list(sys.argv)
    changed = False
    for i in range(len(args) - 1):
        if args[i] in ("-t", "--task"):
            target = args[i + 1]
            new_index = argv_target_map.get(target)
            if new_index:
                args[i + 1] = str(new_index)
                changed = True
    if changed:
        sys.argv = args
        logger.info(f"schedule index sync: rewrote sys.argv to {sys.argv}")
    try:
        from ok import og

        ok_obj = getattr(og, "ok", None)
        if ok_obj is not None and isinstance(getattr(ok_obj, "args", None), dict):
            current_task = ok_obj.args.get("task")
            if current_task is not None:
                new_index = argv_target_map.get(str(current_task))
                if new_index:
                    ok_obj.args["task"] = new_index
                    logger.info(
                        f"schedule index sync: rewrote og.ok.args['task'] "
                        f"{current_task} -> {new_index}"
                    )
    except Exception:
        logger.exception("schedule index sync: failed to rewrite og.ok.args['task']")


def _write_cache(cache_file: Path, data: dict):
    """写回缓存（仅在有变更时调用）。"""
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"schedule index sync: cache written to {cache_file}")


def resolve_current_schedule_task():
    """Resolve launch arguments from cache without calling Windows services."""
    tasks = _onetime_tasks()
    cache_file = _cache_file()
    if not tasks or cache_file is None or not cache_file.exists():
        return
    data = _load_cache_data(cache_file)
    if not data:
        return
    corrections, _ = _collect_corrections(
        data, _name_to_index_map(tasks), _schedule_root_path(), tasks)
    targets = {}
    for _, _, new_target, old_target, _ in corrections:
        targets.setdefault(str(old_target), set()).add(str(new_target))
    # An old index shared by different schedules cannot identify this launch.
    _rewrite_current_process_argv({old: next(iter(values))
                                   for old, values in targets.items() if len(values) == 1})


def sync_schedule_task_indexes(onetime_tasks: Optional[Sequence] = None, *, rewrite_argv=True) -> int:
    """启动时校正计划任务 -t 目标并回填元数据，返回被处理的任务数。

    把所有可定位的 -t 目标统一迁移为稳定标识（模块路径.类名），
    并回填缓存的 task_index / task_identifier。

    Args:
        onetime_tasks: 当前 onetime_tasks 列表；不传时自动从 og.executor 读取
            （测试可 monkeypatch `_onetime_tasks` 传入假列表）。

    Returns:
        被修正（含仅回填元数据）的任务数（0 表示无需处理或已跳过）。
    """
    global _SYNCED
    if _SYNCED:
        logger.debug("schedule index sync skipped: already synced this process")
        return 0
    _SYNCED = True

    try:
        tasks = list(onetime_tasks) if onetime_tasks is not None else _onetime_tasks()
        logger.info(
            f"schedule index sync start: {len(tasks)} onetime_tasks, "
            f"root={_schedule_root_path()}"
        )
        name_to_index = _name_to_index_map(tasks)
        if not name_to_index:
            logger.info("schedule index sync skipped: onetime_tasks is empty")
            return 0

        cache_file = _cache_file()
        if cache_file is None or not cache_file.exists():
            logger.info("schedule index sync skipped: cache file not found")
            return 0

        data = _load_cache_data(cache_file)
        if not data:
            logger.info("schedule index sync skipped: cache is empty/invalid")
            return 0
        logger.info(
            f"schedule index sync: read {len(data)} cache entries from {cache_file}"
        )

        corrections, metadata_updates = _collect_corrections(
            data, name_to_index, _schedule_root_path().rstrip("\\"), tasks
        )
        if not corrections and not metadata_updates:
            logger.info("schedule index sync: no stale indexes to correct")
            return 0
        logger.info(
            f"schedule index sync: {len(corrections)} stale task(s) found: "
            + ", ".join(f"{item.get('name')} (old -t {old})" for _, item, _, old, _ in corrections)
            + f"; {len(metadata_updates)} task(s) need metadata backfill"
        )

        changed, argv_target_map = _perform_corrections(corrections)
        metadata_changed = _apply_metadata_updates(metadata_updates)
        if changed and rewrite_argv:
            _rewrite_current_process_argv(argv_target_map)
        if changed or metadata_changed:
            _write_cache(cache_file, data)
            detail = ", ".join(
                f"{item.get('name')} -> -t {target}"
                for _, item, target, _, _ in corrections
            )
            logger.info(
                f"schedule index sync corrected {changed} task(s): {detail}; "
                f"backfilled metadata for {metadata_changed} task(s)"
            )
        else:
            logger.warning(
                "schedule index sync: corrections failed, cache kept unchanged, "
                "will retry next launch"
            )
        return changed + metadata_changed
    except Exception:
        logger.exception("schedule index sync failed")
        return 0
