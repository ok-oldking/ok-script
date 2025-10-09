# mymodule.pyi


import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from functools import cmp_to_key
from logging.handlers import TimedRotatingFileHandler, QueueListener, QueueHandler
from typing import (
    Dict, List, Optional, Union, Any, Tuple, Callable, Set, Pattern,
    Type, overload, TypeVar
)

import cv2
import numpy as np
import psutil
import pyappify
import pydirectinput
import requests
import win32api
import win32gui
import win32process
import win32ui
from PIL import Image
from PySide6.QtCore import QCoreApplication, Qt, QEvent, QSize, QLocale
from PySide6.QtGui import QIcon, QScreen
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QApplication
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow

# Type Aliases for clarity
Frame = np.ndarray
ColorRange = Dict[str, Tuple[int, int]]
T = TypeVar('T')


class Logger:
    """
    一个简单的日志记录器包装类，用于在日志消息前附加模块名称。
    """
    logger: logging.Logger
    name: str

    def __init__(self, name: str):
        """
        初始化 Logger.

        Args:
            name (str): 日志记录器的名称，通常是模块名。
        """
        ...

    def debug(self, message: Any) -> None:
        """
        记录一个 DEBUG 级别的日志消息。

        Args:
            message (Any): 要记录的消息对象。
        """
        ...

    def info(self, message: Any) -> None:
        """
        记录一个 INFO 级别的日志消息。

        Args:
            message (Any): 要记录的消息对象。
        """
        ...

    def warning(self, message: Any) -> None:
        """
        记录一个 WARNING 级别的日志消息。

        Args:
            message (Any): 要记录的消息对象。
        """
        ...

    def error(self, message: Any, exception: Optional[Exception] = None) -> None:
        """
        记录一个 ERROR 级别的日志消息，可以选择性地包含异常信息。

        Args:
            message (Any): 要记录的消息对象。
            exception (Optional[Exception]): 要一起记录的异常对象。
        """
        ...

    def critical(self, message: Any) -> None:
        """
        记录一个 CRITICAL 级别的日志消息。

        Args:
            message (Any): 要记录的消息对象。
        """
        ...

    @staticmethod
    def call_stack() -> str:
        """
        获取并返回当前Python调用栈的字符串表示形式。

        Returns:
            str: 格式化后的调用栈字符串。
        """
        ...

    @staticmethod
    def get_logger(name: str) -> Logger:
        """
        获取一个 Logger 实例。

        Args:
            name (str): 日志记录器的名称。

        Returns:
            Logger: 一个新的 Logger 实例。
        """
        ...

    @staticmethod
    def exception_to_str(exception: Exception) -> str:
        """
        将异常及其堆栈跟踪转换为字符串。

        Args:
            exception (Exception): 要转换的异常对象。

        Returns:
            str: 格式化后的异常信息字符串。
        """
        ...


class InfoFilter(logging.Filter):
    """
    一个日志过滤器，只允许级别低于 ERROR 的记录通过。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        确定是否应记录指定的日志记录。

        Args:
            record (logging.LogRecord): 日志记录对象。

        Returns:
            bool: 如果记录级别低于 ERROR 则返回 True，否则返回 False。
        """
        ...


def config_logger(config: Optional[dict] = None, name: str = 'ok-script') -> None:
    """
    配置应用程序的全局日志系统。

    设置日志级别、处理器（标准输出、标准错误、文件、GUI通信）和未捕获异常的钩子。

    Args:
        config (Optional[dict]): 包含日志配置的字典，例如 `{'debug': True}`。
        name (str): 用于日志文件名的基础名称。
    """
    ...


class SafeFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler 的一个安全版本，用于处理流已关闭时可能发生的错误。
    """

    def emit(self, record: logging.LogRecord) -> None:
        """
        发出一个日志记录。

        Args:
            record (logging.LogRecord): 要发出的日志记录。
        """
        ...


def init_class_by_name(module_name: str, class_name: str, *args, **kwargs) -> Any:
    """
    通过模块名和类名动态导入并实例化一个类。

    Args:
        module_name (str): 包含该类的模块的名称。
        class_name (str): 要实例化的类的名称。
        *args: 传递给类构造函数的位置参数。
        **kwargs: 传递给类构造函数的关键字参数。

    Returns:
        Any: 所请求类的实例。
    """
    ...


class ExitEvent(threading.Event):
    """
    threading.Event 的扩展，用于在设置事件时通知绑定的队列和可停止对象。
    """
    queues: Set[queue.Queue]
    to_stops: Set[Any]

    def bind_queue(self, queue_instance: queue.Queue) -> None:
        """
        将一个队列绑定到此事件。当事件被设置时，`None` 将被放入队列中。

        Args:
            queue_instance (queue.Queue): 要绑定的队列。
        """
        ...

    def bind_stop(self, to_stop: Any) -> None:
        """
        将一个具有 `stop()` 方法的对象绑定到此事件。当事件被设置时，将调用其 `stop()` 方法。

        Args:
            to_stop (Any): 要绑定的可停止对象。
        """
        ...

    def set(self) -> None:
        """
        设置内部标志为 true，并通知所有绑定的队列和可停止对象。
        """
        ...


@dataclass(order=True)
class ScheduledTask:
    """
    表示一个计划在特定时间执行的任务的数据类。
    """
    execute_at: float
    task: Callable = field(compare=False)


class Handler:
    """
    一个处理程序类，在专用线程中按顺序和计划执行任务。
    """
    task_queue: List[ScheduledTask]
    executing: Optional[Callable]
    condition: threading.Condition
    exit_event: ExitEvent
    name: Optional[str]
    thread: threading.Thread

    def __init__(self, event: ExitEvent, name: Optional[str] = None):
        """
        初始化 Handler.

        Args:
            event (ExitEvent): 用于发出退出信号的退出事件。
            name (Optional[str]): 处理程序线程的名称。
        """
        ...

    def post(self, task: Callable, delay: int | float = 0, remove_existing: bool = False,
             skip_if_running: bool = False) -> bool | None:
        """
        将一个任务发布到处理程序队列中执行。

        Args:
            task (Callable): 要执行的任务函数。
            delay (int | float): 执行任务前的延迟时间（秒）。
            remove_existing (bool): 是否移除队列中已存在的相同任务。
            skip_if_running (bool): 如果相同的任务当前正在执行，是否跳过添加。

        Returns:
            bool | None: 如果成功发布则返回 True，如果处理程序已退出则返回 None。
        """
        ...

    def stop(self) -> None:
        """
        停止处理程序线程，清空任务队列。
        """
        ...


def read_json_file(file_path: str) -> Optional[dict]:
    """
    从文件中读取并解析 JSON 数据。

    Args:
        file_path (str): JSON 文件的路径。

    Returns:
        Optional[dict]: 如果成功则返回解析后的字典，如果文件不存在或解析失败则返回 None。
    """
    ...


def write_json_file(file_path: str, data: Any) -> bool:
    """
    将数据以 JSON 格式写入文件。

    Args:
        file_path (str): 要写入的文件的路径。
        data (Any): 要序列化为 JSON 的数据。

    Returns:
        bool: 如果写入成功则返回 True。
    """
    ...


def is_admin() -> bool:
    """
    检查当前用户是否具有管理员权限 (仅限 Windows)。

    Returns:
        bool: 如果用户是管理员则返回 True，否则返回 False。
    """
    ...


@overload
def get_first_item(lst: None, default: T = None) -> T | None: ...


@overload
def get_first_item(lst: list[T], default: Any = None) -> T | Any: ...


def get_first_item(lst: Optional[list], default: Any = None) -> Any:
    """
    安全地获取列表的第一个项目。

    Args:
        lst (Optional[list]): 输入列表。
        default (Any): 如果列表为空或为 None，则返回的默认值。

    Returns:
        Any: 列表的第一个项目或默认值。
    """
    ...


def safe_get(lst: list, idx: int, default: Any = None) -> Any:
    """
    安全地通过索引从列表中获取项目。

    Args:
        lst (list): 输入列表。
        idx (int): 项目的索引。
        default (Any): 如果索引超出范围，则返回的默认值。

    Returns:
        Any: 列表中的项目或默认值。
    """
    ...


def find_index_in_list(my_list: list, target_string: str, default_index: int = -1) -> int:
    """
    在列表中查找目标字符串的索引。

    Args:
        my_list (list): 要搜索的列表。
        target_string (str): 要查找的字符串。
        default_index (int): 如果未找到目标，则返回的索引。

    Returns:
        int: 目标字符串的索引或默认索引。
    """
    ...


def get_path_relative_to_exe(*files: str) -> str | None:
    """
    获取相对于可执行文件或主脚本目录的路径。

    Args:
        *files (str): 要连接到基础目录的路径段。

    Returns:
        str | None: 规范化的绝对路径，如果任何输入为 None 则返回 None。
    """
    ...


def get_relative_path(*files: str) -> str | None:
    """
    获取相对于当前工作目录的路径。

    Args:
        *files (str): 要连接到当前工作目录的路径段。

    Returns:
        str | None: 规范化的绝对路径，如果任何输入为 None 则返回 None。
    """
    ...


def install_path_isascii() -> Tuple[bool, str]:
    """
    检查安装路径是否只包含 ASCII 字符。

    Returns:
        Tuple[bool, str]: 一个元组，其中包含一个布尔值（如果路径是 ASCII 则为 True）和路径本身。
    """
    ...


def resource_path(relative_path: str) -> str:
    """
    获取资源的绝对路径，适用于开发环境和 PyInstaller 打包。

    Args:
        relative_path (str): 相对于项目根目录的资源路径。

    Returns:
        str: 资源的绝对路径。
    """
    ...


def ensure_dir_for_file(file_path: str) -> str:
    """
    确保文件路径所在的目录存在。

    Args:
        file_path (str): 文件的完整路径。

    Returns:
        str: 目录的路径。
    """
    ...


def ensure_dir(directory: str, clear: bool = False) -> str:
    """
    确保指定的目录存在。

    Args:
        directory (str): 目录的路径。
        clear (bool): 如果为 True，则在创建前清空目录中的所有内容。

    Returns:
        str: 目录的路径。
    """
    ...


def delete_if_exists(file_path: str) -> None:
    """
    如果路径存在，则删除文件或目录。

    Args:
        file_path (str): 要删除的文件或目录的路径。
    """
    ...


def delete_folders_starts_with(path: str, starts_with: str) -> None:
    """
    删除指定路径下所有以给定前缀开头的文件夹。

    Args:
        path (str): 要搜索文件夹的父目录。
        starts_with (str): 文件夹名称的前缀。
    """
    ...


def sanitize_filename(filename: str) -> str:
    """
    从文件名中移除无效字符。

    Args:
        filename (str): 要清理的文件名。

    Returns:
        str: 清理后的文件名。
    """
    ...


def clear_folder(folder_path: str) -> None:
    """
    删除文件夹内的所有文件和子文件夹。

    Args:
        folder_path (str): 要清空的文件夹的路径。
    """
    ...


def find_first_existing_file(filenames: List[str], directory: str) -> Optional[str]:
    """
    在指定目录中查找列表中第一个存在的文件。

    Args:
        filenames (List[str]): 要检查的文件名列表。
        directory (str): 要搜索的目录。

    Returns:
        Optional[str]: 找到的第一个文件的完整路径，如果都未找到则返回 None。
    """
    ...


def get_path_in_package(base: str, file: str) -> str:
    """
    获取相对于 Python 包内文件的路径。

    Args:
        base (str): 包内的参考文件路径 (例如 `__file__`)。
        file (str): 相对于参考文件的目标文件名。

    Returns:
        str: 目标文件的绝对路径。
    """
    ...


def dir_checksum(directory: str, excludes: Optional[List[str]] = None) -> str:
    """
    计算目录内容的 MD5 校验和。

    Args:
        directory (str): 要计算校验和的目录。
        excludes (Optional[List[str]]): 要从计算中排除的文件名列表。

    Returns:
        str: MD5 校验和的十六进制摘要。
    """
    ...


def find_folder_with_file(root_folder: str, target_file: str) -> Optional[str]:
    """
    在根文件夹及其子文件夹中查找包含目标文件的文件夹。

    Args:
        root_folder (str): 开始搜索的根目录。
        target_file (str): 要查找的文件的名称。

    Returns:
        Optional[str]: 包含目标文件的文件夹的路径，如果未找到则返回 None。
    """
    ...


def get_folder_size(folder_path: str) -> int:
    """
    计算文件夹的总大小（以字节为单位）。

    Args:
        folder_path (str): 文件夹的路径。

    Returns:
        int: 文件夹中所有文件的总大小（字节）。
    """
    ...


def run_in_new_thread(func: Callable) -> threading.Thread:
    """
    在新线程中运行一个函数。

    Args:
        func (Callable): 要在背景线程中执行的函数。

    Returns:
        threading.Thread: 已启动的线程对象。
    """
    ...


def check_mutex() -> bool:
    """
    检查此应用程序的另一个实例是否已在运行 (仅限 Windows)。

    使用基于当前工作目录的命名互斥锁。如果已存在互斥锁，则会等待并可能尝试终止现有进程。

    Returns:
        bool: 如果可以继续运行（无冲突或冲突已解决），则返回 True。
    """
    ...


def restart_as_admin() -> None:
    """
    如果当前未以管理员权限运行，则以管理员权限重新启动应用程序 (仅限 Windows)。
    """
    ...


def all_pids() -> List[int]:
    """
    获取系统上所有正在运行的进程的 PID 列表 (仅限 Windows)。

    Returns:
        List[int]: 所有进程 ID 的列表。
    """
    ...


def ratio_text_to_number(supported_ratio: str) -> float:
    """
    将 "宽:高" 格式的宽高比字符串转换为浮点数。

    Args:
        supported_ratio (str): 例如 "16:9" 格式的字符串。

    Returns:
        float: 宽高比的浮点表示。
    """
    ...


def data_to_base64(data: Union[Dict, List[Dict]]) -> str:
    """
    将字典或字典列表序列化为 base64 编码的字符串。

    Args:
        data (Union[Dict, List[Dict]]): 要序列化的数据。

    Returns:
        str: base64 编码的字符串。
    """
    ...


def base64_to_data(base64_str: str) -> Union[Dict, List[Dict]]:
    """
    将 base64 编码的字符串反序列化回字典或字典列表。

    Args:
        base64_str (str): base64 编码的字符串。

    Returns:
        Union[Dict, List[Dict]]: 反序列化后的数据。
    """
    ...


def get_readable_file_size(file_path: str) -> str:
    """
    以人类可读的格式计算文件的大小。

    Args:
        file_path (str): 文件的路径。

    Returns:
        str: 可读的文件大小 (例如, "1.23 MB")。
    """
    ...


def bytes_to_readable_size(size_bytes: int) -> str:
    """
    将字节数转换为人类可读的格式。

    Args:
        size_bytes (int): 以字节为单位的大小。

    Returns:
        str: 可读的大小字符串。
    """
    ...


def execute(game_cmd: str) -> bool | None:
    """
    执行一个外部命令，通常用于启动游戏。

    Args:
        game_cmd (str): 要执行的命令字符串。

    Returns:
        bool | None: 如果成功启动进程则返回 True，否则返回 None。
    """
    ...


def get_path(input_string: str) -> str:
    """
    从可能包含参数的输入字符串中提取可执行文件路径。

    Args:
        input_string (str): 包含路径和可选参数的字符串。

    Returns:
        str: 提取的路径部分。
    """
    ...


class Box:
    """
    表示一个具有位置、尺寸、置信度和名称的矩形框。
    """
    x: int
    y: int
    width: int
    height: int
    confidence: float
    name: Any

    def __init__(self, x: float | int, y: float | int, width: float | int = 0, height: float | int = 0,
                 confidence: float = 1.0, name: Optional[Any] = None, to_x: int = -1, to_y: int = -1):
        """
        初始化 Box.

        Args:
            _x (float | int): 左上角的 x 坐标。
            _y (float | int): 左上角的 y 坐标。
            width (float | int): 框的宽度。
            height (float | int): 框的高度。
            confidence (float): 与此框相关的置信度分数。
            name (Optional[Any]): 框的可选名称或标识符。
            to_x (int): 如果提供，则用于计算宽度的右下角 x 坐标。
            to_y (int): 如果提供，则用于计算高度的右下角 y 坐标。
        """
        ...

    def __eq__(self, other: object) -> bool: ...

    def __repr__(self) -> str: ...

    def __str__(self) -> str: ...

    def area(self) -> int:
        """
        计算框的面积。

        Returns:
            int: 框的面积 (宽 * 高)。
        """
        ...

    def in_boundary(self, boxes: List[Box]) -> List[Box]:
        """
        查找完全位于此框边界内的框。

        Args:
            boxes (List[Box]): 要检查的框列表。

        Returns:
            List[Box]: 位于此框内的框列表。
        """
        ...

    def scale(self, width_ratio: float, height_ratio: Optional[float] = None) -> Box:
        """
        按给定的宽度和高度比例缩放框，保持中心点不变。

        Args:
            width_ratio (float): 宽度的缩放比例。
            height_ratio (Optional[float]): 高度的缩放比例。如果为 None，则默认为 width_ratio。

        Returns:
            Box: 一个具有缩放尺寸和位置的新 Box 对象。
        """
        ...

    def closest_distance(self, other: Box) -> float:
        """
        计算此框与另一个框之间的最近边缘距离。

        Args:
            other (Box): 要计算距离的另一个框。

        Returns:
            float: 两个框之间的最短距离。如果它们相交，则距离为 0。
        """
        ...

    def center_distance(self, other: Box) -> float:
        """
        计算此框与另一个框中心点之间的欧几里得距离。

        Args:
           other (Box): 要计算距离的另一个框。

        Returns:
            float: 两个框中心点之间的距离。
        """
        ...

    def relative_with_variance(self, relative_x: float = 0.5, relative_y: float = 0.5) -> Tuple[int, int]:
        """
        计算框内带有随机微小变化的相对坐标。

        Args:
            relative_x (float): 框内相对的 x 位置 (0.0 到 1.0)。
            relative_y (float): 框内相对的 y 位置 (0.0 到 1.0)。

        Returns:
            Tuple[int, int]: 计算出的 (x, y) 坐标。
        """
        ...

    def copy(self, x_offset: int = 0, y_offset: int = 0, width_offset: int = 0, height_offset: int = 0,
             name: Optional[Any] = None) -> Box:
        """
        创建此框的一个副本，可以带有偏移量。

        Args:
            x_offset (int): x 坐标的偏移量。
            y_offset (int): y 坐标的偏移量。
            width_offset (int): 宽度的偏移量。
            height_offset (int): 高度的偏移量。
            name (Optional[Any]): 新框的名称。如果为 None，则使用原始名称。

        Returns:
            Box: 一个新的 Box 实例。
        """
        ...

    def crop_frame(self, frame: Frame) -> Frame:
        """
        使用此框的尺寸从图像帧中裁剪出一个区域。

        Args:
            frame (Frame): 要裁剪的图像 (numpy 数组)。

        Returns:
            Frame: 裁剪后的图像区域。
        """
        ...

    def center(self) -> Tuple[int, int]:
        """
        计算框的中心点坐标。

        Returns:
            Tuple[int, int]: (x, y) 中心坐标。
        """
        ...

    def find_closest_box(self, direction: str, boxes: List[Box], condition: Optional[Callable[[Box], bool]] = None) -> \
            Optional[Box]:
        """
        在给定方向上查找最近的框。

        Args:
            direction (str): 搜索方向 ('up', 'down', 'left', 'right', 'all')。
            boxes (List[Box]): 要搜索的框列表。
            condition (Optional[Callable[[Box], bool]]): 用于筛选候选框的可选函数。

        Returns:
            Optional[Box]: 找到的最近的框，如果未找到则返回 None。
        """
        ...


def find_highest_confidence_box(boxes: List[Box]) -> Optional[Box]:
    """
    从列表中查找置信度最高的框。

    Args:
        boxes (List[Box]): 要搜索的框列表。

    Returns:
        Optional[Box]: 置信度最高的框，如果列表为空则返回 None。
    """
    ...


def sort_boxes(boxes: List[Box]) -> List[Box]:
    """
    根据阅读顺序（从上到下，从左到右）对框进行排序。

    Args:
        boxes (List[Box]): 要排序的框列表。

    Returns:
        List[Box]: 排序后的框列表。
    """
    ...


def find_box_by_name(boxes: List[Box], names: Union[str, Pattern[str], List[Union[str, Pattern[str]]]]) -> Optional[
    Box]:
    """
    通过名称在框列表中查找框。

    Args:
        boxes (List[Box]): 要搜索的框列表。
        names (Union[str, Pattern, List[Union[str, Pattern]]]): 要匹配的单个名称/模式或名称/模式列表。

    Returns:
        Optional[Box]: 找到的第一个匹配的框，如果未找到则返回 None。
    """
    ...


def get_bounding_box(boxes: List[Box]) -> Box:
    """
    计算完全包围列表中所有框的最小边界框。

    Args:
        boxes (List[Box]): 要包围的框列表。

    Returns:
        Box: 包含所有输入框的边界框。
    """
    ...


def find_boxes_within_boundary(boxes: List[Box], boundary_box: Box, sort: bool = True) -> List[Box]:
    """
    查找所有完全位于给定边界框内的框。

    Args:
        boxes (List[Box]): 要筛选的框列表。
        boundary_box (Box): 边界框。
        sort (bool): 是否对结果进行排序。

    Returns:
        List[Box]: 位于边界内的框列表。
    """
    ...


def average_width(boxes: List[Box]) -> int:
    """
    计算框列表的平均宽度。

    Args:
        boxes (List[Box]): 框列表。

    Returns:
        int: 平均宽度。
    """
    ...


def crop_image(image: Frame, box: Optional[Box] = None) -> Frame:
    """
    如果提供了框，则从图像中裁剪一个区域。

    Args:
        image (Frame): 原始图像。
        box (Optional[Box]): 用于裁剪的框。

    Returns:
        Frame: 裁剪后的图像或原始图像。
    """
    ...


def relative_box(frame_width: int, frame_height: int, x: float, y: float, to_x: float = 1, to_y: float = 1,
                 width: float = 0, height: float = 0, name: Optional[Any] = None, confidence: float = 1.0) -> Box:
    """
    根据相对坐标和尺寸创建 Box。

    Args:
        frame_width (int): 参照系的总宽度。
        frame_height (int): 参照系的总高度。
        x (float): 相对 x 坐标 (0 到 1)。
        y (float): 相对 y 坐标 (0 到 1)。
        to_x (float): 相对右下角 x 坐标。
        to_y (float): 相对右下角 y 坐标。
        width (float): 相对宽度。
        height (float): 相对高度。
        name (Optional[Any]): 框的名称。
        confidence (float): 框的置信度。

    Returns:
        Box: 创建的 Box 对象。
    """
    ...


def find_boxes_by_name(boxes: List[Box], names: Union[str, Pattern[str], List[Union[str, Pattern[str]]]]) -> List[Box]:
    """
    通过名称或模式在框列表中查找所有匹配的框。

    Args:
        boxes (List[Box]): 要搜索的框列表。
        names (Union[str, Pattern, List[Union[str, Pattern]]]): 要匹配的单个名称/模式或名称/模式列表。

    Returns:
        List[Box]: 所有匹配框的列表。
    """
    ...


def is_close_to_pure_color(image: Frame, max_colors: int = 5000, percent: float = 0.97) -> bool:
    """
    检查图像是否主要由单一颜色构成。

    Args:
        image (Frame): 要检查的图像。
        max_colors (int): 提前退出的不同颜色数量阈值。
        percent (float): 构成单一颜色的像素百分比阈值。

    Returns:
        bool: 如果图像接近纯色则返回 True。
    """


_ok_logger: logging.Logger
...


def get_mask_in_color_range(image: Frame, color_range: ColorRange) -> Tuple[Frame, int]:
    """
    在图像中为指定的颜色范围创建掩码。

    Args:
        image (Frame): 输入图像。
        color_range (ColorRange): 颜色范围字典。

    Returns:
        Tuple[Frame, int]: 掩码图像和掩码中的非零像素数。
    """
    ...


def get_connected_area_by_color(image: Frame, color_range: ColorRange, connectivity: int = 4, gray_range: int = 0) -> \
        Tuple[int, Frame, Frame, Frame]:
    """
    查找指定颜色范围内的连通区域。

    Args:
        image (Frame): 输入图像。
        color_range (ColorRange): 颜色范围字典。
        connectivity (int): 连通性 (4 或 8)。
        gray_range (int): 用于筛选灰色区域的附加范围。

    Returns:
        Tuple[int, Frame, Frame, Frame]: 标签数量、统计信息、标签和质心。
    """
    ...


def color_range_to_bound(color_range: ColorRange) -> Tuple[Frame, Frame]:
    """
    将颜色范围字典转换为 numpy 格式的下界和上界。

    Args:
        color_range (ColorRange): 颜色范围字典。

    Returns:
        Tuple[Frame, Frame]: 下界和上界 numpy 数组。
    """
    ...


def calculate_colorfulness(image: Frame, box: Optional[Box] = None) -> float:
    """
    计算图像或图像区域的色彩丰富度。

    Args:
        image (Frame): 输入图像。
        box (Optional[Box]): 要计算的特定区域。

    Returns:
        float: 色彩丰富度分数。
    """
    ...


def get_saturation(image: Frame, box: Optional[Box] = None) -> float:
    """
    计算图像或图像区域的平均饱和度。

    Args:
        image (Frame): 输入图像。
        box (Optional[Box]): 要计算的特定区域。

    Returns:
        float: 平均饱和度值 (0 到 1)。
    """
    ...


def find_color_rectangles(image: Frame, color_range: ColorRange, min_width: int, min_height: int, max_width: int = -1,
                          max_height: int = -1, threshold: float = 0.95, box: Optional[Box] = None) -> List[Box]:
    """
    查找图像中与指定颜色范围和尺寸约束匹配的矩形。

    Args:
        image (Frame): 输入图像。
        color_range (ColorRange): 颜色范围字典。
        min_width (int): 最小宽度。
        min_height (int): 最小高度。
        max_width (int): 最大宽度。
        max_height (int): 最大高度。
        threshold (float): 矩形内颜色匹配的百分比阈值。
        box (Optional[Box]): 要搜索的特定区域。

    Returns:
        List[Box]: 找到的矩形框列表。
    """
    ...


def is_pure_black(frame: Frame) -> bool:
    """
    检查图像帧是否完全是黑色的。

    Args:
        frame (Frame): 输入图像。

    Returns:
        bool: 如果图像是纯黑色则返回 True。
    """
    ...


def calculate_color_percentage(image: Frame, color_ranges: ColorRange, box: Optional[Box] = None) -> float:
    """
    计算图像区域中特定颜色范围的像素百分比。

    Args:
        image (Frame): 输入图像。
        color_ranges (ColorRange): 颜色范围字典。
        box (Optional[Box]): 要计算的特定区域。

    Returns:
        float: 颜色所占的百分比 (0 到 1)。
    """
    ...


def rgb_to_gray(rgb: Tuple[int, int, int]) -> float:
    """
    将 RGB 颜色值转换为灰度值。

    Args:
        rgb (Tuple[int, int, int]): RGB 元组。

    Returns:
        float: 灰度值。
    """
    ...


def create_non_black_mask(image: Frame) -> Frame:
    """
    创建一个识别图像中非黑色像素的二进制掩码。

    Args:
        image (Frame): 输入图像 (BGR 或灰度)。

    Returns:
        Frame: 二进制掩码 (非黑色为 255，黑色为 0)。
    """
    ...


class CommunicateHandler(logging.Handler):
    """
    一个日志处理器，通过 `communicate` 信号系统将日志消息发送到 GUI。
    """

    def __init__(self):
        """
        初始化 CommunicateHandler。
        """
        ...

    def emit(self, record: logging.LogRecord) -> None:
        """
        发出一个日志记录，将其格式化并通过信号发送。

        Args:
            record (logging.LogRecord): 日志记录。
        """
        ...


class App:
    """
    主应用程序类，管理 GUI、配置、认证和全局状态。
    """
    config: Dict[str, Any]
    global_config: Any  # GlobalConfig
    app: QApplication
    ok_config: Any  # Config
    auth_config: Any  # Config
    locale: QLocale
    overlay: Any
    start_controller: Any  # StartController
    loading_window: Any
    overlay_window: Any  # OverlayWindow
    main_window: Any  # MainWindow
    exit_event: ExitEvent
    icon: QIcon
    fire_base_analytics: Any  # Analytics
    to_translate: Set[str]
    po_translation: Any
    updater: Any  # GitUpdater
    about: str
    title: str
    version: str
    debug: bool

    def __init__(self, config: Dict[str, Any], task_executor: Any, exit_event: Optional[ExitEvent] = None):
        """
        初始化 App。

        Args:
            config (Dict[str, Any]): 应用程序配置。
            task_executor (Any): TaskExecutor 实例。
            exit_event (Optional[ExitEvent]): 退出事件。
        """
        ...

    def check_auth(self, key: Optional[str] = None, uid: str = "") -> Tuple[bool, Any]:
        """
        检查用户认证。

        Args:
            key (Optional[str]): 要验证的激活码。如果为 None，则使用已保存的密钥。
            uid (str): 用户 ID。

        Returns:
            Tuple[bool, Any]: 一个元组，包含认证是否成功和来自服务器的响应。
        """
        ...

    def trial(self) -> Tuple[bool, Any]:
        """
        请求试用期。

        Returns:
            Tuple[bool, Any]: 一个元组，包含试用请求是否成功和来自服务器的响应。
        """
        ...

    def quit(self) -> None:
        """
        退出应用程序。
        """
        ...

    def tr(self, key: str) -> str:
        """
        翻译给定的键字符串。

        Args:
            key (str): 要翻译的文本键。

        Returns:
            str: 翻译后的文本。
        """
        ...

    def request(self, path: str, params: dict) -> Any:
        """
        向认证服务器发送请求。

        Args:
            path (str): API 端点路径。
            params (dict): 请求参数。

        Returns:
            Any: 来自服务器的响应。
        """
        ...

    def gen_tr_po_files(self) -> str:
        """
        为收集到的待翻译字符串生成 .po 翻译文件。

        Returns:
            str: 生成 .po 文件的文件夹路径。
        """
        ...

    def show_message_window(self, title: str, message: str) -> None:
        """
        显示一个简单的消息窗口。

        Args:
            title (str): 窗口标题。
            message (str): 要显示的消息。
        """
        ...

    def show_already_running_error(self) -> None:
        """
        显示一个错误消息，指示另一个实例已在运行。
        """
        ...

    def show_path_ascii_error(self, path: str) -> None:
        """
        显示一个错误消息，指示安装路径必须为 ASCII。

        Args:
            path (str): 无效的路径。
        """
        ...

    def update_overlay(self, visible: bool, x: int, y: int, window_width: int, window_height: int, width: int,
                       height: int, scaling: float) -> None:
        """
        更新叠加窗口的位置和可见性。
        """
        ...

    def show_main_window(self) -> None:
        """
        检查认证并显示主应用程序窗口。
        """
        ...

    def do_show_main(self) -> None:
        """
        实际创建并显示主窗口的内部方法。
        """
        ...

    def exec(self) -> None:
        """
        进入 Qt 应用程序的主事件循环。
        """
        ...


def get_my_id() -> str:
    """
    生成一个基于 MAC 地址的唯一 ID。

    Returns:
        str: 8 个字符的哈希 ID。
    """
    ...


def get_my_id_with_cwd() -> str:
    """
    生成一个基于 MAC 地址和当前工作目录的唯一 ID。

    Returns:
        str: 8 个字符的哈希 ID。
    """
    ...


class Response:
    """
    表示来自认证服务器的响应的数据类。
    """
    code: int
    message: str
    data: Any


def r(path: str, params: dict) -> Response:
    """
    向认证服务器发送一个 msgpack 编码和加密的请求。

    Args:
        path (str): API 端点。
        params (dict): 请求参数。

    Returns:
        Response: 包含响应数据的 Response 对象。
    """
    ...


class OK:
    """
    应用程序的主要入口点和协调器类。
    """
    app: App
    exit_event: ExitEvent

    def __init__(self, config: dict):
        """
        初始化 OK 应用程序。

        Args:
            config (dict): 主应用程序配置。
        """
        ...

    def start(self) -> None:
        """
        启动应用程序，可以带 GUI，也可以不带。
        """
        ...

    def do_init(self) -> bool:
        """
        执行核心初始化任务，如设置特征集和任务执行器。

        Returns:
            bool: 如果初始化成功则返回 True。
        """
        ...

    def quit(self) -> None:
        """
        干净地关闭应用程序。
        """
        ...


class BaseScene:
    """
    场景识别的基类。
    """

    def reset(self) -> None:
        """
        重置场景识别状态。
        """
        ...


class BaseTask:
    """
    所有任务的基类，提供通用功能如配置、日志、状态管理等。
    """
    name: str
    description: str
    config: Config
    info: Dict[str, Any]
    default_config: Dict[str, Any]
    config_description: Dict[str, str]
    config_type: Dict[str, Any]
    running: bool
    exit_after_task: bool
    start_time: float
    icon: Any

    def __init__(self, executor: Optional[TaskExecutor] = None):
        """
        初始化 BaseTask.

        Args:
            executor (Optional[TaskExecutor]): TaskExecutor 实例。
        """
        ...

    def run_task_by_class(self, cls: type) -> None:
        """
        运行另一个由其类指定的任务。

        Args:
            cls (type): 要运行的任务的类。
        """
        ...

    def post_init(self) -> None:
        """
        在任务完全初始化后调用的钩子。
        """
        ...

    def create_shortcut(self) -> None:
        """
        为此任务创建桌面快捷方式。
        """
        ...

    def tr(self, message: str) -> str:
        """
        翻译给定的消息字符串。

        Args:
            message (str): 要翻译的文本键。

        Returns:
            str: 翻译后的文本。
        """
        ...

    def should_trigger(self) -> bool:
        """
        检查此任务是否应该被触发（基于时间间隔）。

        Returns:
            bool: 如果任务应该触发则返回 True。
        """
        ...

    def is_custom(self) -> bool:
        """
        检查任务是否为用户自定义任务。

        Returns:
            bool: 如果是自定义任务则为 True。
        """
        ...

    def get_status(self) -> str:
        """
        获取任务的当前状态。

        Returns:
            str: 状态字符串 (例如, "Running", "Paused")。
        """
        ...

    def enable(self) -> None:
        """
        启用此任务以供执行。
        """
        ...

    @property
    def handler(self) -> Handler:
        """
        获取与此任务关联的 Handler 实例。
        """
        ...

    def pause(self) -> None:
        """
        暂停此任务的执行。
        """
        ...

    def unpause(self) -> None:
        """
        取消暂停此任务。
        """
        ...

    @property
    def paused(self) -> bool:
        """
        检查任务是否已暂停。
        """
        ...

    def log_info(self, message: str, notify: bool = False) -> None:
        """
        记录一条信息级日志并更新任务信息。
        """
        ...

    def log_debug(self, message: str, notify: bool = False) -> None:
        """
        记录一条调试级日志。
        """
        ...

    def log_error(self, message: str, exception: Optional[Exception] = None, notify: bool = False) -> None:
        """
        记录一条错误级日志并更新任务信息。
        """
        ...

    def go_to_tab(self, tab: str) -> None:
        """
        请求 GUI 导航到指定的选项卡。
        """
        ...

    def notification(self, message: str, title: Optional[str] = None, error: bool = False, tray: bool = False,
                     show_tab: Optional[str] = None) -> None:
        """
        显示一个通知。
        """
        ...

    @property
    def enabled(self) -> bool:
        """
        检查任务是否已启用。
        """
        ...

    def info_clear(self) -> None: ...

    def info_incr(self, key: str, inc: int = 1) -> None: ...

    def info_add_to_list(self, key: str, item: Any) -> None: ...

    def info_set(self, key: str, value: Any) -> None: ...

    def info_get(self, key: str, default: Any = None) -> Any: ...

    def info_add(self, key: str, count: int = 1) -> None: ...

    def load_config(self) -> None:
        """
        加载任务的配置文件。
        """
        ...

    def disable(self) -> None:
        """
        禁用此任务。
        """
        ...

    @property
    def hwnd_title(self) -> str: ...

    def run(self) -> Any:
        """
        任务的主要执行逻辑。应由子类重写。
        """
        ...

    def trigger(self) -> bool:
        """
        触发任务的逻辑，如果适用。应由子类重写。
        """
        ...

    def on_destroy(self) -> None: ...

    def on_create(self) -> None: ...

    def set_executor(self, executor: TaskExecutor) -> None:
        """
        设置任务执行器并加载配置。
        """
        ...

    def find_boxes(self, boxes: List[Box], match: Optional[Any] = None, boundary: Optional[Union[Box, str]] = None) -> \
            List[Box]:
        """
        在给定的边界内筛选和/或按名称匹配框。
        """
        ...


class TaskDisabledException(Exception): ...


class CannotFindException(Exception): ...


class FinishedException(Exception): ...


class WaitFailedException(Exception): ...


class TaskExecutor:
    """
    在专用线程中管理和执行任务的主类。
    """
    device_manager: DeviceManager
    feature_set: FeatureSet
    exit_event: ExitEvent
    debug: bool
    global_config: Any  # GlobalConfig
    ocr_target_height: int
    current_task: Optional[BaseTask]
    trigger_tasks: List[TriggerTask]
    onetime_tasks: List[BaseTask]
    scene: Optional[BaseScene]
    config: Dict[str, Any]

    def __init__(self, device_manager: Any, wait_until_timeout: int = 10, wait_until_settle_time: int = -1,
                 exit_event: Optional[ExitEvent] = None, feature_set: Optional[Any] = None,
                 ocr_lib: Optional[Any] = None, config_folder: Optional[str] = None, debug: bool = False,
                 global_config: Optional[Any] = None, ocr_target_height: int = 0, config: Optional[dict] = None): ...

    @property
    def interaction(self) -> BaseInteraction: ...

    @property
    def method(self) -> BaseCaptureMethod: ...

    def ocr_lib(self, name: str = "default") -> Any:
        """
        获取指定名称的 OCR 库实例。
        """
        ...

    def nullable_frame(self) -> Optional[Frame]:
        """
        获取当前帧，如果不存在则返回 None，不会触发新的捕获。
        """
        ...

    def check_frame_and_resolution(self, supported_ratio: str, min_size: Tuple[int, int], time_out: float = 8.0) -> \
            Tuple[bool, str]:
        """
        检查捕获的帧和分辨率是否符合要求。
        """
        ...

    def can_capture(self) -> bool:
        """
        检查是否可以捕获帧。
        """
        ...

    def next_frame(self) -> Frame:
        """
        捕获并返回下一帧。
        """
        ...

    def is_executor_thread(self) -> bool:
        """
        检查当前线程是否是任务执行器线程。
        """
        ...

    def connected(self) -> bool | None:
        """
        检查设备是否已连接。
        """
        ...

    @property
    def frame(self) -> Frame:
        """
        获取最新的捕获帧，如果需要会触发新的捕获。
        """
        ...

    def check_enabled(self, check_pause: bool = True) -> None:
        """
        检查当前任务是否已启用，如果不是则抛出 TaskDisabledException。
        """
        ...

    def sleep(self, timeout: float) -> None:
        """
        暂停执行指定的秒数，同时检查退出事件。
        """
        ...

    def pause(self, task: Optional[BaseTask] = None) -> bool | None:
        """
        暂停执行器或指定的当前任务。
        """
        ...

    def stop_current_task(self) -> None:
        """
        停止并禁用当前正在运行的任务。
        """
        ...

    def start(self) -> None:
        """
        开始或恢复任务执行循环。
        """
        ...

    def wait_condition(self, condition: Callable, time_out: int = 0, pre_action: Optional[Callable] = None,
                       post_action: Optional[Callable] = None, settle_time: int = -1,
                       raise_if_not_found: bool = False) -> Any:
        """
        等待直到条件为真。
        """
        ...

    def reset_scene(self, check_enabled: bool = True) -> None:
        """
        重置场景状态，强制在下一次操作前重新捕获帧。
        """
        ...

    def stop(self) -> None:
        """
        停止任务执行器。
        """
        ...

    def wait_until_done(self) -> None: ...

    def get_all_tasks(self) -> List[BaseTask]: ...

    def get_task_by_class_name(self, class_name: str) -> Optional[BaseTask]: ...

    def get_task_by_class(self, cls: type) -> Optional[BaseTask]: ...


def list_or_obj_to_str(val: Any) -> str | None: ...


def create_shortcut(exe_path: Optional[str] = None, shortcut_name_post: Optional[str] = None,
                    description: Optional[str] = None, target_path: Optional[str] = None,
                    arguments: Optional[str] = None) -> str | bool: ...


class ExecutorOperation:
    """
    提供高级操作的基类，供任务使用。
    """
    _executor: TaskExecutor
    logger: Logger

    def __init__(self, executor: TaskExecutor) -> None: ...

    def exit_is_set(self) -> bool: ...

    def get_task_by_class(self, cls: type) -> Optional[BaseTask]: ...

    def box_in_horizontal_center(self, box: Box, off_percent: float = 0.02) -> bool: ...

    @property
    def executor(self) -> TaskExecutor: ...

    @property
    def debug(self) -> bool: ...

    def clipboard(self) -> str: ...

    def is_scene(self, the_scene: type) -> bool: ...

    def reset_scene(self) -> None: ...

    def click(self, x: Union[int, Box, List[Box]] = -1, y: int = -1, move_back: bool = False,
              name: Optional[str] = None, interval: int = -1, move: bool = True, down_time: float = 0.01,
              after_sleep: float = 0, key: str = 'left') -> Any: ...

    def back(self, *args, **kwargs) -> Any: ...

    def middle_click(self, *args, **kwargs) -> Any: ...

    def right_click(self, *args, **kwargs) -> Any: ...

    def check_interval(self, interval: float) -> bool: ...

    def is_adb(self) -> bool: ...

    def mouse_down(self, x: int = -1, y: int = -1, name: Optional[str] = None, key: str = "left") -> None: ...

    def mouse_up(self, name: Optional[str] = None, key: str = "left") -> None: ...

    def swipe_relative(self, from_x: float, from_y: float, to_x: float, to_y: float, duration: float = 0.5,
                       settle_time: float = 0) -> None: ...

    def input_text(self, text: str) -> None: ...

    @property
    def hwnd(self) -> Optional[HwndWindow]: ...

    def scroll_relative(self, x: float, y: float, count: int) -> None: ...

    def scroll(self, x: int, y: int, count: int) -> None: ...

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5, after_sleep: float = 0.1,
              settle_time: float = 0) -> None: ...

    def screenshot(self, name: Optional[str] = None, frame: Optional[np.ndarray] = None, show_box: bool = False,
                   frame_box: Optional[Any] = None) -> None: ...

    def click_box_if_name_match(self, boxes: List[Box], names: Any, relative_x: float = 0.5, relative_y: float = 0.5) -> \
            Optional[Box]: ...

    def box_of_screen(self, x: float, y: float, to_x: float = 1.0, to_y: float = 1.0, width: float = 0.0,
                      height: float = 0.0, name: Optional[str] = None, hcenter: bool = False,
                      confidence: float = 1.0) -> Box: ...

    def out_of_ratio(self) -> bool: ...

    def ensure_in_front(self) -> None: ...

    def box_of_screen_scaled(self, original_screen_width: int, original_screen_height: int, x_original: int,
                             y_original: int, to_x: int = 0, to_y: int = 0, width_original: int = 0,
                             height_original: int = 0, name: Optional[str] = None, hcenter: bool = False,
                             confidence: float = 1.0) -> Box: ...

    def height_of_screen(self, percent: float) -> int: ...

    @property
    def screen_width(self) -> int: ...

    @property
    def screen_height(self) -> int: ...

    def width_of_screen(self, percent: float) -> int: ...

    def click_relative(self, x: float, y: float, move_back: bool = False, hcenter: bool = False, move: bool = True,
                       after_sleep: float = 0, name: Optional[str] = None, interval: int = -1, down_time: float = 0.02,
                       key: str = "left") -> None: ...

    def middle_click_relative(self, x: float, y: float, move_back: bool = False, down_time: float = 0.01) -> None: ...

    @property
    def height(self) -> int: ...

    @property
    def width(self) -> int: ...

    def move_relative(self, x: float, y: float) -> None: ...

    def move(self, x: int, y: int) -> None: ...

    def click_box(self, box: Union[Box, List[Box], str, None] = None, relative_x: float = 0.5, relative_y: float = 0.5,
                  raise_if_not_found: bool = False, move_back: bool = False, down_time: float = 0.01,
                  after_sleep: float = 1) -> None: ...

    def wait_scene(self, scene_type: Optional[type] = None, time_out: int = 0, pre_action: Optional[Callable] = None,
                   post_action: Optional[Callable] = None) -> Any: ...

    def sleep(self, timeout: float) -> bool: ...

    def send_key(self, key: Any, down_time: float = 0.02, interval: int = -1, after_sleep: float = 0) -> bool: ...

    def get_global_config(self, option: Any) -> Any: ...

    def get_global_config_desc(self, option: Any) -> Any: ...

    def send_key_down(self, key: Any) -> None: ...

    def send_key_up(self, key: Any) -> None: ...

    def wait_until(self, condition: Callable, time_out: int = 0, pre_action: Optional[Callable] = None,
                   post_action: Optional[Callable] = None, settle_time: int = -1,
                   raise_if_not_found: bool = False) -> Any: ...

    def wait_click_box(self, condition: Callable, time_out: int = 0, pre_action: Optional[Callable] = None,
                       post_action: Optional[Callable] = None, raise_if_not_found: bool = False) -> Any: ...

    def next_frame(self) -> np.ndarray: ...

    def adb_ui_dump(self) -> Optional[str]: ...

    @property
    def frame(self) -> np.ndarray: ...

    @staticmethod
    def draw_boxes(feature_name: Optional[str] = None, boxes: Optional[List[Box]] = None, color: str = "red",
                   debug: bool = True) -> None: ...

    def clear_box(self) -> None: ...

    def calculate_color_percentage(self, color: Any, box: Union[Box, str]) -> float: ...

    def adb_shell(self, *args, **kwargs) -> Any: ...


class TriggerTask(BaseTask): ...


class FindFeature(ExecutorOperation):
    """
    提供基于模板匹配查找特征功能的操作类。
    """

    def find_feature(self, feature_name: Optional[str] = None, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x: int = -1,
                     y: int = -1, to_x: int = -1, to_y: int = -1, width: int = -1, height: int = -1,
                     box: Optional[Box] = None, canny_lower: int = 0, canny_higher: int = 0,
                     frame_processor: Optional[Callable] = None, template: Optional[np.ndarray] = None,
                     match_method: int = ..., screenshot: bool = False, mask_function: Optional[Callable] = None,
                     frame: Optional[np.ndarray] = None) -> List[Box]: ...

    def get_feature_by_name(self, name: str) -> Optional[Feature]: ...

    def get_box_by_name(self, name: Union[Box, str]) -> Box: ...

    def find_feature_and_set(self, features: Union[str, List[str]], horizontal_variance: float = 0,
                             vertical_variance: float = 0, threshold: float = 0) -> bool: ...

    def wait_feature(self, feature: str, horizontal_variance: float = 0, vertical_variance: float = 0,
                     threshold: float = 0, time_out: int = 0, pre_action: Optional[Callable] = None,
                     post_action: Optional[Callable] = None, use_gray_scale: bool = False, box: Optional[Box] = None,
                     raise_if_not_found: bool = False, canny_lower: int = 0, canny_higher: int = 0,
                     settle_time: int = -1, frame_processor: Optional[Callable] = None) -> Any: ...

    def wait_click_feature(self, feature: str, horizontal_variance: float = 0, vertical_variance: float = 0,
                           threshold: float = 0, relative_x: float = 0.5, relative_y: float = 0.5, time_out: int = 0,
                           pre_action: Optional[Callable] = None, post_action: Optional[Callable] = None,
                           box: Optional[Box] = None, raise_if_not_found: bool = True, use_gray_scale: bool = False,
                           canny_lower: int = 0, canny_higher: int = 0, click_after_delay: float = 0,
                           settle_time: int = -1, after_sleep: float = 0) -> bool: ...

    def find_one(self, feature_name: Optional[str] = None, horizontal_variance: float = 0, vertical_variance: float = 0,
                 threshold: float = 0, use_gray_scale: bool = False, box: Optional[Box] = None, canny_lower: int = 0,
                 canny_higher: int = 0, frame_processor: Optional[Callable] = None,
                 template: Optional[np.ndarray] = None, mask_function: Optional[Callable] = None,
                 frame: Optional[np.ndarray] = None, match_method: int = ..., screenshot: bool = False) -> Optional[
        Box]: ...

    def on_feature(self, boxes: List[Box]) -> None: ...

    def feature_exists(self, feature_name: str) -> bool: ...

    def find_best_match_in_box(self, box: Box, to_find: List[str], threshold: float, use_gray_scale: bool = False,
                               canny_lower: int = 0, canny_higher: int = 0, frame_processor: Optional[Callable] = None,
                               mask_function: Optional[Callable] = None) -> Optional[Box]: ...

    def find_first_match_in_box(self, box: Box, to_find: List[str], threshold: float, use_gray_scale: bool = False,
                                canny_lower: int = 0, canny_higher: int = 0, frame_processor: Optional[Callable] = None,
                                mask_function: Optional[Callable] = None) -> Optional[Box]: ...


class OCR(FindFeature):
    """
    提供光学字符识别（OCR）功能的操作类。
    """
    ocr_default_threshold: float

    def ocr(self, x: float = 0, y: float = 0, to_x: float = 1, to_y: float = 1, match: Optional[Any] = None,
            width: int = 0, height: int = 0, box: Optional[Box] = None, name: Optional[str] = None,
            threshold: float = 0, frame: Optional[np.ndarray] = None, target_height: int = 0,
            use_grayscale: bool = False, log: bool = False, frame_processor: Optional[Callable] = None,
            lib: str = 'default') -> List[Box]: ...

    def add_text_fix(self, fix: Dict[str, str]) -> None: ...

    def wait_click_ocr(self, x: float = 0, y: float = 0, to_x: float = 1, to_y: float = 1, width: int = 0,
                       height: int = 0, box: Optional[Box] = None, name: Optional[str] = None,
                       match: Optional[Any] = None, threshold: float = 0, frame: Optional[np.ndarray] = None,
                       target_height: int = 0, time_out: int = 0, raise_if_not_found: bool = False,
                       recheck_time: int = 0, after_sleep: float = 0, post_action: Optional[Callable] = None,
                       log: bool = False, settle_time: int = -1, lib: str = "default") -> Any: ...

    def wait_ocr(self, x: float = 0, y: float = 0, to_x: float = 1, to_y: float = 1, width: int = 0, height: int = 0,
                 name: Optional[str] = None, box: Optional[Box] = None, match: Optional[Any] = None,
                 threshold: float = 0, frame: Optional[np.ndarray] = None, target_height: int = 0, time_out: int = 0,
                 post_action: Optional[Callable] = None, raise_if_not_found: bool = False, log: bool = False,
                 settle_time: int = -1, lib: str = "default") -> Any: ...


class CaptureException(Exception): ...


class BaseCaptureMethod:
    """
    所有屏幕捕获方法的基类。
    """

    def close(self) -> None: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    def get_name(self) -> str: ...

    def get_frame(self) -> Optional[np.ndarray]: ...


class HwndWindow: ...


class BaseWindowsCaptureMethod(BaseCaptureMethod): ...


class WindowsGraphicsCaptureMethod(BaseWindowsCaptureMethod): ...


class BitBltCaptureMethod(BaseWindowsCaptureMethod): ...


class DesktopDuplicationCaptureMethod(BaseWindowsCaptureMethod): ...


class ADBCaptureMethod(BaseCaptureMethod): ...


class ImageCaptureMethod(BaseCaptureMethod): ...


class NemuIpcCaptureMethod(BaseCaptureMethod): ...


class DeviceManager:
    """
    管理设备连接（Windows 窗口或 ADB 设备）、捕获和交互方法。
    """

    def __init__(self, app_config: dict, exit_event: Optional[ExitEvent] = None,
                 global_config: Optional[Any] = None) -> None: ...

    def stop_hwnd(self) -> None: ...

    def select_hwnd(self, exe: str, hwnd: int) -> None: ...

    def refresh(self) -> None: ...

    @property
    def adb(self) -> Any: ...

    def adb_connect(self, addr: str, try_connect: bool = True) -> Any | None: ...

    def get_devices(self) -> List[dict]: ...

    def get_resolution(self, device: Optional[Any] = None) -> Tuple[int, int]: ...

    def set_preferred_device(self, imei: Optional[str] = None, index: int = -1) -> None: ...

    def adb_ui_dump(self) -> str | None: ...

    def get_preferred_device(self) -> dict | None: ...

    def get_preferred_capture(self) -> str: ...

    def set_hwnd_name(self, hwnd_name: str) -> None: ...

    def set_capture(self, capture: str) -> None: ...

    def get_hwnd_name(self) -> str | None: ...

    def start(self) -> None: ...

    @property
    def device(self) -> Any | None: ...

    def adb_kill_server(self) -> None: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    def shell(self, *args, **kwargs) -> Any: ...


class FeatureSet: ...


# interaction.py
class BaseInteraction:
    def __init__(self, capture: BaseCaptureMethod) -> None: ...

    def should_capture(self) -> bool: ...

    def send_key(self, key: Any, down_time: float = 0.02) -> None: ...

    def send_key_down(self, key: Any) -> None: ...

    def send_key_up(self, key: Any) -> None: ...

    def move(self, x: int, y: int) -> None: ...

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float,
              settle_time: float = 0) -> None: ...

    def click(self, x: int = -1, y: int = -1, move_back: bool = False, name: Optional[str] = None, move: bool = True,
              down_time: float = 0.05, key: str = "left") -> None: ...

    def on_run(self) -> None: ...

    def input_text(self, text: str) -> None: ...

    def back(self, after_sleep: float = 0) -> None: ...

    def scroll(self, x: int, y: int, scroll_amount: int) -> None: ...

    def on_destroy(self) -> None: ...


class PyDirectInteraction(BaseInteraction): ...


class PynputInteraction(BaseInteraction): ...


class PostMessageInteraction(BaseInteraction): ...


class DoNothingInteraction(BaseInteraction): ...


class ADBInteraction(BaseInteraction): ...


class GenshinInteraction(BaseInteraction): ...


class ForegroundPostMessageInteraction(GenshinInteraction): ...


class Config(dict):
    """
    一个字典子类，用于处理 JSON 格式的配置文件，支持默认值和自动保存。
    """
    config_folder: str

    def __init__(self, name: str, default: dict, folder: Optional[str] = None,
                 validator: Optional[Callable] = None): ...

    def save_file(self) -> None: ...

    def get_default(self, key: str) -> Any: ...

    def reset_to_default(self) -> None: ...

    def __setitem__(self, key: str, value: Any) -> None: ...

    def has_user_config(self) -> bool: ...


class ConfigOption:
    """
    定义一个全局配置选项及其元数据。
    """

    def __init__(self, name: str, default: Optional[dict] = None, description: str = "",
                 config_description: Optional[dict] = None, config_type: Optional[dict] = None,
                 validator: Optional[Callable] = None, icon: Any = ...): ...


basic_options: ConfigOption


class GlobalConfig:
    def __init__(self, config_options: List[ConfigOption]) -> None: ...

    def get_config(self, option: Union[str, ConfigOption]) -> Config: ...


class Feature:
    """
    表示模板匹配中使用的特征。
    """
    mat: np.ndarray
    scaling: float
    x: int
    y: int
    mask: Optional[np.ndarray]

    def __init__(self, mat: np.ndarray, x: int = 0, y: int = 0, scaling: float = 1) -> None: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...


class MainWindow(MSFluentWindow):
    def __init__(self, app: App, config: dict, ok_config: Config, icon: QIcon, title: str, version: str,
                 debug: bool = False, about: Optional[str] = None, exit_event: Optional[ExitEvent] = None,
                 global_config: Optional[GlobalConfig] = None) -> None: ...


class DiagnosisTask(BaseTask):
    """
    用于性能测试和诊断的任务。
    """

    def __init__(self, *args, **kwargs) -> None: ...

    def run(self) -> None: ...
