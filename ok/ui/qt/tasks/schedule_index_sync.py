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
保留 ok 原生 `-t N`，不修改任何运行时解析 / 创建 / 修改对话框逻辑，
仅在每次启动时（MainWindow.__init__ 构造 ScheduleTaskTab 之前、start_runtime 之前）
自动校正旧索引：

1. 读取 schedule_tasks_cache.json；
2. 只处理本应用（如 ``\\ok-ef\\``）下的任务，其它 ok-* 应用的只读任务不动；
3. 以缓存任务的 ``name``（创建时选择的任务名，不随排序变化）为权威身份，
   在当前 ``onetime_tasks`` 中查找新索引；
4. 把 ``-t X``（旧索引或历史迁移成的任务名）改写为新索引，
   并同步更新缓存 / xml_config / Windows 计划任务（COM，失败回退 schtasks）；
5. 改写本次进程 ``sys.argv``，保证本次启动也使用正确索引；
6. 幂等：每次进程只校正一次，无变更时不写文件、不调 COM，找不到 name 的任务跳过。

调用点
------
- ``ok.ui.qt.MainWindow.MainWindow.__init__``：构造 ScheduleTaskTab（加载任务缓存）之前；
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
    重名/重类时保持第一个（与既有行为一致），由 _collect_corrections 的
    主匹配 + 类名回退逻辑兜底。
    """
    id_to_index = {}
    for index, task in enumerate(onetime_tasks, start=1):
        name = getattr(task, "name", None)
        class_name = task.__class__.__name__
        module_path = f"{task.__class__.__module__}.{class_name}"
        if name:
            id_to_index.setdefault(str(name), index)
        id_to_index.setdefault(class_name, index)
        id_to_index.setdefault(module_path, index)
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


def _replace_task_target(value: str, new_index: int) -> str:
    """把字符串中的 `-t X` 改写为 `-t {new_index}`。"""
    if not value:
        return value
    return _TASK_ARG_PATTERN.sub(lambda m: f"{m.group(1)}-t {new_index}", value)


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
    try:
        import win32com.client

        service = win32com.client.Dispatch("Schedule.Service")
        service.Connect()
        folder_path, task_file_name = path.rsplit("\\", 1)
        task_def = service.NewTask(0)
        task_def.XmlText = new_xml
        folder = service.GetFolder(folder_path or "\\")
        folder.RegisterTaskDefinition(
            task_file_name, task_def, _TASK_CREATE_OR_UPDATE, None, None, 3
        )
        logger.info(f"schedule index sync: updated task {path} via COM")
        return True
    except Exception as e:
        logger.warning(f"schedule index sync: COM update failed for {path}: {e}")
    return _register_task_xml_via_schtasks(path, new_xml)


def _apply_correction(item: dict, new_target) -> bool:
    """改写单个缓存任务的 -t 目标，并同步 Windows 计划任务。

    new_target 可为数字索引（int）或模块路径.类名（str）。
    仅当 Windows 计划任务（若存在）成功用新 XML 重新注册后，才改写缓存字段并返回 True；
    注册失败或无法改写时返回 False，保持缓存不变，下次启动会重试。
    """
    old_xml = item.get("xml_config") or ""
    old_actions = item.get("actions") or ""
    new_xml = _replace_task_target(old_xml, new_target)
    new_actions = _replace_task_target(old_actions, new_target)

    path = item.get("path") or ""
    if path:
        if not (old_xml and new_xml):
            logger.error(f"schedule index sync: no xml_config to rewrite task {path}, skip")
            return False
        if not _register_task_xml(path, new_xml):
            logger.error(f"schedule index sync: failed to update task {path}, keep cache unchanged")
            return False

    item["xml_config"] = new_xml
    item["actions"] = new_actions
    if isinstance(new_target, int):
        item["task_index"] = new_target
    return True


def _collect_corrections(
        data: dict, name_to_index: Dict[str, int], root_path: str,
        onetime_tasks: Sequence = (),
) -> List[Tuple[str, dict, object, str]]:
    """收集需要修正的缓存任务。

    返回 [(task_key, item, new_target, old_target), ...]，new_target 为数字索引或
    模块路径.类名（str）。仅处理本应用（root_path）下的任务：
      - 旧格式 `-t N`（数字）：任务名存在且 -t 不是当前索引时修正为当前索引；
      - 新格式 `-t 模块路径.类名`：模块路径匹配失败（模块移动/重命名）且类名唯一
        匹配时，修正为当前实际的模块路径.类名。
    """
    corrections: List[Tuple[str, dict, object, str]] = []
    for task_key, item in data.items():
        if not isinstance(item, dict):
            continue
        # 只处理本应用（如 ok-ef）下的任务，其它 ok-* 应用只读任务不动
        if not _is_own_task_path(str(item.get("path") or task_key), root_path):
            continue
        old_target = _extract_task_target(item)
        if old_target is None:
            continue

        if old_target.isdigit():
            # 旧格式：数字索引，按任务名校正
            name = item.get("name")
            if not name or str(name) not in name_to_index:
                continue
            new_index = name_to_index[str(name)]
            # 已是正确索引则跳过（幂等）
            if int(old_target) == new_index:
                continue
            corrections.append((task_key, item, new_index, old_target))
        elif "." in old_target:
            # 新格式：模块路径.类名（稳定标识）
            current_module_path = _resolve_identifier_index(onetime_tasks, old_target)
            if current_module_path is None:
                # 任务在当前 onetime_tasks 中找不到（已删除或类名也匹配不到），跳过
                continue
            task = _task_at_index(onetime_tasks, current_module_path)
            if task is None:
                continue
            new_identifier = f"{task.__class__.__module__}.{task.__class__.__name__}"
            # 已是当前模块路径则跳过（幂等）
            if new_identifier == old_target:
                continue
            corrections.append((task_key, item, new_identifier, old_target))
        else:
            # 历史任务名格式（如 -t 日常任务）：按任务名校正为当前数字索引
            name = item.get("name")
            if not name or str(name) not in name_to_index:
                continue
            new_index = name_to_index[str(name)]
            corrections.append((task_key, item, new_index, old_target))
    return corrections


def _perform_corrections(corrections) -> Tuple[int, Dict[str, int]]:
    """逐项应用修正，返回 (成功修正数, 旧 -t 目标 -> 新目标 的 argv 映射)。

    new_target 可为数字索引或模块路径.类名。仅统计并记录真正注册成功的修正；
    失败的条目保持缓存原样，下次启动会重试。
    """
    changed = 0
    argv_target_map: Dict[str, int] = {}
    for task_key, item, new_target, old_target in corrections:
        try:
            if _apply_correction(item, new_target):
                changed += 1
                argv_target_map.setdefault(str(old_target), str(new_target))
        except Exception:
            logger.exception(f"schedule index sync failed for {task_key}")
    return changed, argv_target_map


def _rewrite_current_process_argv(argv_target_map: Dict[str, int]):
    """改写本次进程的 -t 目标，使本次启动也使用新索引。

    同时改写 sys.argv，并把 ``og.ok.args['task']``（在 OK.__init__ 已解析）同步为
    新索引，否则 start_runtime 读取到的仍是旧索引。
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


def sync_schedule_task_indexes(onetime_tasks: Optional[Sequence] = None) -> int:
    """启动时校正计划任务索引，返回被修正的任务数。

    Args:
        onetime_tasks: 当前 onetime_tasks 列表；不传时自动从 og.executor 读取
            （测试可 monkeypatch `_onetime_tasks` 传入假列表）。

    Returns:
        被修正的任务数（0 表示无需修正或已跳过）。
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

        corrections = _collect_corrections(
            data, name_to_index, _schedule_root_path().rstrip("\\"), tasks
        )
        if not corrections:
            logger.info("schedule index sync: no stale indexes to correct")
            return 0
        logger.info(
            f"schedule index sync: {len(corrections)} stale task(s) found: "
            + ", ".join(f"{item.get('name')} (old -t {old})" for _, item, _, old in corrections)
        )

        changed, argv_target_map = _perform_corrections(corrections)
        if changed:
            _rewrite_current_process_argv(argv_target_map)
            _write_cache(cache_file, data)
            detail = ", ".join(
                f"{item.get('name')} -> -t {target}" for _, item, target, _ in corrections
            )
            logger.info(f"schedule index sync corrected {changed} task(s): {detail}")
        else:
            logger.warning(
                "schedule index sync: corrections failed, cache kept unchanged, "
                "will retry next launch"
            )
        return changed
    except Exception:
        logger.exception("schedule index sync failed")
        return 0
