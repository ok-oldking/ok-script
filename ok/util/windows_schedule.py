"""
Windows Task Scheduler Integration Module
Windows 任务计划集成模块 - 实现游戏自动化任务的定时执行

核心特性:
1. COM API 直接调用 (win32com.client)
2. 本地缓存机制（避免频繁 Windows 查询）
3. 操作后增量更新缓存
4. 实时信号通知 UI 更新
"""

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable
from ok.util.config import Config

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """任务触发类型"""

    DAILY = "Daily"  # 每天
    WEEKLY = "Weekly"  # 每周
    MONTHLY = "Monthly"  # 每月
    ONCE = "Once"  # 一次
    CUSTOM = "Custom"  # 自定义间隔（天数或小时数）


class TaskStatus(Enum):
    """任务状态"""

    READY = "Ready"
    RUNNING = "Running"
    DISABLED = "Disabled"
    UNKNOWN = "Unknown"


@dataclass
class ScheduleTaskInfo:
    """计划任务信息数据类"""

    name: str  # 任务名称
    path: str = ""  # 任务路径 (e.g., "\ok-ef\任务名")
    enabled: bool = False  # 是否启用
    status: str = "Unknown"  # 任务状态
    trigger_type: str = ""  # 触发类型 (Daily/Weekly/Monthly/Once/Custom)
    next_run_time: str = ""  # 下次运行时间
    last_run_time: str = ""  # 最后运行时间
    last_result: int = 0  # 最后执行结果代码
    actions: str = ""  # 操作描述
    author: str = ""  # 作者
    created_time: str = ""  # 创建时间
    description: str = ""  # 描述
    xml_config: str = ""  # XML 配置
    task_index: int = -1  # 对应的任务索引 (-1 表示自定义任务)
    interval_days: int = 0  # 自定义间隔（天数），0 表示不使用
    interval_hours: int = 0  # 自定义间隔（小时数），0 表示不使用

    def to_dict(self):
        """转换为字典"""
        return asdict(self)


class WindowsScheduleCache:
    """Windows 任务计划本地缓存管理"""

    def __init__(self,config: Config = None):
        """
        初始化缓存

        Args:
            cache_dir: 缓存目录，默认使用 Config.config_folder
        """
        self.config = config or Config()
        default_cache_dir = self.config.get("config_folder","configs")
        self.cache_dir = Path(default_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "schedule_tasks_cache.json"
        self._migrate_legacy_cache_if_needed()
        self.lock = threading.RLock()
        self.cache: Dict[str, ScheduleTaskInfo] = {}
        self.load_cache()

    def _migrate_legacy_cache_if_needed(self):
        """将旧版 .ok_cache 缓存迁移到 config_folder 下（仅首次）"""
        try:
            if self.cache_file.exists():
                return
            legacy_cache_file = Path(".ok_cache") / "schedule_tasks_cache.json"
            if legacy_cache_file.exists():
                self.cache_file.write_text(
                    legacy_cache_file.read_text(encoding="utf-8"), encoding="utf-8"
                )
                logger.info(
                    f"Migrated schedule cache from {legacy_cache_file} to {self.cache_file}"
                )
        except Exception as e:
            logger.warning(f"Failed to migrate legacy schedule cache: {e}")

    def load_cache(self):
        """从文件加载缓存"""
        with self.lock:
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.cache = {
                        name: ScheduleTaskInfo(**item) for name, item in data.items()
                    }
                    logger.info(f"Loaded {len(self.cache)} tasks from cache")
                except Exception as e:
                    logger.error(f"Failed to load cache: {e}")
                    self.cache = {}
            else:
                self.cache = {}

    def save_cache(self):
        """保存缓存到文件"""
        with self.lock:
            try:
                data = {name: task.to_dict() for name, task in self.cache.items()}
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved {len(self.cache)} tasks to cache")
            except Exception as e:
                logger.error(f"Failed to save cache: {e}")

    def get(self, task_name: str) -> Optional[ScheduleTaskInfo]:
        """获取任务信息"""
        with self.lock:
            return self.cache.get(task_name)

    def get_all(self) -> List[ScheduleTaskInfo]:
        """获取所有任务"""
        with self.lock:
            return list(self.cache.values())

    def add_or_update(self, task_info: ScheduleTaskInfo):
        """添加或更新任务"""
        with self.lock:
            self.cache[task_info.name] = task_info
            self.save_cache()

    def remove(self, task_name: str):
        """删除任务"""
        with self.lock:
            if task_name in self.cache:
                del self.cache[task_name]
                self.save_cache()

    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.save_cache()


class WindowsScheduleManager:
    """
    Windows 任务计划管理器

    直接使用 Windows Task Scheduler API
    提供缓存、信号通知、实时更新等功能
    """

    # COM 接口
    SCHEDULE_SERVICE = None
    SCHEDULE_FOLDER = None

    def __init__(self, config: Config = None):
        """初始化管理器"""
        # 根路径基于当前工作目录的文件夹名称
        self.config = config or Config("main", default={"gui_title": "ok-script"})
        current_folder_name = self.config.get("gui_title", "ok-script")
        self.SCHEDULE_ROOT_PATH = f"\\{current_folder_name}"

        self.cache = WindowsScheduleCache(config=self.config)
        self.lock = threading.RLock()
        self.running = False
        self.sync_thread: Optional[threading.Thread] = None
        self.update_callbacks: List[Callable] = []

        self._init_com_service()

    def _init_com_service(self):
        """初始化 COM 服务"""
        try:
            import win32com.client

            self.SCHEDULE_SERVICE = win32com.client.Dispatch("Schedule.Service")
            self.SCHEDULE_SERVICE.Connect()
            try:
                self.SCHEDULE_FOLDER = self.SCHEDULE_SERVICE.GetFolder(
                    self.SCHEDULE_ROOT_PATH
                )
            except Exception:
                # 首次启动任务目录可能不存在，保留 COM 服务可用，后续创建任务后再获取目录
                self.SCHEDULE_FOLDER = None
            logger.info(f"Windows Task Scheduler COM service initialized, root={self.SCHEDULE_ROOT_PATH}")
        except ImportError:
            logger.warning("win32com not available, will use schtasks command")
            self.SCHEDULE_SERVICE = None
        except Exception as e:
            logger.warning(f"Failed to initialize COM service: {e}, will use schtasks command")
            self.SCHEDULE_SERVICE = None

    def is_com_available(self) -> bool:
        """检查 COM 服务是否可用"""
        return self.SCHEDULE_SERVICE is not None

    def register_update_callback(self, callback: Callable[[ScheduleTaskInfo], None]):
        """注册更新回调（用于 UI 实时更新）"""
        with self.lock:
            if callback not in self.update_callbacks:
                self.update_callbacks.append(callback)

    def unregister_update_callback(self, callback: Callable):
        """注销更新回调"""
        with self.lock:
            if callback in self.update_callbacks:
                self.update_callbacks.remove(callback)

    def _notify_update(self, task_info: ScheduleTaskInfo):
        """通知所有监听器任务已更新"""
        callbacks = self.update_callbacks.copy()
        for callback in callbacks:
            try:
                callback(task_info)
            except Exception as e:
                logger.error(f"Error in update callback: {e}")

    def query_all_tasks(self, force_sync: bool = False) -> List[ScheduleTaskInfo]:
        """
        查询所有计划任务

        Args:
            force_sync: 是否强制同步（忽略缓存）

        Returns:
            任务列表
        """
        with self.lock:
            if not force_sync:
                return self.cache.get_all()

            tasks = []
            try:
                if self.is_com_available():
                    tasks = self._query_tasks_via_com()
                else:
                    tasks = self._query_tasks_via_schtasks()
            except Exception as e:
                logger.error(f"Failed to query tasks: {e}")
                # 降级到缓存
                return self.cache.get_all()

            # 更新缓存
            for task_info in tasks:
                self.cache.add_or_update(task_info)

            return tasks

    def _query_tasks_via_com(self) -> List[ScheduleTaskInfo]:
        """通过 COM API 查询任务"""
        tasks = []
        try:
            import win32com.client

            if not self.SCHEDULE_FOLDER:
                try:
                    self.SCHEDULE_FOLDER = self.SCHEDULE_SERVICE.GetFolder(
                        self.SCHEDULE_ROOT_PATH
                    )
                except Exception:
                    # 目录不存在时返回空列表，属于正常情况
                    return tasks

            task_collection = self.SCHEDULE_FOLDER.GetTasks(0)
            for i in range(task_collection.Count):
                task = task_collection.Item(i + 1)
                task_info = self._parse_task_from_com(task)
                tasks.append(task_info)
                logger.debug(f"Queried task via COM: {task_info.name}")
        except Exception as e:
            logger.error(f"COM query failed: {e}")

        return tasks

    def _parse_task_from_com(self, com_task) -> ScheduleTaskInfo:
        """从 COM 对象解析任务信息"""
        try:
            name = com_task.Name
            enabled = com_task.Enabled
            state = (
                com_task.State
            )  # 0=Unknown, 1=Disabled, 2=Queued, 3=Running, 4=Ready
            state_map = {
                0: "Unknown",
                1: "Disabled",
                2: "Running",
                3: "Running",
                4: "Ready",
            }

            # 提取触发器信息
            trigger_type = ""
            if com_task.Definition.Triggers.Count > 0:
                trigger = com_task.Definition.Triggers.Item(1)
                trigger_type_raw = str(trigger.Type)
                trigger_type_map = {
                    "1": TriggerType.ONCE.value,
                    "2": TriggerType.DAILY.value,
                    "3": TriggerType.WEEKLY.value,
                    "4": TriggerType.MONTHLY.value,
                    "5": TriggerType.MONTHLY.value,
                    "6": TriggerType.MONTHLY.value,
                }
                trigger_type = trigger_type_map.get(trigger_type_raw, trigger_type_raw)

            # 提取操作信息
            actions_desc = ""
            if com_task.Definition.Actions.Count > 0:
                action = com_task.Definition.Actions.Item(1)
                actions_desc = f"{action.Path} {action.Arguments if hasattr(action, 'Arguments') else ''}"

            # 获取 XML 配置
            xml_config = ""
            interval_days = 0
            interval_hours = 0
            try:
                xml_config = com_task.Xml
                # 从 XML 中解析自定义间隔
                import re
                # 解析天间隔: <DaysInterval>N</DaysInterval>
                days_match = re.search(r"<DaysInterval>(\d+)</DaysInterval>", xml_config)
                if days_match:
                    interval_days = int(days_match.group(1))
                    # 如果不是 1 天，说明是自定义间隔
                    if interval_days > 1:
                        trigger_type = "Custom"
                
                # 解析小时间隔: <Interval>PT(\d+)H</Interval>
                hours_match = re.search(r"<Interval>PT(\d+)H</Interval>", xml_config)
                if hours_match:
                    interval_hours = int(hours_match.group(1))
                    trigger_type = "Custom"

                # 兜底：从 XML 识别触发类型，避免 COM 返回异常值/空值
                xml_lower = xml_config.lower()
                if not trigger_type or trigger_type.isdigit():
                    if "<schedulebyweek>" in xml_lower:
                        trigger_type = TriggerType.WEEKLY.value
                    elif "<schedulebymonth>" in xml_lower:
                        trigger_type = TriggerType.MONTHLY.value
                    elif "<timetrigger>" in xml_lower and "<repetition>" not in xml_lower:
                        trigger_type = TriggerType.ONCE.value
                    elif "<schedulebyday>" in xml_lower:
                        trigger_type = TriggerType.DAILY.value

                # 自定义触发优先级最高
                if interval_hours > 0 or interval_days > 1:
                    trigger_type = TriggerType.CUSTOM.value
            except Exception as e:
                logger.debug(f"Failed to get XML config for task {name}: {e}")

            task_info = ScheduleTaskInfo(
                name=name,
                path=f"{self.SCHEDULE_ROOT_PATH}\\{name}",
                enabled=enabled,
                status=state_map.get(state, "Unknown"),
                trigger_type=trigger_type,
                next_run_time=str(com_task.NextRunTime) if com_task.NextRunTime else "",
                last_run_time=str(com_task.LastRunTime) if com_task.LastRunTime else "",
                last_result=com_task.LastTaskResult,
                actions=actions_desc,
                author=(
                    com_task.Definition.RegistrationInfo.Author
                    if hasattr(com_task.Definition.RegistrationInfo, "Author")
                    else ""
                ),
                description=(
                    com_task.Definition.RegistrationInfo.Description
                    if hasattr(com_task.Definition.RegistrationInfo, "Description")
                    else ""
                ),
                created_time=(
                    str(com_task.Definition.RegistrationInfo.Date)
                    if hasattr(com_task.Definition.RegistrationInfo, "Date")
                    else ""
                ),
                xml_config=xml_config,
                interval_days=interval_days,
                interval_hours=interval_hours,
            )
            return task_info
        except Exception as e:
            logger.error(f"Failed to parse COM task: {e}")
            return ScheduleTaskInfo(name="", status="Unknown")

    def _query_tasks_via_schtasks(self) -> List[ScheduleTaskInfo]:
        """通过 schtasks 命令查询任务（降级方案）"""
        tasks = []
        try:
            # 查询目录下所有任务（/TN 需要具体任务名或通配符）
            query_path = (
                f"{self.SCHEDULE_ROOT_PATH}\\*"
                if not self.SCHEDULE_ROOT_PATH.endswith("\\")
                else f"{self.SCHEDULE_ROOT_PATH}*"
            )

            # 使用 CSV 格式输出
            cmd = [
                "schtasks", "/Query", "/TN", query_path, "/Recurse",
                "/FO", "CSV", "/V",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                # 首次启动目录不存在时常见，按空任务处理
                if "cannot find" in (result.stderr or "").lower() or "找不到" in (
                    result.stderr or ""
                ):
                    return tasks
                logger.warning(f"schtasks query failed: {result.stderr}")
                return tasks

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return tasks

            # 解析 CSV 头
            headers = self._parse_csv_line(lines[0])

            for line in lines[1:]:
                if not line.strip():
                    continue
                values = self._parse_csv_line(line)
                if len(values) >= len(headers):
                    task_dict = dict(zip(headers, values))
                    task_info = self._parse_task_from_csv(task_dict)
                    tasks.append(task_info)
                    logger.debug(f"Queried task via schtasks: {task_info.name}")
        except Exception as e:
            logger.error(f"schtasks query failed: {e}")

        return tasks

    def _parse_csv_line(self, line: str) -> List[str]:
        """解析 CSV 行（处理引号和逗号）"""
        result = []
        current = ""
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == "," and not in_quotes:
                result.append(current.strip())
                current = ""
            else:
                current += char

        result.append(current.strip())
        return result

    def _parse_task_from_csv(self, task_dict: Dict[str, str]) -> ScheduleTaskInfo:
        """从 CSV 数据解析任务信息"""
        name = task_dict.get("TaskName", "").split("\\")[-1]

        # 尝试获取 XML 配置
        xml_config = ""
        interval_days = 0
        interval_hours = 0
        try:
            task_path = task_dict.get("TaskName", "")
            if task_path:
                result = subprocess.run(
                    ["schtasks", "/Query", "/TN", task_path, "/XML"],
                    capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    xml_config = result.stdout

            if xml_config:
                import re

                days_match = re.search(r"<DaysInterval>(\d+)</DaysInterval>", xml_config)
                if days_match:
                    interval_days = int(days_match.group(1))

                hours_match = re.search(r"<Interval>PT(\d+)H</Interval>", xml_config)
                if hours_match:
                    interval_hours = int(hours_match.group(1))
        except Exception as e:
            logger.debug(f"Failed to get XML for task {name}: {e}")

        schedule_type = (
            task_dict.get("Schedule Type", "")
            or task_dict.get("ScheduleType", "")
            or task_dict.get("计划类型", "")
        )
        schedule_lower = schedule_type.lower()
        trigger_type = ""
        if "daily" in schedule_lower or "每天" in schedule_type:
            trigger_type = TriggerType.DAILY.value
        elif "weekly" in schedule_lower or "每周" in schedule_type:
            trigger_type = TriggerType.WEEKLY.value
        elif "monthly" in schedule_lower or "每月" in schedule_type:
            trigger_type = TriggerType.MONTHLY.value
        elif "once" in schedule_lower or "one time" in schedule_lower or "一次" in schedule_type:
            trigger_type = TriggerType.ONCE.value

        if interval_hours > 0 or interval_days > 1:
            trigger_type = TriggerType.CUSTOM.value

        status = task_dict.get("Status", "") or task_dict.get("状态", "")

        task_info = ScheduleTaskInfo(
            name=name,
            path=task_dict.get("TaskName", ""),
            enabled=status == "Ready" or status == "Running" or status == "就绪" or status == "正在运行",
            status=status or "Unknown",
            trigger_type=trigger_type,
            next_run_time=task_dict.get("Next Run Time", ""),
            last_run_time=task_dict.get("Last Run Time", ""),
            last_result=(
                int(task_dict.get("Last Result", 0))
                if task_dict.get("Last Result", "").isdigit()
                else 0
            ),
            author=task_dict.get("Author", ""),
            description=task_dict.get("Description", ""),
            xml_config=xml_config,
            interval_days=interval_days,
            interval_hours=interval_hours,
        )
        return task_info

    def create_task(self, task_name: str, task_index: int,
                    trigger_type: TriggerType, timeout_hours: int = 0,
                    start_hour: int = 9, start_minute: int = 0,
                    auto_exit: bool = True, enabled: bool = True,
                    description: str = "", interval_days: int = 0,
                    interval_hours: int = 0) -> bool:
        """
        创建计划任务

        Args:
            task_name: 任务名称
            task_index: 要执行的任务索引 (-t N)
            trigger_type: 触发类型
            timeout_hours: 超时限制（小时），0 表示无限制
            start_hour: 开始小时（24小时制，0-23）
            start_minute: 开始分钟（0-59）
            auto_exit: 执行完成后自动退出（追加 -e）
            enabled: 是否立即启用
            description: 任务描述
            interval_days: 自定义间隔（天数），仅当 trigger_type 为 CUSTOM 时有效
            interval_hours: 自定义间隔（小时数），仅当 trigger_type 为 CUSTOM 时有效

        Returns:
            是否成功
        """
        with self.lock:
            try:
                task_path = f"{self.SCHEDULE_ROOT_PATH}\\{task_name}"

                if self.is_com_available():
                    success = self._create_task_via_com(
                        task_name, task_index, trigger_type, timeout_hours,
                        start_hour, start_minute, auto_exit, enabled,
                        description, task_path, interval_days, interval_hours)
                else:
                    success = self._create_task_via_schtasks(
                        task_name, task_index, trigger_type, enabled,
                        task_path, timeout_hours, start_hour, start_minute,
                        auto_exit, interval_days, interval_hours)

                if success:
                    # 更新缓存
                    task_info = ScheduleTaskInfo(
                        name=task_name,
                        path=task_path,
                        enabled=enabled,
                        status="Ready" if enabled else "Disabled",
                        trigger_type=trigger_type.value,
                        description=description,
                        task_index=task_index,
                        interval_days=interval_days,
                        interval_hours=interval_hours,
                    )
                    self.cache.add_or_update(task_info)
                    self._notify_update(task_info)
                    logger.info(f"Task created: {task_name}")

                return success
            except Exception as e:
                logger.error(f"Failed to create task: {e}")
                return False

    def _create_task_via_com(self, task_name: str, task_index: int,
                            trigger_type: TriggerType, timeout_hours: int,
                            start_hour: int, start_minute: int,
                            auto_exit: bool, enabled: bool, description: str,
                            task_path: str, interval_days: int = 0,
                            interval_hours: int = 0) -> bool:
        """通过 COM API 创建任务"""
        try:
            import win32com.client

            # 检查 COM 服务是否可用
            if not self.is_com_available():
                logger.warning("COM service not available, falling back to schtasks")
                return self._create_task_via_schtasks(
                    task_name, task_index, trigger_type, enabled, task_path,
                    timeout_hours, start_hour, start_minute, auto_exit,
                    interval_days, interval_hours)

            # 生成 XML 配置
            xml_config = self._generate_task_xml(
                task_name, task_index, trigger_type, timeout_hours,
                description, start_hour, start_minute, auto_exit,
                interval_days, interval_hours)

            # 确保已连接
            self.SCHEDULE_SERVICE.Connect()

            # 获取根文件夹
            root_folder = self.SCHEDULE_SERVICE.GetFolder("\\")

            # 确保 ok-ef 文件夹存在
            try:
                self.SCHEDULE_SERVICE.GetFolder(self.SCHEDULE_ROOT_PATH)
            except:
                try:
                    root_folder.CreateFolder(self.SCHEDULE_ROOT_PATH)
                except Exception as e:
                    logger.warning(f"Failed to create schedule folder: {e}")

            # 创建任务定义
            task_def = self.SCHEDULE_SERVICE.NewTask(0)
            task_def.XmlText = xml_config

            # 注册新任务
            folder = self.SCHEDULE_SERVICE.GetFolder(self.SCHEDULE_ROOT_PATH)
            folder.RegisterTaskDefinition(task_name, task_def, 6, None, None, 3)

            # 设置启用状态
            if not enabled:
                self._disable_task_via_schtasks(task_name)

            logger.info(f"Task created via COM: {task_name}")
            return True
        except Exception as e:
            logger.warning(f"COM task creation failed: {e}, falling back to schtasks")
            # 降级到 schtasks
            return self._create_task_via_schtasks(
                task_name, task_index, trigger_type, enabled,
                task_path, timeout_hours, start_hour, start_minute,
                auto_exit, interval_days, interval_hours)

    def _create_task_via_schtasks(self, task_name: str, task_index: int,
                                 trigger_type: TriggerType, enabled: bool,
                                 task_path: str, timeout_hours: int = 0,
                                 start_hour: int = 9, start_minute: int = 0,
                                 auto_exit: bool = True,
                                 interval_days: int = 0,
                                 interval_hours: int = 0) -> bool:
        """通过 schtasks 命令创建任务（降级方案）"""
        try:
            xml_config = self._generate_task_xml(
                task_name, task_index, trigger_type, timeout_hours,
                "", start_hour, start_minute, auto_exit,
                interval_days, interval_hours)
            xml_file = Path(f"temp_task_{task_name}.xml")

            try:
                # UTF-16 LE with BOM for Windows Task Scheduler
                with open(xml_file, "w", encoding="utf-16") as f:
                    f.write(xml_config)

                cmd = [
                    "schtasks", "/Create", "/XML", str(xml_file),
                    "/TN", task_path, "/F",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode != 0:
                    logger.error(f"schtasks create failed: {result.stderr}")
                    logger.debug(f"XML content:\n{xml_config}")
                    return False

                if not enabled:
                    self._disable_task_via_schtasks(task_name)

                return True
            finally:
                if xml_file.exists():
                    xml_file.unlink()
        except Exception as e:
            logger.error(f"schtasks create failed: {e}")
            return False

    def delete_task(self, task_name: str) -> bool:
        """删除计划任务"""
        with self.lock:
            try:
                task_path = f"{self.SCHEDULE_ROOT_PATH}\\{task_name}"

                cmd = ["schtasks", "/Delete", "/TN", task_path, "/F"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode == 0:
                    self.cache.remove(task_name)
                    logger.info(f"Task deleted: {task_name}")
                    return True
                else:
                    logger.error(f"Failed to delete task: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"Failed to delete task: {e}")
                return False

    def enable_task(self, task_name: str) -> bool:
        """启用任务"""
        with self.lock:
            try:
                task_path = f"{self.SCHEDULE_ROOT_PATH}\\{task_name}"
                cmd = ["schtasks", "/Change", "/ENABLE", "/TN", task_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode == 0:
                    task_info = self.cache.get(task_name)
                    if task_info:
                        task_info.enabled = True
                        task_info.status = "Ready"
                        self.cache.add_or_update(task_info)
                        self._notify_update(task_info)
                    logger.info(f"Task enabled: {task_name}")
                    return True
                else:
                    logger.error(f"Failed to enable task: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"Failed to enable task: {e}")
                return False

    def disable_task(self, task_name: str) -> bool:
        """禁用任务"""
        with self.lock:
            try:
                task_path = f"{self.SCHEDULE_ROOT_PATH}\\{task_name}"
                return self._disable_task_via_schtasks(task_name)
            except Exception as e:
                logger.error(f"Failed to disable task: {e}")
                return False

    def _disable_task_via_schtasks(self, task_name: str) -> bool:
        """通过 schtasks 禁用任务"""
        try:
            task_path = f"{self.SCHEDULE_ROOT_PATH}\\{task_name}"
            cmd = ["schtasks", "/Change", "/DISABLE", "/TN", task_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                task_info = self.cache.get(task_name)
                if task_info:
                    task_info.enabled = False
                    task_info.status = "Disabled"
                    self.cache.add_or_update(task_info)
                    self._notify_update(task_info)
                logger.info(f"Task disabled: {task_name}")
                return True
            else:
                logger.error(f"Failed to disable task: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Failed to disable task: {e}")
            return False

    def _generate_task_xml(self, task_name: str, task_index: int,
                          trigger_type: TriggerType, timeout_hours: int = 0,
                          description: str = "", start_hour: int = 9,
                          start_minute: int = 0, auto_exit: bool = True,
                          interval_days: int = 0, interval_hours: int = 0) -> str:
        """
        生成任务 XML 配置

        UTF-16 编码（Windows 要求）
        最高权限运行（HighestAvailable）
        """
        import sys

        python_exe = str(Path(sys.executable).resolve())
        working_directory = os.getcwd()

        # 获取当前登录用户名
        current_user = os.environ.get("USERNAME", "")
        if not current_user:
            try:
                import getpass

                current_user = getpass.getuser()
            except Exception:
                current_user = "User"

        # 构建命令行参数
        cmd_args = f"-t {task_index}"
        if auto_exit:
            cmd_args += " -e"

        timeout_str = ""
        if timeout_hours > 0:
            timeout_str = f"PT{timeout_hours}H"
        else:
            timeout_str = "PT0S"  # 无限制

        # 规范化开始时间
        try:
            start_hour = max(0, min(23, int(start_hour)))
            start_minute = max(0, min(59, int(start_minute)))
        except Exception:
            start_hour = 9
            start_minute = 0
        start_time = f"{start_hour:02d}:{start_minute:02d}:00"

        # 构建触发器配置
        trigger_xml = self._get_trigger_xml(trigger_type, start_time, interval_days, interval_hours)

        xml_template = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>2024-01-01T00:00:00</Date>
    <Author>ok-script</Author>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Triggers>
    {trigger_xml}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{current_user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>{timeout_str}</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{python_exe}"</Command>
      <Arguments>main.py {cmd_args}</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
        return xml_template

    def _get_trigger_xml(self, trigger_type: TriggerType, start_time: str = "09:00:00",
                         interval_days: int = 0, interval_hours: int = 0) -> str:
        """获取触发器 XML"""
        if trigger_type == TriggerType.DAILY:
            return f"""<CalendarTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>"""
        elif trigger_type == TriggerType.WEEKLY:
            return f"""<CalendarTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
                    <Monday></Monday>
                    <Tuesday></Tuesday>
                    <Wednesday></Wednesday>
                    <Thursday></Thursday>
                    <Friday></Friday>
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>"""
        elif trigger_type == TriggerType.MONTHLY:
            return f"""<CalendarTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth>
          <Day>1</Day>
        </DaysOfMonth>
        <Months>
                    <January></January>
                    <February></February>
                    <March></March>
                    <April></April>
                    <May></May>
                    <June></June>
                    <July></July>
                    <August></August>
                    <September></September>
                    <October></October>
                    <November></November>
                    <December></December>
        </Months>
      </ScheduleByMonth>
    </CalendarTrigger>"""
        elif trigger_type == TriggerType.CUSTOM:
            # 自定义间隔：支持天间隔或小时间隔
            if interval_days > 0:
                # 基于天的间隔（使用 CalendarTrigger）
                return f"""<CalendarTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>{interval_days}</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>"""
            elif interval_hours > 0:
                # 基于小时的间隔（使用 TimeTrigger + Repetition）
                return f"""<TimeTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{interval_hours}H</Interval>
        <Duration>P999Y</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>"""
            else:
                # 默认：每天一次
                return f"""<CalendarTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>"""
        else:  # ONCE
            return f"""<TimeTrigger>
      <StartBoundary>2024-01-01T{start_time}</StartBoundary>
            <Enabled>true</Enabled>
    </TimeTrigger>"""

    def sync_tasks(self, force: bool = False):
        """
        同步任务列表（后台线程）

        Args:
            force: 是否强制同步（忽略缓存）
        """

        def _sync():
            try:
                self.query_all_tasks(force_sync=force)
                logger.info("Task sync completed")
            except Exception as e:
                logger.error(f"Task sync failed: {e}")

        thread = threading.Thread(target=_sync, daemon=True)
        thread.start()
        return thread

    def start_background_sync(self, interval: int = 60):
        """
        启动后台定期同步

        Args:
            interval: 同步间隔（秒）
        """
        if self.running:
            return

        self.running = True

        def _background_sync():
            while self.running:
                try:
                    self.query_all_tasks(force_sync=True)
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"Background sync error: {e}")

        self.sync_thread = threading.Thread(
            target=_background_sync, daemon=True, name="ScheduleSync"
        )
        self.sync_thread.start()
        logger.info("Background task sync started")

    def stop_background_sync(self):
        """停止后台同步"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        logger.info("Background task sync stopped")
